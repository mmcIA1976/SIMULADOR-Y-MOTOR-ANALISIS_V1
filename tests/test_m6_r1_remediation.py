from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "auditorias_motor"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def load(name: str) -> dict:
    return json.loads((AUDIT_DIR / name).read_text(encoding="utf-8"))


class M6R1RemediationArtifactTests(unittest.TestCase):
    def test_all_historical_records_are_technically_compatible(self) -> None:
        payload = load("diagnostico_m6_r1_v0_1.json")
        cohort = payload["historical_cohort_after"]
        self.assertEqual(cohort["records"], 201)
        self.assertEqual(cohort["evaluated"], 201)
        self.assertEqual(cohort["blocked"], [])
        self.assertLessEqual(
            cohort["maximum_zero_coefficient_baseline_error"],
            1e-12,
        )

    def test_property_grid_has_no_failures(self) -> None:
        payload = load("diagnostico_m6_r1_v0_1.json")
        self.assertEqual(payload["property_grid"]["cases"], 500)
        self.assertEqual(payload["property_grid"]["failures"], [])
        self.assertLessEqual(
            payload["property_grid"]["maximum_probability_mass_error"],
            1e-12,
        )

    def test_rule_review_does_not_refit_or_reuse_final(self) -> None:
        payload = load("decision_reglas_m6_r1_post_m8_v0_1.json")
        self.assertFalse(payload["constraints"]["m8_candidate_modified"])
        self.assertFalse(
            payload["constraints"]["opened_final_period_reused_for_fitting"]
        )
        self.assertFalse(payload["constraints"]["new_coefficients_estimated"])

    def test_closure_keeps_m9_blocked(self) -> None:
        payload = load("paquete_cierre_m6_r1_v0_1.json")
        self.assertTrue(payload["decision"]["m6_r1_closed"])
        self.assertFalse(payload["decision"]["m9_unblocked"])
        self.assertEqual(payload["boundaries"]["probability_effect"], "none")
        self.assertFalse(payload["boundaries"]["online_deployed"])
        self.assertTrue(payload["scope"]["pretrade_audit_metadata_modified"])

    def test_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [str(PYTHON), "build_m6_r1_remediation.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
