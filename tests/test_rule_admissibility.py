import json
import unittest
from pathlib import Path

import audit_rule_admissibility as admissibility
from audit_historical_rule_impact import DIRECT_ABLATION_UNITS


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "auditorias_motor"


class RuleAdmissibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.matrix = admissibility.build_matrix()

    def test_all_e1_4_direct_units_are_registered(self):
        direct = {
            item["id"].removeprefix("SCORE-").lower()
            for item in self.matrix["rules"]
            if item["id"].startswith("SCORE-")
        }

        self.assertEqual(direct, set(DIRECT_ABLATION_UNITS))

    def test_all_calibration_flags_are_registered(self):
        declared = {item[0] for item in admissibility.CALIBRATION_DEFINITIONS}

        self.assertEqual(declared, admissibility.extract_calibration_flags())

    def test_all_predictive_and_decision_functions_are_linked(self):
        linked = {
            ref
            for item in self.matrix["rules"]
            for ref in item["implementation_refs"]
        }

        self.assertTrue(admissibility.predictive_function_ids().issubset(linked))
        self.assertFalse(
            self.matrix["coverage"]["predictive_functions_missing"]
        )

    def test_no_current_predictive_rule_is_misrepresented_as_validated(self):
        summary = self.matrix["summary"]

        self.assertEqual(summary["temporally_validated_predictive_rules"], 0)
        self.assertEqual(summary["production_authorized_predictive_rules"], 0)

    def test_challenger_plan_geometry_is_explicit_but_not_predictively_claimed(self):
        by_id = {item["id"]: item for item in self.matrix["rules"]}
        for rule_id in (
            "PLAN-TP-LOG-DISTANCE",
            "PLAN-SL-LOG-DISTANCE",
            "PLAN-LOG-HORIZON-SECONDS",
        ):
            item = by_id[rule_id]
            self.assertEqual(
                item["challenger_admission"],
                "calculation_allowed_nonpredictive",
            )
            self.assertEqual(item["predictive_validation"], "not_validated_as_predictor")
        for item in self.matrix["rules"]:
            if item["kind"] in {
                "active_predictive_adjustment",
                "internal_empirical_gate",
            }:
                self.assertTrue(
                    item["challenger_admission"].startswith("blocked_")
                )

    def test_data_sources_do_not_claim_predictive_support(self):
        data_rules = [
            item for item in self.matrix["rules"] if item["kind"] == "data_definition"
        ]

        self.assertTrue(data_rules)
        for item in data_rules:
            self.assertEqual(
                item["challenger_admission"],
                "data_allowed_not_predictive",
            )
            self.assertIn("no ", item["transfer_limit"].lower())

    def test_every_rule_has_all_mandatory_admission_fields(self):
        required = {
            "id",
            "formula",
            "implementation_refs",
            "source_ids",
            "published_support",
            "transfer_limit",
            "exact_formula_support",
            "implementation_fidelity",
            "predictive_validation",
            "coherence",
            "traceability",
            "reliability_tier",
            "current_decision",
            "challenger_admission",
            "blockers",
            "gates",
            "horizons",
            "pair_scope",
        }

        for item in self.matrix["rules"]:
            self.assertTrue(required.issubset(item))
            self.assertEqual(
                set(item["gates"]),
                set(admissibility.PREDICTIVE_GATE_NAMES),
            )

    def test_generated_artifacts_match_the_generator(self):
        stored_matrix = json.loads(
            (AUDIT_DIR / "matriz_admisibilidad_reglas_v0_1.json").read_text(
                encoding="utf-8"
            )
        )
        stored_report = (AUDIT_DIR / "informe_admisibilidad_reglas.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(stored_matrix, self.matrix)
        self.assertEqual(stored_report, admissibility.render_report(self.matrix))

    def test_matrix_generation_is_deterministic(self):
        self.assertEqual(self.matrix, admissibility.build_matrix())


if __name__ == "__main__":
    unittest.main()
