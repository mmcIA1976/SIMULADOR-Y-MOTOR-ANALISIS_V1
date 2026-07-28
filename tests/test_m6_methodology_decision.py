from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m6_methodology_decision as m6  # noqa: E402


class M61MethodologyDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.decision = m6.build_decision()

    def test_owner_order_starts_m6_without_starting_m7(self) -> None:
        authorization = self.decision["owner_authorization"]
        self.assertEqual(authorization["statement"], "continuamos inicia m6")
        self.assertTrue(authorization["m6_started"])
        self.assertFalse(authorization["m6_closed"])
        self.assertFalse(authorization["production_authorized"])
        self.assertFalse(authorization["m7_started"])

    def test_outcome_contract_is_pretrade_and_collectively_exhaustive(self) -> None:
        problem = self.decision["problem_definition"]
        self.assertEqual(problem["analysis_timing"], "strictly_pre_trade")
        self.assertEqual(
            problem["outcomes"],
            [
                "tp_first_within_horizon",
                "sl_first_within_horizon",
                "neither_barrier_before_expiry",
            ],
        )
        self.assertEqual(
            problem["required_identity"],
            "P_TP(T)+P_SL(T)+P_EXPIRY(T)=1",
        )

    def test_first_passage_is_selected_as_baseline(self) -> None:
        methods = {
            item["id"]: item["decision"]
            for item in self.decision["candidate_methods"]
        }
        self.assertEqual(
            methods["brownian_double_barrier_first_passage"],
            "selected_as_baseline",
        )
        self.assertEqual(
            methods["independent_one_sided_barriers"],
            "rejected",
        )

    def test_competing_risks_is_selected_as_evidence_layer(self) -> None:
        methods = {
            item["id"]: item["decision"]
            for item in self.decision["candidate_methods"]
        }
        self.assertEqual(
            methods["discrete_time_competing_risks"],
            "selected_as_future_evidence_layer",
        )
        self.assertEqual(
            methods["endpoint_multinomial_only"],
            "rejected_as_primary",
        )
        evidence = self.decision["selected_architecture"][
            "layer_b_evidence"
        ]
        self.assertIn("P_EXPIRY", evidence["cumulative_incidence"])

    def test_all_27_m5_rules_have_exactly_one_probability_role(self) -> None:
        roles = self.decision["feature_roles"]
        self.assertEqual(len(roles), 27)
        self.assertEqual(len({item["rule_id"] for item in roles}), 27)
        self.assertEqual(
            sum(
                item["m6_role"] == "first_passage_baseline_input"
                for item in roles
            ),
            5,
        )
        self.assertEqual(
            sum(
                item["m6_role"] == "candidate_competing_risk_covariate"
                for item in roles
            ),
            12,
        )

    def test_no_manual_coefficient_or_weight_is_authorized(self) -> None:
        for item in self.decision["feature_roles"]:
            self.assertFalse(item["manual_weight_authorized"])
            self.assertIsNone(item["current_coefficient"])
        gate = self.decision["coefficient_gate"]
        self.assertFalse(gate["manual_coefficients_allowed"])
        self.assertEqual(
            gate["current_status"],
            "all_candidate_coefficients_locked",
        )
        self.assertEqual(
            self.decision["scope"]["probability_coefficients_defined"],
            0,
        )

    def test_execution_and_economics_do_not_modify_physical_probability(self) -> None:
        economic = {
            item["rule_id"]
            for item in self.decision["feature_roles"]
            if item["m6_role"] == "downstream_execution_or_economic_layer"
        }
        self.assertEqual(economic, m6.ECONOMIC_LAYER_RULES)
        self.assertTrue(
            all(
                item["probability_access"] == "none"
                for item in self.decision["feature_roles"]
                if item["rule_id"] in economic
            )
        )

    def test_sources_separate_supported_claims_from_limits(self) -> None:
        sources = self.decision["sources"]
        self.assertGreaterEqual(len(sources), 6)
        self.assertEqual(len({source["id"] for source in sources}), len(sources))
        for source in sources:
            self.assertTrue(source["url"].startswith("https://"))
            self.assertTrue(source["supported_claims"])
            self.assertTrue(source["not_supported"])

    def test_proper_scores_do_not_define_acceptance_thresholds(self) -> None:
        evaluation = self.decision["evaluation_contract"]
        self.assertEqual(
            set(evaluation["proper_scores"]),
            {"multiclass_brier", "multiclass_log_loss"},
        )
        self.assertFalse(evaluation["thresholds_defined"])
        self.assertIn("profit alone", evaluation["not_sufficient"])

    def test_m6_2_requires_owner_methodology_approval(self) -> None:
        gate = self.decision["review_gate"]
        self.assertTrue(gate["technical_recommendation_complete"])
        self.assertEqual(gate["owner_methodology_approval"], "pending")
        self.assertFalse(gate["m6_2_authorized"])

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m6_methodology_decision.py"),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_decision_matches_builder(self) -> None:
        written = json.loads(
            m6.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.decision)


if __name__ == "__main__":
    unittest.main()
