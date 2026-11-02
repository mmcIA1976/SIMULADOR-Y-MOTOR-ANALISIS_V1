"""Derived lab.4 learning attribution; never changes a saved prediction/model.

Correction steps are joint and sequential. Participation of an operand is not
an independently measured causal contribution of its rule.
"""
from copy import deepcopy
from analysis_engine_selection import LAB4
from observational_learning_base import fixed_horizon_outcome_from_evidence, PLAN_RESULT_TO_OUTCOME

CONTRACT = 'lab4-frozen-correction-attribution-v1'


def enhance_rule_learning(snapshot, legacy, *, plan_result, operation=None, evidence=None):
    if snapshot.get('engine_version') != LAB4:
        return legacy
    result = deepcopy(legacy)
    inference = snapshot.get('engine_inference') or {}
    request = inference.get('prediction_input') or {}
    prediction = inference.get('prediction') or {}
    provenance = inference.get('feature_provenance') or {}
    features = request.get('features') or {}
    by_rule = {}
    for field, source in provenance.items():
        if field not in features or not isinstance(source, dict) or not source.get('rule_id'):
            continue
        by_rule.setdefault(source['rule_id'], {})[field] = {
            **deepcopy(source), 'value': features[field],
            'operand_timestamp': (request.get('operand_timestamps') or {}).get(field),
        }
    active = result.setdefault('rules', {})
    observations = result.setdefault('observational_rules', {})
    partial = result.setdefault('partially_observational_rules', {})
    for rule_id, operands in by_rule.items():
        entry = active.get(rule_id) or observations.pop(rule_id, None)
        if entry is None:
            # Missing original attribution is explicit; don't invent a trace.
            entry = {'stage_traces': [], 'rule_status': 'source_attribution_missing'}
        baseline = rule_id in active
        promoted = sorted({source['output'] for source in operands.values()})
        entry['lab4_inputs'] = deepcopy(operands)
        entry['lab4_correction_input_outputs'] = promoted
        entry['probability_effect'] = ('analog_distance_and_frozen_lab4_correction_input'
            if baseline else 'frozen_lab4_correction_input')
        entry['effect_mode'] = ('empirical_analog_distance_and_frozen_correction'
            if baseline else 'frozen_observational_correction')
        entry['probability_effect_reason'] = (
            'Las lecturas indicadas participan en la corrección congelada de lab.4. '
            'La traza cuantifica pasos conjuntos; no atribuye un efecto causal individual a cada regla.')
        entry['active_probability_outputs'] = sorted(set(entry.get('active_probability_outputs') or []) | set(promoted))
        entry['observational_outputs'] = sorted(set(entry.get('observational_outputs') or []) - set(promoted))
        residual = set()
        for trace in entry.get('stage_traces', []):
            fields = sorted({source['output'] for source in operands.values()
                if source.get('stage') == trace.get('time_horizon')})
            if fields:
                trace['lab4_correction_input_outputs'] = fields
                trace['active_probability_outputs'] = sorted(set(trace.get('active_probability_outputs') or []) | set(fields))
                trace['observational_outputs'] = sorted(set(trace.get('observational_outputs') or []) - set(fields))
                trace['probability_effect'] = entry['probability_effect']
            residual.update(trace.get('observational_outputs') or [])
        active[rule_id] = entry
        observations.pop(rule_id, None)
        if residual:
            partial[rule_id] = dict(stage_traces=deepcopy(entry.get('stage_traces', [])),
                formula_outputs=sorted(residual), probability_effect='none_observation_only_formula_subset')
        else:
            partial.pop(rule_id, None)
    for kind, entries in (('active', active), ('observational', observations),
                           ('partially_observational', partial)):
        result[kind+'_rule_ids'] = sorted(entries)
        result[kind+'_rule_count'] = len(entries)
    result['trace_contract'] = CONTRACT
    result['engine_version'] = LAB4
    result['lab4_correction'] = dict(model_sha256=inference.get('model_sha256'),
        prediction_input_sha256=inference.get('prediction_input_sha256'),
        receipt_sha256=inference.get('receipt_sha256'),
        inputs_by_rule=by_rule,
        contribution_trace=deepcopy(prediction.get('observational_contribution_trace', [])),
        contribution_scope='joint_sequential_steps_not_individual_rule_causal_weights')
    operation = operation or {}
    evidence = evidence or {}
    actual = evidence.get('actual_window') or {}
    requested = evidence.get('requested_window') or {}
    touch = evidence.get('first_plan_touch') or {}
    outcome, source = fixed_horizon_outcome_from_evidence(
        recorded_outcome=PLAN_RESULT_TO_OUTCOME.get(plan_result), plan_result=plan_result,
        analysis_at=snapshot.get('analysis_at'),
        evaluation_expires_at=snapshot.get('evaluation_expires_at'),
        closed_at=operation.get('closed_at'), evidence_status=evidence.get('status'),
        evidence_quality=evidence.get('quality'), evidence_coverage_ratio=evidence.get('coverage_ratio'),
        evidence_start_at=actual.get('first_candle_open_at') or requested.get('started_at'),
        evidence_end_at=actual.get('last_candle_close_at') or requested.get('plan_end_at'),
        first_plan_touch_at=touch.get('touched_at'),
        reconstructed_plan_result=evidence.get('reconstructed_plan_result'))
    result['observed_outcome'] = outcome
    result['observed_outcome_scope'] = 'fixed_analysis_horizon'
    result['observed_outcome_source'] = source
    result['final_operation_result'] = dict(plan_result=plan_result,
        close_reason=operation.get('close_reason'), closed_at=operation.get('closed_at'))
    result['evaluation_window'] = dict(analysis_at=snapshot.get('analysis_at'),
        expires_at=snapshot.get('evaluation_expires_at'))
    return result
