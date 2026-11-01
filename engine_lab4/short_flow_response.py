# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
from . import observational_context as c, actual_close_side_weights as w


def eligible(row):
    return not w.eligible(row) and c.finite(row['features'].get('path'))


def target(row):return row['side']=='short' and row['horizon']=='intraday_wide' and eligible(row)


def response_band(value,cut,intensity=True):
    if value<=0:return 'opposed'
    return 'efficient' if not intensity or cut is None or value>cut else 'modest'


def context_key(row,spec):
    return w.key(row,dict(keys=spec['keys'],side=False,positive_only=False))


def predict(row,model,base,matched=False,sign_model=None):
    if not target(row):return base,dict(reason='outside_SHORT24h_or_missing_response',base=base,delta=0,score=base)
    pkey=context_key(row,model['spec']);cut=(model['cuts'].get(row['horizon']) or {}).get('value')
    band=response_band(row['features']['path'],cut,model['spec']['intensity']);child=model['children'].get(pkey+'|'+band)
    parent=model['parents'].get(pkey)
    if not child or not parent:return base,dict(reason='no_previous_comparable_response',base=base,delta=0,score=base,cut=cut,band=band)
    rate=child['TP']/child['n'];parent_rate=parent['TP']/parent['n'];weight=child['n']/(child['n']+20)
    frequency_source='response_band'
    if sign_model is not None:
        cell=sign_model['children'].get(context_key(row,sign_model['spec'])+'|'+response_band(row['features']['path'],cut,False))
        if not cell:raise ValueError('short_response_sign_parent_missing')
        rate=cell['TP']/cell['n'];frequency_source='sign_only_same_weight'
    if matched:rate=parent_rate;frequency_source='parent_same_weight'
    delta=weight*(rate-parent_rate);score=min(1,max(0,base+delta))
    return score,dict(reason=None,context=pkey,band=band,path=row['features']['path'],cut=cut,n=child['n'],
        TP_previous=child['TP'],frequency_used=rate,parent_n=parent['n'],parent_TP=parent['TP'],parent_frequency=parent_rate,
        weight=weight,base=base,delta=delta,score=score,frequency_source=frequency_source)
