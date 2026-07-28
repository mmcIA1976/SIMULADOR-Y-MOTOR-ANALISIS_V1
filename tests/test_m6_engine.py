from __future__ import annotations

import unittest

from m6_competing_risks import LOCKED_STATUS
from m6_engine import run_internal_probability_analysis


FIXED_TIME = "2026-07-28T12:00:00+00:00"


def m5_analysis(
    *,
    tp_distance=0.04,
    sl_distance=0.03,
    sigma=0.05,
    normalized_status="evaluated",
):
    return {
        "analysis_id": "m5-source",
        "analysis_trace_sha256": "m5-analysis-hash",
        "production_effect": "none",
        "traces": [
            {
                "rule_id": "M4-RULE-HORIZON-SAMPLING-001",
                "status": "evaluated",
                "outputs": {
                    "horizon_seconds": 3600,
                    "interval_seconds": 60,
                },
                "trace_sha256": "sampling-hash",
            },
            {
                "rule_id": "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002",
                "status": normalized_status,
                "outputs": (
                    {
                        "tp_log_distance": tp_distance,
                        "sl_log_distance": sl_distance,
                        "sigma_prev_horizon": sigma,
                    }
                    if normalized_status == "evaluated"
                    else {}
                ),
                "trace_sha256": "geometry-hash",
            },
        ],
    }


class M64ProbabilityEngineTests(unittest.TestCase):
    def test_engine_publishes_exactly_three_coherent_outcomes(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="m6-1",
            m5_analysis=m5_analysis(),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(result["status"], "evaluated_internal_only")
        self.assertEqual(
            set(result["probabilities"]),
            {
                "tp_first_within_horizon",
                "sl_first_within_horizon",
                "neither_barrier_before_expiry",
            },
        )
        self.assertAlmostEqual(sum(result["probabilities"].values()), 1.0)

    def test_missing_or_blocked_m5_geometry_blocks_all_probabilities(self) -> None:
        blocked = run_internal_probability_analysis(
            analysis_id="m6-blocked",
            m5_analysis=m5_analysis(normalized_status="blocked"),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(blocked["status"], "blocked")
        self.assertIsNone(blocked["probabilities"])
        self.assertEqual(
            blocked["block_code"],
            "required_m5_trace_not_evaluated",
        )

    def test_locked_coefficients_leave_baseline_unchanged(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="m6-lock",
            m5_analysis=m5_analysis(),
            coefficient_artifact={
                "id": "M6-LOCKED",
                "status": LOCKED_STATUS,
                "coefficients": None,
            },
            executed_at=FIXED_TIME,
        )
        baseline = result["trace"]["baseline"]
        self.assertAlmostEqual(
            result["probabilities"]["tp_first_within_horizon"],
            baseline["p_tp"],
            places=12,
        )
        self.assertEqual(
            result["trace"]["evidence"]["evidence_status"],
            "baseline_only_coefficients_locked",
        )

    def test_uncertainty_is_explicit_when_interval_is_absent(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="m6-point",
            m5_analysis=m5_analysis(),
            executed_at=FIXED_TIME,
        )
        uncertainty = result["trace"]["uncertainty"]
        self.assertEqual(
            uncertainty["status"],
            "not_quantified_no_sigma_interval",
        )
        self.assertIsNone(uncertainty["probability_envelope"])

    def test_supplied_sigma_scenarios_produce_labeled_envelope(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="m6-envelope",
            m5_analysis=m5_analysis(sigma=0.05),
            sigma_scenarios={"low": 0.04, "high": 0.06},
            executed_at=FIXED_TIME,
        )
        uncertainty = result["trace"]["uncertainty"]
        self.assertEqual(
            uncertainty["status"],
            "scenario_envelope_not_confidence_interval",
        )
        for bounds in uncertainty["probability_envelope"].values():
            self.assertLessEqual(bounds[0], bounds[1])

    def test_invalid_sigma_scenarios_block_instead_of_guessing(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="m6-bad-envelope",
            m5_analysis=m5_analysis(sigma=0.05),
            sigma_scenarios={"low": 0.06, "high": 0.07},
            executed_at=FIXED_TIME,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertIsNone(result["probabilities"])

    def test_trace_exposes_m5_hashes_formulas_assumptions_and_limits(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="m6-trace",
            m5_analysis=m5_analysis(),
            executed_at=FIXED_TIME,
        )
        trace = result["trace"]
        self.assertEqual(
            trace["source_rule_trace_hashes"],
            {
                "M4-RULE-HORIZON-SAMPLING-001": "sampling-hash",
                "M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002": "geometry-hash",
            },
        )
        self.assertEqual(
            trace["formulas"],
            [
                "M6-FORMULA-DB-TRANSITION-001",
                "M6-FORMULA-DB-TP-002",
                "M6-FORMULA-DB-SL-003",
                "M6-FORMULA-DB-EXPIRY-004",
                "M6-FORMULA-INTERVAL-HAZARD-005",
                "M6-FORMULA-EVIDENCE-OFFSET-006",
                "M6-FORMULA-CIF-007",
                "M6-FORMULA-SURVIVAL-008",
            ],
        )
        self.assertIn("zero drift", trace["assumptions"])
        self.assertIn(
            "predictive calibration remains unverified",
            trace["limitations"],
        )

    def test_result_is_reproducible_for_fixed_inputs_and_time(self) -> None:
        first = run_internal_probability_analysis(
            analysis_id="same",
            m5_analysis=m5_analysis(),
            executed_at=FIXED_TIME,
        )
        second = run_internal_probability_analysis(
            analysis_id="same",
            m5_analysis=m5_analysis(),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(first["result_sha256"], second["result_sha256"])

    def test_engine_never_claims_production_or_m7(self) -> None:
        result = run_internal_probability_analysis(
            analysis_id="scope",
            m5_analysis=m5_analysis(),
            executed_at=FIXED_TIME,
        )
        self.assertEqual(result["production_effect"], "none")
        self.assertEqual(result["trace"]["production_effect"], "none")
        self.assertFalse(result["m7_started"])


if __name__ == "__main__":
    unittest.main()
