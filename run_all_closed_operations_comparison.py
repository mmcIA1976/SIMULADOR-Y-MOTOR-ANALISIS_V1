from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import m8_evaluation as m8
from db import close_pool, connect
from run_repaired_historical_comparison import (
    actual_class_probability,
    repaired_candidate_predictions,
    top_class_accuracy,
)


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
MODEL_PATH = AUDIT_DIR / "modelo_estimado_calibrado_m8_5_v0_1.json"
FROZEN_CANDIDATE_PATH = AUDIT_DIR / "candidato_m6_v0_2_sin_path_h.json"
OUTPUT_PATH = AUDIT_DIR / "comparacion_todas_operaciones_cerradas_v0_1.json"
REPORT_PATH = AUDIT_DIR / "2026-07-28_comparacion_todas_operaciones_cerradas.md"

SQL_CLOSED = """
SELECT
    o.id AS operation_id,
    o.status,
    o.entry_type,
    o.started_at,
    o.created_at AS operation_created_at,
    o.closed_at,
    o.entry,
    o.stop_loss,
    o.take_profit,
    o.symbol AS operation_symbol,
    o.side AS operation_side,
    o.time_horizon AS operation_time_horizon,
    r.id AS recommendation_id,
    r.created_at AS analysis_at,
    r.symbol,
    r.side,
    r.time_horizon,
    r.engine_version,
    r.snapshot_json,
    r.analysis_json,
    r.tp_probability,
    r.sl_probability,
    r.range_probability
FROM operations o
LEFT JOIN LATERAL (
    SELECT candidate.*
    FROM recommendations candidate
    WHERE candidate.operation_id = o.id
    ORDER BY candidate.created_at DESC, candidate.id DESC
    LIMIT 1
) r ON TRUE
WHERE o.status IN ('CLOSED', 'CANCELLED')
ORDER BY o.id
"""


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )


def positive(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number) and number > 0


def valid_geometry(row: dict) -> bool:
    if not all(
        positive(row.get(key))
        for key in ("entry", "stop_loss", "take_profit")
    ):
        return False
    entry = float(row["entry"])
    stop = float(row["stop_loss"])
    target = float(row["take_profit"])
    if row["side"] == "long":
        return stop < entry < target
    if row["side"] == "short":
        return target < entry < stop
    return False


def normalize_closed_row(raw: dict) -> tuple[dict | None, list[str]]:
    reasons = []
    if raw.get("status") == "CANCELLED":
        return None, ["cancelled_without_trade_outcome"]
    if raw.get("recommendation_id") is None:
        return None, ["recommendation_missing"]
    analysis_at = m8.parse_utc(raw.get("analysis_at"))
    if analysis_at is None:
        return None, ["analysis_at_missing_or_invalid"]
    symbol = str(raw.get("symbol") or raw.get("operation_symbol") or "").upper()
    side = str(raw.get("side") or raw.get("operation_side") or "").lower()
    horizon_name = str(
        raw.get("time_horizon")
        or raw.get("operation_time_horizon")
        or ""
    )
    if symbol not in {
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "BNBUSDT",
        "XRPUSDT",
        "INJUSDT",
    }:
        reasons.append("unsupported_symbol")
    if side not in {"long", "short"}:
        reasons.append("invalid_side")
    if horizon_name not in m8.HORIZON_SECONDS:
        reasons.append("unsupported_horizon")
    candidate = {
        "entry": raw.get("entry"),
        "stop_loss": raw.get("stop_loss"),
        "take_profit": raw.get("take_profit"),
        "side": side,
    }
    if not valid_geometry(candidate):
        reasons.append("invalid_plan_geometry")
    if reasons:
        return None, reasons

    snapshot = m8.parse_json_object(raw.get("snapshot_json"))
    horizon = m8.resolve_horizon(snapshot, horizon_name)
    if horizon["seconds"] is None:
        return None, ["invalid_horizon_duration"]
    entry_type = str(raw.get("entry_type") or "market").lower()
    outcome_start = analysis_at
    if entry_type != "market":
        outcome_start = (
            m8.parse_utc(raw.get("started_at"))
            or m8.parse_utc(raw.get("operation_created_at"))
            or analysis_at
        )
    expiry = outcome_start + timedelta(seconds=int(horizon["seconds"]))
    record = {
        "recommendation_id": int(raw["recommendation_id"]),
        "operation_id": int(raw["operation_id"]),
        "analysis_at": analysis_at.isoformat(),
        "analysis_day_utc": analysis_at.date().isoformat(),
        "outcome_start_at": outcome_start.isoformat(),
        "expiry_at": expiry.isoformat(),
        "partition": "all_closed_diagnostic",
        "symbol": symbol,
        "side": side,
        "time_horizon": horizon_name,
        "horizon_seconds": int(horizon["seconds"]),
        "horizon_status": horizon["status"],
        "horizon_source": horizon["source"],
        "formal_eligible_horizon": horizon["formal_eligible"],
        "entry_type": entry_type,
        "entry": float(raw["entry"]),
        "take_profit": float(raw["take_profit"]),
        "stop_loss": float(raw["stop_loss"]),
        "engine_version": str(raw.get("engine_version") or ""),
        "snapshot_sha256": m8.payload_sha256(snapshot),
        "_snapshot": snapshot,
        "_legacy": m8.normalize_legacy_probabilities(raw),
    }
    return record, []


