from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M7_CLOSURE_PATH = AUDIT_DIR / "paquete_cierre_m7_7_v0_1.json"
M2_CONTRACT_PATH = AUDIT_DIR / "contrato_semantico_m2_v0_1.json"
M3_CONTRACT_PATH = AUDIT_DIR / "catalogo_contratos_datos_m3_v0_1.json"
M6_COEFFICIENT_PATH = AUDIT_DIR / "coeficientes_m6_v0_1_bloqueados.json"
DEFAULT_OUTPUT_PATH = AUDIT_DIR / "protocolo_evaluacion_m8_1_v0_1.json"
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M8_1_protocolo_evaluacion_v0_1.md"
)
VERSION = "M8.1-preregistered-evaluation-protocol-v0.1"
FROZEN_MODEL_FILES = (
    "m5_rules.py",
    "m5_runtime.py",
    "m5_engine.py",
    "m6_first_passage.py",
    "m6_competing_risks.py",
    "m6_engine.py",
    "m7_data_gate.py",
)
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_record(path: Path) -> dict:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
    }


def frozen_model_records() -> list[dict]:
    if DEFAULT_OUTPUT_PATH.exists():
        written = read_json(DEFAULT_OUTPUT_PATH)
        frozen = written.get("frozen_model", {}).get("files")
        if isinstance(frozen, list):
            records = [
                item
                for item in frozen
                if isinstance(item, dict)
                and item.get("path") in FROZEN_MODEL_FILES
            ]
            if len(records) == len(FROZEN_MODEL_FILES):
                return records
    return [
        artifact_record(ROOT / path)
        for path in FROZEN_MODEL_FILES
    ]


