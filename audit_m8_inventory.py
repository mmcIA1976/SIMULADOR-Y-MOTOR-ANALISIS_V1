from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from db import close_pool, connect


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
PROTOCOL_PATH = AUDIT_DIR / "protocolo_evaluacion_m8_1_v0_1.json"
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "inventario_elegibilidad_m8_2_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M8_2_inventario_elegibilidad_v0_1.md"
)
VERSION = "M8.2-eligibility-inventory-v0.1"
SUPPORTED_PAIRS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "INJUSDT",
)
SUPPORTED_HORIZONS = (
    "intraday_short",
    "intraday_wide",
    "short_swing",
)
FORBIDDEN_OUTCOME_TOKENS = (
    "close_reason",
    "close_price",
    "closed_at",
    "final_pnl",
    "learning_outcome",
    "observation_result",
    "tp_probability",
    "sl_probability",
    "range_probability",
)

SQL_TOTALS = """
SELECT
    (SELECT COUNT(*) FROM operations) AS operations_total,
    (SELECT COUNT(*) FROM recommendations) AS recommendations_total,
    (
        SELECT COUNT(*)
        FROM recommendations
        WHERE operation_id IS NOT NULL
    ) AS linked_recommendations_total
"""

SQL_METADATA_ROWS = """
SELECT
    r.created_at AS analysis_at,
    r.symbol,
    r.side,
    r.time_horizon,
    r.engine_version,
    r.snapshot_json,
    r.analysis_json,
    o.entry,
    o.stop_loss,
    o.take_profit,
    o.time_horizon AS operation_time_horizon,
    COALESCE(o.entry_type, 'market') AS entry_type,
    o.started_at,
    o.created_at AS operation_created_at
FROM recommendations r
JOIN operations o ON o.id = r.operation_id
WHERE r.operation_id IS NOT NULL
ORDER BY r.created_at, r.id
"""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_queries_are_outcome_blind() -> None:
    normalized = f"{SQL_TOTALS}\n{SQL_METADATA_ROWS}".lower()
    leaked = [token for token in FORBIDDEN_OUTCOME_TOKENS if token in normalized]
    if leaked:
        raise ValueError(f"outcome_columns_forbidden:{','.join(leaked)}")


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def positive_finite(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def valid_plan_geometry(row: dict) -> bool:
    if not all(
        positive_finite(row.get(field))
        for field in ("entry", "take_profit", "stop_loss")
    ):
        return False
    entry = float(row["entry"])
    tp = float(row["take_profit"])
    sl = float(row["stop_loss"])
    if row.get("side") == "long":
        return sl < entry < tp
    if row.get("side") == "short":
        return tp < entry < sl
    return False


def json_present(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value)
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return False
    return isinstance(parsed, dict) and bool(parsed)


def structural_reasons(row: dict) -> list[str]:
    reasons = []
    analysis_at = parse_datetime(row.get("analysis_at"))
    if analysis_at is None:
        reasons.append("analysis_at_missing_or_invalid")
    if str(row.get("symbol") or "").upper() not in SUPPORTED_PAIRS:
        reasons.append("unsupported_symbol")
    if row.get("side") not in {"long", "short"}:
        reasons.append("invalid_side")
    if row.get("time_horizon") not in SUPPORTED_HORIZONS:
        reasons.append("unsupported_horizon")
    if row.get("operation_time_horizon") != row.get("time_horizon"):
        reasons.append("operation_analysis_horizon_mismatch")
    if str(row.get("entry_type") or "").lower() != "market":
        reasons.append("non_market_entry")
    if not valid_plan_geometry(row):
        reasons.append("invalid_or_missing_plan_geometry")
    if not row.get("engine_version"):
        reasons.append("engine_version_missing")
    if not json_present(row.get("snapshot_json")):
        reasons.append("snapshot_json_missing_or_invalid")
    if not json_present(row.get("analysis_json")):
        reasons.append("analysis_json_missing_or_invalid")
    return reasons


def choose_timestamp_cuts(eligible_dates: list[date]) -> dict:
    distinct = sorted(set(eligible_dates))
    if len(distinct) < 3:
        return {
            "status": "insufficient_distinct_analysis_dates",
            "development_end": None,
            "calibration_end": None,
            "final_test_start": None,
            "selection_uses_outcomes": False,
        }
    development_index = max(0, min(len(distinct) - 3, int(len(distinct) * 0.60) - 1))
    calibration_index = max(
        development_index + 1,
        min(len(distinct) - 2, int(len(distinct) * 0.80) - 1),
    )
    development_end = distinct[development_index]
    calibration_end = distinct[calibration_index]
    final_start = distinct[calibration_index + 1]
    return {
        "status": "frozen_from_analysis_dates_only",
        "development_end": development_end.isoformat(),
        "calibration_end": calibration_end.isoformat(),
        "final_test_start": final_start.isoformat(),
        "distinct_analysis_dates": len(distinct),
        "selection_uses_outcomes": False,
        "selection_uses_pnl": False,
        "selection_uses_probabilities": False,
    }


def partition_for(day: date, cuts: dict) -> str | None:
    if cuts["status"] != "frozen_from_analysis_dates_only":
        return None
    development_end = date.fromisoformat(cuts["development_end"])
    calibration_end = date.fromisoformat(cuts["calibration_end"])
    if day <= development_end:
        return "development"
    if day <= calibration_end:
        return "calibration"
    return "final_test"


def build_inventory(
    *,
    totals: dict,
    rows: list[dict],
    captured_at: datetime,
) -> dict:
    assert_queries_are_outcome_blind()
    reason_counts: Counter[str] = Counter()
    eligible = []
    metadata_counts: Counter[tuple[str, str, str]] = Counter()
    all_dates = []
    for row in rows:
        analysis_at = parse_datetime(row.get("analysis_at"))
        if analysis_at is not None:
            all_dates.append(analysis_at.date())
        reasons = structural_reasons(row)
        reason_counts.update(reasons)
        if reasons:
            continue
        eligible.append(row)
        metadata_counts[
            (
                str(row["symbol"]).upper(),
                str(row["side"]),
                str(row["time_horizon"]),
            )
        ] += 1

    eligible_dates = [
        parse_datetime(row["analysis_at"]).date()
        for row in eligible
        if parse_datetime(row["analysis_at"]) is not None
    ]
    cuts = choose_timestamp_cuts(eligible_dates)
    partition_counts: Counter[str] = Counter()
    partition_cells: Counter[tuple[str, str, str, str]] = Counter()
    for row in eligible:
        timestamp = parse_datetime(row["analysis_at"])
        if timestamp is None:
            continue
        partition = partition_for(timestamp.date(), cuts)
        if partition is None:
            continue
        partition_counts[partition] += 1
        partition_cells[
            (
                partition,
                str(row["symbol"]).upper(),
                str(row["side"]),
                str(row["time_horizon"]),
            )
        ] += 1

    coverage = [
        {
            "symbol": symbol,
            "side": side,
            "time_horizon": horizon,
            "records": metadata_counts[(symbol, side, horizon)],
        }
        for symbol in SUPPORTED_PAIRS
        for side in ("long", "short")
        for horizon in SUPPORTED_HORIZONS
    ]
    partition_coverage = [
        {
            "partition": partition,
            "symbol": symbol,
            "side": side,
            "time_horizon": horizon,
            "records": partition_cells[(partition, symbol, side, horizon)],
        }
        for partition in ("development", "calibration", "final_test")
        for symbol in SUPPORTED_PAIRS
        for side in ("long", "short")
        for horizon in SUPPORTED_HORIZONS
    ]
    payload = {
        "version": VERSION,
        "phase": "M8",
        "subphase": "M8.2",
        "status": "inventory_captured_outcome_blind",
        "captured_at": captured_at.astimezone(timezone.utc).isoformat(),
        "source": "supabase_postgres_read_only",
        "outcome_embargo": {
            "outcome_columns_selected": [],
            "legacy_probability_columns_selected": [],
            "performance_evaluated": False,
            "pnl_read": False,
        },
        "query_contract": {
            "totals_sha256": sha256_text(SQL_TOTALS.strip()),
            "metadata_rows_sha256": sha256_text(SQL_METADATA_ROWS.strip()),
            "forbidden_tokens": list(FORBIDDEN_OUTCOME_TOKENS),
            "outcome_blind": True,
        },
        "totals": {
            "operations_total": int(totals.get("operations_total") or 0),
            "recommendations_total": int(
                totals.get("recommendations_total") or 0
            ),
            "linked_recommendations_total": int(
                totals.get("linked_recommendations_total") or 0
            ),
            "metadata_rows_read": len(rows),
            "structurally_eligible_before_outcomes": len(eligible),
            "structurally_ineligible_before_outcomes": len(rows) - len(eligible),
        },
        "date_coverage": {
            "first_analysis_date": min(all_dates).isoformat() if all_dates else None,
            "last_analysis_date": max(all_dates).isoformat() if all_dates else None,
            "distinct_analysis_dates": len(set(all_dates)),
        },
        "structural_exclusion_reasons": [
            {"reason": reason, "records": count}
            for reason, count in sorted(reason_counts.items())
        ],
        "coverage": coverage,
        "chronological_cuts": cuts,
        "partition_counts_before_outcomes": dict(partition_counts),
        "partition_coverage_before_outcomes": partition_coverage,
        "limitations": [
            "Counts precede outcome eligibility and may decrease in M8.3.",
            "No claim is made about closed-operation success or class balance.",
            "Historical pre-trade raw data may still be insufficient for exact reconstruction.",
        ],
        "boundaries": {
            "production_effect": "none",
            "m8_closed": False,
            "m9_started": False,
        },
        "next_step": {
            "id": "M8.3",
            "name": "Reconstruccion de outcomes y confirmacion de cortes",
            "outcome_embargo_release_authorized": True,
            "started": False,
        },
    }
    payload["canonical_payload_sha256"] = sha256_text(
        canonical_json(
            {
                key: value
                for key, value in payload.items()
                if key != "canonical_payload_sha256"
            }
        )
    )
    return payload


def fetch_live_inventory() -> dict:
    with connect() as db:
        totals = dict(db.execute(SQL_TOTALS).fetchone())
        rows = [dict(row) for row in db.execute(SQL_METADATA_ROWS).fetchall()]
        captured = db.execute("SELECT CURRENT_TIMESTAMP AS captured_at").fetchone()
    close_pool()
    return build_inventory(
        totals=totals,
        rows=rows,
        captured_at=parse_datetime(captured["captured_at"])
        or datetime.now(timezone.utc),
    )


def render_report(payload: dict) -> str:
    totals = payload["totals"]
    cuts = payload["chronological_cuts"]
    return "\n".join(
        [
            "# M8.2 - Inventario de elegibilidad",
            "",
            f"Capturado: {payload['captured_at']}",
            "Estado: INVENTARIO METADATA-ONLY; OUTCOMES EMBARGADOS",
            "",
            "## Volumen",
            "",
            f"- Operaciones registradas: {totals['operations_total']}.",
            f"- Analisis registrados: {totals['recommendations_total']}.",
            (
                "- Analisis vinculados a operacion: "
                f"{totals['linked_recommendations_total']}."
            ),
            (
                "- Estructuralmente elegibles antes de outcomes: "
                f"{totals['structurally_eligible_before_outcomes']}."
            ),
            "",
            "## Cortes cronologicos",
            "",
            f"- Estado: {cuts['status']}.",
            f"- Fin desarrollo: {cuts.get('development_end')}.",
            f"- Fin calibracion: {cuts.get('calibration_end')}.",
            f"- Inicio prueba final: {cuts.get('final_test_start')}.",
            "",
            "Los cortes utilizan exclusivamente analysis_at y cobertura.",
            "",
            "## Embargo",
            "",
            "- Outcomes leidos: NO.",
            "- PnL leido: NO.",
            "- Porcentajes antiguos leidos: NO.",
            "- Rendimiento calculado: NO.",
            "",
            "Siguiente subfase: M8.3.",
            "",
            "SHA-256 del payload canonico: "
            f"`{payload['canonical_payload_sha256']}`.",
            "",
        ]
    )


def verify_stored_snapshot() -> None:
    assert_queries_are_outcome_blind()
    payload = json.loads(DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8"))
    stored_hash = payload.pop("canonical_payload_sha256")
    if sha256_text(canonical_json(payload)) != stored_hash:
        raise SystemExit("Stored M8.2 inventory hash mismatch")
    report = render_report(payload | {"canonical_payload_sha256": stored_hash})
    if DEFAULT_REPORT_PATH.read_text(encoding="utf-8") != report:
        raise SystemExit("Stored M8.2 report is stale")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        verify_stored_snapshot()
        return
    payload = fetch_live_inventory()
    DEFAULT_OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    DEFAULT_REPORT_PATH.write_text(
        render_report(payload),
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
