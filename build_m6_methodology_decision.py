from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_DIR = ROOT / "auditorias_motor"
M5_CLOSURE_PATH = AUDIT_DIR / "paquete_cierre_m5_6_v0_1.json"
M5_CONTRACT_PATH = (
    AUDIT_DIR / "contrato_implementacion_m5_1_v0_1.json"
)
DEFAULT_OUTPUT_PATH = (
    AUDIT_DIR / "decision_metodologica_m6_1_v0_1.json"
)
DEFAULT_REPORT_PATH = (
    AUDIT_DIR / "2026-07-28_M6_1_decision_metodologica_v0_1.md"
)
VERSION = "M6.1-methodology-decision-v0.1"

SOURCES = (
    {
        "id": "WIESE-2019-FIRST-PASSAGE-INTERVAL",
        "type": "primary_research",
        "title": "First passage in an interval for fractional Brownian motion",
        "url": "https://arxiv.org/abs/1807.08807",
        "supported_claims": [
            "First exit from an interval is defined by two absorbing boundaries.",
            "For ordinary Brownian motion the eventual upper-exit splitting probability is determined by the normalized starting position.",
            "Finite discretization can materially affect observed barrier crossings.",
        ],
        "not_supported": [
            "Bitcoin log returns are Brownian.",
            "Realized volatility is a calibrated forecast.",
            "Technical indicators have any specified coefficient.",
        ],
    },
    {
        "id": "RANGARAJAN-DING-2001-TWO-BARRIERS",
        "type": "primary_research",
        "title": "Anomalous diffusion and the first passage time problem",
        "url": "https://arxiv.org/abs/cond-mat/0105267",
        "supported_claims": [
            "Two absorbing barriers admit a finite-time first-passage power-series treatment.",
            "Ordinary Brownian diffusion is a special case of the derivation.",
        ],
        "not_supported": [
            "The Brownian special case is empirically sufficient for crypto.",
            "A finite series truncation tolerance for this project.",
        ],
    },
    {
        "id": "KIM-ET-AL-2023-CIF",
        "type": "primary_research",
        "title": "Revisiting the cumulative incidence function with competing risks data",
        "url": (
            "https://academic.oup.com/jrsssc/article/72/2/498/7076689"
        ),
        "supported_claims": [
            "A cause-specific cumulative incidence is an absolute event probability.",
            "The cumulative incidence integrates survival times the cause-specific hazard.",
            "All competing event types must be modeled jointly for coherent absolute risk.",
        ],
        "not_supported": [
            "A specific crypto covariate set or coefficient.",
            "A project-specific bin width.",
        ],
    },
    {
        "id": "LEE-ET-AL-2025-DISCRETE-COMPETING-RISKS",
        "type": "primary_research",
        "title": "Discrete-time competing-risks regression with or without penalization",
        "url": (
            "https://academic.oup.com/biometrics/article/81/2/"
            "ujaf040/8120014"
        ),
        "supported_claims": [
            "Discrete cause-specific hazards can produce cumulative incidence through survival products.",
            "A discrete competing-risks likelihood can estimate covariate effects without treating competing events as ordinary censoring.",
        ],
        "not_supported": [
            "M5 variables are predictive.",
            "Penalty strength, coefficients or promotion thresholds.",
        ],
    },
    {
        "id": "GNEITING-RAFTERY-2007-PROPER-SCORES",
        "type": "primary_research",
        "title": "Strictly Proper Scoring Rules, Prediction, and Estimation",
        "url": (
            "https://sites.stat.washington.edu/people/raftery/"
            "Research/PDF/Gneiting2007jasa.pdf"
        ),
        "supported_claims": [
            "Strictly proper scores reward reporting the forecaster's true predictive distribution.",
            "Logarithmic and Brier-type scores are suitable for probabilistic evaluation.",
        ],
        "not_supported": [
            "This project's probabilities are calibrated.",
            "Any acceptable score threshold.",
        ],
    },
    {
        "id": "BRIER-1950-PROBABILITY-FORECASTS",
        "type": "primary_research",
        "title": "Verification of forecasts expressed in terms of probability",
        "url": (
            "https://journals.ametsoc.org/view/journals/mwre/78/1/"
            "1520-0493_1950_078_0001_vofeit_2_0_co_2.xml"
        ),
        "supported_claims": [
            "Probability forecasts can be evaluated with squared probability error.",
        ],
        "not_supported": [
            "Brier score alone establishes profitability.",
            "A project-specific acceptance threshold.",
        ],
    },
)

