from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CATALOG_PATH = (
    ROOT
    / "auditorias_motor"
    / "catalogo_maestro_biblioteca_predictiva_v0_1.json"
)
EXPECTED_LIBRARY_VERSION = "TP-SL-RULE-LIBRARY-v0.1"
ALLOWED_ROLES = {
    "baseline",
    "standalone",
    "group",
    "contextual",
    "interaction",
    "blocking",
    "economic",
    "presentation",
}
EXPECTED_HORIZONS = {
    "intraday_short",
    "intraday_wide",
    "short_swing",
}
REQUIRED_RULE_FIELDS = {
    "rule_id",
    "version",
    "name",
    "family_id",
    "role",
    "lifecycle_status",
    "origin",
    "objective",
    "applicable_pairs",
    "applicable_horizons",
    "inputs",
    "formula_ids",
    "deterministic_formulas",
    "probability_integration_formula",
    "normalization",
    "activation_conditions",
    "non_application_conditions",
    "missing_data_behavior",
    "evidence",
    "expected_probability_effect",
    "interactions",
    "parameters",
    "trace_contract",
    "learning_contract",
    "refutation_or_retirement",
}


def canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_catalog(payload: dict) -> dict:
    if payload.get("library_version") != EXPECTED_LIBRARY_VERSION:
        raise ValueError("invalid_rule_library_version")
    stored_hash = payload.get("catalog_sha256")
    unhashed = {
        key: value
        for key, value in payload.items()
        if key != "catalog_sha256"
    }
    if stored_hash != canonical_sha256(unhashed):
        raise ValueError("invalid_rule_library_hash")
    sources = payload.get("sources")
    rules = payload.get("rules")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("rule_library_sources_required")
    if not isinstance(rules, list) or not rules:
        raise ValueError("rule_library_rules_required")
    ids = [item.get("rule_id") for item in rules if isinstance(item, dict)]
    if len(ids) != len(rules) or len(ids) != len(set(ids)):
        raise ValueError("rule_library_ids_must_be_unique")
    known_ids = set(ids)
    for rule in rules:
        missing = sorted(REQUIRED_RULE_FIELDS - set(rule))
        if missing:
            raise ValueError(
                f"incomplete_rule_contract:{rule.get('rule_id')}:{','.join(missing)}"
            )
        if rule["role"] not in ALLOWED_ROLES:
            raise ValueError(f"invalid_rule_role:{rule['rule_id']}")
        if not rule["applicable_pairs"]:
            raise ValueError(f"rule_pairs_required:{rule['rule_id']}")
        if set(rule["applicable_horizons"]) != EXPECTED_HORIZONS:
            raise ValueError(f"invalid_rule_horizons:{rule['rule_id']}")
        evidence = rule["evidence"]
        source_ids = evidence.get("source_ids")
        if not source_ids or any(item not in sources for item in source_ids):
            raise ValueError(f"invalid_rule_sources:{rule['rule_id']}")
        if not evidence.get("project_hypothesis"):
            raise ValueError(f"rule_hypothesis_required:{rule['rule_id']}")
        if not evidence.get("unsupported_claim"):
            raise ValueError(f"rule_transfer_limit_required:{rule['rule_id']}")
        interactions = rule["interactions"]
        parent_ids = interactions.get("parent_rule_ids", [])
        if any(parent not in known_ids for parent in parent_ids):
            raise ValueError(f"unknown_rule_parent:{rule['rule_id']}")
        for parameter in rule["parameters"]:
            if not parameter.get("origin") or not parameter.get("status"):
                raise ValueError(
                    f"parameter_provenance_required:{rule['rule_id']}"
                )
        learning = rule["learning_contract"]
        if learning.get("may_self_modify_production") is not False:
            raise ValueError(
                f"automatic_production_learning_forbidden:{rule['rule_id']}"
            )
        if rule["lifecycle_status"].startswith("active"):
            if not rule["formula_ids"] or not rule["deterministic_formulas"]:
                raise ValueError(f"active_rule_formula_required:{rule['rule_id']}")
            if rule["trace_contract"].get("requires_source_hash") is not True:
                raise ValueError(f"active_rule_trace_hash_required:{rule['rule_id']}")
    summary = payload.get("summary", {})
    if summary.get("rules") != len(rules):
        raise ValueError("rule_library_summary_mismatch")
    return payload


@lru_cache(maxsize=1)
def load_rule_library() -> dict:
    return validate_catalog(
        json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    )


def rule_registry() -> dict[str, dict]:
    return {
        rule["rule_id"]: rule
        for rule in load_rule_library()["rules"]
    }


def rule_metadata(rule_id: str) -> dict:
    try:
        return rule_registry()[rule_id]
    except KeyError as exc:
        raise KeyError(f"unknown_rule_library_id:{rule_id}") from exc


def rules_by_status(*statuses: str) -> list[dict]:
    accepted = set(statuses)
    return [
        rule
        for rule in load_rule_library()["rules"]
        if rule["lifecycle_status"] in accepted
    ]
