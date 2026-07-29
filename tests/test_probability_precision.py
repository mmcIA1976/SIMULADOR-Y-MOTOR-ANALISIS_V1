from __future__ import annotations

import unittest

from app import recommendation_probability_value


class ProbabilityPrecisionTests(unittest.TestCase):
    def test_exact_analysis_range_recovers_rounded_database_zero(self):
        operation = {
            "recommendation_tp_probability": 0.0,
            "recommendation_analysis_json": {
                "tp_probability": 0.0,
                "probability_ranges": {
                    "tp": {
                        "low": 9.506366087128875e-11,
                        "high": 9.506366087128875e-11,
                    }
                },
            },
        }
        self.assertEqual(
            recommendation_probability_value(operation, "tp"),
            9.506366087128875e-11,
        )

    def test_missing_recommendation_probability_stays_missing(self):
        self.assertIsNone(
            recommendation_probability_value(
                {
                    "recommendation_tp_probability": None,
                    "recommendation_analysis_json": None,
                },
                "tp",
            )
        )


if __name__ == "__main__":
    unittest.main()
