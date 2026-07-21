import unittest
from unittest.mock import Mock, patch

from app import finalize_due_observations


class LearningFinalizationTests(unittest.TestCase):
    @patch("app.refresh_learning_evaluations")
    @patch("app.refresh_learning_conclusions")
    @patch("app.finalize_due_observations_with_db")
    def test_finalized_observation_immediately_refreshes_learning(
        self,
        finalize_with_db,
        refresh_conclusions,
        refresh_evaluations,
    ):
        db = Mock()
        finalized = [{"id": 227, "result": "plan_would_succeed"}]
        finalize_with_db.return_value = finalized

        result = finalize_due_observations(db)

        self.assertEqual(result, finalized)
        refresh_conclusions.assert_called_once_with(db)
        refresh_evaluations.assert_called_once_with(db)

    @patch("app.refresh_learning_evaluations")
    @patch("app.refresh_learning_conclusions")
    @patch("app.finalize_due_observations_with_db", return_value=[])
    def test_no_learning_refresh_without_newly_finalized_observations(
        self,
        finalize_with_db,
        refresh_conclusions,
        refresh_evaluations,
    ):
        db = Mock()

        result = finalize_due_observations(db)

        self.assertEqual(result, [])
        finalize_with_db.assert_called_once_with(db)
        refresh_conclusions.assert_not_called()
        refresh_evaluations.assert_not_called()


if __name__ == "__main__":
    unittest.main()
