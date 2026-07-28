from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from m5_rules import execute_rule
from m5_runtime import RuleTrace


ROOT = Path(__file__).resolve().parent
CONTRACT_PATH = (
    ROOT / "auditorias_motor" / "contrato_implementacion_m5_1_v0_1.json"
)
ENGINE_VERSION = "M5-internal-engine-v0.1"


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def engine_contract() -> dict:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract["scope"]["rules"] != 27 or not contract["dag"]["acyclic"]:
        raise ValueError("invalid_m5_engine_contract")
    return contract


def dependency_registry(contract: dict) -> dict[str, list[dict]]:
    registry = {rule["rule_id"]: [] for rule in contract["rules"]}
    for edge in contract["dag"]["edges"]:
        registry[edge["to"]].append(edge)
    return registry


def selected_dependencies(
    rule_id: str,
    inputs: dict,
    edges: list[dict],
    traces: dict[str, RuleTrace],
) -> dict[str, RuleTrace]:
    selected = {}
    basis_source = inputs.get("basis_source")
    basis_selection = {
        "spot_futures": "M4-RULE-SPOT-FUTURES-BASIS-001",
        "mark_index": "M4-RULE-MARK-INDEX-PREMIUM-001",
    }.get(str(basis_source).lower())
    for edge in edges:
        parent = edge["from"]
        if edge["relation"] == "alternative_basis_input":
            if rule_id != "M4-RULE-DERIVATIVES-CONTEXT-001":
                raise ValueError("unexpected_alternative_basis_target")
            if parent != basis_selection:
                continue
        selected[parent] = traces[parent]
    return selected


def run_internal_analysis(
    *,
    analysis_id: str,
    rule_inputs: dict[str, dict],
    source_observations: dict[str, tuple[dict, ...]] | None = None,
    executed_at: str | None = None,
) -> dict:
    if not analysis_id:
        raise ValueError("analysis_id_required")
    contract = engine_contract()
    dependencies = dependency_registry(contract)
    traces: dict[str, RuleTrace] = {}
    source_map = source_observations or {}
    for rule_id in contract["dag"]["topological_order"]:
        inputs = rule_inputs.get(rule_id, {})
        parents = selected_dependencies(
            rule_id,
            inputs,
            dependencies[rule_id],
            traces,
        )
        traces[rule_id] = execute_rule(
            rule_id,
            analysis_id=analysis_id,
            inputs=inputs,
            dependencies=parents,
            source_observations=source_map.get(rule_id, ()),
            executed_at=executed_at,
        )

    ordered = [
        traces[rule_id].to_dict()
        | {"trace_sha256": traces[rule_id].trace_sha256}
        for rule_id in contract["dag"]["topological_order"]
    ]
    counts = {
        status: sum(trace.status == status for trace in traces.values())
        for status in (
            "evaluated",
            "blocked",
            "not_applicable",
            "deferred",
            "error",
        )
    }
    family_registry = {}
    for rule in contract["rules"]:
        family = rule["canonical_family"]
        if family is None:
            continue
        family_registry.setdefault(family, []).append(rule["rule_id"])
    result = {
        "engine_version": ENGINE_VERSION,
        "analysis_id": analysis_id,
        "status": (
            "complete_internal_trace"
            if counts["error"] == 0
            else "internal_trace_with_errors"
        ),
        "rule_count": len(ordered),
        "status_counts": counts,
        "topological_order": contract["dag"]["topological_order"],
        "traces": ordered,
        "canonical_families": [
            {
                "family": family,
                "member_rules": members,
                "additive_aggregation_performed": False,
            }
            for family, members in sorted(family_registry.items())
        ],
        "probability_output": None,
        "numeric_score_output": None,
        "production_effect": "none",
        "m6_started": False,
    }
    result["analysis_trace_sha256"] = sha256_json(
        {
            key: value
            for key, value in result.items()
            if key != "analysis_trace_sha256"
        }
    )
    return result
