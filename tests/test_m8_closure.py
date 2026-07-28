from __future__ import annotations

import json
import unittest
from pathlib import Path

from m8_evaluation import payload_sha256


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "auditorias_motor"


def load(name: str) -> dict:
    return json.loads((AUDIT_DIR / name).read_text(encoding="utf-8"))


class M8ClosureTests(unittest.TestCase):
    def test_final_dataset_was_sealed_without_labels(self) -> None:
        payload = load("dataset_final_sellado_m8_3_v0_1.json")
        self.assertEqual(
            payload["status"],
            "features_prepared_labels_not_fetched",
        )
        self.assertEqual(payload["outcome_fields"], [])
        self.assertEqual(payload["legacy_probability_fields"], [])
        self.assertTrue(
            all("outcome" not in row for row in payload["records"])
        )

    def test_final_test_was_opened_without_retuning(self) -> None:
        payload = load("evaluacion_final_m8_6_v0_1.json")
        self.assertEqual(
            payload["status"],
            "final_test_opened_once_no_retuning",
        )
        self.assertFalse(payload["retuning_after_final_open"])

    def test_m8_is_closed_and_m9_remains_blocked(self) -> None:
        payload = load("paquete_cierre_m8_7_v0_1.json")
        self.assertEqual(payload["status"], "m8_closed")
        self.assertEqual(
            payload["decision"]["state"],
            "return_to_earlier_phase",
        )
        self.assertTrue(payload["boundaries"]["m9_blocked"])
        self.assertFalse(payload["boundaries"]["production_authorized"])

    def test_all_m8_artifact_hashes_are_reproducible(self) -> None:
        names = (
            "contrato_ejecucion_m8_3_v0_1.json",
            "dataset_desarrollo_calibracion_m8_3_v0_1.json",
            "dataset_final_sellado_m8_3_v0_1.json",
            "evaluacion_baseline_m8_4_v0_1.json",
            "modelo_estimado_calibrado_m8_5_v0_1.json",
            "evaluacion_final_m8_6_v0_1.json",
            "paquete_cierre_m8_7_v0_1.json",
        )
        for name in names:
            with self.subTest(name=name):
                payload = load(name)
                expected = payload.pop("canonical_payload_sha256")
                self.assertEqual(payload_sha256(payload), expected)


if __name__ == "__main__":
    unittest.main()
