# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
from . import actual_close_side_weights as w


def eligible(row):
    return row['side']=='long' and not w.eligible(row) and row['features']['extension']>=1


def value(row,kind):
    x=row['features']
    return x['ema_slope']/x['extension'] if kind=='ratio' else x['ema_slope'] if kind=='slope' else x['extension']


def context_key(row):return w.key(row,w.SPECS['pooled-all'])


def predict(row,model,base,horizons=('intraday_wide',),matched=False,slope_model=None):
    if not eligible(row) or row['horizon'] not in horizons:return base,dict(reason='outside_registered_scope',base=base,delta=0,score=base)
    cut=(model['cuts'].get(row['horizon']) or {}).get('value')
    if cut is None:return base,dict(reason='insufficient_previous_cut',base=base,delta=0,score=base)
    x=value(row,model['kind']);pkey=context_key(row);child=model['children'].get(pkey+'|'+str(int(x>=cut)));parent=model['parents'].get(pkey)
    if not child or not parent:return base,dict(reason='unseen_previous_context',base=base,delta=0,score=base,value=x,cut=cut)
    rate=child['TP']/child['n'];parent_rate=parent['TP']/parent['n'];weight=child['n']/(child['n']+20);source='ratio_or_field_band'
    if slope_model is not None:
        scut=(slope_model['cuts'].get(row['horizon']) or {}).get('value')
        cell=slope_model['children'].get(pkey+'|'+str(int(value(row,'slope')>=scut))) if scut is not None else None
        if not cell:raise ValueError('extension_slope_control_missing')
        rate=cell['TP']/cell['n'];source='slope_frequency_same_ratio_support'
    if matched:rate=parent_rate;source='parent_frequency_same_support'
    delta=weight*(rate-parent_rate);score=min(1,max(0,base+delta))
    return score,dict(reason=None,context=pkey,kind=model['kind'],value=x,cut=cut,n=child['n'],TP_previous=child['TP'],
        child_frequency=rate,parent_n=parent['n'],parent_TP=parent['TP'],parent_frequency=parent_rate,weight=weight,
        base=base,delta=delta,score=score,frequency_source=source)
