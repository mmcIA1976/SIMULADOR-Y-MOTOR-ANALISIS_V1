# Generated from frozen lab functions by tools/package_lab4.py.
import math
import json
from hashlib import sha256
from datetime import datetime, timezone
from .storage import canonical


KEYS = ('cvd', 'volume', 'extension')


FIELDS = ('ema_slope',) + KEYS


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def finite(x):
    return type(x) in (int, float) and math.isfinite(x)


def epoch(x):
    t = datetime.fromisoformat(str(x).replace('Z', '+00:00'))
    return (t if t.tzinfo is not None else t.replace(tzinfo=timezone.utc)).timestamp()


def logit(q):
    q = min(1-1e-12, max(1e-12, q))
    return math.log(q/(1-q))


def sigmoid(z):
    return 1/(1+math.exp(-max(-50, min(50, z))))
