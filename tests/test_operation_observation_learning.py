from __future__ import annotations

import unittest
from pathlib import Path

from backfill_operation_404_observation import (
    CHECKPOINTS,
    EXIT_REFERENCES,
    REPORTED_CHECKPOINTS,
    probability_values,
)
from operation_observation_learning import (
    OBSERVATION_ANALYSIS_TYPE,
    OBSERVATION_CONTRACT_VERSION,
    _probability_triplet,
    canonical_json,
    checkpoint_code,
    payload_sha256,
)


ROOT = Path(__file__).resolve().parents[1]


class OperationObservationLearningTests(unittest.TestCase):
    def test_checkpoint_identity_is_stable_and_unambiguous(self) -> None:
        self.assertEqual(checkpoint_code(404, 1), "404o1")
        self.assertEqual(checkpoint_code(450, 27), "450o27")
        with self.assertRaises(ValueError):
            checkpoint_code(404, 0)

    def test_json_hash_is_deterministic(self) -> None:
        left = {"operation": 404, "signals": {"ema": 1, "book": -1}}
        right = {"signals": {"book": -1, "ema": 1}, "operation": 404}
        self.assertEqual(canonical_json(left), canonical_json(right))
        self.assertEqual(payload_sha256(left), payload_sha256(right))

    def test_probability_contract_accepts_reconstructed_rounding(self) -> None:
        tp, sl, unresolved = probability_values(50.2, 49.7)
        normalized = _probability_triplet(tp, sl, unresolved)
        self.assertAlmostEqual(sum(normalized), 1.0)
        with self.assertRaises(ValueError):
            _probability_triplet(0.5, None, 0.5)

    def test_operation_404_reconstruction_never_claims_missing_evidence(self) -> None:
        self.assertEqual(REPORTED_CHECKPOINTS, 47)
        self.assertEqual(len(CHECKPOINTS), 32)
        self.assertEqual(CHECKPOINTS[0][0], 16)
        self.assertEqual(CHECKPOINTS[-1][0], 47)
        self.assertTrue(all(row[1] for row in CHECKPOINTS))
        self.assertEqual(
            [row[0] for row in CHECKPOINTS if row[-1]],
            [25, 32, 43],
        )
        self.assertEqual(sorted(EXIT_REFERENCES), [25, 32, 33, 35, 39, 43, 44, 45, 46])

    def test_schema_and_migration_preserve_exact_vs_reconstructed_contract(self) -> None:
        schema = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
        migration = (
            ROOT
            / "supabase"
            / "migrations"
            / "20260908_operation_observation_learning.sql"
        ).read_text(encoding="utf-8")
        for sql in (schema, migration):
            self.assertIn("operation_observation_sessions", sql)
            self.assertIn("operation_observation_checkpoints", sql)
            self.assertIn("operation_exit_counterfactuals", sql)
            self.assertIn("formal_learning_eligible", sql)
            self.assertIn("reconstructed_partial", sql)
            self.assertIn("operation_observation_fact_is_append_only", sql)
            self.assertIn("production_effect = 'none'", sql)

    def test_application_keeps_observations_out_of_trade_creation(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn(
            'WHERE operation_id = ? AND analysis_type = \'pre_trade\'',
            source,
        )
        self.assertIn("AND analysis_type = 'pre_trade'", source)
        self.assertIn(
            "AND analysis_type <> 'operation_observation'",
            source,
        )
        self.assertIn(
            '@app.post("/api/operations/{operation_id}/observation-checkpoints")',
            source,
        )
        self.assertEqual(OBSERVATION_ANALYSIS_TYPE, "operation_observation")
        self.assertEqual(
            OBSERVATION_CONTRACT_VERSION,
            "operation-observation-contract-v0.1",
        )
        self.assertIn(
            'OBSERVATION_OPERATOR_USERNAME = "mauriciomc"',
            source,
        )
        self.assertGreaterEqual(
            source.count("require_observation_operator(user)"),
            4,
        )

    def test_database_bootstrap_releases_relation_locks_before_indexes(self) -> None:
        source = (ROOT / "db.py").read_text(encoding="utf-8")
        update = (
            "UPDATE recommendations SET time_horizon = 'intraday_short' "
            "WHERE time_horizon IS NULL OR time_horizon = ''"
        )
        update_position = source.index(update)
        commit_position = source.index("db.commit()", update_position)
        index_position = source.index("create_indexes(db)", update_position)
        self.assertLess(commit_position, index_position)

    def test_frontend_exposes_manual_observation_without_reusing_opening_state(self) -> None:
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="startObservationButton"', html)
        self.assertIn('id="recordObservationButton"', html)
        self.assertIn("latestObservationAnalysisByOperation", javascript)
        self.assertIn("recordObservationCheckpoint", javascript)
        self.assertIn(
            'const OBSERVATION_OPERATOR_USERNAME = "mauriciomc";',
            javascript,
        )
        self.assertIn("canManageOperationObservations()", javascript)
        observation_function = javascript.split(
            "async function recordObservationCheckpoint()", 1
        )[1].split("async function closeOperationById", 1)[0]
        self.assertNotIn("lastAnalysis =", observation_function)
        self.assertNotIn("lastAnalysisPayload =", observation_function)


if __name__ == "__main__":
    unittest.main()
