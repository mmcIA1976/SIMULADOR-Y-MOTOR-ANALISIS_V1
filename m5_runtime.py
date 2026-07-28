from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable


RUNTIME_VERSION = "M5-runtime-v0.1"
PRODUCTION_EFFECT_NONE = "none"
ALLOWED_STATUSES = {
    "evaluated",
    "blocked",
    "not_applicable",
    "deferred",
    "error",
}


class RuleControlFlow(Exception):
    status = "error"

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RuleBlocked(RuleControlFlow):
    status = "blocked"


class RuleNotApplicable(RuleControlFlow):
    status = "not_applicable"


class RuleDeferred(RuleControlFlow):
    status = "deferred"


@dataclass(frozen=True)
class RuleTrace:
    analysis_id: str
    rule_id: str
    implementation_version: str
    executed_at: str
    status: str
    source_observations: tuple[dict, ...]
    inputs: dict
    outputs: dict
    formula_ids: tuple[str, ...]
    invariant_results: tuple[dict, ...]
    reason_codes: tuple[str, ...]
    dependencies: tuple[dict, ...]
    canonical_family: str | None
    production_effect: str = PRODUCTION_EFFECT_NONE

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def trace_sha256(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_mapping(value: Any, name: str) -> dict:
    if not isinstance(value, dict):
        raise RuleBlocked(f"invalid_{name}", f"{name} must be an object")
    return value


def require_sequence(value: Any, name: str, minimum: int = 1) -> list:
    if not isinstance(value, (list, tuple)) or len(value) < minimum:
        raise RuleBlocked(
            f"invalid_{name}",
            f"{name} must contain at least {minimum} values",
        )
    return list(value)


def require_choice(value: Any, name: str, choices: set[str]) -> str:
    normalized = str(value).lower()
    if normalized not in choices:
        raise RuleBlocked(
            f"invalid_{name}",
            f"{name} must be one of {sorted(choices)}",
        )
    return normalized


def require_finite(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RuleBlocked(f"invalid_{name}", f"{name} must be numeric") from exc
    if not math.isfinite(number):
        raise RuleBlocked(f"invalid_{name}", f"{name} must be finite")
    return number


def require_positive(value: Any, name: str) -> float:
    number = require_finite(value, name)
    if number <= 0:
        raise RuleBlocked(f"invalid_{name}", f"{name} must be positive")
    return number


def require_non_negative(value: Any, name: str) -> float:
    number = require_finite(value, name)
    if number < 0:
        raise RuleBlocked(f"invalid_{name}", f"{name} must be non-negative")
    return number


def require_timestamp_ms(value: Any, name: str) -> int:
    number = require_finite(value, name)
    integer = int(number)
    if integer <= 0 or integer != number:
        raise RuleBlocked(
            f"invalid_{name}",
            f"{name} must be a positive integer millisecond timestamp",
        )
    return integer


def validate_json_numbers(value: Any, path: str = "value") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise ValueError(f"non_finite_trace_number:{path}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            validate_json_numbers(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            validate_json_numbers(item, f"{path}[{index}]")
        return
    raise ValueError(f"non_json_trace_value:{path}")


def safe_trace_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, dict):
        return {
            str(key): safe_trace_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [safe_trace_value(item) for item in value]
    if (
        value is None
        or isinstance(value, (bool, int, float, str))
    ):
        return value
    return repr(value)


def dependency_records(dependencies: dict[str, RuleTrace] | None) -> tuple[dict, ...]:
    records = []
    for rule_id, trace in sorted((dependencies or {}).items()):
        if not isinstance(trace, RuleTrace):
            raise ValueError(f"invalid_dependency_trace:{rule_id}")
        records.append(
            {
                "rule_id": rule_id,
                "status": trace.status,
                "trace_sha256": trace.trace_sha256,
            }
        )
    return tuple(records)


def run_rule(
    *,
    analysis_id: str,
    rule_id: str,
    canonical_family: str | None,
    formula_ids: tuple[str, ...],
    inputs: dict,
    evaluator: Callable[[dict, dict[str, RuleTrace]], dict],
    dependencies: dict[str, RuleTrace] | None = None,
    source_observations: tuple[dict, ...] = (),
    invariant_evaluator: Callable[[dict, dict], tuple[dict, ...]] | None = None,
    executed_at: str | None = None,
) -> RuleTrace:
    if not analysis_id or not rule_id or not formula_ids:
        raise ValueError("incomplete_rule_runtime_contract")
    require_mapping(inputs, "inputs")
    trace_inputs = safe_trace_value(inputs)
    trace_observations = tuple(
        safe_trace_value(item)
        for item in source_observations
    )
    dependency_map = dependencies or {}
    records = dependency_records(dependency_map)
    failed_dependencies = [
        item
        for item in records
        if item["status"] != "evaluated"
    ]
    if failed_dependencies:
        return RuleTrace(
            analysis_id=analysis_id,
            rule_id=rule_id,
            implementation_version=RUNTIME_VERSION,
            executed_at=executed_at or utc_now_iso(),
            status="blocked",
            source_observations=trace_observations,
            inputs=trace_inputs,
            outputs={},
            formula_ids=formula_ids,
            invariant_results=(),
            reason_codes=("dependency_not_evaluated",),
            dependencies=records,
            canonical_family=canonical_family,
        )

    try:
        outputs = require_mapping(
            evaluator(inputs, dependency_map),
            "outputs",
        )
        if not outputs:
            raise RuleBlocked(
                "empty_outputs",
                "evaluated rules must expose outputs",
            )
        validate_json_numbers(outputs, "outputs")
        invariant_results = (
            invariant_evaluator(inputs, outputs)
            if invariant_evaluator
            else ()
        )
        if any(not item.get("passed") for item in invariant_results):
            raise RuleBlocked(
                "invariant_failed",
                "one or more rule invariants failed",
            )
        status = "evaluated"
        reasons: tuple[str, ...] = ()
    except RuleControlFlow as exc:
        outputs = {}
        invariant_results = ()
        status = exc.status
        reasons = (exc.code,)
    except Exception as exc:
        outputs = {}
        invariant_results = ()
        status = "error"
        reasons = (f"unexpected_{type(exc).__name__}",)

    if status not in ALLOWED_STATUSES:
        raise ValueError(f"invalid_trace_status:{status}")
    if status != "evaluated" and outputs:
        raise ValueError("non_evaluated_trace_has_outputs")
    trace = RuleTrace(
        analysis_id=analysis_id,
        rule_id=rule_id,
        implementation_version=RUNTIME_VERSION,
        executed_at=executed_at or utc_now_iso(),
        status=status,
        source_observations=trace_observations,
        inputs=trace_inputs,
        outputs=outputs,
        formula_ids=formula_ids,
        invariant_results=invariant_results,
        reason_codes=reasons,
        dependencies=records,
        canonical_family=canonical_family,
    )
    validate_json_numbers(trace.to_dict(), "trace")
    return trace
