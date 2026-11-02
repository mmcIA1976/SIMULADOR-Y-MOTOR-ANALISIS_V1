from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

import app
from analysis_engine_selection import LAB4, V11
from engine_lab4.observational_context import digest
from tests.test_lab4_replacement import synthetic_run, single_analysis
from versioning import learning_evaluator_version_for_engine, LAB4_LEARNING_EVALUATOR_VERSION, LEGACY_LEARNING_EVALUATOR_VERSION


class LearningAttributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot=single_analysis(synthetic_run('intraday_short','long'))['snapshot']

    def evaluate(self, *, late=False, complete=True):
        snapshot=deepcopy(self.snapshot)
        at=datetime.fromisoformat(snapshot['analysis_at'])
        close=at+timedelta(hours=5 if late else 1)
        evidence=dict(status='complete' if complete else 'partial',quality='complete_1m_with_boundary_approximation',
            coverage_ratio=1,actual_window=dict(first_candle_open_at=at.isoformat(),last_candle_close_at=close.isoformat()),
            first_plan_touch=dict(touched_at=close.isoformat()),reconstructed_plan_result='plan_failure')
        return snapshot,app.predictive_rule_learning_snapshot(snapshot,plan_result='plan_failure',
            operation=dict(closed_at=close.isoformat(),close_reason='stop_loss'),historical_evidence=evidence)

    def test_weighted_inputs_and_joint_trace_survive_rule_attribution(self):
        before=digest(self.snapshot)
        snapshot,result=self.evaluate()
        cvd=result['rules']['LIB-CAND-CVD-SLOPE-001']
        self.assertEqual(cvd['probability_effect'],'frozen_lab4_correction_input')
        self.assertNotIn('LIB-CAND-CVD-SLOPE-001',result['observational_rule_ids'])
        self.assertIn('side_adjusted_normalized_cvd_slope',cvd['active_probability_outputs'])
        fields={field for entries in result['lab4_correction']['inputs_by_rule'].values() for field in entries}
        self.assertEqual(fields,{'ema_slope','ema_price','cvd','volume','extension','path'})
        self.assertEqual(result['lab4_correction']['contribution_trace'],
            snapshot['engine_inference']['prediction']['observational_contribution_trace'])
        self.assertEqual(digest(self.snapshot),before)
        self.assertEqual(result['observed_outcome'],'sl_first_within_horizon')

    def test_late_real_sl_is_neither_inside_four_hours(self):
        snapshot,result=self.evaluate(late=True)
        self.assertEqual(result['observed_outcome'],'neither_barrier_before_expiry')
        self.assertEqual(result['observed_outcome_source'],'reconstructed_1m_no_touch')
        self.assertEqual(result['final_operation_result']['close_reason'],'stop_loss')
        self.assertEqual(result['final_operation_result']['plan_result'],'plan_failure')

    def test_incomplete_late_path_is_not_invented_as_no_touch(self):
        _,result=self.evaluate(late=True,complete=False)
        self.assertIsNone(result['observed_outcome'])
        self.assertEqual(result['observed_outcome_source'],'late_or_indirect_label_not_verified')

    def test_legacy_rule_contract_is_unchanged(self):
        snapshot=deepcopy(self.snapshot);snapshot['engine_version']=V11
        expected=app.empirical_predictive_rule_learning_snapshot(snapshot,plan_result='plan_failure')
        actual=app.predictive_rule_learning_snapshot(snapshot,plan_result='plan_failure')
        self.assertEqual(actual,expected)
        self.assertEqual(learning_evaluator_version_for_engine(V11),LEGACY_LEARNING_EVALUATOR_VERSION)
        self.assertEqual(learning_evaluator_version_for_engine(LAB4),LAB4_LEARNING_EVALUATOR_VERSION)


if __name__=='__main__': unittest.main()
