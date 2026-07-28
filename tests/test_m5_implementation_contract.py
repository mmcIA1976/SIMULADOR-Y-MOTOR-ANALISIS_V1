from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m5_implementation_contract as m5  # noqa: E402


class M51ImplementationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = m5.build_contract()

    def test_owner_authorization_starts_only_m5(self) -> None:
        authorization = self.contract["owner_authorization"]
        self.assertTrue(authorization["authorized"])
        self.assertEqual(authorization["statement"], "bien inicia m5")
        self.assertFalse(authorization["production_authorized"])
        self.assertFalse(authorization["probability_integration_authorized"])
        self.assertFalse(authorization["learning_engine_authorized"])
        self.assertTrue(self.contract["scope"]["m5_started"])
        self.assertFalse(self.contract["scope"]["m5_closed"])
        self.assertFalse(self.contract["scope"]["m6_started"])

    def test_exact_m4_rule_universe_is_frozen(self) -> None:
        rules = self.contract["rules"]
        self.assertEqual(len(rules), 27)
        self.assertEqual(len({rule["rule_id"] for rule in rules}), 27)
        self.assertEqual(self.contract["scope"]["p0_core_rules"], 26)
        self.assertEqual(self.contract["scope"]["auxiliary_operators"], 1)
        self.assertTrue(
            all(
                rule["implementation_requirement"] == "required_in_m5"
                for rule in rules
            )
        )

    def test_every_source_formula_has_one_stable_m5_id(self) -> None:
        source = m5.read_json(m5.M4_RULES_PATH)
        source_formulas = {}
        for rule in source["rules"]:
            formulas = rule["exact_transformation_and_formula"]
            if not isinstance(formulas, list):
                formulas = [formulas]
            source_formulas[rule["id"]] = [str(item) for item in formulas]
        observed_ids = set()
        for rule in self.contract["rules"]:
            formulas = rule["formulas"]
            self.assertEqual(
                [item["expression"] for item in formulas],
                source_formulas[rule["rule_id"]],
            )
            for formula in formulas:
                self.assertNotIn(formula["id"], observed_ids)
                observed_ids.add(formula["id"])
                self.assertEqual(
                    formula["implementation_status"],
                    "pending_m5_code",
                )
        self.assertEqual(len(observed_ids), self.contract["scope"]["formulas"])

    def test_missing_pseudocode_is_not_invented(self) -> None:
        source = {
            rule["id"]: rule
            for rule in m5.read_json(m5.M4_RULES_PATH)["rules"]
        }
        for rule in self.contract["rules"]:
            original = source[rule["rule_id"]]
            if original.get("pseudocode"):
                self.assertEqual(rule["pseudocode"], original["pseudocode"])
                self.assertEqual(
                    rule["pseudocode_status"],
                    "source_preserved",
                )
            else:
                self.assertEqual(rule["pseudocode"], [])
                self.assertEqual(
                    rule["pseudocode_status"],
                    "not_declared_in_m4_use_formulas_only",
                )

    def test_all_108_invariants_map_to_unique_required_tests(self) -> None:
        registry = self.contract["m5_test_registry"]
        self.assertEqual(len(registry), 108)
        self.assertEqual(len({item["test_id"] for item in registry}), 108)
        self.assertEqual(
            len({item["m4_invariant_id"] for item in registry}),
            108,
        )
        self.assertTrue(
            all(item["status"] == "required_not_implemented" for item in registry)
        )
        nested = {
            item["m5_test_id"]
            for rule in self.contract["rules"]
            for item in rule["invariants"]
        }
        self.assertEqual(nested, {item["test_id"] for item in registry})

    def test_dag_order_respects_every_dependency(self) -> None:
        dag = self.contract["dag"]
        self.assertTrue(dag["acyclic"])
        order = {
            rule_id: index
            for index, rule_id in enumerate(dag["topological_order"])
        }
        self.assertEqual(len(order), 27)
        for edge in dag["edges"]:
            self.assertLess(order[edge["from"]], order[edge["to"]])
        for rule in self.contract["rules"]:
            for parent in rule["dependencies"]:
                self.assertLess(order[parent], order[rule["rule_id"]])

    def test_trace_contract_forbids_hidden_or_neutral_results(self) -> None:
        trace = self.contract["trace_contract"]
        self.assertEqual(
            set(trace["required_fields"]),
            set(m5.TRACE_REQUIRED_FIELDS),
        )
        self.assertEqual(
            set(trace["allowed_statuses"]),
            set(m5.TRACE_STATUSES),
        )
        rules = " ".join(trace["rules"])
        self.assertIn("forbids synthetic neutral outputs", rules)
        self.assertIn("production_effect is always none", rules)

    def test_market_scope_and_m6_dependency_are_explicit(self) -> None:
        by_id = {
            rule["rule_id"]: rule
            for rule in self.contract["rules"]
        }
        pending = by_id["M4-RULE-PENDING-ACTIVATION-001"]
        self.assertEqual(
            pending["runtime_activation"]["state"],
            "market_branch_only",
        )
        expected_value = by_id["M4-RULE-EXPECTED-VALUE-001"]
        self.assertEqual(
            expected_value["runtime_activation"]["state"],
            "blocked_until_m6_probabilities",
        )

    def test_no_rule_has_probability_weight_or_production_authority(self) -> None:
        for rule in self.contract["rules"]:
            self.assertFalse(rule["direct_probability_effect_authorized"])
            self.assertFalse(rule["numeric_weight_authorized"])
            self.assertFalse(rule["production_authorized"])
        boundary = self.contract["implementation_boundary"]
        self.assertEqual(boundary["production_output_effect"], "none")
        self.assertEqual(boundary["probability_output_effect"], "none")
        self.assertFalse(boundary["numeric_weights_allowed"])
        self.assertFalse(boundary["learning_feedback_allowed"])

    def test_operational_detours_remain_deferred(self) -> None:
        self.assertEqual(
            set(
                self.contract["implementation_boundary"][
                    "deferred_outside_scope"
                ]
            ),
            {
                "pending_order_automation",
                "analysis_revalidation_policy",
                "automatic_time_expiry_execution",
                "production_first_passage_correction",
            },
        )

    def test_frozen_sources_and_production_hashes_are_current(self) -> None:
        self.assertTrue(m5.PRODUCTION_ACTIVATION_PATH.is_file())
        for item in (
            self.contract["frozen_sources"]
            + self.contract["production_source_hashes_at_start"]
        ):
            path = ROOT / item["path"]
            self.assertTrue(path.is_file(), item["path"])
            self.assertEqual(len(item["sha256"]), 64)

    def test_next_subphase_is_not_self_authorized(self) -> None:
        next_subphase = self.contract["next_subphase"]
        self.assertEqual(next_subphase["id"], "M5.2")
        self.assertFalse(next_subphase["authorized"])

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m5_implementation_contract.py"),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_contract_matches_builder(self) -> None:
        written = json.loads(
            m5.DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(written, self.contract)


if __name__ == "__main__":
    unittest.main()
