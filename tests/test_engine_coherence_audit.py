import json
import unittest
from pathlib import Path

import audit_engine_coherence


ROOT = Path(__file__).resolve().parents[1]


class EngineCoherenceAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = audit_engine_coherence.build_audit()
        cls.by_id = {item["id"]: item for item in cls.audit["findings"]}

    def test_invariant_registry_covers_required_e1_3_categories(self):
        categories = {item["category"] for item in audit_engine_coherence.INVARIANTS}

        self.assertTrue(
            {
                "probability_semantics",
                "monotonicity",
                "continuity",
                "horizon",
                "costs",
                "data_quality",
                "double_counting",
                "separation",
                "traceability",
                "cross_pair_validity",
            }.issubset(categories)
        )

    def test_target_distance_insensitivity_is_reproduced(self):
        outputs = self.by_id["E1.3-F02"]["reproduction"]["observed_outputs"]

        self.assertEqual(outputs["near_reward_distance_pct"], 0.5)
        self.assertEqual(outputs["far_reward_distance_pct"], 2.5)
        self.assertEqual(outputs["delta_probability"], 0.0)

    def test_stop_distance_insensitivity_is_reproduced(self):
        outputs = self.by_id["E1.3-F03"]["reproduction"]["observed_outputs"]

        self.assertEqual(outputs["near_risk_distance_pct"], 1.0)
        self.assertEqual(outputs["far_risk_distance_pct"], 2.5)
        self.assertEqual(outputs["delta_probability"], 0.0)

    def test_price_entry_discontinuity_is_exactly_five_points(self):
        outputs = self.by_id["E1.3-F04"]["reproduction"]["observed_outputs"]

        self.assertEqual(outputs["bias_a"], -0.02)
        self.assertEqual(outputs["bias_b"], 0.03)
        self.assertEqual(outputs["probability_delta"], 0.05)

    def test_probability_floor_can_break_normalization(self):
        outputs = self.by_id["E1.3-F05"]["reproduction"]["observed_outputs"]

        self.assertEqual(outputs["raw_sl_residual"], 0.04)
        self.assertEqual(outputs["floored_sl_probability"], 0.05)
        self.assertEqual(outputs["sum_after_floor"], 1.01)

    def test_funding_sign_is_lost(self):
        outputs = self.by_id["E1.3-F07"]["reproduction"]["observed_outputs"]

        self.assertEqual(
            outputs["positive_estimated_cost_usdt"],
            outputs["negative_estimated_cost_usdt"],
        )
        self.assertEqual(outputs["positive_ev_usdt"], outputs["negative_ev_usdt"])

    def test_unavailable_snapshot_still_returns_decision(self):
        outputs = self.by_id["E1.3-F10"]["reproduction"]["observed_outputs"]

        self.assertIsInstance(outputs["tp_probability"], float)
        self.assertIsInstance(outputs["sl_probability"], float)
        self.assertTrue(outputs["training_decision"])

    def test_every_incoherence_has_required_audit_fields(self):
        invariant_ids = {item["id"] for item in audit_engine_coherence.INVARIANTS}

        for finding in self.audit["findings"]:
            self.assertIn(finding["invariant_id"], invariant_ids)
            self.assertIn(finding["severity"], {"critical", "high", "medium", "low"})
            self.assertIn(finding["status"], {"failed", "unverified"})
            self.assertTrue(finding["reproduction"]["observed_outputs"])
            self.assertTrue(finding["candidate_correction"])
            self.assertTrue(finding["code_refs"])
            self.assertFalse(finding["production_changed"])

    def test_audit_is_deterministic(self):
        second = audit_engine_coherence.build_audit()

        self.assertEqual(self.audit, second)
        self.assertFalse(self.audit["production_modified"])

    def test_committed_artifacts_match_generator(self):
        invariants = json.loads(
            (ROOT / "auditorias_motor" / "invariantes_coherencia_motor_v0_1.json").read_text(
                encoding="utf-8"
            )
        )
        findings = json.loads(
            (ROOT / "auditorias_motor" / "coherencia_motor_v0_1.json").read_text(
                encoding="utf-8"
            )
        )
        report = (ROOT / "auditorias_motor" / "informe_coherencia_motor.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(invariants, audit_engine_coherence.build_invariant_document())
        self.assertEqual(findings, self.audit)
        self.assertEqual(report, audit_engine_coherence.render_report(self.audit))


if __name__ == "__main__":
    unittest.main()
