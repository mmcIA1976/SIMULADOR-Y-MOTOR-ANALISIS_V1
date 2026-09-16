from __future__ import annotations

import gzip
import json
import math
from copy import deepcopy
from pathlib import Path

from audit_empirical_active_rules import _load_numpy
from build_empirical_temporal_engine import (
    SELECTION,
    _raw_feature_map,
    _robust_scaling,
    _standardized_vector,
    load_or_build_records,
)
from empirical_temporal_engine import canonical_sha256


ROOT = Path(__file__).resolve().parent
BASE_ARTIFACT_PATH = (
    ROOT / "auditorias_motor" / "motor_v0_10_empirical_analog.json.gz"
)
RELEASE_EVIDENCE_PATH = (
    ROOT / "outputs" / "volume_relative_target_horizon_check.json"
)
OUTPUT_PATH = (
    ROOT / "auditorias_motor" / "motor_v0_11_empirical_analog.json.gz"
)

ENGINE_VERSION = "TP-SL-EMPIRICAL-ANALOG-v0.11"
SCORING_VERSION = "historical-analog-first-touch-v0.11"
BUILD_VERSION = "empirical-target-profile-builder-v0.1"
ARTIFACT_ID = "TP-SL-EMPIRICAL-ANALOG-v0.11-frozen-001"
PROFILE_ID = "intraday_wide::relative_volume_4_24h"
RULE_ID = "LIB-CAND-RELATIVE-VOLUME-001"
FORMULA_OUTPUT = "log_relative_horizon_volume"


def _verified_json(path: Path, hash_field: str) -> tuple[dict, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.pop(hash_field, ""))
    if not expected or canonical_sha256(payload) != expected:
        raise ValueError(f"invalid_source_hash:{path.name}")
    return payload, expected


def _base_artifact() -> dict:
    with gzip.open(BASE_ARTIFACT_PATH, "rt", encoding="utf-8") as source:
        payload = json.load(source)
    expected = str(payload.pop("artifact_sha256", ""))
    if canonical_sha256(payload) != expected:
        raise ValueError("base_artifact_hash_invalid")
    payload["artifact_sha256"] = expected
    return payload


def override_feature_names() -> list[str]:
    return [
        f"{stage}::{feature}"
        for stage in ("intraday_short", "intraday_wide")
        for feature in (
            "log_context_sigma",
            f"{RULE_ID}::{FORMULA_OUTPUT}",
        )
    ]


def _support_limit(records: list[dict], names, scaling) -> float:
    np = _load_numpy()
    development = [row for row in records if row["partition"] == "development"]
    calibration = [row for row in records if row["partition"] == "calibration"]
    vectors = np.asarray(
        [
            _standardized_vector(
                row, "intraday_wide", orientation, names, scaling
            )
            for row in development
            for orientation in (0, 1)
        ],
        dtype=np.float64,
    )
    symbols = np.asarray(
        [row["symbol"] for row in development for _ in (0, 1)],
        dtype=object,
    )
    distances = []
    for row in calibration:
        for orientation in (0, 1):
            query = np.asarray(
                _standardized_vector(
                    row, "intraday_wide", orientation, names, scaling
                ),
                dtype=np.float64,
            )
            difference = vectors - query
            values = np.sqrt(
                np.minimum(36.0, difference * difference).mean(axis=1)
            )
            values += np.where(
                symbols == str(row["symbol"]),
                0.0,
                float(SELECTION["cross_symbol_penalty"]),
            )
            distances.append(float(values.min()))
    if not distances:
        raise ValueError("override_support_distances_missing")
    ordered = sorted(distances)
    index = min(len(ordered) - 1, math.ceil(0.995 * len(ordered)) - 1)
    return round(max(0.25, ordered[index] + 0.05), 8)


