import unittest

from evaluate_contextual_lift_candidate import (
    _candidate_subsets,
    _component_indices,
    _replicated_gate,
    blend_probabilities,
    candidate_stage_probabilities,
)


class ContextualLiftCandidateTests(unittest.TestCase):
    def test_zero_context_weight_is_exact_baseline(self):
        baseline = (0.45, 0.35, 0.20)
        context = (0.75, 0.15, 0.10)
        self.assertEqual(blend_probabilities(baseline, context, 0.0), baseline)

    def test_full_context_weight_is_exact_context(self):
        baseline = (0.45, 0.35, 0.20)
        context = (0.75, 0.15, 0.10)
        self.assertEqual(blend_probabilities(baseline, context, 1.0), context)

    def test_blend_preserves_probability_mass(self):
        result = blend_probabilities((0.5, 0.4, 0.1), (0.2, 0.7, 0.1), 0.35)
        self.assertAlmostEqual(sum(result), 1.0)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in result))

    def test_v0_10_blend_base_has_exact_no_change_point(self):
        exposure = (0.55, 0.25, 0.20)
        production = (0.40, 0.45, 0.15)
        context = (0.70, 0.20, 0.10)
        self.assertEqual(
            candidate_stage_probabilities(
                exposure=exposure,
                production=production,
                context=context,
                context_weight=0.0,
                blend_base="v0_10",
            ),
            production,
        )

    def test_rule_components_do_not_gain_weight_from_coordinate_count(self):
        names = [
            "intraday_short::log_context_sigma",
            "intraday_short::M4-RULE-PATH-STRUCTURE-001::directional_path_efficiency_h",
            "intraday_short::M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_2h",
            "intraday_short::M4-RULE-MTF-HIERARCHY-001::directional_path_efficiency_4h",
        ]
        exposure, components = _component_indices(names)
        self.assertEqual(exposure, [0])
        self.assertEqual(len(components["M4-RULE-PATH-STRUCTURE-001"]), 1)
        self.assertEqual(len(components["M4-RULE-MTF-HIERARCHY-001"]), 2)

    def test_all_component_subsets_are_predeclared(self):
        subsets = _candidate_subsets(("a", "b", "c"))
        self.assertEqual(len(subsets), 8)
        self.assertIn((), subsets)
        self.assertIn(("a", "b", "c"), subsets)

    def test_release_gate_rejects_one_failing_horizon_despite_positive_macro(self):
        comparisons = {"candidate_vs_v0_10": {}, "candidate_vs_exposure": {}}
        for reference in ("v0_10", "exposure"):
            for horizon in ("intraday_short", "intraday_wide", "short_swing"):
                value = -0.001 if horizon == "short_swing" else 0.01
                comparisons[f"candidate_vs_{reference}"][horizon] = {
                    direction: {
                        "log_loss_improvement": value,
                        "brier_improvement": value,
                    }
                    for direction in ("long", "short")
                }
        evaluation = {
            "partition": "test",
            "comparisons": comparisons,
            "macro": {
                "candidate_vs_v0_10": {
                    "log_loss_improvement": 0.006,
                    "brier_improvement": 0.006,
                },
                "candidate_vs_exposure": {
                    "log_loss_improvement": 0.006,
                    "brier_improvement": 0.006,
                },
            },
        }
        result = _replicated_gate(evaluation)
        self.assertFalse(result["passed"])
        self.assertFalse(
            result["requirements"][
                "beats_v0_10_log_loss_in_every_horizon_and_partition"
            ]
        )


if __name__ == "__main__":
    unittest.main()