BASELINE_RULES = {
    "M4-RULE-HORIZON-SAMPLING-001",
    "M4-RULE-PLAN-GEOMETRY-001",
    "M4-RULE-LOG-RETURNS-001",
    "M4-RULE-REALIZED-VOLATILITY-001",
    "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
}
NO_VOTE_RULES = {
    "M4-RULE-PENDING-ACTIVATION-001",
    "M4-RULE-EXPONENTIAL-SMOOTHER-001",
}
ECONOMIC_LAYER_RULES = {
    "M4-RULE-QUOTED-SPREAD-001",
    "M4-RULE-DEPTH-SWEEP-001",
    "M4-RULE-FEE-SCENARIOS-001",
    "M4-RULE-FUNDING-CASHFLOW-001",
    "M4-RULE-PLAN-EXPOSURE-001",
    "M4-RULE-NET-PAYOFFS-001",
    "M4-RULE-EXPECTED-VALUE-001",
    "M4-RULE-EVALUATION-READINESS-001",
}


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


def build_feature_roles(rules: list[dict]) -> list[dict]:
    rule_ids = {rule["rule_id"] for rule in rules}
    declared = BASELINE_RULES | NO_VOTE_RULES | ECONOMIC_LAYER_RULES
    covariates = rule_ids - declared
    roles = []
    for rule in sorted(rules, key=lambda item: item["sequence"]):
        rule_id = rule["rule_id"]
        if rule_id in BASELINE_RULES:
            role = "first_passage_baseline_input"
            probability_access = "deterministic_baseline_only"
        elif rule_id in NO_VOTE_RULES:
            role = "policy_or_auxiliary_no_probability_vote"
            probability_access = "none"
        elif rule_id in ECONOMIC_LAYER_RULES:
            role = "downstream_execution_or_economic_layer"
            probability_access = "none"
        else:
            role = "candidate_competing_risk_covariate"
            probability_access = "coefficient_locked_until_estimated_and_validated"
        roles.append(
            {
                "rule_id": rule_id,
                "canonical_family": rule["canonical_family"],
                "m6_role": role,
                "probability_access": probability_access,
                "manual_weight_authorized": False,
                "current_coefficient": None,
            }
        )
    if len(roles) != 27 or len(covariates) != 12:
        raise ValueError("unexpected_m6_feature_role_partition")
    return roles


