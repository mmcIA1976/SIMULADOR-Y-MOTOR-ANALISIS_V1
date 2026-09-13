import unittest

import audit_empirical_active_rules as audit
from empirical_temporal_engine import CONDITIONAL_CLASSES, _stage_label


class EmpiricalActiveRuleAttributionTests(unittest.TestCase):
    def test_variants_cover_individual_removal_and_pairs(self):
        variants = audit.component_variants(include_pairs=True)
        components = tuple(audit.ACTIVE_COMPONENTS)

        self.assertEqual(variants["full"], components)
        self.assertEqual(
            len([name for name in variants if name.startswith("only::")]),
            len(components),
        )
        self.assertEqual(
            len([name for name in variants if name.startswith("without::")]),
            len(components),
        )
        self.assertEqual(
            len([name for name in variants if name.startswith("pair::")]),
            10,
        )
        self.assertEqual(len(variants), 31)
        self.assertEqual(
            set(variants.values()),
            {
                selected
                for size in range(1, len(components) + 1)
                for selected in __import__("itertools").combinations(components, size)
            },
        )

    def test_features_are_partitioned_once_per_horizon(self):
        for horizon in audit.STAGE_ORDER:
            names = audit.expanded_feature_names(horizon)
            indices = audit.expanded_component_indices(horizon)
            flattened = [index for values in indices.values() for index in values]

            self.assertEqual(sorted(flattened), list(range(len(names))))
            self.assertEqual(len(flattened), len(set(flattened)))

    def test_atomic_features_match_every_production_distance_coordinate(self):
        for horizon in audit.STAGE_ORDER:
            names = audit.expanded_feature_names(horizon)
            indices = audit.expanded_atomic_indices(horizon)

            self.assertEqual(set(indices), set(names))
            self.assertEqual(sorted(indices.values()), list(range(len(names))))
            self.assertEqual(
                len(names),
                len(audit.ATOMIC_FEATURES)
                * (audit.STAGE_ORDER.index(horizon) + 1),
            )

    def test_direct_quantile_boundaries_are_deterministic_and_deduplicated(self):
        boundaries = audit._quantile_boundaries([0.0, 0.0, 0.0, 1.0, 1.0])

        self.assertEqual(boundaries, audit._quantile_boundaries([1.0, 0.0, 1.0, 0.0, 0.0]))
        self.assertEqual(len(boundaries), len(set(boundaries)))
        self.assertEqual(boundaries, sorted(boundaries))

    def test_direct_probability_smoothing_is_normalized(self):
        probabilities = audit._smoothed_probabilities([3, 1, 0])

        self.assertAlmostEqual(sum(probabilities), 1.0)
        self.assertGreater(probabilities[2], 0.0)

    def test_replication_requires_both_metrics_on_both_tests(self):
        positive = {
            "independent_units": 100,
            "log_loss": 0.01,
            "brier": 0.005,
            "log_loss_ci95": [-0.01, 0.03],
            "brier_ci95": [-0.005, 0.015],
        }
        negative = {
            "independent_units": 100,
            "log_loss": -0.01,
            "brier": -0.005,
            "log_loss_ci95": [-0.03, 0.01],
            "brier_ci95": [-0.015, 0.005],
        }

        self.assertEqual(
            audit.classify_replication(positive, positive),
            "helpful_consistent_but_uncertain",
        )
        self.assertEqual(
            audit.classify_replication(negative, negative),
            "harmful_consistent_but_uncertain",
        )
        self.assertEqual(
            audit.classify_replication(positive, negative),
            "mixed_or_unstable",
        )

    def test_replication_rejects_small_sample(self):
        small = {
            "independent_units": 12,
            "log_loss": 0.01,
            "brier": 0.005,
            "log_loss_ci95": [-0.01, 0.03],
            "brier_ci95": [-0.005, 0.015],
        }
        self.assertEqual(
            audit.classify_replication(small, small),
            "insufficient_evidence",
        )

    def test_replication_requires_confidence_interval_for_confirmation(self):
        confirmed = {
            "independent_units": 100,
            "log_loss": 0.01,
            "brier": 0.005,
            "log_loss_ci95": [0.001, 0.019],
            "brier_ci95": [0.001, 0.009],
        }
        self.assertEqual(
            audit.classify_replication(confirmed, confirmed),
            "helpful_confirmed",
        )

    def test_vectorized_labels_match_production_contract(self):
        try:
            np = audit._load_numpy()
        except RuntimeError:
            self.skipTest("numpy is only required by the offline audit runtime")
        record = {
            "up_frontier": [[0.02, 1], [0.05, 12], [0.1, 80], [0.2, 400]],
            "down_frontier": [[0.01, 2], [0.05, 24], [0.1, 160], [0.2, 500]],
        }
        prepared = {
            "frontiers": [
                (
                    tuple(item[0] for item in record["up_frontier"]),
                    tuple(item[1] for item in record["up_frontier"]),
                    tuple(item[0] for item in record["down_frontier"]),
                    tuple(item[1] for item in record["down_frontier"]),
                )
            ]
        }
        matrices = audit._conditional_label_matrices(np, prepared, 0.05)

        for horizon in audit.STAGE_ORDER:
            start_step, end_step = audit.STAGE_BOUNDS[horizon]
            for geometry_index, (tp_multiple, sl_multiple) in enumerate(
                audit.GEOMETRY_GRID
            ):
                expected = _stage_label(
                    record,
                    0,
                    tp_distance=tp_multiple * 0.05,
                    sl_distance=sl_multiple * 0.05,
                    start_step=start_step,
                    end_step=end_step,
                )
                expected_code = audit.LABEL_CODE.get(expected, -1)
                self.assertEqual(
                    int(matrices[horizon][geometry_index, 0]),
                    expected_code,
                )

    def test_shapley_additivity_validator(self):
        direction_metrics = {
            "geometry": {h: {d: {"log_loss": 1.0, "brier": 0.5} for d in audit.DIRECTIONS.values()} for h in audit.STAGE_ORDER},
            "full": {h: {d: {"log_loss": 0.9, "brier": 0.45} for d in audit.DIRECTIONS.values()} for h in audit.STAGE_ORDER},
        }
        shapley = {
            component: {
                h: {
                    d: {
                        "log_loss": 0.1 / len(audit.ACTIVE_COMPONENTS),
                        "brier": 0.05 / len(audit.ACTIVE_COMPONENTS),
                    }
                    for d in audit.DIRECTIONS.values()
                }
                for h in audit.STAGE_ORDER
            }
            for component in audit.ACTIVE_COMPONENTS
        }
        partitions = {
            "rule_test": {
                "summaries": direction_metrics,
                "shapley_attribution": shapley,
            }
        }
        self.assertLess(audit.validate_shapley_additivity(partitions), 1e-12)


if __name__ == "__main__":
    unittest.main()
