# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
from . import observational_context as c, actual_close_context as a, actual_close_side_weights as w, long_rebound_review as r, short_flow_response as f, long_extension_context as e


ENGINE_VERSION = 'TP-SL-EXPERIMENTAL-v0.12-lab.1'


def temperature(q, alpha):
    value = c.sigmoid(alpha*c.logit(q))
    if q > .5 and value <= .5: return math.nextafter(.5, 1)
    if q < .5 and value >= .5: return math.nextafter(.5, 0)
    return value


def raw_prediction(row, model, variant, shared=None):
    q = temperature(row['q0'], model['c6_scale']); trace = [dict(stage='C6', score=q)]
    q, detail = w.predict(row, model['pooled'], q); trace.append(dict(stage='context', **detail))
    q, detail = r.predict(row, model['rebound'], q); trace.append(dict(stage='LONG_EMA50', **detail))
    q, detail = f.predict(row, model['response'], q); trace.append(dict(stage='SHORT_response', **detail))
    raw, anchor = e.predict(row, model['ratio'], q, horizons=('intraday_short',))
    if variant in ('frequency-calibrated', 'book-calibrated'):
        q, detail = g.predict(row, model['episode'], q, anchor, 'frequencies-only')
    else: q, detail = raw, anchor
    trace.append(dict(stage='LONG4h_ratio', **detail))
    if variant == 'book-calibrated':
        _, local = b.predict(row, model['book_local'], q)
        delta, detail = book_delta(row, shared, local); q = min(1, max(0, q+delta))
        trace.append(dict(stage='shared_book_change', score=q, **detail))
    return q, trace


FIELD_RULES = dict(ema_slope='EMA', ema_price='EMA', cvd='CVD', volume='VOLUME', extension='ATR', path='PATH',
                  book='BOOK', book_slope='BOOK', book_samples='BOOK')


def apply_frozen(model, request):
    if request.get('forecast_engine') != 'TP-SL-EMPIRICAL-ANALOG-v0.11': raise ValueError('proposal_v011_reference_required')
    at = c.epoch(request['analysis_at'])
    if at <= c.epoch(model['frozen_at']): raise ValueError('proposal_final_model_cannot_score_earlier_analysis')
    probabilities = request['forecast_probabilities']; tp, sl = probabilities['tp'], probabilities['sl']
    if not all(c.finite(x) and 0 <= x <= 1 for x in (tp, sl)) or not 0 < tp+sl <= 1+1e-9: raise ValueError('proposal_invalid_base_probabilities')
    if request.get('side') not in ('long', 'short') or request.get('horizon') not in ('intraday_short', 'intraday_wide', 'short_swing'): raise ValueError('proposal_invalid_scope')
    features = {k: v for k, v in request.get('features', {}).items() if c.finite(v)}; times = request.get('operand_timestamps') or {}; excluded = []
    for key, rule in FIELD_RULES.items():
        ts = times.get(key, times.get(rule))
        if c.finite(ts) and ts > at and key in features: features.pop(key); excluded.append(key)
    row = dict(side=request['side'], horizon=request['horizon'], analysis_epoch=at, q0=tp/(tp+sl), features=features,
        book_input=request.get('book_input') or {})
    if model['selected_variant'] == 'frozen-66': variant = 'observational-calibrated'
    else: variant = model['selected_variant']
    raw, trace = raw_prediction(row, model['components'], variant, model.get('shared_book'))
    q = temperature(raw, model['temperature']['scale'])
    return dict(engine_version=ENGINE_VERSION, model_sha256=c.digest(model), target=a.DEFINITION['target'],
        probabilities=dict(tp=q, sl=1-q), raw_observational_score=raw,
        original_horizon_forecast=probabilities, contribution_trace=trace,
        temperature=model['temperature']['scale'], excluded_postanalysis_fields=excluded, production_effect='none')
