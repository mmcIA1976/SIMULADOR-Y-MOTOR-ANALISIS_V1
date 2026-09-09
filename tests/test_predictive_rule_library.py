from __future__ import annotations

import unittest

from empirical_temporal_engine import load_production_artifact
from predictive_rule_library import (
    EXPECTED_HORIZONS,
    load_rule_library,
    rule_metadata,
    rule_registry,
)


class PredictiveRuleLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        load_rule_library.cache_clear()
        cls.catalog = load_rule_library()
        cls.registry = rule_registry()

    def test_catalog_has_unique_complete_rule_contracts(self) -> None:
        self.assertEqual(
            self.catalog["summary"]["rules"],
            len(self.registry),
        )
        self.assertGreaterEqual(len(self.registry), 30)

    def test_all_current_predictive_rules_are_migrated(self) -> None:
        active = {
            rule_id
            for rule_id, rule in self.registry.items()
            if rule["lifecycle_status"] == "active_provisional"
        }
        governed = set(
            self.catalog["governance"]["current_active_predictive_rule_ids"]
        )
        artifact_rule_ids = {
            parts[1]
            for names in load_production_artifact()["feature_names"].values()
            for name in names
            if len(parts := name.split("::", 2)) == 3
        }
        self.assertEqual(active, governed)
        self.assertEqual(active, artifact_rule_ids)
        self.assertEqual(
            active,
            {
                "M4-RULE-PATH-STRUCTURE-001",
                "M4-RULE-MTF-HIERARCHY-001",
                "M4-RULE-VOLATILITY-RANK-001",
                "LIB-CAND-COMPRESSION-001",
            },
        )

    def test_every_rule_uses_the_three_owner_approved_horizons(self) -> None:
        for rule in self.registry.values():
            self.assertEqual(
                set(rule["applicable_horizons"]),
                EXPECTED_HORIZONS,
            )

    def test_no_observational_candidate_has_an_active_probability_formula(self) -> None:
        for rule in self.registry.values():
            if rule["lifecycle_status"] in {
                "proposed",
                "data_blocked",
                "data_limited",
                "implemented_shadow",
                "historical_evidence_available_data_limited",
            }:
                self.assertTrue(
                    rule["probability_integration_formula"].startswith("none")
                )
                self.assertIn(
                    rule["expected_probability_effect"]["mode"],
                    {
                        "hypothesis_not_active",
                        "observation_only_no_production_effect",
                    },
                )

    def test_known_interactions_declare_parents(self) -> None:
        for rule_id in (
            "M4-RULE-CONTINUOUS-REGIME-001",
            "M4-RULE-PRICE-OI-STATE-001",
            "LIB-CAND-ABSORPTION-001",
            "LIB-CAND-PULLBACK-CONTEXT-001",
        ):
            self.assertTrue(
                rule_metadata(rule_id)["interactions"]["parent_rule_ids"]
            )

    def test_current_engine_declares_analog_features_without_fake_weights(self) -> None:
        path = rule_metadata("M4-RULE-PATH-STRUCTURE-001")
        self.assertEqual(
            path["parameters"][0]["origin"],
            "motor_v0_9_empirical_analog_frozen_artifact",
        )
        self.assertEqual(
            path["parameters"][0]["status"],
            "active_frozen_production",
        )
        self.assertEqual(
            path["expected_probability_effect"]["mode"],
            "empirical_analog_distance_input",
        )

    def test_learning_cannot_modify_production(self) -> None:
        for rule in self.registry.values():
            self.assertIs(
                rule["learning_contract"]["may_self_modify_production"],
                False,
            )

    def test_heatmap_historical_evidence_is_preserved(self) -> None:
        heatmap = rule_metadata("LIB-CAND-LIQUIDATION-ZONE-001")
        evidence = heatmap["historical_evidence"]
        self.assertEqual(evidence["recommendations"], 107)
        self.assertEqual(evidence["observations_available"], 104)
        self.assertEqual(
            evidence["linked_closed_resolved_operations"],
            24,
        )
        self.assertIn(
            "do_not_reuse_legacy",
            evidence["reuse_policy"],
        )

    def test_observational_rules_match_the_current_single_engine(self) -> None:
        expected = {
            "LIB-CAND-EMA-TREND-001",
            "LIB-CAND-RSI-WILDER-001",
            "LIB-CAND-ATR-EXTENSION-001",
            "LIB-CAND-RELATIVE-VOLUME-001",
            "LIB-CAND-CVD-SLOPE-001",
            "LIB-CAND-ORDERBOOK-IMBALANCE-001",
            "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001",
            "LIB-CAND-FIBONACCI-DISTANCE-001",
            "LIB-CAND-FUNDING-PERCENTILE-001",
            "LIB-CAND-CROWDING-PERCENTILE-001",
            "LIB-CAND-BREADTH-001",
            "LIB-CAND-SENTIMENT-PERCENTILE-001",
            "LIB-CAND-LIQUIDATION-ZONE-001",
            "LIB-CAND-ABSORPTION-001",
            "LIB-CAND-PULLBACK-CONTEXT-001",
            "M4-RULE-PRIOR-EXTREMA-001",
            "M4-RULE-CONTINUOUS-REGIME-001",
            "M4-RULE-AGGRESSOR-IMBALANCE-001",
            "M4-RULE-OPEN-INTEREST-CHANGE-001",
            "M4-RULE-PRICE-OI-STATE-001",
            "M4-RULE-SPOT-FUTURES-BASIS-001",
            "M4-RULE-MARK-INDEX-PREMIUM-001",
            "M4-RULE-FUNDING-STATE-001",
        }
        actual = {
            rule_id
            for rule_id, rule in self.registry.items()
            if rule["lifecycle_status"] == "implemented_shadow"
        }
        self.assertEqual(actual, expected)
        for rule_id in expected:
            self.assertNotEqual(
                self.registry[rule_id]["inputs"][0]["provider"],
                "must_be_approved_before_implementation",
            )

    def test_two_data_quality_gates_are_active_but_not_predictive(self) -> None:
        expected = {
            "LIB-CAND-DATA-FRESHNESS-001",
            "LIB-CAND-CANDLE-INTEGRITY-001",
        }
        actual = {
            rule_id
            for rule_id, rule in self.registry.items()
            if rule["lifecycle_status"] == "active_blocking"
        }
        self.assertEqual(actual, expected)
        self.assertEqual(
            self.catalog["summary"]["active_data_quality_gates"],
            2,
        )
        for rule_id in expected:
            rule = self.registry[rule_id]
            self.assertEqual(
                rule["expected_probability_effect"]["mode"],
                "blocking_gate_not_predictive",
            )
            self.assertFalse(
                rule["trace_contract"]["requires_probability_ablation"]
            )

    def test_execution_candidates_are_merged_into_canonical_rules(self) -> None:
        expected = {
            "M4-RULE-QUOTED-SPREAD-001",
            "M4-RULE-DEPTH-SWEEP-001",
        }
        actual = {
            rule_id
            for rule_id, rule in self.registry.items()
            if rule["lifecycle_status"] == "active_economic"
        }
        self.assertEqual(actual, expected)
        self.assertEqual(
            set(
                self.catalog["governance"][
                    "active_economic_rule_ids"
                ]
            ),
            expected,
        )
        self.assertEqual(
            self.catalog["summary"]["active_economic"],
            2,
        )
        for obsolete_id in (
            "LIB-CAND-SPREAD-EXECUTION-001",
            "LIB-CAND-DEPTH-COVERAGE-001",
        ):
            self.assertNotIn(obsolete_id, self.registry)
        for rule_id in expected:
            rule = self.registry[rule_id]
            self.assertEqual(
                rule["expected_probability_effect"]["mode"],
                "execution_economic_only",
            )
            self.assertFalse(
                rule["trace_contract"]["requires_probability_ablation"]
            )

    def test_legacy_fibonacci_is_preserved_without_reusing_scores(self) -> None:
        fibonacci = rule_metadata(
            "LIB-CAND-FIBONACCI-DISTANCE-001"
        )
        evidence = fibonacci["historical_evidence"]
        self.assertEqual(evidence["legacy_closed_operations"], 154)
        self.assertIn(
            "do_not_reuse_legacy_scores",
            evidence["reuse_policy"],
        )

    def test_legacy_market_context_is_preserved_without_old_thresholds(
        self,
    ) -> None:
        breadth = rule_metadata("LIB-CAND-BREADTH-001")
        sentiment = rule_metadata(
            "LIB-CAND-SENTIMENT-PERCENTILE-001"
        )
        self.assertEqual(
            breadth["historical_evidence"][
                "legacy_observations_available"
            ],
            718,
        )
        self.assertEqual(
            sentiment["historical_evidence"][
                "legacy_observations_available"
            ],
            874,
        )


if __name__ == "__main__":
    unittest.main()
