# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical
from . import observational_context as c, actual_close_side_weights as w


def usable(row,field):
    return not w.eligible(row) and row['features']['ema_slope']<=0 and c.finite(row['features'].get(field))


def predict(row,model,parent_score,matched=False):
    reason='outside_adverse_EMA_LONG' if row['side']!='long' or not usable(row,model['field']) else None
    if reason:return parent_score,dict(reason=reason,base=parent_score,delta=0,score=parent_score)
    pkey=w.key(row,w.SPECS['pooled-all']);ckey=pkey+'|'+str(int(row['features'][model['field']]>0))
    child=model['children'].get(ckey);parent=model['parents'].get(pkey)
    if not child or not parent:return parent_score,dict(reason='no_previous_comparable_child',base=parent_score,delta=0,score=parent_score)
    rate=child['TP']/child['n'];parent_rate=parent['TP']/parent['n'];weight=child['n']/(child['n']+20)
    delta=0 if matched else weight*(rate-parent_rate)
    score=min(1,max(0,parent_score+delta))
    return score,dict(reason=None,context=ckey,field=model['field'],value=row['features'][model['field']],
        n=child['n'],TP_previous=child['TP'],child_frequency=rate,parent_n=parent['n'],
        parent_TP=parent['TP'],parent_frequency=parent_rate,weight=weight,delta=delta,base=parent_score,score=score)
