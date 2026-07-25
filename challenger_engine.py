from __future__ import annotations

from datetime import datetime, timezone
from math import exp, isfinite, log
from typing import Any


CHALLENGER_VERSION = "challenger-v0.1-contract-only"
MODEL_SCHEMA_VERSION = "challenger-model-v0.1"
TRACE_SCHEMA_VERSION = "challenger-trace-v0.1"

OUTCOMES = ("tp_first", "sl_first", "expiry_unresolved")
HORIZON_LIMITS_SECONDS = {
    "intraday_short": (30 * 60, 4 * 60 * 60),
    "intraday_wide": (4 * 60 * 60, 24 * 60 * 60),
    "short_swing": (24 * 60 * 60, 7 * 24 * 60 * 60),
}
SHADOW_ADMISSION_STATES = {"shadow"}
FEATURE_CALCULATION_STATES = {
    "shadow",
    "data_allowed_not_predictive",
    "calculation_allowed_nonpredictive",
}
MANDATORY_PLAN_FEATURES = {
    "PLAN-TP-LOG-DISTANCE",
    "PLAN-SL-LOG-DISTANCE",
    "PLAN-LOG-HORIZON-SECONDS",
}


def _blocked(code: str, message: str, details: dict | None = None) -> dict:
    return {
        "status": "blocked",
        "block_code": code,
        "message": message,
        "challenger_version": CHALLENGER_VERSION,
        "probabilities": None,
        "trace": None,
        "details": details or {},
    }


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_without_timezone")
    return parsed.astimezone(timezone.utc)


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def validate_plan(plan: dict) -> tuple[dict | None, dict | None]:
    required = (
        "symbol",
        "side",
        "entry",
        "take_profit",
        "stop_loss",
        "time_horizon",
        "horizon_seconds",
        "analysis_at",
    )
    missing = [field for field in required if plan.get(field) in (None, "")]
    if missing:
        return None, _blocked(
            "invalid_plan",
            "Faltan campos obligatorios del plan.",
            {"missing_fields": missing},
        )

    side = str(plan["side"]).lower()
    horizon = str(plan["time_horizon"])
    if side not in {"long", "short"}:
        return None, _blocked("invalid_side", "El lado debe ser long o short.")
    if horizon not in HORIZON_LIMITS_SECONDS:
        return None, _blocked(
            "invalid_horizon",
            "El horizonte no pertenece a los tres marcos vigentes.",
            {"allowed": sorted(HORIZON_LIMITS_SECONDS)},
        )

    prices = {}
    for field in ("entry", "take_profit", "stop_loss"):
        value = plan[field]
        if not _finite_number(value) or value <= 0:
            return None, _blocked(
                "invalid_price",
                "Entrada, TP y SL deben ser numeros positivos y finitos.",
                {"field": field},
            )
        prices[field] = float(value)

    entry = prices["entry"]
    take_profit = prices["take_profit"]
    stop_loss = prices["stop_loss"]
    valid_geometry = (
        stop_loss < entry < take_profit
        if side == "long"
        else take_profit < entry < stop_loss
    )
    if not valid_geometry:
        return None, _blocked(
            "invalid_barrier_geometry",
            "TP y SL no estan situados correctamente para el lado indicado.",
        )

    normalized = {
        "symbol": str(plan["symbol"]).upper(),
        "side": side,
        "entry": entry,
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "time_horizon": horizon,
    }
    normalized["analysis_at"] = str(plan["analysis_at"])
    normalized["horizon_seconds"] = plan["horizon_seconds"]
    return normalized, None