def build_protocol() -> dict:
    m7 = read_json(M7_CLOSURE_PATH)
    coefficients = read_json(M6_COEFFICIENT_PATH)
    if not m7["scope"]["m7_closed"]:
        raise ValueError("M7_must_be_closed_before_M8")
    if m7["scope"]["m8_started"]:
        raise ValueError("historical_M7_closure_must_remain_immutable")
    if coefficients["coefficients"] is not None:
        raise ValueError("M8_must_start_with_locked_coefficients")

    payload = {
        "version": VERSION,
        "phase": "M8",
        "subphase": "M8.1",
        "status": "protocol_frozen_owner_authorized",
        "date": "2026-07-28",
        "owner_authorization": {
            "instruction": "continuemos con M8",
            "m8_started": True,
            "m9_started": False,
            "production_authorized": False,
        },
        "objective": (
            "Evaluate the already defined probability engine independently, "
            "without learning from legacy heuristic scores."
        ),
        "historical_outcome_embargo": {
            "status": "active_during_M8_1_and_M8_2",
            "closed_operations_performance_inspected_in_M8_1": False,
            "database_queried_in_M8_1": False,
            "release_condition": (
                "Protocol, eligibility inventory and chronological cut "
                "timestamps must be frozen first."
            ),
            "legacy_probabilities_allowed_as_final_comparator_only": True,
            "legacy_probabilities_allowed_as_label_or_training_target": False,
        },
        "frozen_model": {
            "files": frozen_model_records(),
            "m7_closure": artifact_record(M7_CLOSURE_PATH),
            "coefficient_artifact": artifact_record(M6_COEFFICIENT_PATH),
            "active_evidence_coefficients": 0,
            "manual_weights": 0,
        },
        "eligible_record_contract": {
            "required_identity": [
                "analysis_id",
                "analysis_at",
                "data_cutoff_at",
                "symbol",
                "side",
                "entry",
                "take_profit",
                "stop_loss",
                "time_horizon",
                "horizon_seconds",
                "engine_version",
            ],
            "required_pretrade_evidence": (
                "stored snapshot or reconstructible raw observations whose "
                "timestamps are all <= analysis_at"
            ),
            "supported_pairs": list(SUPPORTED_PAIRS),
            "supported_horizons": list(SUPPORTED_HORIZONS),
            "sides": ["long", "short"],
            "entry_type": "market",
            "data_rule": "data_cutoff_at <= analysis_at",
            "legacy_probability_required": False,
        },
        "outcome_contract": {
            "classes": [
                "tp_first_within_horizon",
                "sl_first_within_horizon",
                "neither_barrier_before_expiry",
            ],
            "label_source": (
                "chronological market observations after analysis_at and no "
                "later than expiry_at"
            ),
            "expiry_formula": "expiry_at=analysis_at+horizon_seconds",
            "same_bar_ambiguity": (
                "ambiguous unless finer timestamped observations establish "
                "which barrier was first"
            ),
            "manual_close_before_resolved_barrier": "right_censored_not_a_class",
            "missing_market_coverage": "censored_or_excluded_with_reason",
            "forced_tp_or_sl_label": False,
        },
        "chronological_partition_policy": {
            "partitions": [
                {
                    "id": "development",
                    "allowed_uses": [
                        "fit candidate coefficients",
                        "select predeclared regularization",
                        "diagnose implementation defects",
                    ],
                },
                {
                    "id": "calibration",
                    "allowed_uses": [
                        "probability calibration",
                        "single model selection between frozen candidates",
                    ],
                },
                {
                    "id": "final_test",
                    "allowed_uses": [
                        "one final evaluation",
                        "paired comparison with frozen comparators",
                    ],
                },
            ],
            "ordering": "development_end < calibration_start <= calibration_end < final_test_start",
            "cut_selection": (
                "Exact timestamps are selected in M8.2 using only analysis_at "
                "counts and pair-side-horizon coverage, never outcomes, PnL "
                "or predicted probabilities."
            ),
            "final_test_is_latest_period": True,
            "final_test_reuse_after_failure": False,
            "minimum_50_rule": "rejected",
            "insufficient_evidence_policy": (
                "Declare insufficient_evidence when class or subgroup coverage "
                "cannot support stable uncertainty estimates."
            ),
        },
        "models_to_compare": [
            {
                "id": "M8-MODEL-A",
                "name": "first_passage_baseline",
                "fit_allowed": False,
                "role": "new_design_mathematical_baseline",
            },
            {
                "id": "M8-MODEL-B",
                "name": "estimated_competing_risk_evidence",
                "fit_allowed": "development_only",
                "calibration_allowed": "calibration_only",
                "role": "new_design_with_rules",
            },
            {
                "id": "M8-COMPARATOR-LEGACY",
                "name": "stored_legacy_engine_probabilities",
                "fit_allowed": False,
                "role": "final_comparator_only_not_ground_truth",
            },
            {
                "id": "M8-COMPARATOR-EMPIRICAL",
                "name": "development_class_frequency",
                "fit_allowed": "development_only",
                "role": "naive_reference",
            },
        ],
        "metrics": [
            {
                "id": "M8-METRIC-BRIER-3C",
                "name": "unscaled_multiclass_brier",
                "formula": (
                    "BS=(1/N)*sum_i sum_c (p_ic-y_ic)^2"
                ),
                "direction": "lower_is_better",
                "primary": True,
            },
            {
                "id": "M8-METRIC-LOGLOSS-3C",
                "name": "multiclass_log_loss",
                "formula": (
                    "LL=-(1/N)*sum_i log(max(p_i,true_class,1e-15))"
                ),
                "direction": "lower_is_better",
                "primary": True,
            },
            {
                "id": "M8-METRIC-CALIBRATION",
                "name": "one_vs_rest_reliability",
                "formula": (
                    "For each class use chronological equal-count bins, at "
                    "most 10 and at least 20 observations per bin; publish "
                    "mean forecast, observed frequency and weighted absolute "
                    "calibration error."
                ),
                "direction": "closer_to_diagonal_is_better",
                "primary": True,
            },
            {
                "id": "M8-METRIC-AUC-OVR",
                "name": "macro_one_vs_rest_rank_auc",
                "formula": (
                    "Mean rank AUC across classes containing both positive "
                    "and negative observations."
                ),
                "direction": "higher_is_better",
                "primary": False,
            },
        ],
        "uncertainty_protocol": {
            "method": "paired_UTC_day_block_bootstrap",
            "resamples": 2000,
            "seed": 20260728,
            "confidence_level": 0.95,
            "paired_differences": [
                "Brier_new_minus_comparator",
                "logloss_new_minus_comparator",
            ],
            "few_calendar_blocks": "insufficient_evidence",
            "subgroup_reporting": [
                "pair",
                "side",
                "time_horizon",
                "outcome",
                "predeclared_regime",
            ],
        },
        "rule_evaluation": {
            "coefficient_source": "development_partition_only",
            "manual_coefficients_allowed": False,
            "interactions": (
                "Only combinations already registered in M4/M5 may be tested; "
                "new combinations require return to an earlier phase."
            ),
            "ablation": (
                "Remove one rule or registered group at a time without "
                "refitting on final_test."
            ),
            "double_counting_check_required": True,
        },
        "final_decision_states": [
            {
                "state": "approved_for_M9_consideration",
                "condition": (
                    "Final-test probabilistic metrics and uncertainty support "
                    "the frozen candidate without critical subgroup failure."
                ),
            },
            {
                "state": "rejected",
                "condition": (
                    "Frozen candidate is materially worse or violates a "
                    "probabilistic invariant."
                ),
            },
            {
                "state": "return_to_earlier_phase",
                "condition": (
                    "A quantified model, rule, formula or data-contract defect "
                    "requires redesign."
                ),
            },
            {
                "state": "insufficient_evidence",
                "condition": (
                    "Coverage or uncertainty is inadequate for a reliable "
                    "decision."
                ),
            },
        ],
        "prohibited_actions": [
            "inspect closed-operation performance before protocol freeze",
            "use legacy score or probability as an outcome label",
            "use post-analysis data as a predictive feature",
            "choose chronological cuts from outcomes or PnL",
            "tune any rule after opening final_test",
            "force ambiguous or censored records into TP or SL",
            "declare profitability from Brier or log-loss alone",
            "activate production during M8",
        ],
        "phase_plan": [
            "M8.1 protocol and embargo",
            "M8.2 eligibility inventory without performance",
            "M8.3 labels and chronological cuts",
            "M8.4 frozen baseline evaluation",
            "M8.5 development fit and calibration",
            "M8.6 locked final test, stability and ablation",
            "M8.7 secondary economics and quantified decision",
        ],
        "boundaries": {
            "production_effect": "none",
            "m8_started": True,
            "m8_closed": False,
            "m9_started": False,
        },
        "inputs": [
            artifact_record(M7_CLOSURE_PATH),
            artifact_record(M2_CONTRACT_PATH),
            artifact_record(M3_CONTRACT_PATH),
            artifact_record(M6_COEFFICIENT_PATH),
        ],
        "next_step": {
            "id": "M8.2",
            "name": "Inventario de elegibilidad sin evaluar resultados",
            "historical_performance_access_allowed": False,
            "started": False,
        },
    }
    payload["canonical_payload_sha256"] = sha256_text(canonical_json(payload))
    return payload