def outcome_record(record: dict) -> dict:
    clone = dict(record)
    clone["analysis_at"] = record["outcome_start_at"]
    return clone


def metric_bundle(
    rows: list[dict],
    candidate: dict[int, dict],
    baseline: dict[int, dict],
    legacy: dict[int, dict],
) -> dict:
    candidate_metrics = m8.evaluate_predictions(rows, candidate)
    baseline_metrics = m8.evaluate_predictions(rows, baseline)
    legacy_metrics = m8.evaluate_predictions(rows, legacy)
    wins = Counter()
    for row in rows:
        new_value = actual_class_probability(row, candidate)
        old_value = actual_class_probability(row, legacy)
        wins[
            "new" if new_value > old_value
            else "old" if old_value > new_value
            else "tie"
        ] += 1
    return {
        "records": len(rows),
        "old_engine": legacy_metrics,
        "new_baseline": baseline_metrics,
        "new_candidate": candidate_metrics,
        "top_class_accuracy": {
            "old_engine": top_class_accuracy(rows, legacy),
            "new_baseline": top_class_accuracy(rows, baseline),
            "new_candidate": top_class_accuracy(rows, candidate),
        },
        "new_candidate_vs_old": {
            "brier_reduction": (
                legacy_metrics["brier_3c"]
                - candidate_metrics["brier_3c"]
            ),
            "brier_reduction_pct": (
                (
                    legacy_metrics["brier_3c"]
                    - candidate_metrics["brier_3c"]
                )
                / legacy_metrics["brier_3c"]
                * 100
            ),
            "log_loss_reduction": (
                legacy_metrics["log_loss_3c"]
                - candidate_metrics["log_loss_3c"]
            ),
            "log_loss_reduction_pct": (
                (
                    legacy_metrics["log_loss_3c"]
                    - candidate_metrics["log_loss_3c"]
                )
                / legacy_metrics["log_loss_3c"]
                * 100
            ),
            "higher_probability_for_actual_outcome": {
                "new": wins["new"],
                "old": wins["old"],
                "tie": wins["tie"],
            },
        },
    }


