from __future__ import annotations

import unittest

from m6_competing_risks import (
    EvidenceArtifactError,
    LOCKED_STATUS,
    MAX_INTERVAL_COUNT,
    apply_competing_risk_evidence,
    build_baseline_intervals,
    canonical_sha256,
)
from m6_first_passage import double_barrier_first_passage


GEOMETRY = {
    "tp_log_distance": 0.04,
    "sl_log_distance": 0.03,
    "sigma_horizon": 0.05,
}


def artifact(tp_beta=0.0, sl_beta=0.0):
    features = ["path_efficiency"]
    return {
        "id": "TEST-ESTIMATED-ARTIFACT",
        "status": "estimated_internal_candidate",
        "provenance": "estimated_temporal_training",
        "training_cutoff": "2026-01-01T00:00:00Z",
        "feature_schema_sha256": canonical_sha256(features),
        "coefficients": {
            "tp": {"path_efficiency": tp_beta},
            "sl": {"path_efficiency": sl_beta},
        },
        "production_authorized": False,
    }


class M63CompetingRiskTests(unittest.TestCase):
    def test_baseline_intervals_reconstruct_final_first_passage(self) -> None:
        intervals = build_baseline_intervals(**GEOMETRY, interval_count=24)
        final = double_barrier_first_passage(**GEOMETRY)
        self.assertEqual(len(intervals), 24)
        self.assertAlmostEqual(
            intervals[-1]["baseline_cumulative_tp"],
            final.p_tp,
        )
        self.assertAlmostEqual(
            intervals[-1]["baseline_cumulative_sl"],
            final.p_sl,
        )
        self.assertAlmostEqual(
            intervals[-1]["baseline_survival_after"],
            final.p_expiry,
        )

    def test_no_artifact_returns_exact_baseline(self) -> None:
        result = apply_competing_risk_evidence(**GEOMETRY)
        baseline = double_barrier_first_passage(**GEOMETRY)
        self.assertEqual(result.evidence_status, "baseline_only_no_artifact")
        self.assertAlmostEqual(result.p_tp, baseline.p_tp, places=12)
        self.assertAlmostEqual(result.p_sl, baseline.p_sl, places=12)
        self.assertAlmostEqual(result.p_expiry, baseline.p_expiry, places=12)

    def test_locked_artifact_returns_exact_baseline(self) -> None:
        result = apply_competing_risk_evidence(
            **GEOMETRY,
            coefficient_artifact={
                "id": "M6-LOCKED",
                "status": LOCKED_STATUS,
                "coefficients": None,
            },
        )
        baseline = double_barrier_first_passage(**GEOMETRY)
        self.assertEqual(
            result.evidence_status,
            "baseline_only_coefficients_locked",
        )
        self.assertAlmostEqual(result.p_tp, baseline.p_tp, places=12)
        self.assertAlmostEqual(result.p_sl, baseline.p_sl, places=12)

    def test_zero_estimated_coefficients_equal_baseline(self) -> None:
        result = apply_competing_risk_evidence(
            **GEOMETRY,
            features={"path_efficiency": 0.8},
            coefficient_artifact=artifact(),
        )
        baseline = double_barrier_first_passage(**GEOMETRY)
        self.assertEqual(result.evidence_status, "estimated_evidence_applied")
        self.assertAlmostEqual(result.p_tp, baseline.p_tp, places=12)
        self.assertAlmostEqual(result.p_sl, baseline.p_sl, places=12)

    def test_positive_tp_coefficient_increases_tp_incidence_coherently(self) -> None:
        baseline = apply_competing_risk_evidence(**GEOMETRY)
        adjusted = apply_competing_risk_evidence(
            **GEOMETRY,
            features={"path_efficiency": 1.0},
            coefficient_artifact=artifact(tp_beta=0.5),
        )
        self.assertGreater(adjusted.p_tp, baseline.p_tp)
        self.assertAlmostEqual(
            adjusted.p_tp + adjusted.p_sl + adjusted.p_expiry,
            1.0,
            places=13,
        )

    def test_manual_or_unknown_coefficients_are_rejected(self) -> None:
        invalid = artifact()
        invalid["provenance"] = "manual"
        with self.assertRaises(EvidenceArtifactError):
            apply_competing_risk_evidence(
                **GEOMETRY,
                features={"path_efficiency": 0.8},
                coefficient_artifact=invalid,
            )

    def test_feature_schema_mismatch_is_rejected(self) -> None:
        with self.assertRaises(EvidenceArtifactError):
            apply_competing_risk_evidence(
                **GEOMETRY,
                features={"different_feature": 0.8},
                coefficient_artifact=artifact(),
            )

    def test_locked_artifact_cannot_hide_coefficients(self) -> None:
        with self.assertRaises(EvidenceArtifactError):
            apply_competing_risk_evidence(
                **GEOMETRY,
                coefficient_artifact={
                    "id": "BAD-LOCK",
                    "status": LOCKED_STATUS,
                    "coefficients": {
                        "tp": {"x": 1},
                        "sl": {"x": 1},
                    },
                },
            )

    def test_every_interval_hazard_has_unit_mass(self) -> None:
        result = apply_competing_risk_evidence(**GEOMETRY)
        for interval in result.intervals:
            self.assertAlmostEqual(
                interval["adjusted_h_tp"]
                + interval["adjusted_h_sl"]
                + interval["adjusted_h_none"],
                1.0,
                places=14,
            )

    def test_extreme_finite_predictors_use_stable_softmax(self) -> None:
        result = apply_competing_risk_evidence(
            **GEOMETRY,
            features={"path_efficiency": 1.0},
            coefficient_artifact=artifact(
                tp_beta=1000.0,
                sl_beta=-1000.0,
            ),
        )
        self.assertEqual(result.layer_version, "M6-discrete-competing-risks-v0.2")
        self.assertAlmostEqual(
            result.p_tp + result.p_sl + result.p_expiry,
            1.0,
            places=13,
        )

    def test_interval_count_is_resource_bounded_and_rejects_bool(self) -> None:
        for value in (True, MAX_INTERVAL_COUNT + 1):
            with self.assertRaises(EvidenceArtifactError):
                apply_competing_risk_evidence(
                    **GEOMETRY,
                    interval_count=value,
                )


if __name__ == "__main__":
    unittest.main()
