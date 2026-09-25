"""Short-bot entry confirmation, independent of the probability engine.

Only eligible proposals have a lineage. Each checkpoint stores its own geometry
and numerical context once; no candle history, snapshot or growing JSON arrays.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone


CONFIRMATION_VERSION = "short-entry-confirmation-v2"
LEGACY_CONFIRMATION_VERSION = "short-entry-confirmation-v1"
CONFIRMATION_MINUTES = 30
CONFIRMATION_CONTROLS = 3
# One missed 15-minute check may be retried; older valid evidence is stale.
MAX_VALID_CONTROL_GAP_MINUTES = 30
CONTROL_JSON_BYTE_BUDGET = 2048


def enabled(policy) -> bool:
    return policy.code == "auto_intraday_short"


def utc(value) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def as_object(value) -> dict:
    if isinstance(value, str):
        value = json.loads(value)
    return value if isinstance(value, dict) else {}


def rank_key(candidate) -> tuple:
    return (-float(candidate.edge), -float(candidate.tp_probability),
            float(candidate.unresolved_probability), candidate.symbol, candidate.side)


def data_unavailable(candidate) -> bool:
    """A failed/blocked analysis is not evidence that the trading signal weakened."""
    return candidate.analysis_status in {"failed", "blocked"}


def pause(candidate, previous: dict, *, slot, reason: str) -> None:
    """Keep an existing episode, without counting a check or allowing entry."""
    old = as_object(previous.get("confirmation"))
    candidate.confirmation = {
        **old,
        "version": CONFIRMATION_VERSION,
        "slot": utc(slot).isoformat(),
        "state": "paused",
        "last_valid_analyzed_at": old.get("last_valid_analyzed_at") or str(previous["analyzed_at"]),
        "artifact_id": old.get("artifact_id") or previous.get("artifact_id"),
        "deferred_checks": int(old.get("deferred_checks") or 0) + 1,
        "pause_reason": reason,
        "rank": None,
        "counterfactual_role": "none",
    }
    candidate.confirmation.pop("end_reason", None)


def advance(candidates, policy, previous_rows, *, slot, scan_run_id, engine_version):
    """Advance once per valid check, never once per in-scan reanalysis.

    One missing/failed check pauses rather than rejects an episode. A genuine
    rule failure, consumed lineage, model change or stale valid check resets it.
    """
    if not enabled(policy):
        return
    prior = {(row["symbol"], row["side"]): row for row in previous_rows}
    eligible = sorted((c for c in candidates if c.eligible_for(policy)), key=rank_key)
    ranks = {(c.symbol, c.side): index + 1 for index, c in enumerate(eligible)}
    previous_slot = utc(slot) - timedelta(minutes=policy.cadence_minutes)
    oldest_slot = previous_slot - timedelta(minutes=policy.cadence_minutes)
    for candidate in candidates:
        row = prior.get((candidate.symbol, candidate.side), {})
        old = as_object(row.get("confirmation"))
        old_slot = utc(old["slot"]) if old.get("slot") else None
        preceding_control = bool(
            old.get("version") in {CONFIRMATION_VERSION, LEGACY_CONFIRMATION_VERSION}
            and old.get("state") in {"watching", "ready", "paused"}
            and old_slot is not None and oldest_slot <= old_slot <= previous_slot
            and row.get("engine_version") == engine_version
            and candidate.analyzed_at > utc(row["analyzed_at"])
        )
        if not candidate.eligible_for(policy) and preceding_control and data_unavailable(candidate):
            pause(candidate, row, slot=slot, reason=candidate.rejection_code or candidate.analysis_status)
            continue
        last_valid_at = None
        if preceding_control:
            last_valid_at = utc(old.get("last_valid_analyzed_at") or row["analyzed_at"])
        previous_artifact = (
            old.get("artifact_id") if old.get("state") == "paused"
            else row.get("artifact_id")
        )
        continuation = bool(
            preceding_control
            and previous_artifact == candidate.artifact_id
            and last_valid_at is not None
            and candidate.analyzed_at - last_valid_at <= timedelta(minutes=MAX_VALID_CONTROL_GAP_MINUTES)
        )
        if not candidate.eligible_for(policy):
            if preceding_control:
                candidate.confirmation = {
                    **old, "version": CONFIRMATION_VERSION,
                    "slot": utc(slot).isoformat(), "state": "discarded",
                    "end_reason": candidate.rejection_code or "eligibility_lost",
                    "rank": None, "counterfactual_role": "none",
                }
            continue
        count = int(old["controls"]) + 1 if continuation else 1
        first_at = old["first_analyzed_at"] if continuation else candidate.analyzed_at.isoformat()
        elapsed = (candidate.analyzed_at - utc(first_at)).total_seconds()
        ready = count >= CONFIRMATION_CONTROLS and elapsed >= CONFIRMATION_MINUTES * 60
        candidate.confirmation = {
            "version": CONFIRMATION_VERSION,
            "first_scan_run_id": int(old["first_scan_run_id"]) if continuation else scan_run_id,
            "first_analyzed_at": first_at,
            "last_valid_analyzed_at": candidate.analyzed_at.isoformat(),
            "artifact_id": candidate.artifact_id,
            "slot": utc(slot).isoformat(),
            "controls": count,
            "elapsed_seconds": round(elapsed, 3),
            "state": "ready" if ready else "watching",
            "rank": ranks[(candidate.symbol, candidate.side)],
            "deferred_checks": int(old.get("deferred_checks") or 0) if continuation else 0,
            "counterfactual_role": "none" if continuation else "immediate",
        }


def select(candidates, policy):
    eligible = [c for c in candidates if c.eligible_for(policy)]
    if enabled(policy):
        eligible = [c for c in eligible if c.confirmation.get("state") == "ready"]
    return min(eligible, key=rank_key) if eligible else None


def finish(candidates, selected, *, status, reason, operation_id):
    """Persist execution outcome in the same transaction as the actual entry."""
    for candidate in candidates:
        state = candidate.confirmation
        if not state:
            continue
        if candidate is selected:
            state["decision_reason"] = reason
            if status in {"opened", "would_open"}:
                state.update(state="consumed", counterfactual_role="confirmed",
                             operation_id=operation_id)
        elif state.get("state") == "ready":
            state["decision_reason"] = "another_candidate_selected" if selected else reason


def compact_payload(candidate) -> dict:
    """Keep only numerical outputs actually used by the active short engine."""
    result = candidate.analysis_result or {}
    snapshot = result.get("snapshot") or {}
    traces = (snapshot.get("stage_rule_traces") or {}).get("intraday_short") or []
    active = {}
    for trace in traces:
        outputs = trace.get("outputs") or {}
        values = {
            name: value for name in trace.get("active_probability_outputs", [])
            if isinstance(value := outputs.get(name), (int, float)) and math.isfinite(value)
        }
        if values:
            active[trace["rule_id"]] = values
    payload = {
        "confirmation": candidate.confirmation,
        "active_context": active,
        "data_cutoff_at": snapshot.get("data_cutoff_at"),
        "raw_market_payloads_stored": False,
    }
    size = len(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode())
    if size > CONTROL_JSON_BYTE_BUDGET:
        raise ValueError("short_confirmation_control_exceeds_byte_budget")
    return payload


def evaluate_endpoint(candles, *, start_ms, end_ms, side, entry, take_profit, stop_loss):
    """Conservative 1m first-touch evidence for the exact four-hour window.

    An OHLC candle straddling entry/expiry cannot date a touch inside that
    candle. Such touches remain ambiguous, rather than inventing a win/loss.
    Missing minutes are retried by the caller, never treated as unresolved.
    """
    first_open = start_ms // 60_000 * 60_000
    expected = list(range(first_open, end_ms, 60_000))
    material = {int(c["open_time_ms"]): c for c in candles}
    if any(t not in material for t in expected):
        raise ValueError("confirmation_future_path_incomplete")
    last_inside = entry
    for stamp in expected:
        candle = material[stamp]
        partial = stamp < start_ms or stamp + 60_000 > end_ms
        tp = candle["high"] >= take_profit if side == "long" else candle["low"] <= take_profit
        sl = candle["low"] <= stop_loss if side == "long" else candle["high"] >= stop_loss
        if tp or sl:
            ambiguous = partial or (tp and sl)
            return {
                "first_touch": "ambiguous" if ambiguous else "tp" if tp else "sl",
                "first_touch_at": datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat(),
                "terminal_price": None if ambiguous else take_profit if tp else stop_loss,
                "r_multiple": None if ambiguous else abs(take_profit - entry) / abs(entry - stop_loss) if tp else -1.0,
            }
        if stamp + 60_000 <= end_ms:
            last_inside = float(candle["close"])
    direction = 1 if side == "long" else -1
    return {"first_touch": "unresolved", "first_touch_at": None,
            "terminal_price": last_inside,
            "r_multiple": direction * (last_inside - entry) / abs(entry - stop_loss)}


def summarize_trials(rows, *, fee_per_side=None):
    """Manual evaluation, no writes, no model updates and no independent-case inflation.

    Input rows are compact checkpoints for a bounded period. Returns paired
    same-opportunity endpoints, plus discarded/missed winners. This is not a
    replay of the old daily-quota policy. PnL is risk-normalized, not fictitious
    dollars; unknown costs are never silently reported as net profit.
    """
    groups = {}
    for row in rows:
        meta = as_object(row.get("confirmation"))
        if meta.get("version") not in {CONFIRMATION_VERSION, LEGACY_CONFIRMATION_VERSION}:
            continue
        key = (row["participant_id"], meta["first_scan_run_id"], row["symbol"], row["side"])
        groups.setdefault(key, []).append((row, meta))
    pairs, discarded, pending, unpaired = [], [], 0, 0

    def endpoint(row):
        gross = row.get("r_multiple")
        net = None
        if gross is not None and fee_per_side is not None and row.get("terminal_price") is not None:
            net = gross - fee_per_side * (row["entry"] + row["terminal_price"]) / abs(row["entry"] - row["stop_loss"])
        return {"outcome": row.get("first_touch"), "gross_r": gross,
                "fee_adjusted_r": net, "tp_forecast": row["tp_probability"]}

    for key, controls in groups.items():
        controls.sort(key=lambda item: utc(item[0]["analyzed_at"]))
        initial = next((r for r, m in controls if m.get("counterfactual_role") == "immediate"), None)
        confirmed = next((r for r, m in controls if m.get("counterfactual_role") == "confirmed"), None)
        if initial is None:
            unpaired += 1
            continue
        if initial["outcome_status"] != "evaluated" or (confirmed and confirmed["outcome_status"] != "evaluated"):
            pending += 1
            continue
        identity = {"first_scan_run_id": key[1], "symbol": key[2], "side": key[3]}
        if confirmed:
            before, after = endpoint(initial), endpoint(confirmed)
            pairs.append({**identity, "immediate": before, "confirmed": after,
                          "delta_gross_r": after["gross_r"] - before["gross_r"]
                          if after["gross_r"] is not None and before["gross_r"] is not None else None})
        elif controls[-1][1].get("state") == "discarded":
            discarded.append({**identity, **endpoint(initial), "reason": controls[-1][1].get("end_reason")})
        else:
            pending += 1
    valid = [p for p in pairs if p["delta_gross_r"] is not None]
    return {
        "contract": CONFIRMATION_VERSION, "episodes": len(groups),
        "paired_endpoints": pairs, "discarded_episodes": discarded,
        "pending_or_unfinished_episodes": pending, "missing_initial_endpoint": unpaired,
        "improved": sum(p["delta_gross_r"] > 0 for p in valid),
        "worsened": sum(p["delta_gross_r"] < 0 for p in valid),
        "unchanged": sum(p["delta_gross_r"] == 0 for p in valid),
        "discarded_winners": sum(p["outcome"] == "tp" for p in discarded),
        "avoided_losers": sum(p["outcome"] == "sl" for p in discarded),
        "fee_per_side": fee_per_side,
        "limitations": ["paired_opportunities_not_full_daily_policy_replay",
                        "episodes_can_share_market_path_do_not_assume_independence",
                        "unresolved_mark_uses_last_full_minute_inside_horizon",
                        "slippage_and_funding_not_modeled"],
    }