def build_artifact() -> dict:
    release, release_hash = _verified_json(
        RELEASE_EVIDENCE_PATH, "canonical_payload_sha256"
    )
    if release.get("acceptance_gate", {}).get("passed") is not True:
        raise ValueError("target_horizon_release_evidence_not_passed")
    if (
        release.get("acceptance_gate", {}).get(
            "production_replacement_authorized"
        )
        is not True
    ):
        raise ValueError("target_horizon_release_not_authorized")
    records = load_or_build_records()
    records_by_id = {str(record["id"]): record for record in records}
    base = _base_artifact()
    if set(records_by_id) != {str(analog["id"]) for analog in base["analogs"]}:
        raise ValueError("base_artifact_record_set_mismatch")

    names = override_feature_names()
    scaling = _robust_scaling(records, {"intraday_wide": names})[
        "intraday_wide"
    ]
    support_limit = _support_limit(records, names, scaling)
    analogs = deepcopy(base["analogs"])
    for analog in analogs:
        record = records_by_id[str(analog["id"])]
        analog["target_profile_feature_vectors"] = {
            PROFILE_ID: [
                _standardized_vector(
                    record,
                    "intraday_wide",
                    orientation,
                    names,
                    scaling,
                )
                for orientation in (0, 1)
            ]
        }

    payload = deepcopy(base)
    payload.update(
        {
            "artifact_id": ARTIFACT_ID,
            "engine_version": ENGINE_VERSION,
            "scoring_version": SCORING_VERSION,
            "build_version": BUILD_VERSION,
            "status": "frozen_production",
            "production_authorized": True,
            "single_engine": True,
            "parallel_probability_engines": 0,
            "automatic_weight_updates": False,
            "release_evidence": {
                "source": str(RELEASE_EVIDENCE_PATH.relative_to(ROOT)),
                "canonical_payload_sha256": release_hash,
                "acceptance_gate": release["acceptance_gate"],
            },
            "target_horizon_rule_profiles": {
                "intraday_short": {
                    "profile": "v0_10_exact",
                    "overrides": {},
                },
                "intraday_wide": {
                    "profile": "relative_volume_4_24h",
                    "overrides": {
                        "intraday_wide": {
                            "profile_id": PROFILE_ID,
                            "distance_method": "coordinate_equal",
                            "feature_names": names,
                            "feature_scaling": scaling,
                            "maximum_nearest_context_distance": support_limit,
                            "active_rule_ids": [RULE_ID],
                            "active_formula_outputs": [FORMULA_OUTPUT],
                            "scope": "medium_target_only",
                        }
                    },
                },
                "short_swing": {
                    "profile": "v0_10_exact",
                    "overrides": {},
                },
            },
            "active_rule_ids_by_target_horizon": {
                "intraday_short": [
                    "M4-RULE-PATH-STRUCTURE-001",
                    "M4-RULE-MTF-HIERARCHY-001",
                    "M4-RULE-VOLATILITY-RANK-001",
                    "LIB-CAND-COMPRESSION-001",
                    "LIB-CAND-EMA-TREND-001",
                ],
                "intraday_wide": [
                    "M4-RULE-PATH-STRUCTURE-001",
                    "M4-RULE-MTF-HIERARCHY-001",
                    "M4-RULE-VOLATILITY-RANK-001",
                    "LIB-CAND-COMPRESSION-001",
                    "LIB-CAND-EMA-TREND-001",
                    RULE_ID,
                ],
                "short_swing": [
                    "M4-RULE-PATH-STRUCTURE-001",
                    "M4-RULE-MTF-HIERARCHY-001",
                    "M4-RULE-VOLATILITY-RANK-001",
                    "LIB-CAND-COMPRESSION-001",
                    "LIB-CAND-EMA-TREND-001",
                ],
            },
            "analogs": analogs,
        }
    )
    payload.pop("artifact_sha256", None)
    payload["artifact_sha256"] = canonical_sha256(payload)
    return payload


def main() -> None:
    payload = build_artifact()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUTPUT_PATH, "wt", encoding="utf-8", newline="\n") as target:
        json.dump(payload, target, ensure_ascii=True, separators=(",", ":"))
    print(
        json.dumps(
            {
                "path": str(OUTPUT_PATH.relative_to(ROOT)),
                "artifact_id": payload["artifact_id"],
                "engine_version": payload["engine_version"],
                "artifact_sha256": payload["artifact_sha256"],
                "analogs": len(payload["analogs"]),
                "target_horizon_rule_profiles": payload[
                    "target_horizon_rule_profiles"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
