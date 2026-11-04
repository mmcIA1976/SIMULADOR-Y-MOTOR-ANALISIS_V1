"""Regression cases from the November admission audit; no live orders."""
import unittest

from autonomous_contest import determine_position_sizing,PARTICIPANT_POLICIES,rejection_code
from autonomous_sizing_diagnostics import SizingLimitError,explain_scan
from tests.test_autonomous_entry_standard import proposal


class FundedMarginTests(unittest.TestCase):
    def test_archived_xrp_can_target_twenty_five_with_586_free_cash(self):
        p=proposal(PARTICIPANT_POLICIES[2],tp=.5685464501120049,sl=.4297136848557246,unresolved=.0017398650322705)
        p.entry,p.take_profit,p.stop_loss=1.2835,1.3088707052511728,1.2581292947488274
        result=determine_position_sizing(p,586.4828)
        self.assertEqual(result.leverage,10)
        self.assertAlmostEqual(result.margin,126.4747,places=4)
        self.assertGreaterEqual(result.estimated_tp_pnl,25)
        self.assertAlmostEqual(result.estimated_sl_pnl,-25,delta=.0001)
        self.assertLess(result.margin,result.available_cash)
        self.assertIsNone(result.maximum_sl_loss_usdt)

    def test_eight_points_do_not_turn_into_a_second_cash_percentage_gate(self):
        for policy in PARTICIPANT_POLICIES:
            for side in ('long','short'):
                with self.subTest(bot=policy.code,side=side):
                    p=proposal(policy,side=side)
                    p.take_profit,p.stop_loss=((102,98) if side=='long' else (98,102))
                    self.assertIsNone(rejection_code(p,policy))
                    result=determine_position_sizing(p,150)
                    self.assertGreaterEqual(result.estimated_tp_pnl,policy.minimum_target_profit_usdt)
                    self.assertLess(result.margin,150)
                    self.assertLessEqual(abs(result.estimated_sl_pnl),result.margin)

    def test_reserved_margin_leaves_cash_for_eight_positions_when_it_fits(self):
        p=proposal(PARTICIPANT_POLICIES[2]);p.take_profit,p.stop_loss=102,98
        cash=1000
        for _ in range(8):
            result=determine_position_sizing(p,cash)
            cash-=result.margin
            self.assertGreaterEqual(cash,0)
        self.assertAlmostEqual(cash,0)

    def test_actual_margin_shortfall_is_still_rejected(self):
        p=proposal(PARTICIPANT_POLICIES[2]);p.take_profit,p.stop_loss=102,98
        with self.assertRaises(SizingLimitError) as error:determine_position_sizing(p,124.9999)
        self.assertEqual(error.exception.details['limiting_factor'],'cash_and_leverage')
        self.assertGreater(error.exception.details['required_margin_usdt'],124.9999)
        self.assertIsNone(error.exception.details['maximum_allowed_sl_loss_usdt'])
        self.assertGreaterEqual(determine_position_sizing(p,125).estimated_tp_pnl,25)

    def test_wide_sl_is_funded_without_a_percentage_of_account_budget(self):
        p=proposal(PARTICIPANT_POLICIES[2]);p.take_profit,p.stop_loss=112,88
        result=determine_position_sizing(p,100)
        self.assertEqual(result.leverage,8)
        self.assertGreaterEqual(result.estimated_tp_pnl,25)
        self.assertLessEqual(abs(result.estimated_sl_pnl),result.margin)

    def test_historical_rejection_explanation_preserves_the_old_risk_reason(self):
        old=explain_scan(dict(status='no_cash',reason_code='autonomous_minimum_tp_profit_unreachable',
            audit=dict(gates=dict(position_sizing=dict(limiting_factor='sl_risk_budget')))))
        self.assertIn('política histórica',old['decision_explanation'])
        new=explain_scan(dict(status='no_trade',reason_code='autonomous_minimum_tp_profit_unreachable',
            audit=dict(gates=dict(position_sizing=dict(limiting_factor='cash_and_leverage')))))
        self.assertIn('margen necesario',new['decision_explanation'])


if __name__=='__main__':unittest.main()