def derive_plan_features(plan: dict) -> tuple[dict | None, dict | None]:
    horizon_seconds = plan.get("horizon_seconds")
    if not _finite_number(horizon_seconds):
        return None, _blocked(
            "missing_horizon_duration",
            "El challenger exige una duracion concreta dentro del marco elegido.",
        )
    horizon_seconds = float(horizon_seconds)
    lower, upper = HORIZON_LIMITS_SECONDS[plan["time_horizon"]]
    if not lower <= horizon_seconds <= upper:
        return None, _blocked(
            "horizon_duration_out_of_range",
            "La duracion concreta queda fuera del marco temporal declarado.",
            {"minimum_seconds": lower, "maximum_seconds": upper},
        )

    entry = plan["entry"]
    take_profit = plan["take_profit"]
    stop_loss = plan["stop_loss"]
    if plan["side"] == "long":
        tp_log_distance = log(take_profit / entry)
        sl_log_distance = log(entry / stop_loss)
    else:
        tp_log_distance = log(entry / take_profit)
        sl_log_distance = log(stop_loss / entry)

    return {
        "PLAN-TP-LOG-DISTANCE": tp_log_distance,
        "PLAN-SL-LOG-DISTANCE": sl_log_distance,
        "PLAN-LOG-HORIZON-SECONDS": log(horizon_seconds),
        "PLAN-SIDE-SIGN": 1.0 if plan["side"] == "long" else -1.0,
    }, None


