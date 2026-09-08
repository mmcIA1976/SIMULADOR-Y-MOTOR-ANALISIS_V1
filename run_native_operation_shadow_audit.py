from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from champion_shadow_learning import (
    CLASSES,
    build_global_champion_shadow_learning_audit,
)
from db import close_pool, connect


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
OUTPUT_PATH = AUDIT_DIR / "auditoria_sombra_nativa_operaciones_v0_1.json"
REPORT_PATH = AUDIT_DIR / "2026-08-13_auditoria_sombra_nativa_operaciones.md"
AUDIT_VERSION = "native-operation-shadow-audit-v0.1"
HORIZON_LABELS = {
    "intraday_short": "hasta 4 h",
    "intraday_wide": "hasta 24 h",
    "short_swing": "hasta 7 dias",
}


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _observed_direction(delta: dict) -> str:
    values = [delta.get("brier_3c"), delta.get("log_loss_3c")]
    if all(value is not None and value < 0 for value in values):
        return "alternative_observed_better"
    if all(value is not None and value > 0 for value in values):
        return "full_model_observed_better"
    return "mixed_or_unavailable"


def build_payload(audit: dict) -> dict:
    exact = int(audit["eligible_cases"])
    excluded = int(audit["excluded_cases"])
    episode = audit["independent_episode_comparison"]
    shadow_by_horizon = audit["independent_episode_by_horizon"]
    shadow_observations = {
        horizon: {
            "raw_cases": comparison["raw_cases"],
            "effective_episodes": comparison["effective_episodes"],
            "challenger_minus_champion": comparison[
                "challenger_minus_champion"
            ],
            "observed_direction": _observed_direction(
                comparison["challenger_minus_champion"]
            ),
            "formal_conclusion": "insufficient_effective_evidence",
        }
        for horizon, comparison in shadow_by_horizon.items()
    }
    rule_observations = {}
    for rule_id, horizons in audit["native_rule_ablation"]["rules"].items():
        rule_observations[rule_id] = {}
        for horizon, comparison in horizons.items():
            delta = comparison["without_rule_minus_full"]
            direction = _observed_direction(
                {
                    "brier_3c": -delta["brier_3c"],
                    "log_loss_3c": -delta["log_loss_3c"],
                }
            )
            if direction == "alternative_observed_better":
                reading = "rule_observed_better"
            elif direction == "full_model_observed_better":
                reading = "without_rule_observed_better"
            else:
                reading = "mixed_or_unavailable"
            rule_observations[rule_id][horizon] = {
                "raw_cases": comparison["raw_cases"],
                "effective_episodes": comparison["effective_episodes"],
                "without_rule_minus_full": delta,
                "observed_direction": reading,
                "formal_conclusion": comparison["evidence_status"],
            }

    payload = {
        "audit_version": AUDIT_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "cohort": "current_engine_real_closed_operations_only",
            "operation_link_required": True,
            "counterfactual_operations": 0,
            "synthetic_operations": 0,
            "ambiguous_outcomes_used_as_labels": 0,
            "independent_unit": "overlapping_episode_by_symbol_and_horizon",
        },
        "engine_version": audit["engine_version"],
        "inventory": {
            "closed_current_engine_operations": exact + excluded,
            "exact_metric_eligible_operations": exact,
            "excluded_operations": excluded,
            "exclusion_reasons": audit["exclusion_reasons"],
            "resolved_cases_by_horizon": audit[
                "resolved_cases_by_horizon"
            ],
            "effective_episodes": episode["effective_episodes"],
            "effective_outcome_mass": episode[
                "effective_outcome_mass"
            ],
        },
        "storage_contract": {
            "extra_supabase_rows_required": 0,
            "extra_price_ticks_required": 0,
            "prediction_source": (
                "recommendations.snapshot_json.m6_probability_trace"
            ),
            "outcome_source": "learning_evaluations.first_plan_touch",
            "link": "recommendations.operation_id -> operations.id",
            "reason": (
                "champion, horizon challenger and fitted rule ablations are "
                "already stored once inside the linked recommendation snapshot"
            ),
        },
        "horizon_shadow_challenger": {
            "version": audit["policy"]["challenger"]["version"],
            "production_effect": "none",
            "overall_raw_operation_comparison": audit["overall"],
            "overall_independent_episode_comparison": episode,
            "observations_by_horizon": shadow_observations,
            "formal_gates": {
                "interim_ready": audit["interim_ready"],
                "promotion_sample_ready": audit[
                    "promotion_sample_ready"
                ],
                "metric_gates_passed": audit["metric_gates_passed"],
                "automatic_promotion": audit["automatic_promotion"],
            },
        },
        "native_active_rule_ablation": {
            "contract": audit["native_rule_ablation"],
            "observations": rule_observations,
        },
        "decision": {
            "champion": "keep_frozen",
            "shadow_challenger": "continue_collecting_real_operations",
            "rule_weights": "no_change_authorized",
            "reason": (
                f"only {episode['effective_episodes']} independent exact "
                "episodes; "
                f"{audit['resolved_cases_by_horizon']['short_swing']} usable "
                "short_swing outcomes and "
                f"{episode['effective_outcome_mass'][CLASSES[2]]:.3f} "
                "expiry-class effective mass"
            ),
        },
        "production_effect": "none",
        "supabase_writes": 0,
    }
    payload["audit_sha256"] = _canonical_sha256(payload)
    return payload


