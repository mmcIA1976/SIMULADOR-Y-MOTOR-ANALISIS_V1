# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical


STAGES = ('C6', 'context', 'LONG_EMA50', 'SHORT_response', 'LONG4h_ratio')


def stages(row):
    """Recover the actual applied stack, excluding the rejected book experiment."""
    context = row['weight_details']['pooled-all']
    q = row['q0']; out = []
    for stage, target in (
        ('C6', context['base']), ('context', context['score']),
        ('LONG_EMA50', row['rebound_details']['price-recovery']['score']),
        ('SHORT_response', row['response_details']['response-sign']['score']),
        ('LONG4h_ratio', row['extension_details']['four-hour-control']['score'])):
        out.append(dict(stage=stage, base=q, score=target, delta=target-q))
        q = target
    if abs(q-row['scores']['current']) > 1e-12:
        raise ValueError('correction_archived_stack_not_reproduced')
    return out


def gate_key(row, stage, delta):
    return '|'.join((stage, row['side'], row['horizon'], 'up' if delta > 0 else 'down'))


def predict(row, model):
    q = row['q0']; trace = []
    for old in stages(row):
        if old['stage'] == 'C6':
            target = old['score']
        elif old['stage'] == 'context':
            detail = row['weight_details']['pooled-all']
            target = (1-detail['weight'])*q+detail['weight']*detail['frequency_used'] if detail.get('reason') is None else q
        else:
            target = min(1., max(0., q+old['delta']))
        delta = target-q
        key = gate_key(row, old['stage'], delta)
        group = model['groups'].get(key, {})
        alpha = group.get('alpha', 1.)
        after = min(1., max(0., q+alpha*delta))
        trace.append(dict(stage=old['stage'], base=q, raw_target=target, alpha=alpha, score=after,
                          group=key, reason=group.get('reason', 'no_earlier_group')))
        q = after
    return q, trace
