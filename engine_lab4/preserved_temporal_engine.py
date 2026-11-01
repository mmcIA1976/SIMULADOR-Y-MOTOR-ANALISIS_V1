# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
from . import temporal_engine as base


VERSION = 'lab-preserved-direction-temporal-v1'


ENGINE_VERSION = 'TP-SL-EXPERIMENTAL-v0.12-lab.4'


DEFINITION = dict(method='frozen_lab2_cause_shared_resolution_hazard',
    frozen_direction='exact_same_lab2_score_no_direction_refit',
    assumptions='lab2_TP_SL_ratio_preserved_conditionally_on_resolution_at_each_stage',
    objective='joint_three_class_log_loss_plus_20_half_squared_offsets',
    offset_bounds=[-3., 3.], ridge=20., minimum_records=20, minimum_episodes=5.,
    maximum_iterations=160, gradient_tolerance=1e-8,
    chronology='earlier_own_horizon_plus_one_own_horizon_embargo',
    controls='original_v011_and_exact_saved_lab2; no_grid_no_post_result_selection')


def validate_q(q):
    if type(q) not in (float, int) or not math.isfinite(q) or not 0 <= q <= 1:
        raise ValueError('preserved_lab2_probability_invalid')
    return float(q)


def hazards(stages, offsets):
    base.cumulative(stages)
    if len(offsets) != 3 or any(not math.isfinite(x) or abs(x) > 3 for x in offsets):
        raise ValueError('preserved_time_offsets_invalid')
    result = []
    for i, stage in enumerate(stages):
        value = 1-stage['conditional'][2]
        if value in (0., 1.): new = value
        else:
            x = math.log(value/(1-value))+offsets[i]
            new = 1/(1+math.exp(-x))
        result.append(new)
    return result


def split_mass(q, mass):
    tp = q*mass; sl = mass-tp
    # Preserve even a one-ULP strict preference, without changing mass.
    if q > .5 and tp <= sl: tp = math.nextafter(mass/2, math.inf); sl = mass-tp
    if q < .5 and tp >= sl: tp = math.nextafter(mass/2, -math.inf); sl = mass-tp
    return tp, sl


def predict(stages, q, model):
    q = validate_q(q); values = hazards(stages, model['offsets'])
    original = base.cumulative(stages); output = []; traces = []
    for i, (stage, resolved) in enumerate(zip(stages, values)):
        tp, sl = split_mass(q, resolved)
        conditional = [tp, sl, 1-resolved]
        output.append(dict(stage=stage['stage'], conditional=base.probability_vector(conditional)))
        old = stage['conditional']
        traces.append(dict(stage=stage['stage'], baseline=old, probabilities=conditional,
            delta_pp=[100*(a-b) for a, b in zip(conditional, old)],
            frozen_lab2_q=q, direction_refitted=False, time_logit_offset=model['offsets'][i],
            prior_training_n=model.get('training_n', 0), prior_episode_mass=model.get('episode_mass', 0),
            fallback_reason=model.get('fallback_reason')))
    curve = base.cumulative(output); horizon = stages[-1]['stage']; p = curve[horizon]
    # Accumulation roundoff must never silently reverse an inherited decision.
    tp, sl = split_mass(q, p[0]+p[1]); p = [tp, sl, p[2]]
    curve[horizon] = base.probability_vector(p)
    conditional_q = p[0]/(p[0]+p[1]) if p[0]+p[1] else q
    if abs(conditional_q-q) > 1e-12 or (p[0] > p[1]) != (q > .5) or (p[0] < p[1]) != (q < .5):
        raise ValueError('preserved_lab2_direction_changed')
    return dict(engine_version=ENGINE_VERSION, target='TP_SL_same_plan_including_no_resolution',
        probabilities=dict(tp=p[0], sl=p[1], unresolved=p[2]),
        decision_probabilities=dict(tp_before_sl_within_horizon=p[0], sl_before_tp_within_horizon=p[1],
            neither_before_expiry=p[2], resolution_within_horizon=p[0]+p[1]),
        probability_curve={h: dict(tp=v[0], sl=v[1], unresolved=v[2]) for h, v in curve.items()},
        original_probability_curve=original, corrected_stages=output, stage_traces=traces,
        inherited_lab2=dict(q=q, recovered_ratio=conditional_q, absolute_error=abs(conditional_q-q),
            preference='tp' if q > .5 else 'sl' if q < .5 else 'tie', direction_refitted=False),
        production_effect='none')