def _number(value: Any) -> str:
    return "--" if value is None else f"{float(value):+.6f}"


def render_report(payload: dict) -> str:
    inventory = payload["inventory"]
    shadow = payload["horizon_shadow_challenger"]
    short_reading = shadow["observations_by_horizon"][
        "intraday_short"
    ]["observed_direction"]
    wide_reading = shadow["observations_by_horizon"][
        "intraday_wide"
    ]["observed_direction"]
    swing_cases = shadow["observations_by_horizon"]["short_swing"][
        "raw_cases"
    ]
    volatility = payload["native_active_rule_ablation"]["observations"].get(
        "M4-RULE-VOLATILITY-RANK-001",
        {},
    )
    volatility_short = volatility.get("intraday_short", {}).get(
        "observed_direction",
        "unavailable",
    )
    volatility_wide = volatility.get("intraday_wide", {}).get(
        "observed_direction",
        "unavailable",
    )
    lines = [
        "# Auditoria nativa de sombra con operaciones reales",
        "",
        f"- Motor: `{payload['engine_version']}`.",
        (
            "- Cohorte: solo operaciones reales cerradas con recomendacion "
            "vinculada del motor actual."
        ),
        "- Operaciones sinteticas o contrafactuales: **0**.",
        f"- Escrituras nuevas en Supabase: **{payload['supabase_writes']}**.",
        "",
        "## Inventario exacto",
        "",
        (
            f"Hay **{inventory['closed_current_engine_operations']}** "
            "operaciones cerradas del motor actual: "
            f"**{inventory['exact_metric_eligible_operations']}** tienen "
            "resultado exacto utilizable y "
            f"**{inventory['excluded_operations']}** quedan excluidas."
        ),
        (
            "Tras agrupar operaciones solapadas del mismo simbolo y horizonte, "
            f"solo existen **{inventory['effective_episodes']} episodios "
            "independientes**."
        ),
        "",
        "## Candidato especifico por horizonte frente al motor estable",
        "",
        (
            "Delta = candidato menos motor estable. Un valor negativo mejora "
            "la metrica; uno positivo la empeora."
        ),
        "",
        "| Horizonte | Casos | Episodios | Delta Brier | Delta log-loss | Lectura observada |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for horizon in HORIZON_LABELS:
        item = shadow["observations_by_horizon"][horizon]
        delta = item["challenger_minus_champion"]
        lines.append(
            f"| {HORIZON_LABELS[horizon]} | {item['raw_cases']} | "
            f"{item['effective_episodes']} | {_number(delta['brier_3c'])} | "
            f"{_number(delta['log_loss_3c'])} | "
            f"`{item['observed_direction']}` |"
        )

    lines.extend(
        [
            "",
            "## Ablacion exacta de las reglas activas",
            "",
            (
                "Delta = modelo sin la regla menos modelo completo. Un valor "
                "positivo indica que, en esta muestra, la regla ayudo."
            ),
            "",
            "| Regla | Horizonte | Casos | Episodios | Delta Brier | Delta log-loss | Lectura observada |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    observations = payload["native_active_rule_ablation"]["observations"]
    for rule_id, horizons in sorted(observations.items()):
        for horizon, item in sorted(horizons.items()):
            delta = item["without_rule_minus_full"]
            lines.append(
                f"| `{rule_id}` | {HORIZON_LABELS[horizon]} | "
                f"{item['raw_cases']} | {item['effective_episodes']} | "
                f"{_number(delta['brier_3c'])} | "
                f"{_number(delta['log_loss_3c'])} | "
                f"`{item['observed_direction']}` |"
            )

    lines.extend(
        [
            "",
            "## Conclusion valida ahora",
            "",
            (
                "Lectura observada del candidato: hasta 4 h "
                f"`{short_reading}`; hasta 24 h `{wide_reading}`; y "
                f"{swing_cases} casos exactos utilizables de hasta 7 dias. "
                "La muestra no autoriza sustituir el motor estable."
            ),
            (
                "Lectura observada de la regla de volatilidad: hasta 4 h "
                f"`{volatility_short}` y hasta 24 h `{volatility_wide}`. "
                "Eso justifica observarla por horizonte, pero "
                f"{inventory['effective_episodes']} episodios independientes "
                "no permiten fijar pesos nuevos."
            ),
            (
                "No hace falta guardar datos adicionales: las probabilidades "
                "alternativas ya estan dentro del snapshot de la recomendacion "
                "vinculada, y el resultado exacto se une cuando la operacion "
                "cierra."
            ),
            "",
            f"Hash de auditoria: `{payload['audit_sha256']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def run() -> dict:
    try:
        with connect() as db:
            db.execute("SET TRANSACTION READ ONLY")
            audit = build_global_champion_shadow_learning_audit(db)
            db.rollback()
    finally:
        close_pool()
    payload = build_payload(audit)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    REPORT_PATH.write_text(render_report(payload), encoding="utf-8")
    return payload


def main() -> None:
    payload = run()
    print(
        json.dumps(
            {
                "audit_version": payload["audit_version"],
                "audit_sha256": payload["audit_sha256"],
                "inventory": payload["inventory"],
                "decision": payload["decision"],
                "production_effect": payload["production_effect"],
                "supabase_writes": payload["supabase_writes"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
