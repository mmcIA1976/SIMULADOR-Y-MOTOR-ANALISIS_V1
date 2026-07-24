import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "CONTRATO_FASE_1_MOTOR_ANALISIS.md"
COVERAGE = ROOT / "COBERTURA_ANALITICA_FASE_1.md"


class Phase1ContractTests(unittest.TestCase):
    def test_contract_preserves_non_negotiable_requirements(self):
        text = CONTRACT.read_text(encoding="utf-8")
        required = (
            "probabilidad de TP",
            "probabilidad de SL",
            "Contrato obligatorio de cada regla",
            "Traza obligatoria por analisis",
            "Funcion exacta del motor de aprendizaje",
            "Reglas combinadas e interacciones",
            "No se permite presentar como probabilidad una suma arbitraria de puntos.",
            "Ningun cambio llega a produccion sin aprobacion humana.",
        )

        for statement in required:
            with self.subTest(statement=statement):
                self.assertIn(statement, text)

    def test_coverage_matrix_contains_all_34_blocks(self):
        text = COVERAGE.read_text(encoding="utf-8")
        block_numbers = {
            int(match.group(1))
            for match in re.finditer(r"^\|\s*(\d+)\s*\|", text, flags=re.MULTILINE)
        }

        self.assertEqual(block_numbers, set(range(1, 35)))

    def test_primary_documents_declare_contract_precedence(self):
        for relative_path in (
            "README.md",
            "NORTE_ESTRATEGICO_AUTONOMIA.md",
            "ESPECIFICACION_MOTOR_ANALISIS.md",
        ):
            with self.subTest(path=relative_path):
                text = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertIn("CONTRATO_FASE_1_MOTOR_ANALISIS.md", text)

    def test_open_product_decisions_remain_explicit(self):
        text = CONTRACT.read_text(encoding="utf-8")

        self.assertIn("Semantica exacta de los dos porcentajes", text)
        self.assertIn("Horizonte operativo definitivo", text)
        self.assertIn("Universo inicial de activos", text)


if __name__ == "__main__":
    unittest.main()
