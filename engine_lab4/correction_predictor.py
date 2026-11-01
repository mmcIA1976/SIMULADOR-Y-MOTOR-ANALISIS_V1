# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
from . import observational_context as c, engine_proposal as p, correction_review as r


VERSION = 'lab-correction-gated-model-v1'


ENGINE_VERSION = 'TP-SL-EXPERIMENTAL-v0.12-lab.2'


def archived_row(request, result):
    trace = {x['stage']: x for x in result['contribution_trace']}
    probabilities = request['forecast_probabilities']
    return dict(side=request['side'], horizon=request['horizon'],
        q0=probabilities['tp']/(probabilities['tp']+probabilities['sl']),
        scores={'current': result['raw_observational_score']},
        weight_details={'pooled-all': trace['context']},
        rebound_details={'price-recovery': trace['LONG_EMA50']},
        response_details={'response-sign': trace['SHORT_response']},
        extension_details={'four-hour-control': trace['LONG4h_ratio']})


def apply_frozen(model, request):
    if model.get('version') != VERSION:
        raise ValueError('correction_predictor_model_version')
    if c.epoch(request['analysis_at']) <= c.epoch(model['frozen_at']):
        raise ValueError('correction_final_model_cannot_score_earlier_analysis')
    parent = p.apply_frozen(model['parent_model'], request)
    row = archived_row(request, parent)
    q, trace = r.predict(row, model['gate_model'])
    return dict(engine_version=ENGINE_VERSION, model_sha256=c.digest(model),
        target=parent['target'], probabilities=dict(tp=q, sl=1-q),
        original_horizon_forecast=parent['original_horizon_forecast'],
        parent_probabilities=parent['probabilities'], parent_contribution_trace=parent['contribution_trace'],
        contribution_trace=trace, excluded_postanalysis_fields=parent['excluded_postanalysis_fields'],
        production_effect='none')
