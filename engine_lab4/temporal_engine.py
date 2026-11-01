# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
from . import observational_context as c
STAGES = ("intraday_short", "intraday_wide", "short_swing")


def probability_vector(p):
    if (not isinstance(p, (list, tuple)) or len(p) != 3
            or any(not c.finite(v) or not 0 <= v <= 1 for v in p)
            or abs(math.fsum(p)-1) > 1e-9):
        raise ValueError('temporal_three_class_probability_required')
    return list(p)


def cumulative(stages):
    result = {}; mass = [0., 0., 1.]
    for i, row in enumerate(stages):
        if row['stage'] != STAGES[i]:
            raise ValueError('temporal_stage_order_invalid')
        p = probability_vector(row['conditional'])
        survival = mass[2]
        mass = [mass[0]+survival*p[0], mass[1]+survival*p[1], survival*p[2]]
        mass[2] += 1-math.fsum(mass)
        result[row['stage']] = probability_vector(mass)
    if not stages or len(stages) > 3:
        raise ValueError('temporal_stage_count_invalid')
    return result


def marginal_reachability(result, rates):
    """A generative continuation after the absorbing first-touch decision."""
    stages = result['corrected_stages']
    if len(rates) != len(stages):
        raise ValueError('temporal_second_touch_stage_count')
    first_tp = first_sl = after_tp = after_sl = 0.; survival = 1.
    contributions = []
    for stage, rate in zip(stages, rates):
        if rate['stage'] != stage['stage']:
            raise ValueError('temporal_second_touch_stage_identity')
        tp_after_sl, sl_after_tp = rate['tp_after_sl'], rate['sl_after_tp']
        if any(not c.finite(v) or not 0 <= v <= 1 for v in (tp_after_sl, sl_after_tp)):
            raise ValueError('temporal_second_touch_rate_invalid')
        t, s, n = stage['conditional']; mt, ms = survival*t, survival*s
        first_tp += mt; first_sl += ms
        after_tp += ms*tp_after_sl; after_sl += mt*sl_after_tp
        contributions.append(dict(rate, first_tp_mass=mt, first_sl_mass=ms,
                                  additional_tp_mass=ms*tp_after_sl, additional_sl_mass=mt*sl_after_tp))
        survival *= n
    mt, ms = min(1., first_tp+after_tp), min(1., first_sl+after_sl)
    return dict(tp=dict(touch=mt, not_touch=1-mt, first_touch=first_tp, after_other=after_tp),
                sl=dict(touch=ms, not_touch=1-ms, first_touch=first_sl, after_other=after_sl),
                less_reachable='tp' if mt < ms-1e-12 else 'sl' if ms < mt-1e-12 else 'equal',
                difference_pp=100*abs(mt-ms), contributions=contributions,
                interpretation='hypothetical_path_continuation_after_first_touch_not_a_second_trade_result',
                calibration_status='analog_estimate_not_independently_validated_on_complete_postclose_paths')
