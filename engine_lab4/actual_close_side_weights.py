# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
from . import observational_context as c


PRIMARY='side-all'


KEYS=('ema_slope','cvd','strong_flow','volume','extension')


SPECS={PRIMARY:dict(keys=KEYS,side=True,positive_only=False),
       'pooled-all':dict(keys=KEYS,side=False,positive_only=False),
       'side-positive':dict(keys=KEYS[1:],side=True,positive_only=True),
       'side-no-cvd':dict(keys=('ema_slope','volume','extension'),side=True,positive_only=False),
       'side-no-volume':dict(keys=('ema_slope','cvd','strong_flow','extension'),side=True,positive_only=False),
       'side-sign-only':dict(keys=('ema_slope','cvd','volume','extension'),side=True,positive_only=False)}


def eligible(row,positive_only=False):
    f=row['features']
    if row['side'] not in ('long','short') or not all(c.finite(f.get(k)) for k in c.FIELDS) or f['volume']<=0:
        return 'missing_comparable_preanalysis_fields'
    if positive_only and f['ema_slope']<=0:return 'EMA_not_positive_control_scope'
    return None


def key(row,spec):
    f=row['features'];values={**f,'strong_flow':int(abs(f['cvd'])>=.02)}
    bits=''.join(str(int(values[k]>0 if k in ('ema_slope','cvd') else values[k]>=1)) for k in spec['keys'])
    return (row['side']+'|' if spec['side'] else '')+row['horizon']+'|'+bits


def predict(row,model,q,pooled=None):
    reason=eligible(row,model['spec']['positive_only'])
    context=None if reason else key(row,model['spec'])
    cell=model['cells'].get(context)
    if not cell:return q,dict(reason=reason or 'no_previous_context',context=context,n=0,weight=0,base=q,score=q)
    rate=cell['TP_rate']
    if pooled is not None:
        parent=pooled['cells'].get(key(row,pooled['spec']))
        if not parent:raise ValueError('side_pooled_parent_missing')
        rate=parent['TP_rate']
    weight=cell['observation_weight'];score=weight*rate+(1-weight)*q
    return score,dict(reason=None,context=context,n=cell['n'],TP_previous=cell['TP'],frequency_used=rate,
                      weight=weight,base=q,score=score,frequency_source='pooled_context' if pooled is not None or not model['spec']['side'] else 'same_side_context')
