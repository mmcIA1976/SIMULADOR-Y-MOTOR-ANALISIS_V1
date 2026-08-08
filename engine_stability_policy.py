from __future__ import annotations

from copy import deepcopy


STABILITY_POLICY_VERSION = "engine-stability-policy-v0.1"
STABLE_CHAMPION_VERSION = "M6-global-frozen-champion-v0.1"
SHADOW_CHALLENGER_VERSION = "M6-horizon-overlay-shadow-v0.1"

_POLICY = {
    "version": STABILITY_POLICY_VERSION,
    "champion": {
        "version": STABLE_CHAMPION_VERSION,
        "mutation": "frozen",
        "scope": "all_three_time_horizons",
        "automatic_weight_updates": False,
    },
    "challenger": {
        "version": SHADOW_CHALLENGER_VERSION,
        "production_effect": "none",
        "storage": "compact_inside_existing_recommendation_snapshot",
    },
    "forward_evaluation": {
        "cohort": "chronological_post_deployment_exact_horizon_outcomes",
        "interim_resolved_cases_per_horizon": 25,
        "promotion_review_resolved_cases_per_horizon": 50,
        "primary_metrics": ["log_loss_3c", "brier_3c"],
        "minimum_relative_improvement": 0.02,
        "maximum_relative_regression_per_horizon": 0.02,
        "calendar_block_bootstrap_confidence": 0.95,
        "automatic_promotion": False,
        "owner_review_required": True,
    },
}


def stability_policy_snapshot() -> dict:
    """Return the immutable promotion contract used by production traces."""
    return deepcopy(_POLICY)
