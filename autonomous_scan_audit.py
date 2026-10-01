"""Small, complete decision records; never market payloads or rule snapshots."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone


AUDIT_VERSION = "autonomous-scan-audit-v1"
MAX_REPORT_SCANS = 12
MAX_REPORT_DATABASE_BYTES = 512 * 1024
FIELDS = (
    "phase", "symbol", "side", "analyzed_at", "entry", "take_profit",
    "stop_loss", "tp_probability", "sl_probability", "unresolved_probability",
    "edge", "selected_analogs_min", "analysis_status", "rejection_code",
    "eligible", "artifact_id", "context_sigma", "proposal_version",
    "reason_truncated", "reason_sha256",
)


def _finite(value):
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def candidate_record(candidate, policy, *, phase="panel") -> dict:
    """Copy only scalars, before confirmation/execution can mutate a candidate."""
    reason = str(candidate.rejection_code or "")
    reason_bytes = reason.encode("utf-8")
    truncated = len(reason_bytes) > 256
    return {
        "phase": phase,
        "symbol": candidate.symbol,
        "side": candidate.side,
        "analyzed_at": candidate.analyzed_at.isoformat(),
        "entry": _finite(candidate.entry),
        "take_profit": _finite(candidate.take_profit),
        "stop_loss": _finite(candidate.stop_loss),
        "tp_probability": _finite(candidate.tp_probability),
        "sl_probability": _finite(candidate.sl_probability),
        "unresolved_probability": _finite(candidate.unresolved_probability),
        "edge": _finite(candidate.edge),
        "selected_analogs_min": candidate.selected_analogs_min,
        "analysis_status": candidate.analysis_status,
        "rejection_code": (reason_bytes[:256].decode("utf-8", errors="ignore")
                           if truncated else reason) or None,
        "eligible": candidate.eligible_for(policy),
        "artifact_id": candidate.artifact_id,
        "context_sigma": _finite(candidate.sigma),
        "proposal_version": (candidate.trade_plan or candidate.horizon_geometry).get("version"),
        "reason_truncated": truncated,
        "reason_sha256": hashlib.sha256(reason_bytes).hexdigest() if truncated else None,
    }


def ensure_candidate_records(records, candidates, policy, *, phase="panel", start=0):
    """Include provider/plan failures too; preserve all alternative analyses."""
    recorded = {(r["symbol"], r["side"]) for r in records[start:] if r["phase"] == phase}
    for candidate in candidates:
        key = (candidate.symbol, candidate.side)
        if key not in recorded:
            records.append(candidate_record(candidate, policy, phase=phase))
            recorded.add(key)


def encode_audit(records, policy, *, selected=None, gates=None) -> str:
    selected_indices = [i for i, row in enumerate(records)
                        if selected is not None and row["symbol"] == selected.symbol
                        and row["side"] == selected.side]
    payload = {
        "version": AUDIT_VERSION,
        "coverage": "complete",
        "time_horizon": policy.time_horizon,
        "fields": FIELDS,
        "rows": [[record.get(key) for key in FIELDS] for record in records],
        "record_count": len(records),
        "evaluated_analyses": sum(row["analysis_status"] == "evaluated" for row in records),
        "selected_index": selected_indices[-1] if selected_indices else None,
        "gates": gates or {},
    }
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def decode_audit(payload) -> dict:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict) or payload.get("version") != AUDIT_VERSION:
        raise ValueError("autonomous_audit_unknown_contract")
    fields = payload.get("fields")
    rows = payload.get("rows")
    if not isinstance(fields, list) or not isinstance(rows, list):
        raise ValueError("autonomous_audit_invalid_contract")
    if any(not isinstance(row, list) or len(row) != len(fields) for row in rows):
        raise ValueError("autonomous_audit_invalid_row")
    return {key: value for key, value in payload.items() if key not in {"fields", "rows"}} | {
        "analyses": [dict(zip(fields, row)) for row in rows],
    }


def _utc(value):
    if value.tzinfo is None:
        raise ValueError("autonomous_audit_dates_require_timezone")
    return value.astimezone(timezone.utc)


def scan_audit_report(db, *, participant_code, start_at, end_at, before_id=None, limit=6):
    """Manual, cursor-paginated reads. Existing learning snapshots stay unread."""
    start, end = _utc(start_at), _utc(end_at)
    if end <= start or end - start > timedelta(days=31):
        raise ValueError("autonomous_audit_date_range_invalid")
    if not 1 <= limit <= MAX_REPORT_SCANS or (before_id is not None and before_id <= 0):
        raise ValueError("autonomous_audit_page_invalid")
    # The extra row is metadata only: do not transfer a thirteenth JSON payload.
    cursor_clause = "AND s.id < ?" if before_id is not None else ""
    params = [participant_code, start.isoformat(), end.isoformat()]
    if before_id is not None:
        params.append(before_id)
    params.append(limit + 1)
    metadata = [dict(row) for row in db.execute(
        f"""
        SELECT s.id, s.scan_slot_at, s.analyzed_at, s.status, s.reason_code,
               s.candidates_evaluated, s.candidates_blocked, s.candidates_eligible,
               s.selected_symbol, s.selected_side, s.operation_id,
               s.engine_version, s.policy_version
        FROM autonomous_scan_runs s
        JOIN autonomous_contest_participants p ON p.id = s.participant_id
        WHERE p.code = ? AND s.scan_slot_at >= ? AND s.scan_slot_at < ?
          {cursor_clause}
        ORDER BY s.id DESC LIMIT ?
        """, tuple(params),
    ).fetchall()]
    more = len(metadata) > limit
    scans = metadata[:limit]
    ids = [int(row["id"]) for row in scans]
    payloads = {}
    legacy = {}
    bytes_read = 0
    if ids:
        placeholders = ",".join("?" for _ in ids)
        for row in db.execute(
            f"SELECT id, candidate_audit_json FROM autonomous_scan_runs WHERE id IN ({placeholders})",
            tuple(ids),
        ).fetchall():
            value = row["candidate_audit_json"]
            if value is not None:
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                bytes_read += len(text.encode("utf-8"))
                payloads[int(row["id"])] = decode_audit(value)
        legacy_ids = [scan_id for scan_id in ids if scan_id not in payloads]
        if legacy_ids:
            placeholders = ",".join("?" for _ in legacy_ids)
            for row in db.execute(
                f"""
                SELECT scan_run_id, symbol, side, analyzed_at, entry, take_profit,
                       stop_loss, tp_probability, sl_probability, unresolved_probability,
                       edge, selected_analogs_min, analysis_status,
                       SUBSTR(rejection_code, 1, 256) AS rejection_code, selected
                FROM autonomous_candidate_observations
                WHERE scan_run_id IN ({placeholders}) ORDER BY scan_run_id, id
                """, tuple(legacy_ids),
            ).fetchall():
                item = dict(row)
                scan_id = int(item.pop("scan_run_id"))
                bytes_read += len(json.dumps(item, default=str, ensure_ascii=False).encode("utf-8"))
                legacy.setdefault(scan_id, []).append(item)
    if bytes_read > MAX_REPORT_DATABASE_BYTES:
        raise ValueError("autonomous_audit_read_budget_exceeded_reduce_page_size")
    for scan in scans:
        scan_id = int(scan["id"])
        audit = payloads.get(scan_id)
        if audit is None:
            analyses = legacy.get(scan_id, [])
            audit = {
                "version": None,
                "coverage": "legacy_sample",
                "analyses": analyses,
                "missing_proposals": max(0, int(scan["candidates_evaluated"])
                                         + int(scan["candidates_blocked"]) - len(analyses)),
            }
        scan["audit"] = audit
    return {
        "participant": participant_code,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "scans": scans,
        "next_cursor": ids[-1] if more else None,
        "database_payload_bytes": bytes_read,
        "snapshots_read": False,
    }
