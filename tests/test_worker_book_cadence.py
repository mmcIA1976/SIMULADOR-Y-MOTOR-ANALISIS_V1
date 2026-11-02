import unittest
from unittest.mock import patch
from operation_worker import WorkerSettings
from order_book_observation import OrderBookObservationTracker
from tests.test_order_book_observation import depth


class WorkerBookCadenceTests(unittest.TestCase):
    def test_explicit_old_configuration_can_accumulate_three_captures(self):
        with patch.dict('os.environ',{'ORDER_BOOK_OBSERVATION_WINDOW_SECONDS':'60',
                                    'ORDER_BOOK_OBSERVATION_PUBLISH_SECONDS':'30'}):
            settings=WorkerSettings.from_env()
        self.assertEqual(settings.order_book_publish_seconds,30)
        self.assertEqual(settings.order_book_window_seconds,120)
        tracker=OrderBookObservationTracker(window_seconds=settings.order_book_window_seconds)
        summaries=[tracker.observe('BTCUSDT',depth(1000000+i*32000),[],
            captured_at_ms=1000000+i*32000) for i in range(8)]
        self.assertEqual(summaries[1]['status'],'partial')
        self.assertTrue(all(row['status']=='ready' and row['sample_count']>=3 for row in summaries[2:]))
        self.assertEqual(summaries[-1]['window_target_seconds'],120)

    def test_larger_explicit_window_is_preserved(self):
        self.assertEqual(WorkerSettings(order_book_window_seconds=240).order_book_window_seconds,240)


if __name__=='__main__': unittest.main()
