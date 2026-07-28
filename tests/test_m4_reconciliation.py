from __future__ import annotations

import json
import unittest

from build_m4_reconciliation import (
    DEFAULT_OUTPUT_PATH,
    P0_BLOCKS,
    RECONCILIATION,
    RULE_ADMISSION_FIELDS,
    build_reconciliation,
)


class M4ReconciliationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build_reconciliation()
        cls.rows = {
            item["current_rule_id"]: item
            for item in cls.payload["rows"]
        }

    def test_all_30_m1_candidates_are_reconciled_once(self):
        summary = self.payload["summary"]
        self.assertEqual(summary["m1_candidates"], 30)
        self.assertEqual(summary["reconciled"], 30)
        self.assertEqual(len(self.rows), 30)
        self.assertEqual(set(self.rows), set(RECONCILIATION))

    def test_scope_preserves_all_pairs_horizons_and_p0_blocks(self):
        universe = self.payload["universe"]
        self.assertEqual(
            set(universe["symbols"]),
            {
                "BTCUSDT",
                "ETHUSDT",
                "SOLUSDT",
                "BNBUSDT",
                "XRPUSDT",
                "INJUSDT",
            },
        )
        self.assertEqual(
            set(universe["horizons"]),
            {"intraday_short", "intraday_wide", "short_swing"},
        )
        self.assertEqual(
            {item["id"] for item in self.payload["p0_blocks"]},
            set(P0_BLOCKS),
        )

    def test_no_legacy_point_weight_or_probability_is_authorized(self):
        for row in self.rows.values():
            self.assertFalse(row["current_points_or_weight_authorized"])
            self.assertFalse(row["direct_probability_effect_authorized"])
            self.assertFalse(row["production_modified"])
        self.assertEqual(
            self.payload["summary"][
                "rows_with_direct_probability_authorized"
            ],
            0,
        )

    def test_admission_contract_is_complete_and_layered(self):
        contract = self.payload["admission_contract"]
        self.assertEqual(
            set(contract["mandatory_fields"]),
            set(RULE_ADMISSION_FIELDS),
        )
        self.assertEqual(
            [item["level"] for item in contract["source_levels"]],
            [
                "definition",
                "technical_foundation",
                "external_predictive_evidence",
                "project_hypothesis",
            ],
        )
        self.assertGreaterEqual(len(contract["hard_gates"]), 9)

    def test_family_registry_is_seed_only(self):
        families = self.payload["target_family_seed_registry"]
        self.assertEqual(len(families), 17)
        for family in families:
            self.assertEqual(family["status"], "seed_only_not_a_rule")
            self.assertFalse(family["formula_defined"])
            self.assertFalse(family["predictive_effect_defined"])

    def test_fibonacci_cannot_enter_p0_through_probability_block(self):
        row = self.rows["SCORE-FIBONACCI_PROBABILITY_ADJUSTMENT"]
        self.assertEqual(row["disposition"], "defer_parent_block_to_m10")
        self.assertEqual(row["parent_block_gate"], "blocked_parent_is_p1")
        self.assertEqual(row["target_rule_families"], [])

    def test_old_learning_adjustments_are_retired(self):
        for rule_id in (
            "SCORE-RISK_CALIBRATION_TP_ADJUSTMENT",
            "SCORE-RISK_CALIBRATION_RANGE_ADJUSTMENT",
        ):
            self.assertEqual(
                self.rows[rule_id]["disposition"],
                "retire_learning_derived_adjustment",
            )
            self.assertEqual(
                self.rows[rule_id]["target_rule_families"],
                [],
            )

    def test_duplicate_evidence_is_merged_not_counted_twice(self):
        self.assertEqual(
            self.rows["SCORE-CVD_BIAS"]["target_rule_families"],
            ["M4-FAMILY-AGGRESSOR-TRADE-IMBALANCE"],
        )
        self.assertEqual(
            self.rows["SCORE-HIGHER_TIMEFRAME_PENALTY"][
                "target_rule_families"
            ],
            ["M4-FAMILY-MTF-HIERARCHY"],
        )
        self.assertEqual(
            self.rows["SCORE-TECHNICAL_BARRIER_PENALTY"][
                "target_rule_families"
            ],
            ["M4-FAMILY-STRUCTURAL-LEVELS"],
        )

    def test_every_m3_reference_exists_in_approved_catalog(self):
        catalog_path = (
            DEFAULT_OUTPUT_PATH.parent
            / "catalogo_contratos_datos_m3_v0_1.json"
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        self.assertEqual(catalog["status"], "completed_owner_approved")
        valid_ids = {item["id"] for item in catalog["contracts"]}
        for row in self.rows.values():
            self.assertTrue(
                set(row["m3_required_data_ids"]).issubset(valid_ids)
            )
            self.assertTrue(
                set(row["m3_conditional_data_ids"]).issubset(valid_ids)
            )

    def test_m4_started_without_starting_m5_or_modifying_production(self):
        scope = self.payload["scope"]
        self.assertTrue(scope["m4_started"])
        self.assertEqual(scope["m4_current_subphase"], "M4.1")
        self.assertEqual(scope["m4_next_subphase"], "M4.2")
        self.assertFalse(scope["m5_started"])
        self.assertFalse(scope["production_modified"])
        self.assertFalse(scope["analysis_engine_modified"])
        self.assertFalse(scope["learning_engine_used"])

    def test_generated_artifact_matches_builder(self):
        committed = json.loads(
            DEFAULT_OUTPUT_PATH.read_text(encoding="utf-8")
        )
        self.assertEqual(committed, self.payload)


if __name__ == "__main__":
    unittest.main()