def build_decision() -> dict:
    m5_closure = read_json(M5_CLOSURE_PATH)
    m5_contract = read_json(M5_CONTRACT_PATH)
    if (
        m5_closure["status"] != "completed_owner_authorized"
        or not m5_closure["scope"]["m5_closed"]
        or m5_closure["scope"]["m6_started"]
    ):
        raise ValueError("m5_closure_gate_not_satisfied")
    roles = build_feature_roles(m5_contract["rules"])
    payload = {
        "version": VERSION,
        "phase": "M6",
        "subphase": "M6.1",
        "status": "methodology_recommendation_complete_owner_review_pending",
        "date": "2026-07-28",
        "owner_authorization": {
            "statement": "continuamos inicia m6",
            "m6_started": True,
            "m6_closed": False,
            "production_authorized": False,
            "m7_started": False,
        },
        "problem_definition": {
            "analysis_timing": "strictly_pre_trade",
            "outcomes": [
                "tp_first_within_horizon",
                "sl_first_within_horizon",
                "neither_barrier_before_expiry",
            ],
            "tie_policy": (
                "continuous model has zero tie probability; discrete observed "
                "ties remain ambiguous and are excluded or reconstructed"
            ),
            "required_identity": "P_TP(T)+P_SL(T)+P_EXPIRY(T)=1",
            "conditioned_on": [
                "symbol",
                "side",
                "entry",
                "take_profit",
                "stop_loss",
                "exact_horizon",
                "information_available_at_analysis_time",
            ],
        },
        "candidate_methods": [
            {
                "id": "independent_one_sided_barriers",
                "decision": "rejected",
                "reason": (
                    "Independent TP and SL calculations ignore competition "
                    "and do not guarantee a coherent three-outcome mass."
                ),
            },
            {
                "id": "endpoint_multinomial_only",
                "decision": "rejected_as_primary",
                "reason": (
                    "It discards event timing and handles horizon censoring "
                    "less naturally than a time-to-first-event model."
                ),
            },
            {
                "id": "brownian_double_barrier_first_passage",
                "decision": "selected_as_baseline",
                "reason": (
                    "It directly conditions on both plan barriers, volatility "
                    "and finite horizon and yields TP, SL and survival mass."
                ),
            },
            {
                "id": "discrete_time_competing_risks",
                "decision": "selected_as_future_evidence_layer",
                "reason": (
                    "It preserves first-event timing, competing outcomes and "
                    "censoring while allowing coefficients to be estimated."
                ),
            },
        ],
        "selected_architecture": {
            "id": "first_passage_baseline_plus_competing_risk_evidence_v0.1",
            "layer_a_baseline": {
                "state_process": "X(t)=sigma_H*W(t)",
                "drift": 0,
                "upper_barrier": "a=d_TP>0",
                "lower_barrier": "-b where b=d_SL>0",
                "horizon": "T=H",
                "stopping_time": "tau=inf{t>=0: X(t)>=a or X(t)<=-b}",
                "probabilities": {
                    "P_TP": "P(tau<=T and X(tau)=a)",
                    "P_SL": "P(tau<=T and X(tau)=-b)",
                    "P_EXPIRY": "P(tau>T)",
                },
                "solver_decision_deferred_to": "M6.2",
            },
            "layer_b_evidence": {
                "model": "discrete_time_competing_risks",
                "cause_specific_hazards": [
                    "h_TP(k|x)",
                    "h_SL(k|x)",
                ],
                "survival": (
                    "S(k|x)=product_(j=1..k)"
                    "[1-h_TP(j|x)-h_SL(j|x)]"
                ),
                "cumulative_incidence": {
                    "P_TP": (
                        "sum_(k=1..K) S(k-1|x)*h_TP(k|x)"
                    ),
                    "P_SL": (
                        "sum_(k=1..K) S(k-1|x)*h_SL(k|x)"
                    ),
                    "P_EXPIRY": "S(K|x)",
                },
                "baseline_use": (
                    "first-passage interval hazards act as fixed offsets; "
                    "M5 covariates may enter only through fitted coefficients"
                ),
            },
        },
        "non_negotiable_constraints": [
            "No indicator receives a manual point, bonus, penalty or coefficient.",
            "With all evidence coefficients locked, output equals the first-passage baseline.",
            "Coefficients may be estimated only from pre-trade features and first-event outcomes.",
            "Calibration, feature construction and final validation use temporally separated data.",
            "TP, SL and expiry probabilities are published together or not at all.",
            "Missing required geometry, sigma or horizon blocks the baseline.",
            "Execution cost and account risk never masquerade as physical barrier probability.",
            "No M6 result changes production before M7, M8 and a later owner gate.",
        ],
        "feature_roles": roles,
        "coefficient_gate": {
            "current_status": "all_candidate_coefficients_locked",
            "manual_coefficients_allowed": False,
            "zero_coefficient_claim": (
                "zero means no evidence adjustment, not evidence of no effect"
            ),
            "future_requirements": [
                "preregistered feature set and interactions",
                "temporally ordered training and calibration data",
                "regularized likelihood or other explicitly approved estimator",
                "coefficient uncertainty and stability report",
                "independent temporal holdout in M8",
            ],
        },
        "evaluation_contract": {
            "proper_scores": [
                "multiclass_brier",
                "multiclass_log_loss",
            ],
            "calibration": [
                "outcome calibration-in-the-large",
                "calibration slope",
                "reliability curves by horizon",
            ],
            "not_sufficient": [
                "accuracy",
                "win rate",
                "profit alone",
                "in-sample fit",
            ],
            "thresholds_defined": False,
        },
        "sources": list(SOURCES),
        "scope": {
            "m6_started": True,
            "m6_1_complete": True,
            "m6_closed": False,
            "m7_started": False,
            "rules_partitioned": len(roles),
            "baseline_inputs": sum(
                item["m6_role"] == "first_passage_baseline_input"
                for item in roles
            ),
            "candidate_covariates": sum(
                item["m6_role"] == "candidate_competing_risk_covariate"
                for item in roles
            ),
            "probability_coefficients_defined": 0,
            "production_modified": False,
        },
        "review_gate": {
            "technical_recommendation_complete": True,
            "owner_methodology_approval": "pending",
            "m6_2_authorized": False,
            "required_owner_decision": (
                "approve or object to the selected two-layer architecture"
            ),
        },
        "source_files": [
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": file_sha256(path),
            }
            for path in (
                M5_CLOSURE_PATH,
                M5_CONTRACT_PATH,
                ROOT / "build_m6_methodology_decision.py",
                ROOT / "tests" / "test_m6_methodology_decision.py",
            )
        ],
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


