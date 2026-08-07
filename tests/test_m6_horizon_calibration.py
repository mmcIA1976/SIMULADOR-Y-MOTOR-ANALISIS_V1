from __future__ import annotations

import unittest
import json
from pathlib import Path
from unittest.mock import patch

import m8_evaluation as m8
from build_m6_horizon_calibration import build_payload
from m6_remediated_competing_risks import apply_competing_risk_evidence

from m6_horizon_calibration import (
    VALID_HORIZONS,
    horizon_calibration_profile,
    load_horizon_calibration,
)


class M6HorizonCalibrationTests(unittest.TestCase):
    def test_artifact_has_one_profile_per_supported_horizon(self):
        artifact = load_horizon_calibration()

        self.assertEqual(set(artifact["profiles"]), set(VALID_HORIZONS))

    def test_committed_artifact_matches_reproducible_builder(self):
        self.assertEqual(build_payload(), load_horizon_calibration())

    def test_every_served_profile_improves_held_out_metrics(self):
        for horizon in VALID_HORIZONS:
            profile = horizon_calibration_profile(horizon)
            self.assertLessEqual(
                profile["served_log_loss"],
                profile["global_log_loss"],
            )
            self.assertLessEqual(
                profile["served_brier_3c"],
                profile["global_brier_3c"],
            )

    def test_small_horizon_sample_is_explicitly_low_confidence(self):
        profile = horizon_calibration_profile("intraday_short")

        self.assertEqual(profile["calibration_records"], 2)
        self.assertEqual(profile["confidence"], "baja")
        self.assertNotEqual(
            profile["temperature"],
            profile["local_best_temperature"],
        )

    def test_horizons_do_not_share_the_same_served_temperature(self):
        temperatures = {
            horizon_calibration_profile(horizon)["temperature"]
            for horizon in VALID_HORIZONS
        }

        self.assertEqual(len(temperatures), len(VALID_HORIZONS))

    def test_metrics_and_local_temperature_are_reproducible(self):
        artifact = load_horizon_calibration()
        dataset = json.loads(
            Path(
                "auditorias_motor/dataset_desarrollo_calibracion_m8_3_v0_1.json"
            ).read_text(encoding="utf-8")
        )
        eligible = m8.eligible_labeled_rows(dataset["records"])

        with patch.object(
            m8,
            "apply_competing_risk_evidence",
            apply_competing_risk_evidence,
        ):
            for horizon in VALID_HORIZONS:
                rows = [
                    row
                    for row in eligible
                    if row["partition"] == "calibration"
                    and row["time_horizon"] == horizon
                ]
                profile = artifact["profiles"][horizon]
                candidate = profile["coefficient_artifact"]
                candidates = []
                for temperature in artifact[
                    "local_temperature_candidates"
                ]:
                    predictions = m8.candidate_predictions(
                        rows,
                        candidate,
                        temperature=temperature,
                    )
                    candidates.append(
                        (
                            m8.metric_log_loss(rows, predictions),
                            m8.metric_brier(rows, predictions),
                            temperature,
                        )
                    )
                self.assertEqual(
                    min(candidates)[2],
                    profile["local_best_temperature"],
                )
                served = m8.candidate_predictions(
                    rows,
                    candidate,
                    temperature=profile["served_temperature"],
                )
                self.assertAlmostEqual(
                    m8.metric_log_loss(rows, served),
                    profile["served_log_loss"],
                    places=14,
                )
                self.assertAlmostEqual(
                    m8.metric_brier(rows, served),
                    profile["served_brier_3c"],
                    places=14,
                )


if __name__ == "__main__":
    unittest.main()