def render_report(protocol: dict) -> str:
    return "\n".join(
        [
            "# M8.1 - Protocolo de evaluacion pre-registrado",
            "",
            "Fecha: 2026-07-28",
            "Estado: M8 INICIADA; PROTOCOLO CONGELADO",
            "",
            "## Embargo",
            "",
            "- Resultados de operaciones cerradas inspeccionados: NO.",
            "- Base de datos consultada en M8.1: NO.",
            "- Porcentajes antiguos como etiqueta o entrenamiento: PROHIBIDO.",
            "- Comparacion con el motor antiguo: solo en la prueba final.",
            "",
            "## Particiones",
            "",
            "1. Desarrollo: estimacion de coeficientes.",
            "2. Calibracion: calibracion y seleccion unica.",
            "3. Prueba final: una evaluacion sin retoques posteriores.",
            "",
            "Los timestamps exactos se fijaran con inventario de cobertura,",
            "sin consultar outcomes, PnL ni probabilidades.",
            "",
            "## Metricas primarias",
            "",
            "- Brier multiclase no escalado.",
            "- Log-loss multiclase.",
            "- Curvas y error de calibracion por clase.",
            "- Intervalos emparejados mediante bootstrap por dia UTC.",
            "",
            "## Decisiones posibles",
            "",
            "- Aprobado para considerar M9.",
            "- Rechazado.",
            "- Devuelto a una fase anterior.",
            "- Evidencia insuficiente.",
            "",
            "## Limites",
            "",
            "- M8 no activa produccion.",
            "- M9 permanece bloqueada.",
            "",
            "Siguiente subfase: M8.2.",
            "",
            "SHA-256 del payload canonico: "
            f"`{protocol['canonical_payload_sha256']}`.",
            "",
        ]
    )


def write_or_check(path: Path, content: str, check: bool) -> None:
    if check:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            raise SystemExit(f"Generated artifact is stale: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    protocol = build_protocol()
    write_or_check(
        DEFAULT_OUTPUT_PATH,
        json.dumps(protocol, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(DEFAULT_REPORT_PATH, render_report(protocol), args.check)


if __name__ == "__main__":
    main()
