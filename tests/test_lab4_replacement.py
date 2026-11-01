"""Release compatibility tests, synthetic inputs only. No market or DB calls."""
from copy import deepcopy
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import empirical_temporal_engine as empirical
import served_analysis as served
import lab4_runtime as runtime
from analysis_engine_selection import V11, LAB4, SCORING_BY_ENGINE, result_version_contract
from analysis_engine import TradeProposal
from operation_observation_learning import compact_observation_snapshot, MAX_COMPACT_SNAPSHOT_BYTES

ROOT = Path(__file__).resolve().parents[1]


def synthetic_run(horizon='intraday_short', side='long', asymmetric=True, symbol='BTCUSDT'):
    fixture = json.loads((ROOT/'tests/fixtures/lab4_synthetic_context.json').read_bytes())
    names = empirical.selected_stage_order(horizon)
    contexts = {h:deepcopy(fixture['stage_contexts'][h]) for h in names}
    traces = {}
    for h, ctx in contexts.items():
        ctx['source_data_sha256'] = sha256(json.dumps(ctx['feature_values'], sort_keys=True).encode()).hexdigest()
        by_rule = {}
        for key, value in ctx['feature_values'].items():
            rule, field = key.split('::',1)
            by_rule.setdefault(rule, {'rule_id':rule, 'outputs':{}, 'status':'evaluated'})['outputs'][field] = value
        volume = by_rule['LIB-CAND-RELATIVE-VOLUME-001']['outputs']
        volume['relative_horizon_volume'] = math.exp(volume['log_relative_horizon_volume'])
        traces[h] = list(by_rule.values())
    entry = 100.
    tp, sl = ((102. if asymmetric else 101.,99.) if side=='long' else (98. if asymmetric else 99.,101.))
    plan = dict(symbol=symbol, side=side, entry=entry, take_profit=tp, stop_loss=sl,
                time_horizon=horizon, analysis_at=fixture['analysis_at'])
    return dict(status='evaluated', plan=plan, stage_contexts=contexts, stage_rule_traces=traces,
        probability_result=None, analysis_engine_execution_count=0, executed_analysis_engines=[],
        data_cutoff_at=fixture['analysis_at'], source_data_sha256='synthetic',
        horizon_volatility=contexts[horizon]['context_sigma'],
        source_data_sha256_by_stage={h:c['source_data_sha256'] for h,c in contexts.items()},
        details={'stage_order':list(contexts)})


def proposal_from_run(run):
    p=run['plan']
    return TradeProposal(p['symbol'],p['side'],p['time_horizon'],p['entry'],100.,1.,p['stop_loss'],p['take_profit'],'market')


def single_analysis(run):
    snapshot={k:run['plan'][k] for k in ('symbol','side','entry','take_profit','stop_loss','analysis_at')}
    snapshot['time_horizon']=run['plan']['time_horizon']
    from datetime import datetime
    snapshot.update(served.original._analysis_stamp(run['plan']['time_horizon'],
        request_received_at=datetime.fromisoformat(snapshot['analysis_at']),
        effective_analysis_at=datetime.fromisoformat(snapshot['analysis_at'])))
    return served.render_lab4(proposal_from_run(run),deepcopy(run),snapshot,include_internal_runtime=True)


