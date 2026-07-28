from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_m4_rule_audit_report as m4  # noqa: E402


class M47RuleAuditReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = m4.build_catalog()

    def test_contains_exactly_27_unique_rules(self) -> None:
        rules = self.catalog["rules"]
        self.assertEqual(len(rules), 27)
        self.assertEqual(len({rule["id"] for rule in rules}), 27)
        self.assertEqual(
            [rule["sequence"] for rule in rules],
            list(range(1, 28)),
        )
        self.assertEqual(self.catalog["scope"]["p0_core_rules"], 26)
        self.assertEqual(self.catalog["scope"]["auxiliary_operators"], 1)

    def test_rule_counts_by_subphase_are_exact(self) -> None:
        self.assertEqual(
            self.catalog["scope"]["rules_by_subphase"],
            m4.EXPECTED_RULE_COUNTS,
        )
        actual = {
            subphase: sum(
                1
                for rule in self.catalog["rules"]
                if rule["source_subphase"] == subphase
            )
            for subphase in m4.EXPECTED_RULE_COUNTS
        }
        self.assertEqual(actual, m4.EXPECTED_RULE_COUNTS)

    def test_formula_index_covers_every_rule_in_order(self) -> None:
        index = self.catalog["formula_index"]
        rules = self.catalog["rules"]
        self.assertEqual(len(index), 27)
        self.assertEqual(
            [item["id"] for item in index],
            [rule["id"] for rule in rules],
        )
        for item in index:
            self.assertTrue(item["formula"])
            self.assertTrue(all(str(part).strip() for part in item["formula"]))

    def test_every_rule_retains_complete_audit_contract(self) -> None:
        for rule in self.catalog["rules"]:
            for field in m4.REQUIRED_FIELDS:
                self.assertIn(field, rule, f"{rule['id']}:{field}")
                self.assertNotIn(
                    rule[field],
                    (None, "", []),
                    f"{rule['id']}:{field}",
                )

    def test_every_source_claim_resolves_inside_its_subphase(self) -> None:
        registries = self.catalog["source_registries"]
        for rule in self.catalog["rules"]:
            source_ids = {
                source["id"]
                for source in registries[rule["source_subphase"]]
            }
            used = {
                claim["source_id"]
                for claim in rule["source_and_exact_supported_claim"]
            }
            self.assertTrue(used)
            self.assertTrue(used.issubset(source_ids), rule["id"])
            self.assertTrue(
                all(
                    claim["evidence_category"]
                    for claim in rule[
                        "source_and_exact_supported_claim"
                    ]
                ),
                rule["id"],
            )
        allowed_categories = {
            "internal_project_contract",
            "provider_semantics",
            "external_methodology",
            "external_family_or_adjacent_evidence",
            "institutional_risk_guidance",
        }
        self.assertTrue(
            all(
                source["evidence_category"] in allowed_categories
                for registry in registries.values()
                for source in registry
            )
        )
        claim_categories = {
            claim["evidence_category"]
            for rule in self.catalog["rules"]
            for claim in rule["source_and_exact_supported_claim"]
        }
        self.assertIn("provider_semantics", claim_categories)
        self.assertIn(
            "external_empirical_evidence_adjacent_to_project_target",
            claim_categories,
        )
        self.assertIn("transfer_limit_evidence", claim_categories)

    def test_produced_and_reserved_null_trace_fields_are_disjoint(self) -> None:
        rules = {rule["id"]: rule for rule in self.catalog["rules"]}
        for rule in rules.values():
            produced = set(rule["produced_trace_fields"])
            reserved = set(rule["forbidden_or_reserved_null_fields"])
            self.assertFalse(produced & reserved, rule["id"])
            self.assertEqual(
                produced | reserved,
                set(rule["trace_output"]),
                rule["id"],
            )
        geometry = rules["M4-RULE-NORMALIZED-BARRIER-GEOMETRY-002"]
        self.assertEqual(
            geometry["forbidden_or_reserved_null_fields"],
            ["probability"],
        )

    def test_policy_decisions_are_separate_and_unique(self) -> None:
        records = self.catalog["policy_decision_records"]
        self.assertEqual(len(records), 4)
        self.assertEqual(
            len({record["id"] for record in records}),
            len(records),
        )
        self.assertTrue(
            all(
                record["evidence_category"]
                == "internal_project_policy_not_external_evidence"
                for record in records
            )
        )

    def test_hypotheses_remain_unverified_and_total_15(self) -> None:
        hypotheses = [
            rule["separate_predictive_hypothesis"]
            for rule in self.catalog["rules"]
            if rule["separate_predictive_hypothesis"] is not None
        ]
        self.assertEqual(len(hypotheses), 15)
        self.assertEqual(len({item["id"] for item in hypotheses}), 15)
        for hypothesis in hypotheses:
            self.assertIn(
                hypothesis["status"],
                {
                    "proposed_unverified",
                    "proposed_unverified_interaction_only",
                    "mathematical_constraint_for_future_model",
                },
            )

    def test_no_rule_has_probability_weight_or_production_authorization(self) -> None:
        for rule in self.catalog["rules"]:
            self.assertFalse(rule["direct_probability_effect_authorized"])
            self.assertFalse(rule["numeric_weight_authorized"])
            self.assertFalse(rule["production_authorized"])

    def test_reading_contract_prevents_false_validation_claim(self) -> None:
        contract = self.catalog["reading_contract"]
        self.assertTrue(contract["formula_is_documented_operator"])
        self.assertFalse(
            contract["formula_is_empirically_validated_probability"]
        )
        self.assertTrue(contract["hypotheses_are_unverified"])
        self.assertTrue(contract["implementation_is_deferred_to_m5"])
        self.assertTrue(
            contract["probability_integration_is_deferred_to_m6"]
        )

    def test_report_contains_every_rule_and_formula_section(self) -> None:
        report = m4.render_report(self.catalog)
        self.assertEqual(report.count("### Formula exacta"), 27)
        self.assertEqual(report.count("### Datos"), 27)
        self.assertEqual(report.count("### Fuentes y afirmacion respaldada"), 27)
        self.assertEqual(report.count("### Control de doble conteo"), 27)
        self.assertEqual(report.count("### Traza producida"), 27)
        self.assertEqual(
            report.count("### Campos prohibidos o reservados a null"),
            27,
        )
        self.assertEqual(
            report.count("### Refutacion, suspension o retirada"),
            27,
        )
        for rule in self.catalog["rules"]:
            self.assertIn(f"## {rule['sequence']}. {rule['id']}", report)

    def test_generated_artifacts_are_reproducible(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "build_m4_rule_audit_report.py"),
                "--check",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_written_catalog_matches_builder(self) -> None:
        path = (
            ROOT
            / "auditorias_motor"
            / "catalogo_27_reglas_formulas_m4_7_v0_2.json"
        )
        written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(written, self.catalog)

    def test_integrity_manifest_hashes_complete_files(self) -> None:
        manifest_path = (
            ROOT
            / "auditorias_motor"
            / "manifiesto_integridad_m4_7_v0_2.json"
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["canonical_payload_sha256"],
            self.catalog["canonical_payload_sha256"],
        )
        for artifact in manifest["artifacts"]:
            path = ROOT / artifact["path"]
            content = path.read_bytes()
            self.assertEqual(
                hashlib.sha256(content).hexdigest(),
                artifact["sha256_full_file"],
            )
            self.assertEqual(len(content), artifact["bytes_utf8"])


if __name__ == "__main__":
    unittest.main()
