from __future__ import annotations

from m6_remediation_engine import (
    ENGINE_VERSION,
    run_internal_probability_analysis,
)
from m6_remediated_competing_risks import LAYER_VERSION


ACTIVE_ENGINE_VERSION = ENGINE_VERSION
ACTIVE_LAYER_VERSION = LAYER_VERSION

__all__ = (
    "ACTIVE_ENGINE_VERSION",
    "ACTIVE_LAYER_VERSION",
    "run_internal_probability_analysis",
)
