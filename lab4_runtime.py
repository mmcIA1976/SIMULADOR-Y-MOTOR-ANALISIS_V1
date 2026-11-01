"""Portable, frozen lab.4 inference from closed market inputs.

No outcomes, training, database access, lab imports, provider requests or fallback.
Only the selected model produces a forecast; no comparison forecast is generated.
"""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
import json
import math
from pathlib import Path

import empirical_temporal_engine as empirical
from engine_lab4 import correction_predictor as binary
from engine_lab4 import preserved_temporal_engine as preserved
from engine_lab4 import temporal_engine as temporal
from engine_lab4 import observational_context as common
from analysis_engine_selection import LAB4, SCORING_BY_ENGINE

MODEL_SHA = '1061816d0899ab541e61bf6e3b789dcb08d7328091f1a4ce2285bf1e59576a32'
PACKAGE = Path(__file__).resolve().parent / 'engine_lab4'
FIELDS = {
    'ema_slope': ('LIB-CAND-EMA-TREND-001', 'side_adjusted_slope_atr'),
    'ema_price': ('LIB-CAND-EMA-TREND-001', 'side_adjusted_close_vs_ema50_log'),
    'cvd': ('LIB-CAND-CVD-SLOPE-001', 'side_adjusted_normalized_cvd_slope'),
    'volume': ('LIB-CAND-RELATIVE-VOLUME-001', 'relative_horizon_volume'),
    'extension': ('LIB-CAND-ATR-EXTENSION-001', 'side_adjusted_extension_atr'),
    'path': ('M4-RULE-PATH-STRUCTURE-001', 'directional_path_efficiency_h'),
}
HOURS = {'intraday_short': 4, 'intraday_wide': 24, 'short_swing': 168}


@lru_cache(maxsize=1)
def load_model():
    raw = (PACKAGE / 'model.json').read_bytes()
    if sha256(raw).hexdigest() != MODEL_SHA:
        raise ValueError('lab4_model_integrity_failed')
    manifest = json.loads((PACKAGE / 'manifest.json').read_bytes())
    for name, expected in manifest['files'].items():
        path = PACKAGE / name
        if path.parent != PACKAGE or sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('lab4_inference_package_integrity_failed')
    model = json.loads(raw)
    if model['engine_version'] != LAB4 or model['definition'] != preserved.DEFINITION:
        raise ValueError('lab4_model_contract_invalid')
    if model['artifact_sha256'] != empirical.load_production_artifact()['artifact_sha256']:
        raise ValueError('lab4_reference_artifact_changed')
    if model['binary_model']['parent_model']['selected_variant'] != 'frozen-66':
        raise ValueError('lab4_unapproved_variant')
    return model


def request_from_run(run):
    plan = run['plan']; horizon = plan['time_horizon']
    contexts = run['stage_contexts']; context = contexts[horizon]
    traces = {t['rule_id']: t for t in run['stage_rule_traces'][horizon]}
    features, times, provenance = {}, {}, {}
    cutoff = context['data_cutoff_at_ms'] / 1000
    for field, (rule, output) in FIELDS.items():
        flat = context.get('feature_values', {}).get(rule + '::' + output)
        traced = traces.get(rule, {}).get('outputs', {}).get(output)
        if field == 'volume' and flat is None:
            log_volume = context.get('feature_values', {}).get(rule + '::log_relative_horizon_volume')
            flat = math.exp(log_volume) if common.finite(log_volume) else None
        if not common.finite(flat) or not common.finite(traced) or not math.isclose(flat,traced,rel_tol=1e-12,abs_tol=1e-12):
            raise ValueError('lab4_observational_operand_missing_or_mismatch:' + field)
        features[field] = traced; times[field] = cutoff
        provenance[field] = {'stage': horizon, 'rule_id': rule, 'output': output,
                             'data_cutoff_at_ms': context['data_cutoff_at_ms'],
                             'source_data_sha256': context['source_data_sha256']}
    request = dict(symbol=plan['symbol'], side=plan['side'], horizon=horizon,
                   entry=plan['entry'], take_profit=plan['take_profit'], stop_loss=plan['stop_loss'],
                   analysis_at=plan['analysis_at'], stage_contexts=deepcopy(contexts),
                   features=features, operand_timestamps=times, evidence_kind='captured_analysis')
    return request, provenance


