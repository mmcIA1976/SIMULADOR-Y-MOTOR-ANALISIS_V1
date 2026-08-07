from __future__ import annotations

import json
import math
import hashlib
from functools import lru_cache
from pathlib import Path


ARTIFACT_PATH = (
    Path(__file__).resolve().parent
    / "auditorias_motor"
    / "calibracion_horizontes_m6_v0_1.json"
)
VALID_HORIZONS = (
    "intraday_short",
    "intraday_wide",
    "short_swing",
)

HORIZON_LABELS = {
    "intraday_short": "Intradía corto · hasta 4 h",
    "intraday_wide": "Intradía amplio · hasta 24 h",
    "short_swing": "Swing corto · hasta 7 días",
}


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _positive_finite(value: object, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}_must_be_numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name}_must_be_positive_finite")
    return number


@lru_cache(maxsize=1)
def load_horizon_calibration() -> dict:
    payload = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != "M6-horizon-calibration-v0.1":
        raise ValueError("horizon_calibration_version_invalid")
    if payload.get("method") != (
        "hierarchical_coefficients_and_log_temperature_partial_pooling"
    ):
        raise ValueError("horizon_calibration_method_invalid")
    expected_payload_hash = payload.get("canonical_payload_sha256")
    actual_payload_hash = _canonical_sha256(
        {
            key: value
            for key, value in payload.items()
            if key != "canonical_payload_sha256"
        }
    )
    if expected_payload_hash != actual_payload_hash:
        raise ValueError("horizon_calibration_payload_hash_invalid")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != set(VALID_HORIZONS):
        raise ValueError("horizon_calibration_profiles_invalid")
    global_temperature = _positive_finite(
        payload.get("global_temperature"),
        "global_temperature",
    )
    temperature_prior_strength = _positive_finite(
        payload.get("temperature_prior_strength_records"),
        "temperature_prior_strength_records",
    )
    _positive_finite(
        payload.get("coefficient_prior_strength_records"),
        "coefficient_prior_strength_records",
    )
    candidates = payload.get("local_temperature_candidates")
    if not isinstance(candidates, list) or len(candidates) < 3:
        raise ValueError("local_temperature_candidates_invalid")
    candidate_values = [
        _positive_finite(value, "local_temperature_candidate")
        for value in candidates
    ]
    if candidate_values != sorted(set(candidate_values)):
        raise ValueError("local_temperature_candidates_not_unique_sorted")
    for horizon, profile in profiles.items():
        records = int(profile.get("calibration_records", -1))
        if records < 1:
            raise ValueError(f"{horizon}_calibration_records_invalid")
        local_temperature = _positive_finite(
            profile.get("local_best_temperature"),
            f"{horizon}_local_temperature",
        )
        if local_temperature not in candidate_values:
            raise ValueError(f"{horizon}_local_temperature_not_candidate")
        served_temperature = _positive_finite(
            profile.get("served_temperature"),
            f"{horizon}_served_temperature",
        )
        local_weight = records / (
            records + temperature_prior_strength
        )
        expected = math.exp(
            local_weight * math.log(local_temperature)
            + (1.0 - local_weight) * math.log(global_temperature)
        )
        if not math.isclose(
            served_temperature,
            expected,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(f"{horizon}_partial_pooling_invalid")
        if profile.get("served_log_loss") > profile.get("global_log_loss"):
            raise ValueError(f"{horizon}_log_loss_not_improved")
        if profile.get("served_brier_3c") > profile.get("global_brier_3c"):
            raise ValueError(f"{horizon}_brier_not_improved")
        coefficient_artifact = profile.get("coefficient_artifact")
        if not isinstance(coefficient_artifact, dict):
            raise ValueError(f"{horizon}_coefficient_artifact_missing")
        expected_artifact_hash = coefficient_artifact.get(
            "artifact_sha256"
        )
        actual_artifact_hash = _canonical_sha256(
            {
                key: value
                for key, value in coefficient_artifact.items()
                if key != "artifact_sha256"
            }
        )
        if expected_artifact_hash != actual_artifact_hash:
            raise ValueError(f"{horizon}_coefficient_artifact_hash_invalid")
    return payload


def horizon_calibration_profile(time_horizon: str) -> dict:
    if time_horizon not in VALID_HORIZONS:
        raise ValueError("unsupported_time_horizon")
    artifact = load_horizon_calibration()
    profile = {
        key: value
        for key, value in artifact["profiles"][time_horizon].items()
        if key != "coefficient_artifact"
    }
    records = int(profile["calibration_records"])
    if records >= 20:
        confidence = "media"
    elif records >= 10:
        confidence = "limitada"
    else:
        confidence = "baja"
    return {
        **profile,
        "version": artifact["version"],
        "method": artifact["method"],
        "source_candidate": artifact["source_candidate"],
        "source_dataset": artifact["source_dataset"],
        "selection_partition": artifact["selection_partition"],
        "selection_metric": artifact["selection_metric"],
        "global_temperature": artifact["global_temperature"],
        "coefficient_prior_strength_records": artifact[
            "coefficient_prior_strength_records"
        ],
        "temperature_prior_strength_records": artifact[
            "temperature_prior_strength_records"
        ],
        "time_horizon": time_horizon,
        "horizon_label": HORIZON_LABELS[time_horizon],
        "confidence": confidence,
        "temperature": float(profile["served_temperature"]),
    }


def horizon_coefficient_artifact(time_horizon: str) -> dict:
    if time_horizon not in VALID_HORIZONS:
        raise ValueError("unsupported_time_horizon")
    artifact = load_horizon_calibration()
    return dict(
        artifact["profiles"][time_horizon]["coefficient_artifact"]
    )
