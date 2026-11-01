"""28-Oct entry standard: boundary values, actual writes and retired wait.

Only synthetic candidates and an in-memory SQL adapter are used. No providers,
worker, real operations, remote connection or historical replay runs here.
"""
import json
import unittest
from unittest.mock import patch

import autonomous_confirmation as confirmation
import autonomous_contest as contest
from tests.test_autonomous_contest import candidate, OperationInsertDb


def proposal(policy, *, side='long', tp=.54, sl=.46, unresolved=0.):
    item = candidate(edge=tp-sl, tp=tp, unresolved=unresolved)
    item.time_horizon = policy.time_horizon
    item.sl_probability = sl
    item.side = side
    item.take_profit, item.stop_loss = ((101., 99.) if side == 'long' else (99., 101.))
    item.sigma = .01
    item.analysis_result = dict(analysis_type='pre_trade', tp_probability=tp,
        sl_probability=sl, range_probability=unresolved, risk_level='test',
        setup_grade='test', confidence='test', training_decision='test',
        parameter_advice={}, reasons=[], alerts=[], snapshot={})
    return item


class StandardTests(unittest.TestCase):
    def test_all_policies_use_eight_points_and_no_fixed_wait(self):
        for policy, minimum in zip(contest.PARTICIPANT_POLICIES, (20., 25., 25.)):
            self.assertEqual(policy.edge_threshold, .08)
            self.assertEqual(policy.minimum_target_profit_usdt, minimum)
            self.assertFalse(confirmation.enabled(policy))
            item = proposal(policy)
            self.assertIs(confirmation.select([item], policy), item)
            self.assertEqual(item.confirmation, {})

    def test_twenty_percent_boundary_on_all_bots_and_both_sides(self):
        for policy in contest.PARTICIPANT_POLICIES:
            for side in ('long', 'short'):
                item = proposal(policy, side=side, tp=.55, sl=.25, unresolved=.20)
                self.assertTrue(item.eligible_for(policy), (policy.code, side))
                item.unresolved_probability = .200001
                item.sl_probability = 1-item.tp_probability-item.unresolved_probability
                item.edge = item.tp_probability-item.sl_probability
                self.assertFalse(item.eligible_for(policy))
                self.assertEqual(contest.rejection_code(item, policy), 'unresolved_probability_above_gate')

    def test_eight_point_boundary_and_strict_rejection_below_it(self):
        for policy in contest.PARTICIPANT_POLICIES:
            item = proposal(policy, tp=.50, sl=.42, unresolved=.08)
            self.assertTrue(item.eligible_for(policy))
            item.sl_probability = .420001
            item.unresolved_probability = .079999
            item.edge = item.tp_probability-item.sl_probability
            self.assertFalse(item.eligible_for(policy))
            self.assertEqual(contest.rejection_code(item, policy), 'edge_below_horizon_gate')
        for policy in contest.PARTICIPANT_POLICIES[1:]:
            item = proposal(policy, tp=.48, sl=.40, unresolved=.12)
            self.assertLess(item.edge, .08)  # Floating representation of exactly eight points.
            self.assertTrue(item.eligible_for(policy))

    def test_short_retains_fifty_percent_tp_floor_without_a_wait_plan(self):
        policy = contest.PARTICIPANT_POLICIES[0]
        item = proposal(policy, tp=.49, sl=.40, unresolved=.11)
        self.assertFalse(item.eligible_for(policy))
        self.assertEqual(contest.rejection_code(item, policy), 'short_plan_tp_probability_below_gate')

    def test_twenty_is_reachable_for_short_but_cannot_replace_twenty_five_on_other_bots(self):
        for policy in contest.PARTICIPANT_POLICIES:
            for side in ('long', 'short'):
                item = proposal(policy, side=side)
                if policy.code == 'auto_intraday_short':
                    sizing = contest.determine_position_sizing(item, 760.)
                    self.assertGreaterEqual(sizing.estimated_tp_pnl, 20.)
                    self.assertLessEqual(abs(sizing.estimated_sl_pnl), 760.*.028+.000051)
                else:
                    with self.assertRaisesRegex(ValueError, 'minimum_tp_profit_unreachable'):
                        contest.determine_position_sizing(item, 760.)

    def test_each_actual_insert_saves_its_own_minimum_and_immediate_policy(self):
        for policy in contest.PARTICIPANT_POLICIES:
            for side in ('long', 'short'):
                item = proposal(policy, side=side); db = OperationInsertDb()
                contest._open_selected_operation(db, participant={'id': 1, 'user_id': 27},
                    season_id=1, candidate=item, policy=policy, execution_entry=100., executed_at=item.analyzed_at)
                fields = next(params for query, params in db.calls if 'INSERT INTO operations' in query)
                self.assertAlmostEqual(abs(fields[4]-fields[7]), abs(fields[8]-fields[4]))
                saved = json.loads(next(params for query, params in db.calls if 'INSERT INTO recommendations' in query)[17])
                sizing = saved['position_sizing']
                self.assertEqual(sizing['minimum_target_profit_usdt'], policy.minimum_target_profit_usdt)
                self.assertGreaterEqual(sizing['estimated_tp_pnl'], policy.minimum_target_profit_usdt)
                self.assertLessEqual(abs(sizing['estimated_sl_pnl']), sizing['maximum_sl_loss_usdt']+.000051)
                self.assertEqual(saved['snapshot']['version_contract']['autonomous_entry_policy_version'], contest.ENTRY_POLICY_VERSION)

    def test_direct_insert_cannot_bypass_resolution_or_edge_gates(self):
        for policy in contest.PARTICIPANT_POLICIES:
            for params in (dict(tp=.55, sl=.249, unresolved=.201), dict(tp=.50, sl=.43, unresolved=.07)):
                item = proposal(policy, **params); db = OperationInsertDb()
                with self.assertRaises(ValueError):
                    contest._open_selected_operation(db, participant={'id': 1, 'user_id': 27},
                        season_id=1, candidate=item, policy=policy, execution_entry=100., executed_at=item.analyzed_at)
                self.assertFalse(any('INSERT INTO' in query for query, _ in db.calls))

    def test_account_policy_cannot_borrow_short_minimum_from_another_horizon(self):
        item = proposal(contest.PARTICIPANT_POLICIES[0]); db = OperationInsertDb()
        with self.assertRaisesRegex(ValueError, 'horizon_policy_mismatch'):
            contest._open_selected_operation(db, participant={'id': 1, 'user_id': 27}, season_id=1,
                candidate=item, policy=contest.PARTICIPANT_POLICIES[1], execution_entry=100., executed_at=item.analyzed_at)
        self.assertFalse(any('INSERT INTO' in query for query, _ in db.calls))

    def test_cached_edge_cannot_override_the_actual_probability_difference(self):
        for policy in contest.PARTICIPANT_POLICIES:
            item = proposal(policy, tp=.50, sl=.43, unresolved=.07)
            item.edge = .20
            self.assertFalse(item.eligible_for(policy))
            self.assertEqual(contest.rejection_code(item, policy), 'edge_below_horizon_gate')


if __name__ == '__main__': unittest.main()
