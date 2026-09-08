from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import audit_counterfactual_rule_evidence as audit


def metric_row(
    evaluation_id: int,
    episode: str,
    value: float,
    label: str,
) -> dict:
    return {
        "evaluation_id": evaluation_id,
        "episode_key": episode,
        "analysis_at": datetime(2026, 8, 1, tzinfo=timezone.utc)
        + timedelta(minutes=evaluation_id),
        "value": value,
        "outcome_label": label,
    }


def ablation_row(
    evaluation_id: int,
    episode: str,
    label: str,
    *,
    contract_key: str = "a" * 64,
) -> dict:
    return {
        "evaluation_id": evaluation_id,
        "episode_key": episode,
        "analysis_at": datetime(2026, 8, 1, tzinfo=timezone.utc)
        + timedelta(minutes=evaluation_id),
        "outcome_label": label,
        "rule_id": "M4-RULE-VOLATILITY-RANK-001",
        "ablation_source": "fitted_rule_ablation",
        "time_horizon": "intraday_short",
        "probability_contract": {
            "contract_key": contract_key,
            "source_engine_version": "engine-test",
        },
        "full_probabilities": {
            audit.CLASSES[0]: 0.7,
            audit.CLASSES[1]: 0.2,
            audit.CLASSES[2]: 0.1,
        },
        "without_probabilities": {
            audit.CLASSES[0]: 0.6,
            audit.CLASSES[1]: 0.3,
            audit.CLASSES[2]: 0.1,
        },
    }


class CounterfactualRuleEvidenceTests(unittest.TestCase):
    def test_soft_auc_supports_binary_and_fractional_episode_outcomes(self) -> None:
        self.assertEqual(audit.soft_auc([0.1, 0.9], [0.0, 1.0]), 1.0)
        result = audit.soft_auc([0.1, 0.9], [0.25, 0.75])
        self.assertGreater(result, 0.5)
        self.assertLess(result, 1.0)

    def test_overlapping_cases_become_one_episode_signal(self) -> None:
        rows = [
            metric_row(1, "episode-a", 0.2, audit.CLASSES[0]),
            metric_row(2, "episode-a", 0.8, audit.CLASSES[1]),
            metric_row(3, "episode-b", 1.0, audit.CLASSES[0]),
        ]
        episodes = audit._episode_signal_rows(rows, "directional")
        self.assertEqual(len(episodes), 2)
        first = next(row for row in episodes if row["episode_key"] == "episode-a")
        self.assertAlmostEqual(first["signal"], 0.5)
        self.assertAlmostEqual(first["positive_share"], 0.5)

    def test_inference_stays_blocked_below_independent_minimum(self) -> None:
        rows = [
            metric_row(
                index,
                f"episode-{index}",
                float(index),
                audit.CLASSES[0] if index % 2 else audit.CLASSES[1],
            )
            for index in range(1, 50)
        ]
        result = audit.evaluate_episode_association(
            rows,
            target="directional",
            seed=1,
        )
        self.assertEqual(result["effective_episodes"], 49)
        self.assertEqual(
            result["evidence_status"],
            "insufficient_effective_independent_evidence",
        )
        self.assertIsNone(result["permutation_p"])

    def test_inference_runs_once_all_preregistered_minima_are_met(self) -> None:
        rows = [
            metric_row(
                index,
                f"episode-{index}",
                float(index),
                audit.CLASSES[0] if index > 25 else audit.CLASSES[1],
            )
            for index in range(1, 51)
        ]
        with patch.object(audit, "BOOTSTRAP_SAMPLES", 40), patch.object(
            audit, "PERMUTATION_SAMPLES", 40
        ):
            result = audit.evaluate_episode_association(
                rows,
                target="directional",
                seed=1,
            )
        self.assertEqual(result["effective_episodes"], 50)
        self.assertEqual(result["episode_soft_auc"], 1.0)
        self.assertEqual(result["evidence_status"], "quantified_pending_fdr")
        self.assertIsNotNone(result["bootstrap_95ci"])
        self.assertIsNotNone(result["permutation_p"])

    def test_ablation_summary_does_not_mix_probability_contracts(self) -> None:
        rows = [
            ablation_row(1, "episode-a", audit.CLASSES[0]),
            ablation_row(2, "episode-b", audit.CLASSES[1]),
            ablation_row(
                3,
                "episode-c",
                audit.CLASSES[0],
                contract_key="b" * 64,
            ),
        ]
        summary = audit.summarize_ablations(rows)
        self.assertEqual(len(summary), 2)
        self.assertEqual(
            sorted(item["effective_episodes"] for item in summary),
            [1, 2],
        )
        self.assertTrue(
            all(
                item["governance_status"]
                == "insufficient_effective_independent_evidence"
                for item in summary
            )
        )

    def test_nested_observational_trace_is_found_without_fake_effect(self) -> None:
        trace = {
            "traces": [
                {
                    "status": "evaluated_shadow",
                    "traces": [
                        {
                            "rule_id": "LIB-CAND-RSI-WILDER-001",
                            "status": "evaluated_shadow",
                            "rule_version": "0.1",
                            "runtime_version": "technical-v0.1",
                            "formula_ids": ["formula-rsi"],
                            "probability_effect": "none_shadow_observation",
                            "outputs": {
                                "side_adjusted_centered_rsi": 0.4
                            },
                        }
                    ],
                }
            ]
        }
        found = list(audit._iter_rule_traces(trace))
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["rule_id"], "LIB-CAND-RSI-WILDER-001")
        self.assertEqual(
            found[0]["probability_effect"],
            "none_shadow_observation",
        )

    def test_shadow_bundle_is_compared_without_individual_attribution(self) -> None:
        rows = [
            {
                **ablation_row(1, "episode-a", audit.CLASSES[0]),
                "shadow_contract": {
                    "contract_key": "c" * 64,
                    "active_rule_ids": ["rule-a", "rule-b"],
                },
                "champion_probabilities": {
                    audit.CLASSES[0]: 0.6,
                    audit.CLASSES[1]: 0.3,
                    audit.CLASSES[2]: 0.1,
                },
                "challenger_probabilities": {
                    audit.CLASSES[0]: 0.7,
                    audit.CLASSES[1]: 0.2,
                    audit.CLASSES[2]: 0.1,
                },
            }
        ]
        summary = audit.summarize_shadow_bundles(rows)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["effective_episodes"], 1)
        self.assertGreater(
            summary[0]["delta_challenger_vs_champion"][
                "log_loss_improvement"
            ],
            0,
        )
        self.assertNotIn("rule_id", summary[0])


if __name__ == "__main__":
    unittest.main()
