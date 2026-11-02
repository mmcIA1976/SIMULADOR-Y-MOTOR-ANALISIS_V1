import unittest
from autonomous_contest import determine_position_sizing
from autonomous_sizing_diagnostics import SizingLimitError,rejection_outcome,explain_scan
from tests.test_autonomous_contest import candidate


class SizingRejectionTests(unittest.TestCase):
    def test_positive_cash_is_reported_as_a_sizing_limit(self):
        item=candidate(edge=.15,tp=.57,unresolved=.01)
        item.time_horizon='intraday_wide'
        with self.assertRaises(SizingLimitError) as caught:
            determine_position_sizing(item,494.586)
        error=caught.exception
        status,reason,details=rejection_outcome(error)
        self.assertEqual(status,'no_trade')
        self.assertEqual(details['available_cash'],494.586)
        self.assertLessEqual(details['maximum_allowed_sl_loss_usdt'],24.7293)
        self.assertEqual(details['minimum_target_profit_usdt'],25)
        self.assertEqual(details['limiting_factor'],'sl_risk_budget')

    def test_old_record_keeps_its_recorded_status_in_the_display(self):
        row=explain_scan(dict(status='no_cash',reason_code='autonomous_minimum_tp_profit_unreachable'))
        self.assertEqual(row['status'],'no_trade')
        self.assertEqual(row['recorded_status'],'no_cash')
        self.assertIn('saldo cero',row['decision_explanation'])


if __name__=='__main__': unittest.main()