def render_report(decision: dict) -> str:
    scope = decision["scope"]
    lines = [
        "# M6.1 - Decision metodologica probabilistica",
        "",
        "Fecha: 2026-07-28",
        "Estado: RECOMENDACION TECNICA COMPLETA; APROBACION PENDIENTE",
        "",
        "## Problema exacto",
        "",
        "El analisis es pre-trade y debe publicar conjuntamente:",
        "",
        "- probabilidad de TP antes que SL dentro de H;",
        "- probabilidad de SL antes que TP dentro de H;",
        "- probabilidad de que ninguna barrera sea primera antes de expirar H.",
        "",
        "La suma debe ser uno. No se calculan TP y SL de forma independiente.",
        "",
        "## Arquitectura recomendada",
        "",
        "### Capa A - baseline de primera barrera",
        "",
        "`X(t)=sigma_H W(t)` en log-precio, sin drift impuesto.",
        "Las barreras son `+d_TP` y `-d_SL`; el horizonte es `H`.",
        "El modelo calcula salida superior, salida inferior y supervivencia.",
        "",
        "### Capa B - evidencia mediante riesgos competitivos",
        "",
        "Las variables M5 no suman puntos. Solo podran modificar los hazards",
        "de TP y SL mediante coeficientes estimados con datos pre-trade y",
        "resultados de primer evento. Mientras esten bloqueados, el resultado",
        "sera exactamente el baseline.",
        "",
        "## Decisiones",
        "",
        "- Primera barrera doble: BASELINE SELECCIONADO.",
        "- Riesgos competitivos discretos: CAPA DE EVIDENCIA SELECCIONADA.",
        "- Multinomial directo: RECHAZADO COMO MODELO PRINCIPAL.",
        "- Barreras TP/SL independientes: RECHAZADAS.",
        "",
        "## Estado de las reglas M5",
        "",
        f"- Entradas directas del baseline: {scope['baseline_inputs']}.",
        f"- Covariables candidatas con coeficiente bloqueado: "
        f"{scope['candidate_covariates']}.",
        "- Reglas de ejecucion/economia: fuera de la probabilidad fisica.",
        "- Coeficientes definidos: 0.",
        "",
        "## Limites",
        "",
        "Browniano es un baseline auditable, no una afirmacion de que BTC o",
        "todos los pares sigan exactamente ese proceso. La suficiencia del",
        "modelo solo podra decidirse con validacion temporal independiente.",
        "",
        "## Puerta",
        "",
        "- M6 iniciada: SI.",
        "- M6.1 completada: SI.",
        "- M6.2 autorizada: NO.",
        "- Produccion modificada: NO.",
        "",
        "Se requiere aprobacion u objecion del propietario sobre la",
        "arquitectura de dos capas antes de definir el solver de M6.2.",
        "",
        "## Fuentes primarias",
        "",
    ]
    for source in decision["sources"]:
        lines.append(
            f"- [{source['title']}]({source['url']}) (`{source['id']}`)."
        )
    lines.extend(
        [
            "",
            "SHA-256 del payload canonico: "
            f"`{decision['canonical_payload_sha256']}`.",
            "",
        ]
    )
    return "\n".join(lines)


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
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    decision = build_decision()
    write_or_check(
        args.output,
        json.dumps(decision, ensure_ascii=True, indent=2) + "\n",
        args.check,
    )
    write_or_check(args.report, render_report(decision), args.check)


if __name__ == "__main__":
    main()