def stages_and_rates(request, artifact):
    """Reproduce the lab's selected neighborhoods using v0.11's scalar code."""
    at = common.epoch(request['analysis_at']); target = request['horizon']
    dt, ds = empirical.plan_log_distances(side=request['side'], entry=request['entry'],
                                         take_profit=request['take_profit'], stop_loss=request['stop_loss'])
    by_id = {a['id']: a for a in artifact['analogs']}
    stages, rates, support = [], [], []
    for stage in empirical.selected_stage_order(target):
        override = artifact['target_horizon_rule_profiles'][target]['overrides'].get(stage)
        names = override['feature_names'] if override else artifact['feature_names'][stage]
        scaling = override['feature_scaling'] if override else artifact['feature_scaling'][stage]
        values = empirical._current_feature_map(stage, request['stage_contexts'], names)
        current = empirical._standardize(values, names, scaling)
        selected, quality = empirical._nearest_eligible(artifact=artifact, horizon=stage,
            current=current, symbol=request['symbol'], tp_distance=dt, sl_distance=ds,
            analysis_epoch=at, target_override=override)
        if len(selected) < int(artifact['selection'].get('absolute_minimum_analogs', 12)):
            raise ValueError('sparse_frozen_neighbors')
        end_step = empirical.STAGE_BOUNDS[stage][1]
        if any(float(by_id[x['analog_id']]['analysis_epoch']) + end_step*300 > at for x in selected):
            raise ValueError('historical_path_not_finished_before_decision')
        # The frozen lab sums each class with fsum; production v0.11 used +=.
        # Reproduce the frozen lab arithmetic directly inside the new engine.
        bandwidth = max(.25, selected[-1]['distance']) if selected else 1.
        weights = [math.exp(-.5*(row['distance']/bandwidth)**2) for row in selected]
        counts = [math.fsum(w for w,row in zip(weights,selected) if row['label']==name)
                  for name in empirical.CONDITIONAL_CLASSES]
        denominator = math.fsum(counts)+1.5
        tempered = [((n+.5)/denominator)**(1/float(artifact['selection'].get('probability_temperature',1))) for n in counts]
        total = math.fsum(tempered)
        p = dict(zip(empirical.CONDITIONAL_CLASSES,(n/total for n in tempered)))
        weight_sum = math.fsum(weights)
        support.append(dict(stage_id=empirical.STAGE_PROFILES[stage]['stage_id'],time_horizon=stage,
            label=empirical.STAGE_PROFILES[stage]['label'],interval=empirical.STAGE_PROFILES[stage]['interval'],
            current_feature_values=values, **quality,
            effective_sample_size=weight_sum**2/math.fsum(w*w for w in weights) if weights else 0.,
            weighted_outcome_counts=dict(zip(empirical.CONDITIONAL_CLASSES,counts)),
            dirichlet_prior_per_class=.5, probability_temperature=float(artifact['selection'].get('probability_temperature',1)),
            posterior_alpha=dict(zip(empirical.CONDITIONAL_CLASSES,(n+.5 for n in counts))),
            bandwidth=bandwidth,furthest_selected_distance=selected[-1]['distance'] if selected else None,
            geometry_application=dict(method='exact_barrier_replay_on_historical_future_paths',
                                      tp_log_distance=dt,sl_log_distance=ds)))
        identity = common.digest([(str(x['analog_id']), 0 if x['orientation']=='long' else 1) for x in selected])
        stages.append({'stage': stage, 'selected': len(selected),
                       'conditional': [p[k] for k in empirical.CONDITIONAL_CLASSES], 'neighbor_sha256': identity})
        bandwidth = max(.25, selected[-1]['distance']) if selected else 1.
        totals = [0., 0.]; second = [0., 0.]; immature = 0
        for row in selected:
            analog = by_id[row['analog_id']]
            if float(analog['analysis_epoch']) + HOURS[target]*3600 >= at:
                immature += 1; continue
            if row['label'] == empirical.CONDITIONAL_CLASSES[2]:
                continue
            label = 0 if row['label'] == empirical.CONDITIONAL_CLASSES[0] else 1
            weight = math.exp(-.5*(row['distance']/bandwidth)**2)
            totals[label] += weight
            # After TP, query the SL frontier; after SL, query the TP frontier.
            direction = ('down_frontier' if row['orientation']=='long' else 'up_frontier') if label == 0 else (
                'up_frontier' if row['orientation']=='long' else 'down_frontier')
            step = empirical._first_crossing(analog[direction], ds if label==0 else dt)
            if step is not None and step <= empirical.STAGE_BOUNDS[target][1]:
                second[label] += weight
        rates.append(dict(stage=stage, tp_after_sl=(second[1]+.5)/(totals[1]+1),
            sl_after_tp=(second[0]+.5)/(totals[0]+1), weighted_first_counts=totals,
            weighted_second_counts=second, beta_prior=[.5, .5], selected=len(selected),
            immature_paths_excluded=immature, neighbor_sha256=identity, neighborhood_verified=True))
    return stages, rates, support


def predict_from_run(run):
    model = load_model(); request, provenance = request_from_run(run)
    at = common.epoch(request['analysis_at'])
    if at <= common.epoch(model['frozen_at']):
        raise ValueError('preserved_final_model_cannot_score_earlier_analysis')
    for context in request['stage_contexts'].values():
        certs = [t.get('outputs', {}) for t in context.get('data_quality', {}).get('traces', [])
                 if t.get('rule_id') == 'LIB-CAND-DATA-FRESHNESS-001']
        if len(certs) != 1:
            raise ValueError('execution_context_freshness_not_certified')
        cutoff = certs[0].get('latest_closed_candle_ms'); limit = certs[0].get('freshness_limit_ms')
        if not common.finite(cutoff) or not common.finite(limit) or not 0 <= at*1000-cutoff <= limit:
            raise ValueError('stored_context_stale_at_execution')
        if context['data_cutoff_at_ms'] > at*1000:
            raise ValueError('causal_stage_cutoff_missing_or_future')
    stages, rates, support = stages_and_rates(request, empirical.load_production_artifact())
    original = temporal.cumulative(stages)[request['horizon']]
    parent = binary.apply_frozen(model['binary_model'], dict(forecast_engine=empirical.ENGINE_VERSION,
        analysis_at=request['analysis_at'], side=request['side'], horizon=request['horizon'],
        features=request['features'], operand_timestamps=request['operand_timestamps'],
        forecast_probabilities=dict(tp=original[0],sl=original[1],unresolved=original[2])))
    prediction = preserved.predict(stages, parent['probabilities']['tp'], model['time_model'])
    prediction.update(model_sha256=MODEL_SHA, analysis_at=request['analysis_at'],
        support_stages=support,
        reachability=temporal.marginal_reachability(prediction, rates),
        observational_contribution_trace=parent['contribution_trace'],
        excluded_postanalysis_fields=parent['excluded_postanalysis_fields'],
        evaluation_mode='new_analysis_after_model_freeze', evidence_kind='captured_analysis')
    return prediction, request, provenance