def validate_model_artifact(
    artifact: dict | None,
    plan: dict,
    admission_registry: dict[str, str],
    expected_matrix_sha256: str,
) -> dict | None:
    if not artifact:
        return _blocked(
            "model_artifact_absent",
            "No existe un modelo challenger entrenado, calibrado y aprobado para sombra.",
        )
    if artifact.get("schema_version") != MODEL_SCHEMA_VERSION:
        return _blocked("model_schema_mismatch", "La version del artefacto no es compatible.")
    if artifact.get("admission_matrix_sha256") != expected_matrix_sha256:
        return _blocked(
            "admission_matrix_mismatch",
            "El modelo no fue construido con la matriz de admisibilidad vigente.",
        )
    if artifact.get("deployment_state") not in SHADOW_ADMISSION_STATES:
        return _blocked(
            "model_not_shadow_approved",
            "El artefacto no esta aprobado para evaluacion en sombra.",
        )
    required_identity = ("model_version", "dataset_id", "code_sha256", "training_cutoff_at")
    missing_identity = [field for field in required_identity if not artifact.get(field)]
    if missing_identity:
        return _blocked(
            "model_identity_incomplete",
            "El artefacto no tiene identidad y procedencia completas.",
            {"missing_fields": missing_identity},
        )
    try:
        training_cutoff = _parse_utc(str(artifact["training_cutoff_at"]))
        analysis_at = _parse_utc(plan["analysis_at"])
    except ValueError:
        return _blocked(
            "model_timestamp_invalid",
            "El corte temporal del modelo no es un timestamp UTC valido.",
        )
    if training_cutoff >= analysis_at:
        return _blocked(
            "model_temporal_leakage",
            "El modelo utiliza datos que no son anteriores al analisis.",
            {
                "training_cutoff_at": training_cutoff.isoformat(),
                "analysis_at": analysis_at.isoformat(),
            },
        )

    supported_horizons = artifact.get("supported_horizons", [])
    if plan["time_horizon"] not in supported_horizons:
        return _blocked(
            "horizon_not_validated",
            "El modelo no esta validado para este horizonte.",
        )
    supported_symbols = artifact.get("supported_symbols", [])
    if plan["symbol"] not in supported_symbols:
        return _blocked(
            "pair_not_validated",
            "El modelo no esta validado para este par.",
        )

    calibration = artifact.get("calibration", {})
    temperature = calibration.get("temperature")
    if (
        calibration.get("method") != "multinomial_temperature"
        or not _finite_number(temperature)
        or temperature <= 0
        or not calibration.get("validation_report_id")
    ):
        return _blocked(
            "calibration_missing",
            "Falta una calibracion multinomial versionada y validada.",
        )

    features = artifact.get("features")
    coefficients = artifact.get("coefficients")
    intercepts = artifact.get("intercepts")
    if not isinstance(features, list) or not features:
        return _blocked("model_features_missing", "El modelo no declara sus variables.")
    feature_ids = [feature.get("feature_id") for feature in features]
    if len(feature_ids) != len(set(feature_ids)):
        return _blocked("duplicate_model_feature", "El modelo declara variables duplicadas.")
    missing_plan_features = sorted(MANDATORY_PLAN_FEATURES - set(feature_ids))
    if missing_plan_features:
        return _blocked(
            "mandatory_plan_feature_missing",
            "El modelo omite distancia TP, distancia SL o duracion.",
            {"missing_features": missing_plan_features},
        )
    if not isinstance(coefficients, dict) or not isinstance(intercepts, dict):
        return _blocked("model_parameters_missing", "El modelo no declara parametros completos.")
    if set(coefficients) != set(OUTCOMES) or set(intercepts) != set(OUTCOMES):
        return _blocked(
            "model_outcomes_invalid",
            "El modelo debe parametrizar TP, SL y expiracion.",
        )
    if not all(isinstance(coefficients[outcome], dict) for outcome in OUTCOMES):
        return _blocked(
            "model_coefficients_invalid",
            "Los coeficientes de cada resultado deben formar un registro.",
        )

    for feature in features:
        feature_id = feature.get("feature_id")
        rule_id = feature.get("rule_id")
        scale = feature.get("scale")
        if not feature_id or not rule_id:
            return _blocked("feature_contract_invalid", "Una variable no tiene identidad completa.")
        if admission_registry.get(rule_id) not in FEATURE_CALCULATION_STATES:
            return _blocked(
                "feature_not_admitted",
                "Una variable del modelo no esta aprobada para sombra.",
                {"feature_id": feature_id, "rule_id": rule_id},
            )
        plan_dependencies = feature.get("plan_dependencies")
        if not isinstance(plan_dependencies, list):
            return _blocked(
                "feature_dependencies_missing",
                "Una variable no declara sus dependencias respecto al plan.",
                {"feature_id": feature_id},
            )
        allowed_dependency = (
            [feature_id]
            if feature_id in MANDATORY_PLAN_FEATURES
            else ["PLAN-SIDE-SIGN"]
            if feature_id == "PLAN-SIDE-SIGN"
            else []
        )
        if plan_dependencies != allowed_dependency:
            return _blocked(
                "unsupported_plan_interaction",
                "El baseline no admite interacciones ocultas con entrada, TP, SL u horizonte.",
                {
                    "feature_id": feature_id,
                    "declared_dependencies": plan_dependencies,
                    "allowed_dependencies": allowed_dependency,
                },
            )
        if not _finite_number(feature.get("center")):
            return _blocked("feature_center_invalid", "El centrado de una variable no es valido.")
        if not _finite_number(scale) or scale <= 0:
            return _blocked("feature_scale_invalid", "La escala de una variable no es valida.")
        for outcome in OUTCOMES:
            coefficient = coefficients[outcome].get(feature_id)
            if not _finite_number(coefficient):
                return _blocked(
                    "coefficient_missing",
                    "Falta un coeficiente finito.",
                    {"feature_id": feature_id, "outcome": outcome},
                )
    if not all(_finite_number(intercepts[outcome]) for outcome in OUTCOMES):
        return _blocked("intercept_invalid", "Los interceptos deben ser finitos.")

    monotonic_constraints = (
        ("PLAN-TP-LOG-DISTANCE", "tp_first", ("sl_first", "expiry_unresolved")),
        ("PLAN-SL-LOG-DISTANCE", "sl_first", ("tp_first", "expiry_unresolved")),
        ("PLAN-LOG-HORIZON-SECONDS", "expiry_unresolved", ("tp_first", "sl_first")),
    )
    for feature_id, decreasing_outcome, comparison_outcomes in monotonic_constraints:
        constrained = float(coefficients[decreasing_outcome][feature_id])
        if any(
            constrained > float(coefficients[outcome][feature_id])
            for outcome in comparison_outcomes
        ):
            return _blocked(
                "monotonicity_constraint_failed",
                "El artefacto viola un invariante de distancia u horizonte.",
                {
                    "feature_id": feature_id,
                    "decreasing_outcome": decreasing_outcome,
                },
            )
    return None