def build_comparison() -> dict:
    captured_at = datetime.now(timezone.utc)
    with connect() as db:
        raw_rows = [dict(row) for row in db.execute(SQL_CLOSED).fetchall()]
    close_pool()

    coverage = []
    normalized = []
    for raw in raw_rows:
        record, reasons = normalize_closed_row(raw)
        coverage.append(
            {
                "operation_id": int(raw["operation_id"]),
                "recommendation_id": raw.get("recommendation_id"),
                "entry_type": str(raw.get("entry_type") or "market").lower(),
                "normalization_status": (
                    "included" if record is not None else "excluded"
                ),
                "reasons": reasons,
            }
        )
        if record is not None:
            normalized.append(record)

    m8.enrich_pretrade_features(normalized)
    outcome_inputs = [outcome_record(row) for row in normalized]
    m8.enrich_outcomes(outcome_inputs, captured_at=captured_at)
    outcome_by_id = {
        row["operation_id"]: row.get("outcome")
        for row in outcome_inputs
    }
    for row in normalized:
        row["outcome"] = outcome_by_id[row["operation_id"]]

    eligible = []
    exclusion_counts: Counter[str] = Counter()
    coverage_by_operation = {
        item["operation_id"]: item for item in coverage
    }
    for row in normalized:
        reasons = []
        pretrade = row.get("pretrade") or {}
        outcome = row.get("outcome") or {}
        if pretrade.get("status") != "evaluated":
            reasons.append(
                str(pretrade.get("status") or "pretrade_not_evaluated")
            )
        if outcome.get("status") != "resolved" or not outcome.get("label"):
            reasons.append(
                str(outcome.get("status") or "outcome_not_resolved")
            )
        if row.get("_legacy") is None:
            reasons.append("legacy_probabilities_missing_or_invalid")
        if reasons:
            exclusion_counts.update(reasons)
            item = coverage_by_operation[row["operation_id"]]
            item["normalization_status"] = "excluded"
            item["reasons"] = reasons
            continue
        eligible.append(row)

    frozen_candidate = read_json(FROZEN_CANDIDATE_PATH)
    artifact = frozen_candidate["coefficient_artifact"]
    temperature = float(artifact["calibration"]["temperature"])
    candidate = repaired_candidate_predictions(
        eligible,
        artifact,
        temperature=temperature,
    )
    baseline = m8.baseline_predictions(eligible)
    legacy = {
        row["recommendation_id"]: row["_legacy"]
        for row in eligible
    }
    market_rows = [
        row for row in eligible if row["entry_type"] == "market"
    ]
    pending_rows = [
        row for row in eligible if row["entry_type"] != "market"
    ]

    def selected(
        values: dict[int, dict],
        rows: list[dict],
    ) -> dict[int, dict]:
        return {
            row["recommendation_id"]: values[row["recommendation_id"]]
            for row in rows
        }

    cases = []
    for row in eligible:
        recommendation_id = row["recommendation_id"]
        actual = row["outcome"]["label"]
        cases.append(
            {
                "operation_id": row["operation_id"],
                "recommendation_id": recommendation_id,
                "symbol": row["symbol"],
                "side": row["side"],
                "time_horizon": row["time_horizon"],
                "entry_type": row["entry_type"],
                "comparison_role": (
                    "strict_market_comparison"
                    if row["entry_type"] == "market"
                    else "conditional_pending_diagnostic"
                ),
                "horizon_status": row["horizon_status"],
                "actual_outcome": actual,
                "old_engine": legacy[recommendation_id],
                "new_baseline": baseline[recommendation_id],
                "new_candidate": candidate[recommendation_id],
                "actual_outcome_probability": {
                    "old_engine": legacy[recommendation_id][actual],
                    "new_candidate": candidate[recommendation_id][actual],
                },
            }
        )

    payload = {
        "version": "all-closed-old-vs-repaired-new-v0.1",
        "captured_at": captured_at.isoformat(),
        "coverage": {
            "finalized_operations_found": len(raw_rows),
            "closed_executed_operations": sum(
                row.get("status") == "CLOSED" for row in raw_rows
            ),
            "cancelled_operations": sum(
                row.get("status") == "CANCELLED" for row in raw_rows
            ),
            "operations_processed": len(coverage),
            "operations_compared": len(eligible),
            "strict_market_comparisons": len(market_rows),
            "conditional_pending_diagnostics": len(pending_rows),
            "operations_excluded": len(raw_rows) - len(eligible),
            "formal_exact_horizon_comparisons": sum(
                bool(row["formal_eligible_horizon"]) for row in eligible
            ),
            "exclusion_reason_counts": dict(exclusion_counts),
        },
        "strict_market_results": metric_bundle(
            market_rows,
            selected(candidate, market_rows),
            selected(baseline, market_rows),
            selected(legacy, market_rows),
        ),
        "all_computable_diagnostic_results": metric_bundle(
            eligible,
            candidate,
            baseline,
            legacy,
        ),
        "pending_conditional_results": (
            metric_bundle(
                pending_rows,
                selected(candidate, pending_rows),
                selected(baseline, pending_rows),
                selected(legacy, pending_rows),
            )
            if pending_rows
            else {"records": 0}
        ),
        "operation_coverage": coverage,
        "cases": cases,
        "decision": {
            "strict_market_new_better_than_old": (
                metric_bundle(
                    market_rows,
                    selected(candidate, market_rows),
                    selected(baseline, market_rows),
                    selected(legacy, market_rows),
                )["new_candidate_vs_old"]["brier_reduction"] > 0
            ),
            "pending_results_authorize_market_model": False,
            "production_authorized": False,
        },
        "production_effect": "none",
    }
    return m8.add_payload_hash(payload)