class Lab4ReplacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {(side,h):synthetic_run(h,side) for side in ('long','short') for h in runtime.HOURS}

    def test_frozen_inference_package_and_model_match(self):
        model = runtime.load_model()
        self.assertEqual(model['engine_version'], LAB4)
        self.assertEqual(sha256((runtime.PACKAGE/'model.json').read_bytes()).hexdigest(),runtime.MODEL_SHA)
        for path in runtime.PACKAGE.glob('*.py'):
            self.assertNotIn('def fit(', path.read_text())
            self.assertNotIn('from lab ', path.read_text())

    def test_volume_operand_preserves_the_original_traced_number(self):
        run=deepcopy(self.runs[('long','intraday_short')])
        trace=next(t for t in run['stage_rule_traces']['intraday_short'] if t['rule_id']=='LIB-CAND-RELATIVE-VOLUME-001')
        traced=math.nextafter(trace['outputs']['relative_horizon_volume'],math.inf)
        trace['outputs']['relative_horizon_volume']=traced
        request,_=runtime.request_from_run(run)
        self.assertEqual(request['features']['volume'],traced)

    def test_six_operands_are_available_from_the_real_closed_candle_pipeline(self):
        from tests.test_sequential_production_contract import synthetic_candles
        from multiscale_feature_runtime import build_stage_context, STAGE_PROFILES
        for horizon in runtime.HOURS:
            for side in ('long','short'):
                candles,at=synthetic_candles(horizon)
                plan=dict(symbol='BTCUSDT',side=side,entry=100.,take_profit=102. if side=='long' else 98.,
                          stop_loss=99. if side=='long' else 101.,time_horizon=horizon,
                          horizon_seconds=STAGE_PROFILES[horizon]['horizon_seconds'],analysis_at=at.isoformat())
                context=build_stage_context(plan,candles)
                run=dict(plan=plan,stage_contexts={horizon:context},stage_rule_traces={horizon:context['rule_traces']})
                request,_=runtime.request_from_run(run)
                self.assertEqual(set(request['features']),set(runtime.FIELDS))

    def test_historical_contract_and_model_identity_are_not_replaced_by_current_values(self):
        import app
        old=app.recommendation_version_contract({'recommendation_engine_version':V11,
            'recommendation_data_contract_version':'data-contract-v0.32-target-horizon-attribution'}, {})
        self.assertEqual(old['engine_version'],V11)
        self.assertEqual(old['scoring_version'],SCORING_BY_ENGINE[V11])
        self.assertEqual(old['data_contract_version'],'data-contract-v0.32-target-horizon-attribution')
        contract=result_version_contract({'engine_version':V11},{'engine_version':LAB4,'model_sha256':runtime.MODEL_SHA,'scoring_version':'x'})
        self.assertNotIn('model_sha256',contract)

    @unittest.skipUnless(os.getenv('LAB4_VERIFY_LAB_PARITY')=='1','local lab parity explicitly enabled')
    def test_exact_native_lab_parity_all_sides_horizons_and_asymmetric_plans(self):
        sys.path.insert(0,str(ROOT.parent/'trading_lab'))
        from lab.preserved_engine_service import analyze
        for key,run in self.runs.items():
            with self.subTest(key=key):
                actual, request, _ = runtime.predict_from_run(run)
                expected = analyze(runtime.load_model(),request)
                for k in ('tp','sl','unresolved'):
                    self.assertAlmostEqual(actual['probabilities'][k],expected['probabilities'][k],places=12)
                self.assertEqual(actual['observational_contribution_trace'], expected['observational_contribution_trace'])
                self.assertEqual(actual['inherited_lab2'],expected['inherited_lab2'])
                for k in ('tp','sl'):
                    self.assertAlmostEqual(actual['reachability'][k]['touch'],expected['reachability'][k]['touch'],places=12)
                self.assertEqual([r['neighbor_sha256'] for r in actual['reachability']['contributions']],
                                 [r['neighbor_sha256'] for r in expected['reachability']['contributions']])

    def test_one_new_forecast_and_compact_receipt_keep_all_operands(self):
        for key,run in self.runs.items():
            with self.subTest(key=key):
                before=deepcopy(run)
                result=single_analysis(run)
                self.assertEqual(run,before)
                self.assertEqual(result['engine_version'],LAB4)
                self.assertNotIn('engine_transition',result)
                self.assertNotIn('reference',result['engine_inference'])
                compact=compact_observation_snapshot(result['snapshot'])
                self.assertLessEqual(len(json.dumps(compact,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode()),MAX_COMPACT_SNAPSHOT_BYTES)
                receipt=compact['engine_inference']
                self.assertEqual(receipt['prediction_input']['features'],result['engine_inference']['prediction_input']['features'])
                self.assertEqual(receipt['prediction']['observational_contribution_trace'],result['engine_inference']['prediction']['observational_contribution_trace'])
                self.assertEqual(receipt['prediction']['engine_version'],LAB4)
                self.assertNotIn('reference',receipt)
                self.assertIsNone(result['probability_ranges']['tp']['low'])

    def test_missing_or_future_data_blocks_instead_of_falling_back(self):
        run = deepcopy(self.runs[('long','intraday_short')])
        del run['stage_contexts']['intraday_short']['feature_values'][runtime.FIELDS['cvd'][0]+'::'+runtime.FIELDS['cvd'][1]]
        with self.assertRaisesRegex(ValueError,'operand_missing'):
            runtime.predict_from_run(run)
        run = deepcopy(self.runs[('long','intraday_short')])
        run['stage_contexts']['intraday_short']['data_cutoff_at_ms'] = 9e15
        with self.assertRaisesRegex(ValueError,'cutoff'):
            runtime.predict_from_run(run)

    def test_selected_engine_failure_never_calls_v011(self):
        run=self.runs[('long','intraday_short')]
        from datetime import datetime
        with patch.object(served,'ENGINE_VERSION',LAB4), patch.object(served,'build_production_probability_run',return_value=deepcopy(run)), patch.object(served.original,'analyze_trade',side_effect=AssertionError('old engine forbidden')) as old, patch('lab4_runtime.predict_from_run',side_effect=ValueError('broken_model')):
            with self.assertRaises(served.NewEngineAnalysisError) as caught:
                served.analyze_trade(proposal_from_run(run),effective_analysis_at=datetime.fromisoformat(run['plan']['analysis_at']))
            self.assertFalse(caught.exception.details['fallback_used'])
            old.assert_not_called()

    def test_real_collection_route_does_not_execute_the_v011_analyzer_or_forecast(self):
        from datetime import datetime
        for key,fixture in self.runs.items():
            with self.subTest(key=key):
                def context(plan,candles,**kwargs):
                    h=plan['time_horizon']
                    return {**deepcopy(fixture['stage_contexts'][h]),'rule_traces':deepcopy(fixture['stage_rule_traces'][h])}
                with patch.object(served,'ENGINE_VERSION',LAB4), patch.object(served.original,'analyze_trade',side_effect=AssertionError('v011 analyze forbidden')) as old, patch('sequential_production_runtime.empirical_probabilities',side_effect=AssertionError('v011 forecast forbidden')) as old_forecast, patch('sequential_production_runtime.fetch_klines_range',return_value=[]) as fetch, patch('sequential_production_runtime.build_stage_context',side_effect=context) as build, patch('lab4_runtime.predict_from_run',wraps=runtime.predict_from_run) as selected:
                    result=served.analyze_trade(proposal_from_run(fixture),effective_analysis_at=datetime.fromisoformat(fixture['plan']['analysis_at']))
                old.assert_not_called();old_forecast.assert_not_called()
                self.assertEqual(selected.call_count,1)
                self.assertEqual(fetch.call_count,len(fixture['stage_contexts']))
                self.assertEqual(build.call_count,len(fixture['stage_contexts']))
                self.assertEqual(result['executed_analysis_engines'],[LAB4])
                self.assertNotIn('engine_transition',result)
                self.assertNotIn('v011_reference_executed',result)

    def test_rollback_selects_unmodified_v011_path(self):
        expected = {'engine_version':V11,'tp_probability':.6}
        with patch.object(served,'ENGINE_VERSION',V11), patch.object(served.original,'analyze_trade',return_value=expected) as original:
            self.assertIs(served.analyze_trade(object()),expected)
            original.assert_called_once()

    def test_each_saved_version_uses_its_own_scoring_contract(self):
        for version in (V11,LAB4):
            actual = result_version_contract({'engine_version':version},{'engine_version':LAB4,'scoring_version':'wrong'})
            self.assertEqual(actual['engine_version'],version)
            self.assertEqual(actual['scoring_version'],SCORING_BY_ENGINE[version])
        from versioning import scoring_version_for_legacy_engine
        self.assertEqual(scoring_version_for_legacy_engine(V11),SCORING_BY_ENGINE[V11])

    def test_global_selection_reaches_users_limit_worker_bots(self):
        script = ('import app,autonomous_contest as b,limit_production_analysis as l,limit_lifecycle_runtime as a,versioning as v; '
                  'assert app.analyze_trade is b.analyze_trade is l.analyze_trade is a.analyze_trade; '
                  'assert v.ENGINE_VERSION==b.EMPIRICAL_ENGINE_VERSION==l.LIMIT_PRODUCTION_ENGINE_VERSION; print(v.ENGINE_VERSION)')
        process = subprocess.run([sys.executable,'-B','-c',script],cwd=ROOT,capture_output=True,text=True,
                                 env={**os.environ,'ANALYSIS_ENGINE_RELEASE':'v0.12-lab.4'})
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(process.stdout.strip(),LAB4)

    def test_unknown_release_prevents_startup(self):
        process = subprocess.run([sys.executable,'-B','-c','import analysis_engine_selection'],cwd=ROOT,capture_output=True,text=True,
                                 env={**os.environ,'ANALYSIS_ENGINE_RELEASE':'wrong'})
        self.assertNotEqual(process.returncode,0)
        self.assertIn('unsupported_ANALYSIS_ENGINE_RELEASE',process.stderr)

    def test_approved_release_default_and_explicit_rollback(self):
        environment = {key:value for key,value in os.environ.items()
                       if key != 'ANALYSIS_ENGINE_RELEASE'}
        script = ('import versioning as v, autonomous_contest as b; '
                  'assert v.ENGINE_VERSION == b.EMPIRICAL_ENGINE_VERSION; '
                  'print(v.ENGINE_VERSION)')
        for setting, expected in ((None,LAB4), ('v0.11',V11)):
            selected = dict(environment)
            if setting:
                selected['ANALYSIS_ENGINE_RELEASE'] = setting
            process = subprocess.run([sys.executable,'-B','-c',script],cwd=ROOT,
                                     capture_output=True,text=True,env=selected)
            self.assertEqual(process.returncode,0,process.stderr)
            self.assertEqual(process.stdout.strip(),expected)

    def test_observation_change_of_engine_cannot_manufacture_deterioration(self):
        from operation_observation_learning import observation_closure_advisory
        points = [dict(engine_version=V11,tp_probability=.8,sl_probability=.2,checkpoint_code='old')]
        points += [dict(engine_version=LAB4,tp_probability=.45,sl_probability=.55,checkpoint_code='new')]
        result = observation_closure_advisory(points)
        self.assertEqual(result['edge_change'],0.)
        self.assertEqual(result['recent_checkpoint_count'],1)
        self.assertEqual(result['other_engine_controls_excluded'],1)
        # A rollback also starts a new sequence, rather than jumping back in time.
        points += [dict(engine_version=V11,tp_probability=.3,sl_probability=.7,checkpoint_code='rollback')]
        result = observation_closure_advisory(points)
        self.assertEqual(result['edge_change'],0.)
        self.assertEqual(result['recent_checkpoint_count'],1)

    def test_bot_records_only_the_selected_forecast_and_reads_old_formats(self):
        import autonomous_contest as contest
        import autonomous_scan_audit as audit
        from tests.test_autonomous_contest import candidate
        item=candidate(edge=.1)
        item.analysis_result={'engine_version':LAB4,'model_sha256':runtime.MODEL_SHA,'engine_inference':{'prediction_input_sha256':'abc'}}
        encoded=audit.encode_audit([audit.candidate_record(item,contest.PARTICIPANT_POLICIES[1])],contest.PARTICIPANT_POLICIES[1])
        row=audit.decode_audit(encoded)['analyses'][0]
        self.assertEqual(row['model_sha256'],runtime.MODEL_SHA)
        self.assertEqual(row['forecast_input_sha256'],'abc')
        self.assertFalse(any(key.startswith('reference_') for key in row))
        legacy={'version':audit.AUDIT_VERSION,'fields':['symbol','tp_probability','reference_tp_probability'],'rows':[['BTCUSDT',.5,.6]]}
        self.assertEqual(audit.decode_audit(legacy)['analyses'][0]['reference_tp_probability'],.6)

    def test_v011_and_v12_full_records_are_excluded_from_expiry_compaction(self):
        import app
        class Db:
            def execute(self,query,params):
                self.query,self.params=query,params
                return type('Cursor',(),{'rowcount':0})()
        db=Db();app.compact_expired_unselected_analyses(db)
        self.assertIn('engine_version NOT IN',db.query)
        self.assertIn(V11,db.params);self.assertIn(LAB4,db.params)

    def test_user_api_persists_one_selected_analysis(self):
        import app
        from tests.test_limit_production_analysis import RecommendationDb, connect_factory
        run = self.runs[('long','intraday_short')]
        result = single_analysis(run)
        result.pop('_internal_runtime',None)
        db = RecommendationDb()
        with patch.object(app,'current_user',return_value={'id':7}),patch.object(app,'connect',connect_factory(db)),patch.object(app,'analyze_trade',return_value=result):
            response = app.analyze(app.TradePayload(symbol='BTCUSDT',side='long',time_horizon='intraday_short',
                entry=100.,margin=100.,leverage=1.,stop_loss=99.,take_profit=102.),session_token='test')
        query,params = next((q,p) for q,p in db.queries if 'INSERT INTO recommendations' in q)
        self.assertEqual(params[18],LAB4)
        self.assertEqual(params[20],SCORING_BY_ENGINE[LAB4])
        payload = json.loads(params[17])
        self.assertNotIn('engine_transition',payload)
        self.assertEqual(payload['engine_inference']['prediction']['engine_version'],LAB4)
        self.assertEqual(sum('INSERT INTO recommendations' in q for q,p in db.queries),1)
        self.assertEqual(payload['version_contract']['engine_version'],LAB4)
        self.assertEqual(payload['version_contract']['model_sha256'],runtime.MODEL_SHA)

    def test_limit_preview_keeps_one_selected_forecast(self):
        from limit_production_analysis import analyze_limit_trade
        from tests.test_limit_production_analysis import pending_proposal
        result = single_analysis(self.runs[('long','intraday_short')])
        answer = analyze_limit_trade(pending_proposal(),price_loader=lambda *a,**k:100.,
                                    conditional_analyzer=lambda *a,**k:deepcopy(result))
        self.assertEqual(answer['engine_version'],LAB4)
        self.assertNotIn('engine_transition',answer)
        self.assertEqual(answer['engine_inference']['prediction']['engine_version'],LAB4)
        self.assertEqual(answer['tp_probability'],result['tp_probability'])

    @unittest.skipUnless(os.getenv('LAB4_VERIFY_LAB_PARITY')=='1','local lab parity explicitly enabled')
    def test_all_app_pairs_share_the_same_native_inference_contract(self):
        sys.path.insert(0,str(ROOT.parent/'trading_lab'))
        from lab.preserved_engine_service import analyze
        from autonomous_contest import SYMBOLS
        for symbol in SYMBOLS:
            for side in ('long','short'):
                for horizon in runtime.HOURS:
                    if symbol=='BTCUSDT': continue  # Already compared in full above.
                    with self.subTest(symbol=symbol,side=side,horizon=horizon):
                        run = synthetic_run(horizon,side,symbol=symbol)
                        actual, request, _ = runtime.predict_from_run(run)
                        expected = analyze(runtime.load_model(),request)
                        for k in ('tp','sl','unresolved'):
                            self.assertAlmostEqual(actual['probabilities'][k],expected['probabilities'][k],places=12)
                        self.assertEqual(actual['observational_contribution_trace'],expected['observational_contribution_trace'])
                        for k in ('tp','sl'):
                            self.assertAlmostEqual(actual['reachability'][k]['touch'],expected['reachability'][k]['touch'],places=12)


if __name__=='__main__': unittest.main()