def validate_feature_snapshot(
    artifact: dict,
    feature_snapshot: dict,
    plan_features: dict,
    analysis_at: datetime,
) -> tuple[dict | None, dict | None]:
    values = {}
    trace = []
    for specification in artifact["features"]:
        feature_id = specification["feature_id"]
        if feature_id in plan_features:
            raw_value = plan_features[feature_id]
            provenance = {
                "source": "user_plan",
                "observed_at": analysis_at.isoformat(),
                "age_seconds": 0.0,
            }
        else:
            observed = feature_snapshot.get(feature_id)
            if not isinstance(observed, dict):
                return None, _blocked(
                    "required_feature_missing",
                    "Falta una variable exigida por el modelo.",
                    {"feature_id": feature_id},
                )
            raw_value = observed.get("value")
            if not _finite_number(raw_value):
                return None, _blocked(
                    "required_feature_invalid",
                    "Una variable exigida no tiene valor finito.",
                    {"feature_id": feature_id},
                )
            if not observed.get("source"):
                return None, _blocked(
                    "feature_source_missing",
                    "Una variable no identifica su fuente.",
                    {"feature_id": feature_id},
                )
            try:
                observed_at = _parse_utc(str(observed.get("observed_at", "")))
            except (TypeError, ValueError):
                return None, _blocked(
                    "feature_timestamp_invalid",
                    "Una variable no tiene timestamp UTC valido.",
                    {"feature_id": feature_id},
                )
            age_seconds = (analysis_at - observed_at).total_seconds()
            max_age_seconds = specification.get("max_age_seconds")
            if (
                age_seconds < 0
                or not _finite_number(max_age_seconds)
                or age_seconds > max_age_seconds
            ):
                return None, _blocked(
                    "feature_stale",
                    "Una variable esta fuera de su ventana de frescura.",
                    {
                        "feature_id": feature_id,
                        "age_seconds": age_seconds,
                        "max_age_seconds": max_age_seconds,
                    },
                )
            if observed.get("quality") != "ok":
                return None, _blocked(
                    "feature_quality_degraded",
                    "Una variable requerida esta degradada.",
                    {"feature_id": feature_id},
                )
            provenance = {
                "source": observed.get("source"),
                "observed_at": observed_at.isoformat(),
                "age_seconds": age_seconds,
            }

        standardized = (float(raw_value) - specification["center"]) / specification["scale"]
        values[feature_id] = standardized
        trace.append(
            {
                "feature_id": feature_id,
                "rule_id": specification["rule_id"],
                "raw_value": float(raw_value),
                "unit": specification.get("unit"),
                "center": specification["center"],
                "scale": specification["scale"],
                "standardized_value": standardized,
                **provenance,
            }
        )
    return {"values": values, "trace": trace}, None


def _softmax(logits: dict[str, float]) -> dict[str, float]:
    maximum = max(logits.values())
    exponentials = {key: exp(value - maximum) for key, value in logits.items()}
    total = sum(exponentials.values())
    return {key: exponentials[key] / total for key in OUTCOMES}