def render_report(payload: dict) -> str:
    coverage = payload["coverage"]
    strict = payload["strict_market_results"]
    all_results = payload["all_computable_diagnostic_results"]
    return "\n".join(
        [
            "# Comparacion sobre todas las operaciones cerradas",
            "",
            (
                f"- Operaciones cerradas encontradas: "
                f"{coverage['finalized_operations_found']}."
            ),
            (
                f"- Operaciones ejecutadas y cerradas: "
                f"{coverage['closed_executed_operations']}."
            ),
            f"- Operaciones canceladas: {coverage['cancelled_operations']}.",
            f"- Operaciones procesadas: {coverage['operations_processed']}.",
            f"- Comparaciones calculadas: {coverage['operations_compared']}.",
            (
                f"- Comparaciones estrictas MARKET: "
                f"{coverage['strict_market_comparisons']}."
            ),
            (
                f"- Diagnosticos condicionales PENDING: "
                f"{coverage['conditional_pending_diagnostics']}."
            ),
            f"- Excluidas: {coverage['operations_excluded']}.",
            "",
            "## Resultado estricto MARKET",
            "",
            (
                "- Aciertos motor antiguo: "
                f"{strict['top_class_accuracy']['old_engine']['correct']}/"
                f"{strict['records']}."
            ),
            (
                "- Aciertos motor nuevo: "
                f"{strict['top_class_accuracy']['new_candidate']['correct']}/"
                f"{strict['records']}."
            ),
            (
                "- Aciertos nucleo nuevo: "
                f"{strict['top_class_accuracy']['new_baseline']['correct']}/"
                f"{strict['records']}."
            ),
            (
                "- Reduccion Brier motor nuevo: "
                f"{strict['new_candidate_vs_old']['brier_reduction_pct']:.2f}%."
            ),
            (
                "- Reduccion log-loss motor nuevo: "
                f"{strict['new_candidate_vs_old']['log_loss_reduction_pct']:.2f}%."
            ),
            "",
            "## Total calculable, incluido PENDING condicional",
            "",
            (
                "- Aciertos motor antiguo: "
                f"{all_results['top_class_accuracy']['old_engine']['correct']}/"
                f"{all_results['records']}."
            ),
            (
                "- Aciertos motor nuevo: "
                f"{all_results['top_class_accuracy']['new_candidate']['correct']}/"
                f"{all_results['records']}."
            ),
            (
                "- Reduccion Brier: "
                f"{all_results['new_candidate_vs_old']['brier_reduction_pct']:.2f}%."
            ),
            "",
            "Produccion autorizada: no.",
        ]
    )


def main() -> None:
    payload = build_comparison()
    write_json(OUTPUT_PATH, payload)
    REPORT_PATH.write_text(
        render_report(payload) + "\n",
        encoding="utf-8",
    )
    print(render_report(payload))


if __name__ == "__main__":
    main()