def evaluate_shadow(
    plan: dict,
    feature_snapshot: dict,
    model_artifact: dict | None,
    admission_registry: dict[str, str],
    expected_matrix_sha256: str,
) -> dict:
    normalized_plan, plan_error = validate_plan(plan)
    if plan_error:
        return plan_error

    try:
        analysis_at = _parse_utc(normalized_plan["analysis_at"])
    except ValueError:
        return _blocked("analysis_timestamp_invalid", "analysis_at debe incluir zona horaria.")

    plan_features, feature_error = derive_plan_features(normalized_plan)
    if feature_error:
        return feature_error

    model_error = validate_model_artifact(
        model_artifact,
        normalized_plan,
        admission_registry,
        expected_matrix_sha256,
    )
    if model_error:
        return model_error

    assert model_artifact is not None
    validated, snapshot_error = validate_feature_snapshot(
        model_artifact,
        feature_snapshot,
        plan_features,
        analysis_at,
    )
    if snapshot_error:
        return snapshot_error
    assert validated is not None

    logits = {}
    contributions = {}
    for outcome in OUTCOMES:
        intercept = float(model_artifact["intercepts"][outcome])
        outcome_contributions = []
        total = intercept
        for specification in model_artifact["features"]:
            feature_id = specification["feature_id"]
            coefficient = float(model_artifact["coefficients"][outcome][feature_id])
            contribution = coefficient * validated["values"][feature_id]
            total += contribution
            outcome_contributions.append(
                {
                    "feature_id": feature_id,
                    "rule_id": specification["rule_id"],
                    "coefficient": coefficient,
                    "standardized_value": validated["values"][feature_id],
                    "logit_contribution": contribution,
                }
            )
        logits[outcome] = total
        contributions[outcome] = {
            "intercept": intercept,
            "features": outcome_contributions,
            "logit_total": total,
        }

    temperature = float(model_artifact["calibration"]["temperature"])
    calibrated_logits = {
        outcome: logits[outcome] / temperature
        for outcome in OUTCOMES
    }
    probabilities = _softmax(calibrated_logits)
    return {
        "status": "shadow_prediction",
        "block_code": None,
        "message": "Prediccion disponible solo para comparacion en sombra.",
        "challenger_version": CHALLENGER_VERSION,
        "model_version": model_artifact["model_version"],
        "probabilities": {
            "tp_before_sl_within_horizon": probabilities["tp_first"],
            "sl_before_tp_within_horizon": probabilities["sl_first"],
            "expiry_unresolved": probabilities["expiry_unresolved"],
        },
        "trace": {
            "schema_version": TRACE_SCHEMA_VERSION,
            "analysis_at": analysis_at.isoformat(),
            "plan": normalized_plan,
            "features": validated["trace"],
            "outcomes": contributions,
            "logits_before_calibration": logits,
            "calibration": model_artifact["calibration"],
            "logits_after_calibration": calibrated_logits,
            "probability_mass": sum(probabilities.values()),
            "admission_matrix_sha256": expected_matrix_sha256,
            "production_effect": "none",
        },
        "details": {},
    }


def compare_with_champion(champion_result: dict, challenger_result: dict) -> dict:
    comparison = {
        "champion_engine_version": champion_result.get("engine_version"),
        "champion_tp": champion_result.get("tp_probability"),
        "champion_sl": champion_result.get("sl_probability"),
        "challenger_status": challenger_result.get("status"),
        "challenger_version": challenger_result.get("challenger_version"),
        "production_effect": "none",
    }
    probabilities = challenger_result.get("probabilities")
    if probabilities:
        comparison.update(
            {
                "challenger_tp": probabilities["tp_before_sl_within_horizon"],
                "challenger_sl": probabilities["sl_before_tp_within_horizon"],
                "challenger_expiry": probabilities["expiry_unresolved"],
            }
        )
    return comparison


def select_shadow_artifact(
    artifact_registry: dict[str, dict],
    shadow_config: dict,
) -> tuple[dict | None, dict | None]:
    if shadow_config.get("enabled") is not True:
        return None, _blocked(
            "shadow_disabled",
            "El interruptor del challenger en sombra esta desactivado.",
        )
    selected_version = shadow_config.get("selected_model_version")
    if not selected_version:
        return None, _blocked(
            "shadow_model_not_selected",
            "No hay una version de modelo seleccionada para sombra.",
        )
    artifact = artifact_registry.get(selected_version)
    if artifact is None:
        return None, _blocked(
            "shadow_model_not_found",
            "La version seleccionada no existe en el registro de artefactos.",
            {"selected_model_version": selected_version},
        )
    if artifact.get("model_version") != selected_version:
        return None, _blocked(
            "shadow_registry_identity_mismatch",
            "La clave del registro y la version interna del artefacto no coinciden.",
        )
    return artifact, None


def evaluate_configured_shadow(
    plan: dict,
    feature_snapshot: dict,
    artifact_registry: dict[str, dict],
    shadow_config: dict,
    admission_registry: dict[str, str],
    expected_matrix_sha256: str,
) -> dict:
    artifact, selection_error = select_shadow_artifact(artifact_registry, shadow_config)
    if selection_error:
        return selection_error
    return evaluate_shadow(
        plan,
        feature_snapshot,
        artifact,
        admission_registry,
        expected_matrix_sha256,
    )
