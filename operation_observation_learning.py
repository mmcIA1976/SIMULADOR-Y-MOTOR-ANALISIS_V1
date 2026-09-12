from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from predictive_rule_library import load_rule_library, rule_registry


OBSERVATION_ANALYSIS_TYPE = "operation_observation"
OBSERVATION_CONTRACT_VERSION = "operation-observation-contract-v0.4"
OBSERVATION_STORAGE_PROFILE = "observation-learning-compact-v0.2"
OBSERVATION_PREDICTIVE_EVALUATOR_VERSION = (
    "recommendation-observation-terminal-evaluator-v0.2-stage-context"
)
OBSERVATION_PREDICTIVE_SCHEMA_VERSION = (
    "recommendation-observation-terminal-evaluation-v0.2"
)
OBSERVATION_EPISODE_EVALUATOR_VERSION = (
    "operation-observation-episode-evaluator-v0.1"
)
EXIT_COUNTERFACTUAL_VERSION = "operation-exit-counterfactual-v0.1"
OBSERVATION_CLOSURE_POLICY_VERSION = "observation-closure-advisory-v0.4"
OBSERVATION_PRODUCTION_EFFECT = "none"
OBSERVATION_INTERVAL_CHOICES = (5, 10, 15, 20, 30, 40, 60)

SESSION_STATUSES = {"active", "paused", "completed", "cancelled"}
SESSION_EVENT_TYPES = {
    "started",
    "interval_changed",
    "paused",
    "resumed",
    "stopped",
    "operation_closed",
}
CAPTURE_MODES = {"live", "reconstructed"}
EVIDENCE_QUALITIES = {"exact", "reconstructed_partial"}
CHECKPOINT_DECISIONS = {
    "unreviewed",
    "hold",
    "watch",
    "protect",
    "close",
    "final",
}
MAX_SESSION_SUMMARY_BYTES = 16_384
MAX_CHECKPOINT_CONTEXT_BYTES = 16_384
MAX_EXIT_EVALUATION_BYTES = 8_192
MAX_SESSION_EVENT_DETAILS_BYTES = 4_096
MAX_COMPACT_SNAPSHOT_BYTES = 48_000
PROBABILITY_TOLERANCE = 1.1e-6

RULE_LABELS = {
    "M4-RULE-PATH-STRUCTURE-001": "Estructura del recorrido",
    "M4-RULE-MTF-HIERARCHY-001": "Continuidad entre escalas",
    "M4-RULE-VOLATILITY-RANK-001": "Régimen de volatilidad",
    "M4-RULE-AGGRESSOR-IMBALANCE-001": "Flujo agresor",
    "LIB-CAND-EMA-TREND-001": "Alineación con EMA",
    "LIB-CAND-RSI-WILDER-001": "Momento RSI",
    "LIB-CAND-ATR-EXTENSION-001": "Extensión frente al ATR",
    "LIB-CAND-RELATIVE-VOLUME-001": "Volumen relativo",
    "LIB-CAND-CVD-SLOPE-001": "Persistencia del flujo ejecutado",
    "LIB-CAND-ABSORPTION-001": "Absorción de órdenes",
    "LIB-CAND-COMPRESSION-001": "Compresión del mercado",
    "M4-RULE-PRIOR-EXTREMA-001": "Extremos previos en el camino",
    "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001": "Niveles estructurales",
    "LIB-CAND-FIBONACCI-DISTANCE-001": "Distancias Fibonacci",
    "LIB-CAND-LIQUIDATION-ZONE-001": "Mapa de liquidaciones",
    "LIB-CAND-ORDERBOOK-IMBALANCE-001": "Dinámica del libro de órdenes",
}


def ensure_operation_observation_tables(db) -> None:
    """Create the compact internal observation store and protect fact rows."""
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS operation_observation_sessions (
            id BIGSERIAL PRIMARY KEY,
            operation_id BIGINT NOT NULL UNIQUE
                REFERENCES operations(id) ON DELETE RESTRICT,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            opening_recommendation_id BIGINT
                REFERENCES recommendations(id) ON DELETE RESTRICT,
            session_code TEXT NOT NULL UNIQUE
                CHECK(session_code ~ '^[0-9]+o$'),
            status TEXT NOT NULL
                CHECK(status IN ('active', 'paused', 'completed', 'cancelled')),
            capture_mode TEXT NOT NULL
                CHECK(capture_mode IN ('live', 'reconstructed')),
            contract_version TEXT NOT NULL,
            planned_interval_minutes INTEGER CHECK(
                planned_interval_minutes IS NULL
                OR planned_interval_minutes BETWEEN 1 AND 1440
            ),
            reported_checkpoint_count INTEGER NOT NULL DEFAULT 0
                CHECK(reported_checkpoint_count >= 0),
            stored_checkpoint_count INTEGER NOT NULL DEFAULT 0
                CHECK(stored_checkpoint_count >= 0),
            next_checkpoint_number INTEGER NOT NULL DEFAULT 1
                CHECK(next_checkpoint_number > 0),
            started_at TIMESTAMPTZ NOT NULL,
            paused_at TIMESTAMPTZ,
            ended_at TIMESTAMPTZ,
            evidence_source TEXT NOT NULL,
            evidence_quality TEXT NOT NULL
                CHECK(evidence_quality IN ('exact', 'reconstructed_partial')),
            summary_json TEXT NOT NULL
                CHECK(jsonb_typeof(summary_json::jsonb) = 'object'),
            summary_bytes INTEGER NOT NULL CHECK(
                summary_bytes > 0 AND summary_bytes <= 16384
                AND summary_bytes = octet_length(convert_to(summary_json, 'UTF8'))
            ),
            summary_sha256 TEXT NOT NULL
                CHECK(summary_sha256 ~ '^[0-9a-f]{64}$'),
            production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(id, operation_id),
            CHECK(
                (status IN ('active', 'paused') AND ended_at IS NULL)
                OR (status IN ('completed', 'cancelled') AND ended_at IS NOT NULL)
            ),
            CHECK(
                (status = 'paused' AND paused_at IS NOT NULL)
                OR status <> 'paused'
            ),
            CHECK(
                (capture_mode = 'live' AND evidence_quality = 'exact')
                OR (capture_mode = 'reconstructed'
                    AND evidence_quality = 'reconstructed_partial')
            )
        );

        CREATE TABLE IF NOT EXISTS operation_observation_session_events (
            id BIGSERIAL PRIMARY KEY,
            session_id BIGINT NOT NULL,
            operation_id BIGINT NOT NULL,
            event_type TEXT NOT NULL CHECK(
                event_type IN (
                    'started', 'interval_changed', 'paused', 'resumed',
                    'stopped', 'operation_closed'
                )
            ),
            occurred_at TIMESTAMPTZ NOT NULL,
            from_status TEXT CHECK(
                from_status IS NULL OR from_status IN (
                    'active', 'paused', 'completed', 'cancelled'
                )
            ),
            to_status TEXT CHECK(
                to_status IS NULL OR to_status IN (
                    'active', 'paused', 'completed', 'cancelled'
                )
            ),
            interval_minutes INTEGER CHECK(
                interval_minutes IS NULL OR interval_minutes BETWEEN 1 AND 1440
            ),
            details_json TEXT NOT NULL
                CHECK(jsonb_typeof(details_json::jsonb) = 'object'),
            details_bytes INTEGER NOT NULL CHECK(
                details_bytes > 0 AND details_bytes <= 4096
                AND details_bytes = octet_length(
                    convert_to(details_json, 'UTF8')
                )
            ),
            details_sha256 TEXT NOT NULL
                CHECK(details_sha256 ~ '^[0-9a-f]{64}$'),
            production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id, operation_id)
                REFERENCES operation_observation_sessions(id, operation_id)
                ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS operation_observation_checkpoints (
            id BIGSERIAL PRIMARY KEY,
            session_id BIGINT NOT NULL,
            operation_id BIGINT NOT NULL,
            recommendation_id BIGINT UNIQUE
                REFERENCES recommendations(id) ON DELETE RESTRICT,
            checkpoint_number INTEGER NOT NULL CHECK(checkpoint_number > 0),
            checkpoint_code TEXT NOT NULL UNIQUE
                CHECK(checkpoint_code ~ '^[0-9]+o[0-9]+$'),
            observed_at TIMESTAMPTZ NOT NULL,
            source_turn_id TEXT,
            market_price DOUBLE PRECISION NOT NULL CHECK(market_price > 0),
            unrealized_pnl DOUBLE PRECISION NOT NULL,
            remaining_seconds INTEGER CHECK(remaining_seconds >= 0),
            tp_probability DOUBLE PRECISION
                CHECK(tp_probability BETWEEN 0 AND 1),
            sl_probability DOUBLE PRECISION
                CHECK(sl_probability BETWEEN 0 AND 1),
            range_probability DOUBLE PRECISION
                CHECK(range_probability BETWEEN 0 AND 1),
            decision TEXT NOT NULL CHECK(
                decision IN (
                    'unreviewed', 'hold', 'watch', 'protect', 'close', 'final'
                )
            ),
            decision_candidate BOOLEAN NOT NULL DEFAULT FALSE,
            contract_quality TEXT NOT NULL CHECK(
                contract_quality IN ('exact', 'reconstructed_partial')
            ),
            formal_learning_eligible BOOLEAN NOT NULL,
            evidence_source TEXT NOT NULL,
            context_json TEXT NOT NULL
                CHECK(jsonb_typeof(context_json::jsonb) = 'object'),
            context_bytes INTEGER NOT NULL CHECK(
                context_bytes > 0 AND context_bytes <= 16384
                AND context_bytes = octet_length(convert_to(context_json, 'UTF8'))
            ),
            context_sha256 TEXT NOT NULL
                CHECK(context_sha256 ~ '^[0-9a-f]{64}$'),
            production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, checkpoint_number),
            UNIQUE(id, operation_id),
            FOREIGN KEY(session_id, operation_id)
                REFERENCES operation_observation_sessions(id, operation_id)
                ON DELETE RESTRICT,
            CHECK(
                (contract_quality = 'exact'
                    AND formal_learning_eligible
                    AND recommendation_id IS NOT NULL)
                OR (contract_quality = 'reconstructed_partial'
                    AND NOT formal_learning_eligible
                    AND recommendation_id IS NULL)
            ),
            CHECK(
                (tp_probability IS NULL AND sl_probability IS NULL
                    AND range_probability IS NULL)
                OR (
                    tp_probability IS NOT NULL
                    AND sl_probability IS NOT NULL
                    AND range_probability IS NOT NULL
                    AND abs(
                        tp_probability + sl_probability + range_probability - 1.0
                    ) <= 0.0000011
                )
            )
        );

        CREATE TABLE IF NOT EXISTS operation_exit_counterfactuals (
            id BIGSERIAL PRIMARY KEY,
            operation_id BIGINT NOT NULL,
            checkpoint_id BIGINT NOT NULL,
            evaluator_version TEXT NOT NULL,
            evaluated_at TIMESTAMPTZ NOT NULL,
            actual_final_pnl DOUBLE PRECISION NOT NULL,
            pnl_if_closed DOUBLE PRECISION NOT NULL,
            missed_profit DOUBLE PRECISION NOT NULL,
            protected_drawdown DOUBLE PRECISION,
            tp_reached_after BOOLEAN NOT NULL,
            sl_reached_after BOOLEAN NOT NULL,
            time_to_terminal_minutes DOUBLE PRECISION
                CHECK(time_to_terminal_minutes IS NULL
                    OR time_to_terminal_minutes >= 0),
            absolute_profit_verdict TEXT NOT NULL,
            risk_adjusted_verdict TEXT NOT NULL,
            contract_quality TEXT NOT NULL CHECK(
                contract_quality IN ('exact', 'reconstructed_partial')
            ),
            formal_learning_eligible BOOLEAN NOT NULL,
            evaluation_json TEXT NOT NULL
                CHECK(jsonb_typeof(evaluation_json::jsonb) = 'object'),
            evaluation_bytes INTEGER NOT NULL CHECK(
                evaluation_bytes > 0 AND evaluation_bytes <= 8192
                AND evaluation_bytes = octet_length(
                    convert_to(evaluation_json, 'UTF8')
                )
            ),
            evaluation_sha256 TEXT NOT NULL
                CHECK(evaluation_sha256 ~ '^[0-9a-f]{64}$'),
            production_effect TEXT NOT NULL CHECK(production_effect = 'none'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(checkpoint_id, evaluator_version),
            FOREIGN KEY(checkpoint_id, operation_id)
                REFERENCES operation_observation_checkpoints(id, operation_id)
                ON DELETE RESTRICT,
            CHECK(
                formal_learning_eligible = (contract_quality = 'exact')
            )
        );

        CREATE INDEX IF NOT EXISTS idx_observation_sessions_user_status
            ON operation_observation_sessions(user_id, status, started_at);
        CREATE INDEX IF NOT EXISTS idx_observation_checkpoints_episode_time
            ON operation_observation_checkpoints(operation_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_observation_session_events_timeline
            ON operation_observation_session_events(
                operation_id, occurred_at, id
            );
        CREATE INDEX IF NOT EXISTS idx_observation_checkpoints_learning
            ON operation_observation_checkpoints(
                formal_learning_eligible, contract_quality, observed_at
            );
        CREATE INDEX IF NOT EXISTS idx_exit_counterfactual_operation
            ON operation_exit_counterfactuals(operation_id, evaluated_at);

        ALTER TABLE operation_observation_sessions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE operation_observation_session_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE operation_observation_checkpoints ENABLE ROW LEVEL SECURITY;
        ALTER TABLE operation_exit_counterfactuals ENABLE ROW LEVEL SECURITY;
        REVOKE ALL PRIVILEGES ON TABLE operation_observation_sessions
            FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE operation_observation_session_events
            FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE operation_observation_checkpoints
            FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE operation_exit_counterfactuals
            FROM anon, authenticated;
        REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE operation_observation_sessions FROM service_role;
        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE operation_observation_session_events FROM service_role;
        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE operation_observation_checkpoints FROM service_role;
        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE operation_exit_counterfactuals FROM service_role;
        GRANT SELECT, INSERT, UPDATE ON TABLE operation_observation_sessions
            TO service_role;
        GRANT SELECT, INSERT ON TABLE operation_observation_session_events
            TO service_role;
        GRANT SELECT, INSERT ON TABLE operation_observation_checkpoints
            TO service_role;
        GRANT SELECT, INSERT ON TABLE operation_exit_counterfactuals
            TO service_role;
        GRANT USAGE, SELECT ON SEQUENCE operation_observation_sessions_id_seq
            TO service_role;
        GRANT USAGE, SELECT ON SEQUENCE
            operation_observation_session_events_id_seq TO service_role;
        GRANT USAGE, SELECT ON SEQUENCE operation_observation_checkpoints_id_seq
            TO service_role;
        GRANT USAGE, SELECT ON SEQUENCE operation_exit_counterfactuals_id_seq
            TO service_role;
        """
    )
    db.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_operation_observation_fact_mutation()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SET search_path = ''
        AS $$
        BEGIN
            RAISE EXCEPTION 'operation_observation_fact_is_append_only';
        END;
        $$;
        """
    )
    db.execute(
        """
        REVOKE ALL ON FUNCTION prevent_operation_observation_fact_mutation()
            FROM PUBLIC, anon, authenticated, service_role
        """
    )
    db.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgrelid = 'operation_observation_session_events'::regclass
                  AND tgname = 'operation_observation_session_events_append_only'
                  AND NOT tgisinternal
            ) THEN
                CREATE TRIGGER operation_observation_session_events_append_only
                BEFORE UPDATE OR DELETE ON operation_observation_session_events
                FOR EACH ROW
                EXECUTE FUNCTION prevent_operation_observation_fact_mutation();
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgrelid = 'operation_observation_checkpoints'::regclass
                  AND tgname = 'operation_observation_checkpoints_append_only'
                  AND NOT tgisinternal
            ) THEN
                CREATE TRIGGER operation_observation_checkpoints_append_only
                BEFORE UPDATE OR DELETE ON operation_observation_checkpoints
                FOR EACH ROW
                EXECUTE FUNCTION prevent_operation_observation_fact_mutation();
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_trigger
                WHERE tgrelid = 'operation_exit_counterfactuals'::regclass
                  AND tgname = 'operation_exit_counterfactuals_append_only'
                  AND NOT tgisinternal
            ) THEN
                CREATE TRIGGER operation_exit_counterfactuals_append_only
                BEFORE UPDATE OR DELETE ON operation_exit_counterfactuals
                FOR EACH ROW
                EXECUTE FUNCTION prevent_operation_observation_fact_mutation();
            END IF;
        END;
        $$;
        """
    )


def canonical_json(payload: dict | list) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def payload_sha256(payload: dict | list) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def observation_rule_catalog_reference() -> dict:
    """Return the single immutable catalog identity used by every checkpoint."""
    catalog = load_rule_library()
    return {
        "library_version": catalog["library_version"],
        "catalog_sha256": catalog["catalog_sha256"],
    }


def _compact_scalar_tree(value: Any) -> Any:
    """Keep reproducible scalar evidence while discarding verbose raw arrays."""
    if isinstance(value, dict):
        compact = {
            str(key): child
            for key, raw_child in value.items()
            if (child := _compact_scalar_tree(raw_child)) is not None
        }
        return compact or None
    if isinstance(value, list):
        if len(value) <= 16 and all(
            isinstance(item, (str, int, float, bool)) or item is None
            for item in value
        ):
            return value
        return None
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value if _finite_number(value) is not None else None
    if isinstance(value, str):
        return value[:160]
    return None


def _compact_probability_trace(trace: Any) -> dict:
    if not isinstance(trace, dict):
        return {}
    result = {
        key: trace.get(key)
        for key in (
            "artifact_id",
            "artifact_sha256",
            "engine_version",
            "runtime_version",
            "scoring_version",
            "selected_horizon",
            "executed_stage_count",
            "executed_stages",
            "single_engine",
            "parallel_probability_engines_executed",
            "decision_probabilities",
            "probabilities",
            "probability_ranges_95pct",
            "result_sha256",
            "production_effect",
        )
        if trace.get(key) is not None
    }
    compact_stages = []
    for stage in trace.get("stage_traces") or []:
        if not isinstance(stage, dict):
            continue
        compact_stage = {
            key: stage.get(key)
            for key in (
                "stage_id",
                "label",
                "time_horizon",
                "interval",
                "survival_entering_stage",
                "conditional_probabilities",
                "cumulative_probabilities",
                "effective_sample_size",
                "selected_analogs",
                "same_symbol_analogs",
                "nearest_context_distance",
                "furthest_selected_distance",
                "maximum_context_distance_allowed",
                "conditional_sample_empty",
                "conditional_sample_sparse",
                "resolved_before_stage_excluded",
                "ambiguous_excluded",
                "bandwidth",
                "probability_temperature",
                "dirichlet_prior_per_class",
                "weighted_outcome_counts",
                "posterior_alpha",
                "geometry_application",
                "current_feature_values",
                "uncertainty_policy",
                "kernel",
                "active_rule_groups",
            )
            if stage.get(key) is not None
        }
        compact_stages.append(_compact_scalar_tree(compact_stage) or {})
    compact_result = _compact_scalar_tree(result) or {}
    # ``_compact_scalar_tree`` deliberately drops arrays of objects so raw
    # market arrays cannot leak into storage.  These stage objects have already
    # been reduced field-by-field above, therefore preserve them explicitly.
    compact_result["stage_traces"] = compact_stages
    return compact_result


def _compact_stage_contexts(contexts: Any) -> dict:
    if not isinstance(contexts, dict):
        return {}
    result = {}
    for stage_name, context in contexts.items():
        if not isinstance(context, dict):
            continue
        selected = {
            key: context.get(key)
            for key in (
                "stage_id",
                "label",
                "time_horizon",
                "interval",
                "interval_seconds",
                "increment_seconds",
                "horizon_seconds",
                "required_candle_count",
                "data_cutoff_at_ms",
                "context_sigma",
                "feature_values",
                "data_quality",
                "source_data_sha256",
            )
            if context.get(key) is not None
        }
        result[str(stage_name)] = _compact_scalar_tree(selected) or {}
    return result


def _compact_stage_rule_traces(stage_traces: Any) -> dict:
    if not isinstance(stage_traces, dict):
        return {}
    known_rules = rule_registry()
    result: dict[str, list[dict]] = {}
    for stage_name, traces in stage_traces.items():
        compact_traces = []
        if not isinstance(traces, list):
            continue
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            rule_id = str(trace.get("rule_id") or "")
            if not rule_id or rule_id not in known_rules:
                continue
            outputs = _compact_scalar_tree(trace.get("outputs"))
            compact_trace = {
                "rule_id": rule_id,
                "rule_version": trace.get("rule_version"),
                "status": trace.get("status"),
                "probability_effect": trace.get("probability_effect"),
                "source_data_sha256": trace.get("source_data_sha256"),
                "trace_sha256": trace.get("trace_sha256"),
                "outputs": outputs if isinstance(outputs, dict) else {},
            }
            compact_traces.append(
                {
                    key: value
                    for key, value in compact_trace.items()
                    if value is not None
                }
            )
        result[str(stage_name)] = compact_traces
    return result


def compact_observation_snapshot(snapshot: dict) -> dict:
    """Reduce an observation snapshot to evidence that is actually evaluated.

    Formulas, labels, parameters and lifecycle metadata are referenced through
    the immutable catalog instead of being repeated in every checkpoint.
    """
    if not isinstance(snapshot, dict):
        raise ValueError("observation_snapshot_invalid")
    if snapshot.get("storage_profile") == OBSERVATION_STORAGE_PROFILE:
        return snapshot
    compact = {
        "storage_profile": OBSERVATION_STORAGE_PROFILE,
        "contract_version": OBSERVATION_CONTRACT_VERSION,
        "rule_catalog": observation_rule_catalog_reference(),
        "analysis_at": snapshot.get("analysis_at"),
        "data_cutoff_at": snapshot.get("data_cutoff_at"),
        "evaluation_expires_at": snapshot.get("evaluation_expires_at"),
        "evaluation_horizon_seconds": snapshot.get(
            "evaluation_horizon_seconds"
        ),
        "symbol": snapshot.get("symbol"),
        "side": snapshot.get("side"),
        "time_horizon": snapshot.get("time_horizon"),
        "entry": snapshot.get("entry"),
        "take_profit": snapshot.get("take_profit"),
        "stop_loss": snapshot.get("stop_loss"),
        "decision_probabilities": snapshot.get("decision_probabilities"),
        "entry_order_context": _compact_scalar_tree(
            snapshot.get("entry_order_context")
        ),
        "observation_context": _compact_scalar_tree(
            snapshot.get("observation_context")
        ),
        "version_contract": _compact_scalar_tree(snapshot.get("version_contract")),
        "probability_trace": _compact_probability_trace(
            snapshot.get("probability_trace")
        ),
        "stage_contexts": _compact_stage_contexts(snapshot.get("stage_contexts")),
        "stage_rule_traces": _compact_stage_rule_traces(
            snapshot.get("stage_rule_traces")
        ),
    }
    compact = {key: value for key, value in compact.items() if value is not None}
    compact["compact_sha256"] = payload_sha256(compact)
    encoded = canonical_json(compact)
    if len(encoded.encode("utf-8")) > MAX_COMPACT_SNAPSHOT_BYTES:
        raise ValueError("observation_compact_snapshot_too_large")
    return compact


def utc_iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def observation_interval_minutes(value: Any) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("observation_interval_invalid") from exc
    if interval not in OBSERVATION_INTERVAL_CHOICES:
        raise ValueError("observation_interval_invalid")
    return interval


def observation_next_due_at(session: dict) -> datetime | None:
    if str(session.get("status") or "") != "active":
        return None
    interval = observation_interval_minutes(
        session.get("planned_interval_minutes") or 20
    )
    checkpoint_count = int(
        session.get("checkpoint_count")
        or session.get("stored_checkpoints")
        or session.get("stored_checkpoint_count")
        or 0
    )
    if checkpoint_count <= 0:
        base_value = session.get("started_at")
    else:
        base_value = session.get("last_checkpoint_at") or session.get(
            "started_at"
        )
    if base_value is None:
        raise ValueError("observation_schedule_timestamp_missing")
    base = datetime.fromisoformat(str(base_value).replace("Z", "+00:00"))
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    base = base.astimezone(timezone.utc)
    if checkpoint_count <= 0:
        return base
    return base + timedelta(minutes=interval)


def observation_session_is_due(
    session: dict,
    *,
    now: datetime | str | None = None,
) -> bool:
    if str(session.get("operation_status") or "OPEN").upper() != "OPEN":
        return False
    due_at = observation_next_due_at(session)
    if due_at is None:
        return False
    current = datetime.fromisoformat(
        str(now or datetime.now(timezone.utc)).replace("Z", "+00:00")
    )
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return due_at <= current.astimezone(timezone.utc)


def checkpoint_code(operation_id: int, checkpoint_number: int) -> str:
    operation_id = int(operation_id)
    checkpoint_number = int(checkpoint_number)
    if operation_id <= 0 or checkpoint_number <= 0:
        raise ValueError("observation_checkpoint_identity_invalid")
    return f"{operation_id}o{checkpoint_number}"


def _encoded_json(payload: dict, *, limit: int, error_code: str) -> tuple[str, int, str]:
    encoded = canonical_json(payload)
    payload_bytes = len(encoded.encode("utf-8"))
    if payload_bytes <= 0 or payload_bytes > limit:
        raise ValueError(error_code)
    return encoded, payload_bytes, payload_sha256(payload)


def _probability_triplet(
    tp_probability: Any,
    sl_probability: Any,
    range_probability: Any,
) -> tuple[float | None, float | None, float | None]:
    values = (tp_probability, sl_probability, range_probability)
    if all(value is None for value in values):
        return None, None, None
    try:
        normalized = tuple(float(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise ValueError("observation_probabilities_incomplete") from exc
    if any(not math.isfinite(value) or value < 0 or value > 1 for value in normalized):
        raise ValueError("observation_probabilities_invalid")
    if not math.isclose(
        math.fsum(normalized),
        1.0,
        rel_tol=0.0,
        abs_tol=PROBABILITY_TOLERANCE,
    ):
        raise ValueError("observation_probability_mass_invalid")
    return normalized


def record_observation_session_event(
    db,
    *,
    session_id: int,
    operation_id: int,
    event_type: str,
    occurred_at: datetime | str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    interval_minutes: int | None = None,
    details: dict | None = None,
) -> dict:
    if event_type not in SESSION_EVENT_TYPES:
        raise ValueError("observation_session_event_type_invalid")
    for state in (from_status, to_status):
        if state is not None and state not in SESSION_STATUSES:
            raise ValueError("observation_session_event_status_invalid")
    if interval_minutes is not None:
        interval_minutes = int(interval_minutes)
        if not 1 <= interval_minutes <= 1_440:
            raise ValueError("observation_session_event_interval_invalid")
    details_json, details_bytes, details_hash = _encoded_json(
        details or {},
        limit=MAX_SESSION_EVENT_DETAILS_BYTES,
        error_code="observation_session_event_details_too_large",
    )
    inserted = db.execute(
        """
        INSERT INTO operation_observation_session_events (
            session_id, operation_id, event_type, occurred_at,
            from_status, to_status, interval_minutes, details_json,
            details_bytes, details_sha256, production_effect
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(session_id),
            int(operation_id),
            event_type,
            utc_iso(occurred_at or datetime.now(timezone.utc)),
            from_status,
            to_status,
            interval_minutes,
            details_json,
            details_bytes,
            details_hash,
            OBSERVATION_PRODUCTION_EFFECT,
        ),
    ).fetchone()
    if not inserted:
        raise RuntimeError("observation_session_event_not_inserted")
    return dict(inserted)


def create_or_get_observation_session(
    db,
    *,
    operation: dict,
    opening_recommendation_id: int | None,
    capture_mode: str = "live",
    evidence_quality: str = "exact",
    planned_interval_minutes: int | None = 20,
    status: str = "active",
    started_at: datetime | str | None = None,
    ended_at: datetime | str | None = None,
    evidence_source: str = "application_live_observation",
    summary: dict | None = None,
) -> dict:
    operation_id = int(operation["id"])
    user_id = int(operation["user_id"])
    if capture_mode not in CAPTURE_MODES:
        raise ValueError("observation_capture_mode_invalid")
    if evidence_quality not in EVIDENCE_QUALITIES:
        raise ValueError("observation_evidence_quality_invalid")
    if status not in SESSION_STATUSES:
        raise ValueError("observation_session_status_invalid")
    if (capture_mode == "live") != (evidence_quality == "exact"):
        raise ValueError("observation_capture_quality_mismatch")
    if planned_interval_minutes is not None:
        if capture_mode == "live":
            planned_interval_minutes = observation_interval_minutes(
                planned_interval_minutes
            )
        else:
            planned_interval_minutes = int(planned_interval_minutes)
            if not 1 <= planned_interval_minutes <= 1_440:
                raise ValueError("observation_interval_invalid")
    started = utc_iso(started_at or datetime.now(timezone.utc))
    ended = utc_iso(ended_at) if ended_at is not None else None
    if status in {"active", "paused"} and ended is not None:
        raise ValueError("open_observation_cannot_have_end")
    if status in {"completed", "cancelled"} and ended is None:
        raise ValueError("closed_observation_requires_end")
    summary_json, summary_bytes, summary_hash = _encoded_json(
        summary or {},
        limit=MAX_SESSION_SUMMARY_BYTES,
        error_code="observation_session_summary_too_large",
    )
    session_code = f"{operation_id}o"
    inserted = db.execute(
        """
        INSERT INTO operation_observation_sessions (
            operation_id, user_id, opening_recommendation_id, session_code,
            status, capture_mode, contract_version, planned_interval_minutes,
            reported_checkpoint_count, stored_checkpoint_count,
            next_checkpoint_number, started_at, ended_at, evidence_source,
            evidence_quality, summary_json, summary_bytes, summary_sha256,
            production_effect
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 1, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (operation_id) DO NOTHING
        RETURNING *
        """,
        (
            operation_id,
            user_id,
            opening_recommendation_id,
            session_code,
            status,
            capture_mode,
            OBSERVATION_CONTRACT_VERSION,
            planned_interval_minutes,
            started,
            ended,
            evidence_source,
            evidence_quality,
            summary_json,
            summary_bytes,
            summary_hash,
            OBSERVATION_PRODUCTION_EFFECT,
        ),
    ).fetchone()
    if inserted:
        inserted = dict(inserted)
        record_observation_session_event(
            db,
            session_id=int(inserted["id"]),
            operation_id=operation_id,
            event_type="started",
            occurred_at=started,
            from_status=None,
            to_status=status,
            interval_minutes=planned_interval_minutes,
            details={
                "capture_mode": capture_mode,
                "evidence_quality": evidence_quality,
                "contract_version": OBSERVATION_CONTRACT_VERSION,
            },
        )
        return inserted
    existing = db.execute(
        """
        SELECT *
        FROM operation_observation_sessions
        WHERE operation_id = ?
        LIMIT 1
        """,
        (operation_id,),
    ).fetchone()
    if not existing:
        raise RuntimeError("observation_session_conflict_without_row")
    existing = dict(existing)
    if int(existing["user_id"]) != user_id:
        raise RuntimeError("observation_session_owner_mismatch")
    if existing["capture_mode"] != capture_mode:
        raise RuntimeError("observation_session_capture_mode_mismatch")
    if existing["evidence_quality"] != evidence_quality:
        raise RuntimeError("observation_session_evidence_quality_mismatch")
    if existing["contract_version"] not in {
        "operation-observation-contract-v0.2",
        "operation-observation-contract-v0.3",
        OBSERVATION_CONTRACT_VERSION,
    }:
        raise RuntimeError("observation_session_contract_version_mismatch")
    return existing


def update_active_observation_interval(
    db,
    *,
    operation_id: int,
    user_id: int,
    planned_interval_minutes: int,
) -> dict:
    interval = observation_interval_minutes(planned_interval_minutes)
    current = db.execute(
        """
        SELECT * FROM operation_observation_sessions
        WHERE operation_id = ?
          AND user_id = ?
          AND status IN ('active', 'paused')
          AND capture_mode = 'live'
        FOR UPDATE
        """,
        (int(operation_id), int(user_id)),
    ).fetchone()
    if not current:
        raise ValueError("active_observation_session_not_found")
    current = dict(current)
    previous_interval = int(current.get("planned_interval_minutes") or 20)
    if previous_interval == interval:
        return current
    updated = db.execute(
        """
        UPDATE operation_observation_sessions
        SET planned_interval_minutes = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE operation_id = ?
          AND user_id = ?
          AND status IN ('active', 'paused')
          AND capture_mode = 'live'
        RETURNING *
        """,
        (interval, int(operation_id), int(user_id)),
    ).fetchone()
    if not updated:
        raise ValueError("active_observation_session_not_found")
    updated = dict(updated)
    record_observation_session_event(
        db,
        session_id=int(updated["id"]),
        operation_id=int(operation_id),
        event_type="interval_changed",
        from_status=str(updated["status"]),
        to_status=str(updated["status"]),
        interval_minutes=interval,
        details={"previous_interval_minutes": previous_interval},
    )
    return updated


def transition_observation_session(
    db,
    *,
    operation_id: int,
    user_id: int,
    action: str,
    note: str | None = None,
) -> dict:
    if action not in {"pause", "resume", "stop"}:
        raise ValueError("observation_session_action_invalid")
    session = db.execute(
        """
        SELECT session.*, operation.status AS operation_status
        FROM operation_observation_sessions AS session
        JOIN operations AS operation ON operation.id = session.operation_id
        WHERE session.operation_id = ? AND session.user_id = ?
        FOR UPDATE OF session
        """,
        (int(operation_id), int(user_id)),
    ).fetchone()
    if not session:
        raise ValueError("observation_session_not_found")
    session = dict(session)
    current_status = str(session["status"])
    operation_status = str(session["operation_status"]).upper()
    if action == "pause":
        if current_status != "active" or operation_status != "OPEN":
            raise ValueError("observation_session_cannot_pause")
        target_status = "paused"
        event_type = "paused"
        updated = db.execute(
            """
            UPDATE operation_observation_sessions
            SET status = 'paused', paused_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'active'
            RETURNING *
            """,
            (int(session["id"]),),
        ).fetchone()
    elif action == "resume":
        if current_status != "paused" or operation_status != "OPEN":
            raise ValueError("observation_session_cannot_resume")
        target_status = "active"
        event_type = "resumed"
        updated = db.execute(
            """
            UPDATE operation_observation_sessions
            SET status = 'active', paused_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'paused'
            RETURNING *
            """,
            (int(session["id"]),),
        ).fetchone()
    else:
        if current_status not in {"active", "paused"}:
            raise ValueError("observation_session_cannot_stop")
        target_status = "cancelled"
        event_type = "stopped"
        updated = db.execute(
            """
            UPDATE operation_observation_sessions
            SET status = 'cancelled', paused_at = NULL,
                ended_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status IN ('active', 'paused')
            RETURNING *
            """,
            (int(session["id"]),),
        ).fetchone()
    if not updated:
        raise RuntimeError("observation_session_transition_not_applied")
    updated = dict(updated)
    record_observation_session_event(
        db,
        session_id=int(updated["id"]),
        operation_id=int(operation_id),
        event_type=event_type,
        from_status=current_status,
        to_status=target_status,
        interval_minutes=int(updated.get("planned_interval_minutes") or 20),
        details={"note": str(note or "").strip()[:500]},
    )
    return updated


def due_observation_sessions(
    db,
    *,
    now: datetime | str | None = None,
    limit: int = 8,
) -> list[dict]:
    """Return active live sessions whose next automatic control is due."""
    rows = db.execute(
        """
        SELECT
            session.*,
            operation.status AS operation_status,
            COALESCE(checkpoints.checkpoint_count, 0) AS checkpoint_count,
            checkpoints.last_checkpoint_at
        FROM operation_observation_sessions AS session
        JOIN operations AS operation
          ON operation.id = session.operation_id
        LEFT JOIN (
            SELECT
                session_id,
                COUNT(*) AS checkpoint_count,
                MAX(observed_at) AS last_checkpoint_at
            FROM operation_observation_checkpoints
            GROUP BY session_id
        ) AS checkpoints
          ON checkpoints.session_id = session.id
        WHERE session.status = 'active'
          AND session.capture_mode = 'live'
          AND operation.status = 'OPEN'
        ORDER BY COALESCE(
            checkpoints.last_checkpoint_at,
            session.started_at
        ) ASC, session.id ASC
        """
    ).fetchall()
    capped_limit = max(1, min(int(limit), 100))
    due: list[dict] = []
    for raw_row in rows:
        session = dict(raw_row)
        session["planned_interval_minutes"] = observation_interval_minutes(
            session.get("planned_interval_minutes") or 20
        )
        if observation_session_is_due(session, now=now):
            due.append(session)
            if len(due) >= capped_limit:
                break
    return due


def persist_observation_checkpoint(
    db,
    *,
    session_id: int,
    operation_id: int,
    observed_at: datetime | str,
    market_price: float,
    unrealized_pnl: float,
    remaining_seconds: int | None,
    tp_probability: float | None,
    sl_probability: float | None,
    range_probability: float | None,
    decision: str = "unreviewed",
    decision_candidate: bool = False,
    recommendation_id: int | None = None,
    checkpoint_number: int | None = None,
    source_turn_id: str | None = None,
    contract_quality: str = "exact",
    evidence_source: str = "application_live_observation",
    context: dict | None = None,
) -> dict:
    if contract_quality not in EVIDENCE_QUALITIES:
        raise ValueError("observation_checkpoint_quality_invalid")
    formal_learning_eligible = contract_quality == "exact"
    if formal_learning_eligible != (recommendation_id is not None):
        raise ValueError("observation_checkpoint_recommendation_contract_invalid")
    if decision not in CHECKPOINT_DECISIONS:
        raise ValueError("observation_checkpoint_decision_invalid")
    market_price = float(market_price)
    unrealized_pnl = float(unrealized_pnl)
    if market_price <= 0 or not math.isfinite(market_price):
        raise ValueError("observation_market_price_invalid")
    if not math.isfinite(unrealized_pnl):
        raise ValueError("observation_unrealized_pnl_invalid")
    if remaining_seconds is not None:
        remaining_seconds = max(int(remaining_seconds), 0)
    probabilities = _probability_triplet(
        tp_probability,
        sl_probability,
        range_probability,
    )
    context_json, context_bytes, context_hash = _encoded_json(
        context or {},
        limit=MAX_CHECKPOINT_CONTEXT_BYTES,
        error_code="observation_checkpoint_context_too_large",
    )
    session = db.execute(
        """
        SELECT session.id, session.operation_id, session.user_id,
               session.status, session.next_checkpoint_number,
               session.capture_mode, session.planned_interval_minutes,
               operation.symbol, operation.side, operation.time_horizon
        FROM operation_observation_sessions session
        JOIN operations operation ON operation.id = session.operation_id
        WHERE session.id = ?
        FOR UPDATE
        """,
        (int(session_id),),
    ).fetchone()
    if not session:
        raise ValueError("observation_session_not_found")
    if int(session["operation_id"]) != int(operation_id):
        raise ValueError("observation_checkpoint_operation_mismatch")
    if formal_learning_eligible:
        recommendation = db.execute(
            """
            SELECT id, user_id, operation_id, analysis_type,
                   symbol, side, time_horizon
            FROM recommendations
            WHERE id = ?
            LIMIT 1
            """,
            (int(recommendation_id),),
        ).fetchone()
        if not recommendation:
            raise ValueError("observation_recommendation_not_found")
        recommendation = dict(recommendation)
        if (
            recommendation["operation_id"] is not None
            or recommendation["analysis_type"] != OBSERVATION_ANALYSIS_TYPE
            or int(recommendation["user_id"]) != int(session["user_id"])
            or str(recommendation["symbol"]).upper()
            != str(session["symbol"]).upper()
            or str(recommendation["side"]).lower()
            != str(session["side"]).lower()
            or str(recommendation["time_horizon"])
            != str(session["time_horizon"])
        ):
            raise ValueError("observation_recommendation_identity_mismatch")
    if checkpoint_number is None:
        if session["status"] != "active":
            raise ValueError("observation_session_not_active")
        if session["capture_mode"] == "live":
            previous = db.execute(
                """
                SELECT MAX(observed_at) AS last_checkpoint_at
                FROM operation_observation_checkpoints
                WHERE session_id = ?
                """,
                (int(session_id),),
            ).fetchone()
            last_checkpoint_at = (
                previous["last_checkpoint_at"] if previous else None
            )
            if last_checkpoint_at is not None:
                last_observed = datetime.fromisoformat(
                    str(last_checkpoint_at).replace("Z", "+00:00")
                )
                if last_observed.tzinfo is None:
                    last_observed = last_observed.replace(tzinfo=timezone.utc)
                current_observed = datetime.fromisoformat(
                    utc_iso(observed_at).replace("Z", "+00:00")
                )
                next_allowed_at = last_observed.astimezone(
                    timezone.utc
                ) + timedelta(
                    minutes=observation_interval_minutes(
                        session["planned_interval_minutes"]
                    )
                )
                if current_observed < next_allowed_at:
                    raise ValueError("observation_checkpoint_not_due")
        checkpoint_number = int(session["next_checkpoint_number"])
    else:
        checkpoint_number = int(checkpoint_number)
    code = checkpoint_code(operation_id, checkpoint_number)
    inserted = db.execute(
        """
        INSERT INTO operation_observation_checkpoints (
            session_id, operation_id, recommendation_id, checkpoint_number,
            checkpoint_code, observed_at, source_turn_id, market_price,
            unrealized_pnl, remaining_seconds, tp_probability,
            sl_probability, range_probability, decision, decision_candidate,
            contract_quality, formal_learning_eligible, evidence_source,
            context_json, context_bytes, context_sha256, production_effect
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT (checkpoint_code) DO NOTHING
        RETURNING *
        """,
        (
            int(session_id),
            int(operation_id),
            recommendation_id,
            checkpoint_number,
            code,
            utc_iso(observed_at),
            source_turn_id,
            market_price,
            unrealized_pnl,
            remaining_seconds,
            probabilities[0],
            probabilities[1],
            probabilities[2],
            decision,
            bool(decision_candidate),
            contract_quality,
            formal_learning_eligible,
            evidence_source,
            context_json,
            context_bytes,
            context_hash,
            OBSERVATION_PRODUCTION_EFFECT,
        ),
    ).fetchone()
    if inserted:
        db.execute(
            """
            UPDATE operation_observation_sessions
            SET stored_checkpoint_count = stored_checkpoint_count + 1,
                reported_checkpoint_count = GREATEST(
                    reported_checkpoint_count,
                    ?
                ),
                next_checkpoint_number = GREATEST(
                    next_checkpoint_number,
                    ?
                ),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (checkpoint_number, checkpoint_number + 1, int(session_id)),
        )
        return dict(inserted)
    existing = db.execute(
        """
        SELECT *
        FROM operation_observation_checkpoints
        WHERE checkpoint_code = ?
        LIMIT 1
        """,
        (code,),
    ).fetchone()
    if not existing:
        raise RuntimeError("observation_checkpoint_conflict_without_row")
    existing = dict(existing)
    if existing["context_sha256"] != context_hash:
        raise RuntimeError("observation_checkpoint_existing_payload_mismatch")
    return existing


def update_reconstructed_session_summary(
    db,
    *,
    session_id: int,
    reported_checkpoint_count: int,
    ended_at: datetime | str,
    summary: dict,
) -> dict:
    summary_json, summary_bytes, summary_hash = _encoded_json(
        summary,
        limit=MAX_SESSION_SUMMARY_BYTES,
        error_code="observation_session_summary_too_large",
    )
    return dict(
        db.execute(
            """
            UPDATE operation_observation_sessions
            SET status = 'completed',
                ended_at = ?,
                reported_checkpoint_count = ?,
                summary_json = ?,
                summary_bytes = ?,
                summary_sha256 = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND capture_mode = 'reconstructed'
            RETURNING *
            """,
            (
                utc_iso(ended_at),
                int(reported_checkpoint_count),
                summary_json,
                summary_bytes,
                summary_hash,
                int(session_id),
            ),
        ).fetchone()
    )


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _terminal_outcome(operation: dict) -> tuple[str | None, str | None]:
    reason = str(operation.get("close_reason") or "").strip().lower()
    if reason == "take_profit":
        return "tp_first_within_horizon", None
    if reason == "stop_loss":
        return "sl_first_within_horizon", None
    return None, "operation_terminal_without_tp_sl"


def _pnl_at_price(operation: dict, price: float) -> float:
    entry = float(operation["entry"])
    variation = (float(price) - entry) / entry
    if str(operation["side"]).lower() == "short":
        variation *= -1.0
    return float(operation["margin"]) * float(operation["leverage"]) * variation


def _selected_probability_stage(snapshot: dict, time_horizon: str) -> dict:
    probability_trace = snapshot.get("probability_trace")
    if not isinstance(probability_trace, dict):
        return {}
    stages = probability_trace.get("stage_traces")
    if not isinstance(stages, list):
        return {}
    exact = [
        stage
        for stage in stages
        if isinstance(stage, dict)
        and str(stage.get("time_horizon") or "") == time_horizon
    ]
    if exact:
        return exact[-1]
    usable = [stage for stage in stages if isinstance(stage, dict)]
    return usable[-1] if usable else {}


def _selected_observation_feature_source(
    snapshot: dict,
    time_horizon: str,
) -> tuple[dict, str | None, str]:
    """Read the selected stage from either full or compact v0.9 evidence.

    Early compact observation rows retained ``stage_contexts`` but did not
    always retain ``probability_trace.stage_traces``.  Both locations contain
    the same pre-analysis feature vector; preferring the probability trace and
    falling back to the stage context preserves old evidence without fetching
    or reconstructing market data.
    """
    probability_stage = _selected_probability_stage(snapshot, time_horizon)
    probability_features = _compact_scalar_tree(
        probability_stage.get("current_feature_values")
    )
    if isinstance(probability_features, dict) and probability_features:
        return (
            probability_features,
            probability_stage.get("interval"),
            "snapshot.probability_trace.stage_traces.current_feature_values",
        )

    contexts = snapshot.get("stage_contexts")
    contexts = contexts if isinstance(contexts, dict) else {}
    context = contexts.get(time_horizon)
    if not isinstance(context, dict):
        matching = [
            value
            for value in contexts.values()
            if isinstance(value, dict)
            and str(value.get("time_horizon") or "") == time_horizon
        ]
        context = matching[-1] if matching else {}
    context_features = _compact_scalar_tree(context.get("feature_values"))
    if isinstance(context_features, dict) and context_features:
        return (
            context_features,
            context.get("interval"),
            "snapshot.stage_contexts.selected_horizon.feature_values",
        )
    raise ValueError("observation_predictive_features_missing")


def build_observation_terminal_counterfactual_payload(
    *,
    operation: dict,
    checkpoint: dict,
    snapshot: dict,
) -> dict:
    """Resolve a checkpoint as soon as the real operation hits TP or SL."""
    from counterfactual_learning import MAX_FEATURE_PAYLOAD_BYTES

    analysis_at = _parse_utc(snapshot.get("analysis_at")) or _parse_utc(
        checkpoint.get("observed_at")
    )
    if analysis_at is None:
        raise ValueError("observation_analysis_at_missing")
    data_cutoff_at = _parse_utc(snapshot.get("data_cutoff_at")) or analysis_at
    if data_cutoff_at > analysis_at:
        raise ValueError("observation_data_cutoff_after_analysis")
    time_horizon = str(
        snapshot.get("time_horizon") or operation.get("time_horizon") or ""
    )
    default_horizons = {
        "intraday_short": 14_400,
        "intraday_wide": 86_400,
        "short_swing": 604_800,
    }
    try:
        horizon_seconds = int(snapshot.get("evaluation_horizon_seconds"))
    except (TypeError, ValueError):
        horizon_seconds = int(default_horizons.get(time_horizon, 0))
    if horizon_seconds <= 0:
        raise ValueError("observation_horizon_missing")
    evaluation_expires_at = analysis_at + timedelta(seconds=horizon_seconds)
    feature_values, pretrade_interval, _feature_values_source = (
        _selected_observation_feature_source(snapshot, time_horizon)
    )
    feature_values_json = canonical_json(feature_values)
    feature_payload_bytes = len(feature_values_json.encode("utf-8"))
    if not 0 < feature_payload_bytes <= MAX_FEATURE_PAYLOAD_BYTES:
        raise ValueError("observation_predictive_features_too_large")
    outcome_label, exclusion_code = _terminal_outcome(operation)
    evaluation_status = "evaluated" if outcome_label else "excluded"
    terminal_at = _parse_utc(operation.get("closed_at"))
    terminal_identity = {
        "operation_id": int(operation["id"]),
        "closed_at": utc_iso(terminal_at or datetime.now(timezone.utc)),
        "close_reason": operation.get("close_reason"),
        "close_price": _finite_number(operation.get("close_price")),
        "exit_evidence": _json_object(operation.get("exit_evidence_json")),
    }
    source_snapshot_sha256 = payload_sha256(snapshot)
    run_key = payload_sha256(
        {
            "recommendation_id": int(checkpoint["recommendation_id"]),
            "evaluator_version": OBSERVATION_PREDICTIVE_EVALUATOR_VERSION,
            "source_snapshot_sha256": source_snapshot_sha256,
        }
    )
    result_identity = {
        "run_key": run_key,
        "feature_values": feature_values,
        "outcome_label": outcome_label,
        "exclusion_code": exclusion_code,
        "first_touch_at": terminal_identity["closed_at"] if outcome_label else None,
        "market_sha256": payload_sha256(terminal_identity),
    }
    version_contract = snapshot.get("version_contract")
    version_contract = version_contract if isinstance(version_contract, dict) else {}
    return {
        "run_key": run_key,
        "recommendation_id": int(checkpoint["recommendation_id"]),
        "user_id": int(operation["user_id"]),
        "evaluator_version": OBSERVATION_PREDICTIVE_EVALUATOR_VERSION,
        "schema_version": OBSERVATION_PREDICTIVE_SCHEMA_VERSION,
        "contract_quality": "exact",
        "formal_learning_eligible": True,
        "analysis_at_source": "snapshot.analysis_at",
        "data_cutoff_source": "snapshot.data_cutoff_at",
        "plan_source": "snapshot.explicit_levels",
        "horizon_source": "snapshot.evaluation_horizon_seconds",
        "source_engine_version": str(
            checkpoint.get("engine_version")
            or version_contract.get("engine_version")
            or "unknown"
        ),
        "source_scoring_version": version_contract.get("scoring_version"),
        "symbol": str(operation["symbol"]).upper(),
        "side": str(operation["side"]).lower(),
        "time_horizon": time_horizon,
        "analysis_at": utc_iso(analysis_at),
        "data_cutoff_at": utc_iso(data_cutoff_at),
        "evaluation_expires_at": utc_iso(evaluation_expires_at),
        "horizon_seconds": horizon_seconds,
        "entry": float(snapshot.get("entry") or checkpoint["market_price"]),
        "take_profit": float(operation["take_profit"]),
        "stop_loss": float(operation["stop_loss"]),
        "tp_probability": float(checkpoint["tp_probability"]),
        "sl_probability": float(checkpoint["sl_probability"]),
        "range_probability": float(checkpoint["range_probability"]),
        "evaluation_status": evaluation_status,
        "exclusion_code": exclusion_code,
        "pretrade_status": "evaluated",
        "pretrade_interval": pretrade_interval,
        "feature_values_json": feature_values_json,
        "feature_payload_bytes": feature_payload_bytes,
        "outcome_status": (
            "resolved_from_operation_terminal_event"
            if outcome_label
            else "operation_closed_without_predictive_terminal"
        ),
        "outcome_label": outcome_label,
        "first_touch_at": terminal_identity["closed_at"] if outcome_label else None,
        "coverage_ratio": 1.0 if outcome_label else None,
        "candle_count": None,
        "expected_candle_count": None,
        "market_sha256": result_identity["market_sha256"],
        "source_snapshot_sha256": source_snapshot_sha256,
        "result_sha256": payload_sha256(result_identity),
        "evidence_source": "operation_terminal_event",
        "production_effect": OBSERVATION_PRODUCTION_EFFECT,
    }


def build_exit_counterfactual_evaluation(
    *,
    operation: dict,
    checkpoint: dict,
) -> dict:
    final_pnl = float(operation.get("final_pnl") or 0.0)
    close_pnl = float(checkpoint.get("unrealized_pnl") or 0.0)
    pnl_advantage = close_pnl - final_pnl
    stop_pnl = _pnl_at_price(operation, float(operation["stop_loss"]))
    tp_pnl = _pnl_at_price(operation, float(operation["take_profit"]))
    initial_risk = abs(stop_pnl)
    tp_probability = float(checkpoint.get("tp_probability") or 0.0)
    sl_probability = float(checkpoint.get("sl_probability") or 0.0)
    range_probability = float(checkpoint.get("range_probability") or 0.0)
    expected_hold_pnl = (
        tp_probability * tp_pnl
        + sl_probability * stop_pnl
        + range_probability * close_pnl
    )
    expected_close_advantage = close_pnl - expected_hold_pnl
    tolerance = max(initial_risk * 0.01, 0.01)
    if pnl_advantage > tolerance:
        absolute_verdict = "close_would_have_improved_final_pnl"
    elif pnl_advantage < -tolerance:
        absolute_verdict = "holding_was_better_than_closing_here"
    else:
        absolute_verdict = "economically_equivalent"
    r_advantage = pnl_advantage / initial_risk if initial_risk > 0 else None
    if r_advantage is not None and r_advantage >= 0.10:
        risk_verdict = "close_protected_at_least_0_10r"
    elif r_advantage is not None and r_advantage <= -0.10:
        risk_verdict = "hold_added_at_least_0_10r"
    else:
        risk_verdict = "difference_below_0_10r"
    observed_at = _parse_utc(checkpoint.get("observed_at"))
    closed_at = _parse_utc(operation.get("closed_at"))
    time_to_terminal = None
    if observed_at is not None and closed_at is not None:
        time_to_terminal = max(
            (closed_at - observed_at).total_seconds() / 60.0,
            0.0,
        )
    outcome_label, _ = _terminal_outcome(operation)
    return {
        "persist_args": {
            "actual_final_pnl": final_pnl,
            "pnl_if_closed": close_pnl,
            "tp_reached_after": outcome_label == "tp_first_within_horizon",
            "sl_reached_after": outcome_label == "sl_first_within_horizon",
            "time_to_terminal_minutes": time_to_terminal,
            "protected_drawdown": max(pnl_advantage, 0.0),
            "absolute_profit_verdict": absolute_verdict,
            "risk_adjusted_verdict": risk_verdict,
            "contract_quality": str(
                checkpoint.get("contract_quality") or "exact"
            ),
            "evaluated_at": operation.get("closed_at")
            or datetime.now(timezone.utc),
        },
        "evaluation": {
            "evaluator_version": EXIT_COUNTERFACTUAL_VERSION,
            "checkpoint_code": checkpoint.get("checkpoint_code"),
            "model_probabilities": {
                "tp": tp_probability,
                "sl": sl_probability,
                "range": range_probability,
            },
            "economic_choices": {
                "pnl_if_closed": close_pnl,
                "actual_final_pnl": final_pnl,
                "pnl_advantage_if_closed": pnl_advantage,
                "initial_risk_amount": initial_risk,
                "advantage_r": r_advantage,
                "model_expected_hold_pnl": expected_hold_pnl,
                "model_expected_close_advantage": expected_close_advantage,
                "model_preferred_action": (
                    "close" if expected_close_advantage > 0.0 else "hold"
                ),
                "range_assumption": "retain_current_unrealized_pnl",
            },
            "terminal_outcome": {
                "close_reason": operation.get("close_reason"),
                "time_to_terminal_minutes": time_to_terminal,
            },
            "production_effect": "none",
        },
    }


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    numerator = math.fsum(
        (x - left_mean) * (y - right_mean) for x, y in zip(left, right)
    )
    left_variance = math.fsum((value - left_mean) ** 2 for value in left)
    right_variance = math.fsum((value - right_mean) ** 2 for value in right)
    denominator = math.sqrt(left_variance * right_variance)
    return numerator / denominator if denominator > 0 else None


def _rule_evolution(checkpoints: list[dict], outcome_class: str | None) -> list[dict]:
    grouped: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for checkpoint in checkpoints:
        for signal in checkpoint.get("rule_signals") or []:
            key = (str(signal.get("stage") or ""), str(signal.get("rule_id") or ""))
            grouped.setdefault(key, []).append(
                (
                    str(checkpoint.get("checkpoint_code") or ""),
                    str(signal.get("tone") or "context"),
                    str(signal.get("category") or "observational"),
                )
            )
    result = []
    for (stage, rule_id), readings in sorted(grouped.items()):
        tones = [tone for _, tone, _ in readings]
        categories = Counter(category for _, _, category in readings)
        counts = Counter(tones)
        correct_tone = "favorable" if outcome_class == "tp" else "adverse"
        directional = [tone for tone in tones if tone in {"favorable", "adverse"}]
        longest_adverse = current_adverse = 0
        for tone in tones:
            current_adverse = current_adverse + 1 if tone == "adverse" else 0
            longest_adverse = max(longest_adverse, current_adverse)
        terminal_adverse = 0
        for tone in reversed(tones):
            if tone != "adverse":
                break
            terminal_adverse += 1
        first_adverse = next(
            (code for code, tone, _ in readings if tone == "adverse"),
            None,
        )
        result.append(
            {
                "stage": stage,
                "rule_id": rule_id,
                "category": categories.most_common(1)[0][0],
                "tones": dict(counts),
                "directional": {
                    "cases": len(directional),
                    "hits": sum(tone == correct_tone for tone in directional),
                },
                "first_adverse_checkpoint": first_adverse,
                "last_tone": tones[-1] if tones else None,
                "longest_adverse_streak": longest_adverse,
                "terminal_adverse_streak": terminal_adverse,
            }
        )
    return result


def build_observation_episode_summary(
    *,
    session: dict,
    operation: dict,
    checkpoints: list[dict],
    storage: dict,
    opening_learning: dict | None,
) -> dict:
    checkpoint_views = [observation_checkpoint_view(row) for row in checkpoints]
    outcome_label, exclusion_code = _terminal_outcome(operation)
    outcome_class = (
        "tp" if outcome_label == "tp_first_within_horizon"
        else "sl" if outcome_label == "sl_first_within_horizon"
        else None
    )
    checkpoint_probabilities = [
        (
            row,
            {
                "tp": float(row["tp_probability"]),
                "sl": float(row["sl_probability"]),
                "range": float(row["range_probability"]),
            },
        )
        for row in checkpoints
        if row.get("tp_probability") is not None
        and row.get("sl_probability") is not None
        and row.get("range_probability") is not None
    ]
    probabilities = [probability for _, probability in checkpoint_probabilities]
    prediction = {
        "cases": len(probabilities),
        "outcome": outcome_class or "excluded",
        "exclusion_code": exclusion_code,
        "mean_probabilities": {
            name: (
                math.fsum(row[name] for row in probabilities) / len(probabilities)
                if probabilities else None
            )
            for name in ("tp", "sl", "range")
        },
        "tp_probability_at_least_70pct": sum(
            row["tp"] >= 0.70 for row in probabilities
        ),
    }
    if outcome_class and probabilities:
        prediction.update(
            {
                "log_loss": -math.fsum(
                    math.log(max(row[outcome_class], 1e-15))
                    for row in probabilities
                ) / len(probabilities),
                "multiclass_brier": math.fsum(
                    math.fsum(
                        (
                            row[name]
                            - (1.0 if name == outcome_class else 0.0)
                        ) ** 2
                        for name in ("tp", "sl", "range")
                    )
                    for row in probabilities
                ) / len(probabilities),
                "top_class_accuracy": sum(
                    max(row, key=row.get) == outcome_class
                    for row in probabilities
                ) / len(probabilities),
            }
        )
    conditional_tp = []
    geometry_tp = []
    for checkpoint, probability in checkpoint_probabilities:
        resolution = probability["tp"] + probability["sl"]
        entry = float(checkpoint["market_price"])
        take_profit = float(operation["take_profit"])
        stop_loss = float(operation["stop_loss"])
        if str(operation["side"]).lower() == "short":
            target_distance = abs(math.log(entry / take_profit))
            adverse_distance = abs(math.log(stop_loss / entry))
        else:
            target_distance = abs(math.log(take_profit / entry))
            adverse_distance = abs(math.log(entry / stop_loss))
        distance_sum = target_distance + adverse_distance
        if resolution > 0 and distance_sum > 0:
            conditional_tp.append(probability["tp"] / resolution)
            geometry_tp.append(adverse_distance / distance_sum)
    geometry_correlation = _pearson(conditional_tp, geometry_tp)
    geometry_mae = (
        math.fsum(abs(left - right) for left, right in zip(conditional_tp, geometry_tp))
        / len(conditional_tp)
        if conditional_tp else None
    )
    final_pnl = float(operation.get("final_pnl") or 0.0)
    best_checkpoint = max(
        checkpoints,
        key=lambda row: float(row.get("unrealized_pnl") or 0.0),
        default=None,
    )
    best_observed_pnl = (
        float(best_checkpoint.get("unrealized_pnl") or 0.0)
        if best_checkpoint else None
    )
    intervals = []
    observed_times = [
        _parse_utc(row.get("observed_at")) for row in checkpoints
    ]
    observed_times = [value for value in observed_times if value is not None]
    for previous, current in zip(observed_times, observed_times[1:]):
        intervals.append((current - previous).total_seconds() / 60.0)
    initial_risk = abs(_pnl_at_price(operation, float(operation["stop_loss"])))
    exit_candidates = []
    for row in checkpoints:
        evaluation = build_exit_counterfactual_evaluation(
            operation=operation,
            checkpoint=row,
        )["evaluation"]["economic_choices"]
        if (
            float(evaluation["pnl_if_closed"]) > 0.0
            and float(evaluation["model_expected_close_advantage"]) > 0.0
        ):
            exit_candidates.append(
                {
                    "checkpoint_code": row["checkpoint_code"],
                    "pnl_if_closed": evaluation["pnl_if_closed"],
                    "close_advantage_vs_model_hold": evaluation[
                        "model_expected_close_advantage"
                    ],
                }
            )
    rules = _rule_evolution(checkpoint_views, outcome_class)
    exit_candidate_count = len(exit_candidates)
    exit_candidates = sorted(
        exit_candidates,
        key=lambda item: (
            float(item["pnl_if_closed"]),
            float(item["close_advantage_vs_model_hold"]),
        ),
        reverse=True,
    )[:8]
    conclusions = []
    if outcome_class == "sl" and prediction["tp_probability_at_least_70pct"]:
        conclusions.append(
            {
                "code": "high_tp_confidence_failed",
                "evidence": prediction["tp_probability_at_least_70pct"],
            }
        )
    if geometry_correlation is not None and abs(geometry_correlation) >= 0.90:
        conclusions.append(
            {
                "code": "probability_strongly_geometry_correlated",
                "evidence": geometry_correlation,
            }
        )
    if best_observed_pnl is not None and best_observed_pnl > 0 and final_pnl < 0:
        conclusions.append(
            {
                "code": "profitable_exit_opportunity_before_loss",
                "evidence": {
                    "checkpoint": best_checkpoint["checkpoint_code"],
                    "observed_pnl": best_observed_pnl,
                    "final_pnl": final_pnl,
                },
            }
        )
    actual_mfe = (
        _finite_number(opening_learning.get("max_favorable_pnl"))
        if opening_learning else None
    )
    if (
        actual_mfe is not None
        and best_observed_pnl is not None
        and actual_mfe > best_observed_pnl + 0.01
    ):
        conclusions.append(
            {
                "code": "scheduled_checkpoints_missed_true_mfe",
                "evidence": {
                    "true_mfe": actual_mfe,
                    "best_checkpoint_pnl": best_observed_pnl,
                },
            }
        )
    useful_observational = []
    if outcome_class in {"tp", "sl"}:
        for rule in rules:
            directional = rule["directional"]
            cases = int(directional["cases"])
            hits = int(directional["hits"])
            if (
                rule["stage"] == str(operation["time_horizon"])
                and rule["category"] == "observational"
                and cases >= 3
                and hits / cases >= 0.60
            ):
                useful_observational.append(
                    {
                        "rule_id": rule["rule_id"],
                        "directional_cases": cases,
                        "directional_hits": hits,
                        "first_adverse_checkpoint": rule[
                            "first_adverse_checkpoint"
                        ],
                        "terminal_adverse_streak": rule[
                            "terminal_adverse_streak"
                        ],
                    }
                )
    if useful_observational:
        conclusions.append(
            {
                "code": "observational_rules_directionally_consistent_in_episode",
                "evidence": useful_observational[:6],
                "scope_limit": "single_dependent_episode_not_global_weight_evidence",
            }
        )
    return {
        "learning_status": "complete",
        "episode_evaluator_version": OBSERVATION_EPISODE_EVALUATOR_VERSION,
        "contract_version": OBSERVATION_CONTRACT_VERSION,
        "rule_catalog": observation_rule_catalog_reference(),
        "operation": {
            "id": int(operation["id"]),
            "symbol": operation["symbol"],
            "side": operation["side"],
            "time_horizon": operation["time_horizon"],
            "close_reason": operation.get("close_reason"),
            "final_pnl": final_pnl,
            "initial_risk_amount": initial_risk,
            "final_r_multiple": final_pnl / initial_risk if initial_risk else None,
        },
        "counts": {
            "checkpoints": len(checkpoints),
            "predictive_evaluations": len(
                [row for row in checkpoints if row.get("recommendation_id")]
            ),
            "exit_evaluations": len(checkpoints),
            "rule_series": len(rules),
        },
        "prediction_evaluation": prediction,
        "geometry_diagnostic": {
            "comparison": "conditional_tp_vs_barrier_distance_baseline",
            "correlation": geometry_correlation,
            "mean_absolute_error": geometry_mae,
            "interpretation": (
                "strong_geometry_dependence"
                if geometry_correlation is not None
                and abs(geometry_correlation) >= 0.90
                else "no_strong_geometry_dependence_detected"
            ),
        },
        "exit_evaluation": {
            "best_observed_checkpoint": (
                best_checkpoint.get("checkpoint_code") if best_checkpoint else None
            ),
            "best_observed_pnl": best_observed_pnl,
            "actual_max_favorable_pnl": actual_mfe,
            "actual_max_adverse_pnl": (
                _finite_number(opening_learning.get("max_adverse_pnl"))
                if opening_learning else None
            ),
            "profitable_model_close_candidate_count": exit_candidate_count,
            "profitable_model_close_candidates": exit_candidates,
            "maximum_gap_minutes": max(intervals) if intervals else None,
        },
        "rule_evolution": rules,
        "conclusions": conclusions,
        "storage": storage,
        "governance": {
            "production_effect": "none",
            "automatic_rule_weight_change": False,
            "episode_weighting_required_for_global_inference": True,
        },
    }


def _finalize_observation_session_learning(
    db,
    *,
    session: dict,
    operation: dict,
) -> None:
    from counterfactual_learning import persist_counterfactual_payload

    checkpoint_rows = [
        dict(row)
        for row in db.execute(
            """
            SELECT checkpoint.*, recommendation.snapshot_json,
                   recommendation.engine_version
            FROM operation_observation_checkpoints AS checkpoint
            LEFT JOIN recommendations AS recommendation
              ON recommendation.id = checkpoint.recommendation_id
            WHERE checkpoint.session_id = ?
            ORDER BY checkpoint.checkpoint_number ASC
            """,
            (int(session["id"]),),
        ).fetchall()
    ]
    bytes_before = 0
    bytes_after = 0
    compacted = 0
    compact_exact = 0
    for checkpoint in checkpoint_rows:
        if not checkpoint.get("recommendation_id"):
            continue
        snapshot = _json_object(checkpoint.get("snapshot_json"))
        if not snapshot:
            raise ValueError("observation_snapshot_missing")
        original_json = canonical_json(snapshot)
        bytes_before += len(original_json.encode("utf-8"))
        compact = compact_observation_snapshot(snapshot)
        compact_json = canonical_json(compact)
        bytes_after += len(compact_json.encode("utf-8"))
        existing_evaluation = db.execute(
            """
            SELECT 1
            FROM recommendation_counterfactual_evaluations
            WHERE recommendation_id = ?
            LIMIT 1
            """,
            (int(checkpoint["recommendation_id"]),),
        ).fetchone()
        if snapshot.get("storage_profile") != OBSERVATION_STORAGE_PROFILE:
            if existing_evaluation:
                raise RuntimeError(
                    "observation_snapshot_cannot_compact_after_evaluation"
                )
            db.execute(
                "UPDATE recommendations SET snapshot_json = ? WHERE id = ?",
                (compact_json, int(checkpoint["recommendation_id"])),
            )
            compacted += 1
        checkpoint["snapshot_json"] = compact_json
        compact_exact += 1

    for checkpoint in checkpoint_rows:
        if checkpoint.get("recommendation_id"):
            snapshot = _json_object(checkpoint.get("snapshot_json"))
            payload = build_observation_terminal_counterfactual_payload(
                operation=operation,
                checkpoint=checkpoint,
                snapshot=snapshot,
            )
            persist_counterfactual_payload(db, payload)
        exit_result = build_exit_counterfactual_evaluation(
            operation=operation,
            checkpoint=checkpoint,
        )
        existing_exit = db.execute(
            """
            SELECT 1
            FROM operation_exit_counterfactuals
            WHERE checkpoint_id = ? AND evaluator_version = ?
            LIMIT 1
            """,
            (int(checkpoint["id"]), EXIT_COUNTERFACTUAL_VERSION),
        ).fetchone()
        if not existing_exit:
            persist_exit_counterfactual(
                db,
                checkpoint=checkpoint,
                evaluation=exit_result["evaluation"],
                **exit_result["persist_args"],
            )

    counts = dict(
        db.execute(
            """
            SELECT
                COUNT(*) AS checkpoints,
                COUNT(*) FILTER (
                    WHERE checkpoint.recommendation_id IS NOT NULL
                ) AS predictive_contracts,
                COUNT(rce.id) AS predictive_evaluations,
                COUNT(oec.id) AS exit_evaluations
            FROM operation_observation_checkpoints AS checkpoint
            LEFT JOIN recommendation_counterfactual_evaluations AS rce
              ON rce.recommendation_id = checkpoint.recommendation_id
             AND rce.evaluator_version = ?
            LEFT JOIN operation_exit_counterfactuals AS oec
              ON oec.checkpoint_id = checkpoint.id
             AND oec.evaluator_version = ?
            WHERE checkpoint.session_id = ?
            """,
            (
                OBSERVATION_PREDICTIVE_EVALUATOR_VERSION,
                EXIT_COUNTERFACTUAL_VERSION,
                int(session["id"]),
            ),
        ).fetchone()
    )
    if int(counts["predictive_evaluations"]) != int(counts["predictive_contracts"]):
        raise RuntimeError("observation_predictive_evaluation_incomplete")
    if int(counts["exit_evaluations"]) != int(counts["checkpoints"]):
        raise RuntimeError("observation_exit_evaluation_incomplete")
    if compact_exact != int(counts["predictive_contracts"]):
        raise RuntimeError("observation_compact_contract_incomplete")

    opening_learning_raw = db.execute(
        """
        SELECT max_favorable_pnl, max_adverse_pnl, evidence_coverage_ratio,
               evidence_candle_count, evidence_expected_candles,
               learning_evaluator_version
        FROM learning_evaluations
        WHERE operation_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(operation["id"]),),
    ).fetchone()
    opening_learning = dict(opening_learning_raw) if opening_learning_raw else None
    summary = build_observation_episode_summary(
        session=session,
        operation=operation,
        checkpoints=checkpoint_rows,
        storage={
            "profile": OBSERVATION_STORAGE_PROFILE,
            "compacted_snapshots": compacted,
            "snapshot_bytes_before": bytes_before,
            "snapshot_bytes_after": bytes_after,
            "bytes_saved": bytes_before - bytes_after,
            "reduction_ratio": (
                1.0 - bytes_after / bytes_before if bytes_before else 0.0
            ),
        },
        opening_learning=opening_learning,
    )
    summary["counts"]["predictive_evaluations"] = int(
        counts["predictive_evaluations"]
    )
    summary["counts"]["exit_evaluations"] = int(counts["exit_evaluations"])
    summary_json, summary_bytes, summary_hash = _encoded_json(
        summary,
        limit=MAX_SESSION_SUMMARY_BYTES,
        error_code="observation_episode_summary_too_large",
    )
    current_status = str(session["status"])
    target_status = "cancelled" if current_status == "cancelled" else "completed"
    ended_at = (
        session.get("ended_at")
        if target_status == "cancelled" and session.get("ended_at")
        else operation.get("closed_at") or datetime.now(timezone.utc)
    )
    existing_close_event = db.execute(
        """
        SELECT 1
        FROM operation_observation_session_events
        WHERE session_id = ? AND event_type = 'operation_closed'
        LIMIT 1
        """,
        (int(session["id"]),),
    ).fetchone()
    if not existing_close_event:
        record_observation_session_event(
            db,
            session_id=int(session["id"]),
            operation_id=int(session["operation_id"]),
            event_type="operation_closed",
            occurred_at=operation.get("closed_at") or ended_at,
            from_status=current_status,
            to_status=target_status,
            interval_minutes=int(session.get("planned_interval_minutes") or 20),
            details={
                "operation_status": "CLOSED",
                "learning_status": "complete",
                "episode_evaluator_version": OBSERVATION_EPISODE_EVALUATOR_VERSION,
            },
        )
    updated = db.execute(
        """
        UPDATE operation_observation_sessions
        SET status = ?, paused_at = NULL, ended_at = ?,
            summary_json = ?, summary_bytes = ?, summary_sha256 = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING id
        """,
        (
            target_status,
            utc_iso(ended_at),
            summary_json,
            summary_bytes,
            summary_hash,
            int(session["id"]),
        ),
    ).fetchone()
    if not updated:
        raise RuntimeError("observation_session_learning_not_finalized")
    from observational_learning_base import persist_observation_checkpoint_cases

    persist_observation_checkpoint_cases(db, int(operation["id"]))


def finalize_closed_observation_sessions(
    db,
    *,
    operation_id: int | None = None,
) -> int:
    """Finalize only after every checkpoint has evaluable conclusions."""
    operation_filter = ""
    params: tuple[int, ...] = ()
    if operation_id is not None:
        operation_filter = "AND session.operation_id = ?"
        params = (int(operation_id),)
    rows = db.execute(
        f"""
        SELECT to_jsonb(session) AS session_record,
               to_jsonb(operation) AS operation_record
        FROM operation_observation_sessions AS session
        JOIN operations AS operation ON operation.id = session.operation_id
        WHERE operation.status = 'CLOSED'
          AND session.status IN ('active', 'paused', 'completed', 'cancelled')
          AND (
                COALESCE(
                    session.summary_json::jsonb->>'learning_status',
                    ''
                ) <> 'complete'
                OR EXISTS (
                    SELECT 1
                    FROM operation_observation_checkpoints AS checkpoint
                    WHERE checkpoint.session_id = session.id
                      AND checkpoint.recommendation_id IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM recommendation_counterfactual_evaluations AS rce
                          WHERE rce.recommendation_id = checkpoint.recommendation_id
                            AND rce.evaluator_version = ?
                      )
                )
              )
          {operation_filter}
        ORDER BY session.id ASC
        FOR UPDATE OF session
        """,
        (OBSERVATION_PREDICTIVE_EVALUATOR_VERSION, *params),
    ).fetchall()
    finalized = 0
    for raw_row in rows:
        records = dict(raw_row)
        session = _json_object(records.get("session_record"))
        operation = _json_object(records.get("operation_record"))
        if not session or not operation:
            raise RuntimeError("observation_finalization_record_invalid")
        _finalize_observation_session_learning(
            db,
            session=session,
            operation=operation,
        )
        finalized += 1
    return finalized


def persist_exit_counterfactual(
    db,
    *,
    checkpoint: dict,
    actual_final_pnl: float,
    pnl_if_closed: float,
    tp_reached_after: bool,
    sl_reached_after: bool,
    time_to_terminal_minutes: float | None,
    protected_drawdown: float | None,
    absolute_profit_verdict: str,
    risk_adjusted_verdict: str,
    contract_quality: str,
    evaluation: dict,
    evaluated_at: datetime | str,
) -> dict:
    if contract_quality not in EVIDENCE_QUALITIES:
        raise ValueError("observation_exit_quality_invalid")
    evaluation_json, evaluation_bytes, evaluation_hash = _encoded_json(
        evaluation,
        limit=MAX_EXIT_EVALUATION_BYTES,
        error_code="observation_exit_evaluation_too_large",
    )
    actual_final_pnl = float(actual_final_pnl)
    pnl_if_closed = float(pnl_if_closed)
    inserted = db.execute(
        """
        INSERT INTO operation_exit_counterfactuals (
            operation_id, checkpoint_id, evaluator_version, evaluated_at,
            actual_final_pnl, pnl_if_closed, missed_profit,
            protected_drawdown, tp_reached_after, sl_reached_after,
            time_to_terminal_minutes, absolute_profit_verdict,
            risk_adjusted_verdict, contract_quality,
            formal_learning_eligible, evaluation_json, evaluation_bytes,
            evaluation_sha256, production_effect
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT (checkpoint_id, evaluator_version) DO NOTHING
        RETURNING *
        """,
        (
            int(checkpoint["operation_id"]),
            int(checkpoint["id"]),
            EXIT_COUNTERFACTUAL_VERSION,
            utc_iso(evaluated_at),
            actual_final_pnl,
            pnl_if_closed,
            actual_final_pnl - pnl_if_closed,
            protected_drawdown,
            bool(tp_reached_after),
            bool(sl_reached_after),
            time_to_terminal_minutes,
            absolute_profit_verdict,
            risk_adjusted_verdict,
            contract_quality,
            contract_quality == "exact",
            evaluation_json,
            evaluation_bytes,
            evaluation_hash,
            OBSERVATION_PRODUCTION_EFFECT,
        ),
    ).fetchone()
    if inserted:
        return dict(inserted)
    existing = db.execute(
        """
        SELECT *
        FROM operation_exit_counterfactuals
        WHERE checkpoint_id = ? AND evaluator_version = ?
        LIMIT 1
        """,
        (int(checkpoint["id"]), EXIT_COUNTERFACTUAL_VERSION),
    ).fetchone()
    if not existing:
        raise RuntimeError("observation_exit_conflict_without_row")
    existing = dict(existing)
    if existing["evaluation_sha256"] != evaluation_hash:
        raise RuntimeError("observation_exit_existing_payload_mismatch")
    return existing


def observation_session_report(db, operation_id: int) -> dict | None:
    session = db.execute(
        """
        SELECT *
        FROM operation_observation_sessions
        WHERE operation_id = ?
        LIMIT 1
        """,
        (int(operation_id),),
    ).fetchone()
    if not session:
        return None
    session = dict(session)
    counts = dict(
        db.execute(
            """
            SELECT
                COUNT(*) AS stored_checkpoints,
                COUNT(*) FILTER (
                    WHERE oc.formal_learning_eligible
                ) AS exact_cases,
                COUNT(*) FILTER (
                    WHERE oc.decision_candidate
                ) AS decision_candidates,
                COUNT(rce.id) FILTER (
                    WHERE rce.evaluation_status = 'evaluated'
                ) AS predictively_resolved,
                COUNT(oec.id) AS exit_counterfactuals,
                MAX(oc.observed_at) AS last_checkpoint_at
            FROM operation_observation_checkpoints oc
            LEFT JOIN recommendation_counterfactual_evaluations rce
                ON rce.recommendation_id = oc.recommendation_id
               AND rce.evaluator_version = ?
            LEFT JOIN operation_exit_counterfactuals oec
                ON oec.checkpoint_id = oc.id
               AND oec.evaluator_version = ?
            WHERE oc.session_id = ?
            """,
            (
                OBSERVATION_PREDICTIVE_EVALUATOR_VERSION,
                EXIT_COUNTERFACTUAL_VERSION,
                int(session["id"]),
            ),
        ).fetchone()
    )
    session["summary"] = json.loads(session.pop("summary_json"))
    session.update(counts)
    if session["capture_mode"] == "live":
        session["planned_interval_minutes"] = observation_interval_minutes(
            session.get("planned_interval_minutes") or 20
        )
    last_checkpoint_at = session.get("last_checkpoint_at")
    if last_checkpoint_at is not None:
        session["last_checkpoint_at"] = utc_iso(last_checkpoint_at)
    next_due_at = observation_next_due_at(session)
    session["next_checkpoint_due_at"] = (
        next_due_at.isoformat() if next_due_at is not None else None
    )
    return session


def _json_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _flatten_numeric_values(value: Any, prefix: str = "") -> dict[str, float]:
    flattened: dict[str, float] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten_numeric_values(child, path))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        number = _finite_number(value)
        if number is not None:
            flattened[prefix] = number
    return flattened


def _metric(
    values: dict[str, float],
    path: str,
    label: str,
) -> dict | None:
    value = values.get(path)
    if value is None:
        return None
    return {"key": path, "label": label, "value": value}


def _tone_from_score(score: float | None, threshold: float) -> str:
    if score is None or not math.isfinite(score):
        return "context"
    if score >= threshold:
        return "favorable"
    if score <= -threshold:
        return "adverse"
    return "neutral"


def _rule_signal(trace: dict, *, stage: str, side: str) -> dict | None:
    rule_id = str(trace.get("rule_id") or "")
    metadata = rule_registry().get(rule_id)
    if metadata is None:
        return None
    outputs = trace.get("outputs") if isinstance(trace.get("outputs"), dict) else {}
    values = _flatten_numeric_values(outputs)
    probability_effect = str(trace.get("probability_effect") or "")
    category = "principal" if (
        probability_effect
        and "none" not in probability_effect
        and "shadow" not in str(trace.get("status") or "")
    ) else "observational"
    side_sign = -1.0 if str(side).lower() == "short" else 1.0
    score: float | None = None
    threshold = 0.05
    metrics: list[dict] = []
    explanation = "Lectura contextual; por sí sola no decide mantener ni cerrar."

    def add(path: str, label: str) -> float | None:
        item = _metric(values, path, label)
        if item is not None:
            metrics.append(item)
            return float(item["value"])
        return None

    if rule_id == "M4-RULE-PATH-STRUCTURE-001":
        raw = add("directional_path_efficiency_h", "Eficiencia direccional")
        score = raw
        threshold = 0.04
        explanation = "Mide si el recorrido reciente avanza de forma eficiente hacia la dirección de la operación."
    elif rule_id == "M4-RULE-MTF-HIERARCHY-001":
        parts = [
            add("directional_path_efficiency_2h", "Eficiencia 2 h"),
            add("directional_path_efficiency_4h", "Eficiencia 4 h"),
        ]
        usable = [value for value in parts if value is not None]
        score = math.fsum(usable) / len(usable) if usable else None
        threshold = 0.04
        explanation = "Comprueba si los tramos cortos mantienen una dirección compatible con el plan."
    elif rule_id == "M4-RULE-VOLATILITY-RANK-001":
        add("volatility_percentile_60", "Percentil de volatilidad")
        explanation = "Sitúa la volatilidad actual frente a sus 60 referencias; no aporta dirección por sí sola."
    elif rule_id == "M4-RULE-AGGRESSOR-IMBALANCE-001":
        raw = add("ATI_H", "Desequilibrio agresor")
        score = side_sign * raw if raw is not None else None
        threshold = 0.03
        explanation = "Compara compras y ventas ejecutadas agresivamente y las orienta al lado de la operación."
    elif rule_id == "LIB-CAND-EMA-TREND-001":
        slope = add("side_adjusted_slope_atr", "Pendiente EMA50 / ATR")
        close = add("side_adjusted_close_vs_ema50_log", "Precio frente EMA50")
        cross = add("side_adjusted_ema50_vs_ema200_log", "EMA50 frente EMA200")
        votes = []
        if slope is not None:
            votes.append(max(-1.0, min(1.0, slope / 0.20)))
        if close is not None:
            votes.append(max(-1.0, min(1.0, close / 0.004)))
        if cross is not None:
            votes.append(max(-1.0, min(1.0, cross / 0.004)))
        score = math.fsum(votes) / len(votes) if votes else None
        threshold = 0.20
        explanation = "Resume posición, cruce y pendiente de las medias, ya ajustados a LONG o SHORT."
    elif rule_id == "LIB-CAND-RSI-WILDER-001":
        score = add("side_adjusted_centered_rsi", "RSI centrado y orientado")
        threshold = 0.12
        explanation = "Mide si el impulso RSI acompaña la dirección de la operación."
    elif rule_id == "LIB-CAND-ATR-EXTENSION-001":
        extension = add("side_adjusted_extension_atr", "Extensión en ATR")
        if extension is not None:
            score = -1.0 if extension > 2.5 else extension / 2.0
        threshold = 0.25
        explanation = "Indica avance o retroceso frente a EMA20; una extensión extrema también alerta de agotamiento."
    elif rule_id == "LIB-CAND-RELATIVE-VOLUME-001":
        add("relative_horizon_volume", "Volumen relativo")
        add("volume_midrank_60", "Rango de volumen")
        explanation = "Mide actividad, pero necesita una señal direccional para ser favorable o adversa."
    elif rule_id == "LIB-CAND-CVD-SLOPE-001":
        slope = add("side_adjusted_normalized_cvd_slope", "Pendiente CVD orientada")
        imbalance = add("side_adjusted_terminal_imbalance", "Desequilibrio terminal")
        usable = [value for value in (slope, imbalance) if value is not None]
        score = math.fsum(usable) / len(usable) if usable else None
        threshold = 0.025
        explanation = "Comprueba si el flujo ejecutado persiste a favor o en contra del lado elegido."
    elif rule_id == "LIB-CAND-ABSORPTION-001":
        favorable = add("favorable_absorption_score", "Absorción favorable")
        adverse = add("adverse_absorption_score", "Absorción adversa")
        displacement = add(
            "side_adjusted_horizon_displacement_atr",
            "Desplazamiento orientado / ATR",
        )
        if favorable is not None or adverse is not None:
            score = float(favorable or 0.0) - float(adverse or 0.0)
        threshold = 0.12
        explanation = (
            "Busca absorción real combinando volumen, desplazamiento, mechas y "
            "flujo ejecutado; sin sus puntuaciones de absorción queda como contexto."
        )
    elif rule_id == "LIB-CAND-COMPRESSION-001":
        add("compression_vector.atr_rank", "Rango ATR")
        add("compression_vector.bollinger_width_rank", "Anchura Bollinger")
        explanation = "Describe compresión o expansión; no establece por sí sola hacia dónde romperá."
    elif rule_id == "M4-RULE-PRIOR-EXTREMA-001":
        obstacle = add("target_extreme_between_entry_and_tp", "Extremo previo hacia TP")
        score = -float(obstacle) if obstacle is not None else None
        threshold = 0.50
        explanation = "Detecta si existe un extremo previo que puede actuar como obstáculo antes del TP."
    elif rule_id == "LIB-CAND-STRUCTURAL-LEVEL-DISTANCE-001":
        target = add("target_path_level_count", "Niveles hacia TP")
        adverse = add("adverse_path_level_count", "Niveles hacia SL")
        if target is not None or adverse is not None:
            denominator = max(float(target or 0.0) + float(adverse or 0.0), 1.0)
            score = (float(adverse or 0.0) - float(target or 0.0)) / denominator
        threshold = 0.20
        explanation = "Compara barreras estructurales en el camino al TP frente a las situadas hacia el SL."
    elif rule_id == "LIB-CAND-FIBONACCI-DISTANCE-001":
        add(
            "nearest_to_take_profit.absolute_distance_sigma_horizon",
            "Distancia Fibonacci a TP / sigma",
        )
        add(
            "nearest_to_stop_loss.absolute_distance_sigma_horizon",
            "Distancia Fibonacci a SL / sigma",
        )
        explanation = "Muestra proximidad a niveles Fibonacci; todavía es evidencia observacional, no una dirección."
    elif rule_id == "LIB-CAND-LIQUIDATION-ZONE-001":
        target = add("target_cascade_mass.within_2pct", "Masa hacia TP (2%)")
        adverse = add("adverse_cascade_mass.within_2pct", "Masa hacia SL (2%)")
        add("sample_size", "Muestra del mapa")
        if target is not None or adverse is not None:
            score = math.log((float(target or 0.0) + 1.0) / (float(adverse or 0.0) + 1.0))
        threshold = 0.35
        explanation = "Compara concentraciones de liquidación visibles hacia el objetivo y hacia el riesgo."
    elif rule_id == "LIB-CAND-ORDERBOOK-IMBALANCE-001":
        current = add(
            "current_snapshot.side_adjusted_imbalances.top_20",
            "Desequilibrio top 20",
        )
        persistent = add(
            "persistence.top_20.side_adjusted_mean",
            "Persistencia media",
        )
        flow = add(
            "executed_flow.side_adjusted_executed_flow_imbalance",
            "Flujo ejecutado",
        )
        usable = [value for value in (current, persistent, flow) if value is not None]
        score = math.fsum(usable) / len(usable) if usable else None
        threshold = 0.10
        explanation = "Combina desequilibrio, persistencia y flujo ejecutado; una fotografía aislada no basta."

    return {
        "key": f"{stage}:{rule_id}",
        "stage": stage,
        "rule_id": rule_id,
        "label": RULE_LABELS.get(rule_id, str(metadata["name"])),
        "category": category,
        "status": str(trace.get("status") or "unknown"),
        "probability_effect": probability_effect or "unknown",
        "tone": _tone_from_score(score, threshold),
        "score": score,
        "metrics": metrics[:3],
        "explanation": explanation,
    }


def observation_rule_signals(snapshot: dict) -> list[dict]:
    stage_traces = snapshot.get("stage_rule_traces")
    if not isinstance(stage_traces, dict):
        return []
    side = str(snapshot.get("side") or "long")
    result: list[dict] = []
    for stage, traces in stage_traces.items():
        if not isinstance(traces, list):
            continue
        for trace in traces:
            if not isinstance(trace, dict):
                continue
            signal = _rule_signal(trace, stage=str(stage), side=side)
            if signal is not None:
                result.append(signal)
    return result


def observation_checkpoint_view(row: dict) -> dict:
    snapshot = _json_object(row.get("snapshot_json"))
    context = _json_object(row.get("context_json"))
    stored_rule_signals = context.get("monitor_rule_signals")
    rule_signals = (
        stored_rule_signals
        if isinstance(stored_rule_signals, list)
        else observation_rule_signals(snapshot)
    )
    probability_trace = snapshot.get("probability_trace")
    stage_count = 0
    horizon_seconds = _finite_number(
        context.get("analysis_horizon_seconds")
        or snapshot.get("evaluation_horizon_seconds")
    )
    if isinstance(probability_trace, dict):
        traces = probability_trace.get("stage_traces")
        stage_count = len(traces) if isinstance(traces, list) else 0
    return {
        "id": int(row.get("id") or 0),
        "checkpoint_number": int(row.get("checkpoint_number") or 0),
        "checkpoint_code": str(row.get("checkpoint_code") or ""),
        "observed_at": utc_iso(row["observed_at"]),
        "market_price": _finite_number(row.get("market_price")),
        "unrealized_pnl": _finite_number(row.get("unrealized_pnl")),
        "remaining_seconds": (
            int(row["remaining_seconds"])
            if row.get("remaining_seconds") is not None
            else None
        ),
        "analysis_horizon_seconds": (
            int(horizon_seconds) if horizon_seconds is not None else None
        ),
        "tp_probability": _finite_number(row.get("tp_probability")),
        "sl_probability": _finite_number(row.get("sl_probability")),
        "range_probability": _finite_number(row.get("range_probability")),
        "stored_decision": str(row.get("decision") or "unreviewed"),
        "stored_decision_candidate": bool(row.get("decision_candidate")),
        "contract_quality": str(row.get("contract_quality") or "unknown"),
        "formal_learning_eligible": bool(row.get("formal_learning_eligible")),
        "recommendation_id": row.get("recommendation_id"),
        "engine_version": row.get("engine_version"),
        "stage_count": stage_count,
        "rule_signals": rule_signals,
        "context": {
            "checkpoint_trigger": context.get("checkpoint_trigger"),
            "market_price_source": context.get("market_price_source"),
        },
    }


def observation_closure_advisory(
    checkpoints: list[dict],
    *,
    terminal_pnl: dict[str, float] | None = None,
) -> dict:
    usable = [
        item
        for item in checkpoints
        if _finite_number(item.get("tp_probability")) is not None
        and _finite_number(item.get("sl_probability")) is not None
    ]
    if not usable:
        return {
            "policy_version": OBSERVATION_CLOSURE_POLICY_VERSION,
            "level": "waiting",
            "label": "Esperando controles",
            "headline": "Aún no hay un análisis exacto para interpretar.",
            "reasons": ["El worker generará el primer punto de control cuando corresponda."],
            "checkpoint_code": None,
            "production_effect": "none",
        }
    latest = usable[-1]
    first = usable[0]
    recent = usable[-3:]
    tp = float(latest["tp_probability"])
    sl = float(latest["sl_probability"])
    edge = tp - sl
    first_edge = float(first["tp_probability"]) - float(first["sl_probability"])
    edge_change = edge - first_edge
    recent_edges = [
        float(item["tp_probability"]) - float(item["sl_probability"])
        for item in recent
    ]
    persistent_adverse = len(recent) >= 3 and all(value <= -0.06 for value in recent_edges)
    persistent_favorable = len(recent) >= 3 and all(value >= 0.06 for value in recent_edges)
    deteriorating = len(usable) >= 2 and edge_change <= -0.10
    improving = len(usable) >= 2 and edge_change >= 0.10
    latest_observational = [
        signal
        for signal in latest.get("rule_signals", [])
        if signal.get("category") == "observational"
    ]
    adverse_rules = [
        signal["label"]
        for signal in latest_observational
        if signal.get("tone") == "adverse"
    ]
    favorable_rules = [
        signal["label"]
        for signal in latest_observational
        if signal.get("tone") == "favorable"
    ]
    pnl = _finite_number(latest.get("unrealized_pnl"))
    economic_advantages: list[float] = []
    if terminal_pnl is not None:
        tp_pnl = _finite_number(terminal_pnl.get("tp"))
        sl_pnl = _finite_number(terminal_pnl.get("sl"))
        if tp_pnl is not None and sl_pnl is not None:
            for item in recent:
                item_pnl = _finite_number(item.get("unrealized_pnl"))
                if item_pnl is None:
                    continue
                hold_value = (
                    float(item["tp_probability"]) * tp_pnl
                    + float(item["sl_probability"]) * sl_pnl
                    + float(item.get("range_probability") or 0.0) * item_pnl
                )
                economic_advantages.append(item_pnl - hold_value)
    persistent_profit_protection = (
        pnl is not None
        and pnl > 0.0
        and len(economic_advantages) >= 3
        and all(value > 0.0 for value in economic_advantages[-3:])
    )
    reasons: list[str] = []
    level = "hold"
    label = "Mantener bajo observación"
    headline = "No hay evidencia conjunta suficiente para señalar un cierre."

    if persistent_profit_protection:
        level = "protect_candidate"
        label = "Candidato para proteger beneficio"
        headline = (
            "Cerrar conserva más valor que mantener según tres evaluaciones "
            "económicas consecutivas."
        )
        reasons.append(
            f"La operación conserva {pnl:+.2f} USDT y la ventaja estimada de "
            f"cerrar ahora es {economic_advantages[-1]:+.2f} USDT frente a mantener."
        )
        reasons.append(
            "La señal económica se ha repetido en tres controles; no depende de un único tick."
        )
        if adverse_rules:
            reasons.append(
                "Acompañan la protección: "
                + ", ".join(list(dict.fromkeys(adverse_rules))[:4])
                + "."
            )
    elif persistent_adverse and (deteriorating or len(set(adverse_rules)) >= 2):
        level = "close_candidate"
        label = "Candidato de cierre"
        headline = "La ventaja se ha deteriorado de forma persistente y varias señales coinciden."
        reasons.append(
            f"En los tres últimos controles, la diferencia TP−SL se mantuvo adversa; ahora es {edge * 100:+.1f} puntos."
        )
        if deteriorating:
            reasons.append(
                f"La ventaja ha caído {abs(edge_change) * 100:.1f} puntos desde el primer control disponible."
            )
        if adverse_rules:
            reasons.append(
                "Confirman el deterioro: "
                + ", ".join(list(dict.fromkeys(adverse_rules))[:4])
                + "."
            )
    elif edge <= -0.06 or deteriorating or len(set(adverse_rules)) >= 2:
        level = "watch"
        label = "Vigilar de cerca"
        headline = "Hay deterioro, pero todavía no es persistente o no tiene confirmación suficiente."
        if edge <= -0.06:
            reasons.append(f"La lectura actual TP−SL es adversa: {edge * 100:+.1f} puntos.")
        if deteriorating:
            reasons.append("La lectura ha empeorado frente al primer control disponible.")
        if adverse_rules:
            reasons.append(
                "Señales observacionales adversas: "
                + ", ".join(list(dict.fromkeys(adverse_rules))[:4])
                + "."
            )
    elif persistent_favorable or edge >= 0.06:
        label = "Mantener"
        headline = "La lectura principal conserva ventaja hacia el TP."
        reasons.append(f"La diferencia TP−SL actual es {edge * 100:+.1f} puntos.")
        if improving:
            reasons.append("La ventaja ha mejorado desde el primer control disponible.")
        if favorable_rules:
            reasons.append(
                "Acompañan, sin alterar la probabilidad: "
                + ", ".join(list(dict.fromkeys(favorable_rules))[:4])
                + "."
            )
    else:
        reasons.append(f"La diferencia TP−SL actual es {edge * 100:+.1f} puntos.")

    if pnl is not None:
        reasons.append(f"Resultado flotante observado: {pnl:+.2f} USDT.")
    if len(usable) < 3:
        reasons.append(
            f"Sólo hay {len(usable)} control(es); se exige persistencia en tres para declarar un candidato de cierre."
        )
        if level == "close_candidate":
            level = "watch"
            label = "Vigilar de cerca"
    remaining = latest.get("remaining_seconds")
    horizon = latest.get("analysis_horizon_seconds")
    if remaining is not None and horizon and int(remaining) < int(horizon):
        reasons.append(
            "La probabilidad mostrada reevalúa una entrada nueva en el horizonte completo; el tiempo restante del plan se muestra aparte y no se falsea con una interpolación."
        )
    return {
        "policy_version": OBSERVATION_CLOSURE_POLICY_VERSION,
        "level": level,
        "label": label,
        "headline": headline,
        "reasons": reasons,
        "checkpoint_code": latest.get("checkpoint_code"),
        "current_edge": edge,
        "edge_change": edge_change,
        "recent_checkpoint_count": len(recent),
        "adverse_observational_count": len(set(adverse_rules)),
        "favorable_observational_count": len(set(favorable_rules)),
        "model_expected_close_advantage": (
            economic_advantages[-1] if economic_advantages else None
        ),
        "economic_confirmation_count": len(
            [value for value in economic_advantages[-3:] if value > 0.0]
        ),
        "production_effect": "none",
    }


def observation_monitor_report(
    db,
    operation_id: int,
    *,
    checkpoint_limit: int = 120,
    before_checkpoint_number: int | None = None,
    after_checkpoint_number: int | None = None,
) -> dict | None:
    if before_checkpoint_number is not None and after_checkpoint_number is not None:
        raise ValueError("observation_monitor_cursor_conflict")
    session = observation_session_report(db, operation_id)
    if session is None:
        return None
    operation = db.execute(
        """
        SELECT id, user_id, symbol, side, status, time_horizon, entry,
               stop_loss, take_profit, margin, leverage, started_at,
               closed_at, close_price, final_pnl
        FROM operations
        WHERE id = ?
        LIMIT 1
        """,
        (int(operation_id),),
    ).fetchone()
    if not operation:
        raise ValueError("observation_operation_not_found")
    limit = max(10, min(int(checkpoint_limit), 200))
    params: list[Any] = [int(session["id"])]
    cursor_sql = ""
    order_sql = "DESC"
    if before_checkpoint_number is not None:
        cursor_sql = "AND checkpoint.checkpoint_number < ?"
        params.append(int(before_checkpoint_number))
    elif after_checkpoint_number is not None:
        cursor_sql = "AND checkpoint.checkpoint_number > ?"
        order_sql = "ASC"
        params.append(int(after_checkpoint_number))
    params.append(limit + 1)
    rows = db.execute(
        f"""
        SELECT checkpoint.*,
               CASE
                   WHEN jsonb_typeof(
                       checkpoint.context_json::jsonb -> 'monitor_rule_signals'
                   ) = 'array'
                   THEN NULL
                   ELSE jsonb_build_object(
                       'side', recommendation.snapshot_json::jsonb -> 'side',
                       'stage_rule_traces', recommendation.snapshot_json::jsonb -> 'stage_rule_traces',
                       'probability_trace', jsonb_build_object(
                           'stage_traces', recommendation.snapshot_json::jsonb #> '{{probability_trace,stage_traces}}'
                       ),
                       'evaluation_horizon_seconds', recommendation.snapshot_json::jsonb -> 'evaluation_horizon_seconds'
                   )
               END AS snapshot_json,
               recommendation.engine_version
        FROM operation_observation_checkpoints AS checkpoint
        LEFT JOIN recommendations AS recommendation
          ON recommendation.id = checkpoint.recommendation_id
        WHERE checkpoint.session_id = ?
          {cursor_sql}
        ORDER BY checkpoint.checkpoint_number {order_sql}
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    has_more = len(rows) > limit
    selected_rows = list(rows[:limit])
    checkpoints = [observation_checkpoint_view(dict(row)) for row in selected_rows]
    if order_sql == "DESC":
        checkpoints.reverse()
    events = []
    for raw_event in db.execute(
        """
        SELECT id, event_type, occurred_at, from_status, to_status,
               interval_minutes, details_json
        FROM operation_observation_session_events
        WHERE session_id = ?
        ORDER BY occurred_at ASC, id ASC
        """,
        (int(session["id"]),),
    ).fetchall():
        event = dict(raw_event)
        event["occurred_at"] = utc_iso(event["occurred_at"])
        event["details"] = _json_object(event.pop("details_json"))
        events.append(event)
    terminal_pnl = {
        "tp": _pnl_at_price(dict(operation), float(operation["take_profit"])),
        "sl": _pnl_at_price(dict(operation), float(operation["stop_loss"])),
    }
    advisory = None
    if after_checkpoint_number is None:
        advisory = observation_closure_advisory(
            checkpoints,
            terminal_pnl=terminal_pnl,
        )
    elif checkpoints:
        # Incremental refreshes return no historical snapshots.  Only scalar
        # values from the first and last three checkpoints are needed for the
        # closure policy; the newest compact rule signals are already present.
        recent_rows = db.execute(
            """
            SELECT id, checkpoint_number, checkpoint_code, observed_at,
                   market_price, unrealized_pnl, remaining_seconds,
                   tp_probability, sl_probability, range_probability,
                   decision, decision_candidate, contract_quality,
                   formal_learning_eligible, recommendation_id, context_json
            FROM operation_observation_checkpoints
            WHERE session_id = ?
            ORDER BY checkpoint_number DESC
            LIMIT 3
            """,
            (int(session["id"]),),
        ).fetchall()
        advisory_checkpoints = [
            observation_checkpoint_view(dict(row))
            for row in reversed(recent_rows)
        ]
        newest = checkpoints[-1]
        advisory_checkpoints = [
            newest
            if int(item["checkpoint_number"]) == int(newest["checkpoint_number"])
            else item
            for item in advisory_checkpoints
        ]
        first_row = db.execute(
            """
            SELECT id, checkpoint_number, checkpoint_code, observed_at,
                   market_price, unrealized_pnl, remaining_seconds,
                   tp_probability, sl_probability, range_probability,
                   decision, decision_candidate, contract_quality,
                   formal_learning_eligible, recommendation_id, context_json
            FROM operation_observation_checkpoints
            WHERE session_id = ?
            ORDER BY checkpoint_number ASC
            LIMIT 1
            """,
            (int(session["id"]),),
        ).fetchone()
        if first_row:
            first_view = observation_checkpoint_view(dict(first_row))
            if not advisory_checkpoints or (
                int(first_view["checkpoint_number"])
                != int(advisory_checkpoints[0]["checkpoint_number"])
            ):
                advisory_checkpoints.insert(0, first_view)
        advisory = observation_closure_advisory(
            advisory_checkpoints,
            terminal_pnl=terminal_pnl,
        )
    return {
        "operation": dict(operation),
        "session": session,
        "checkpoints": checkpoints,
        "events": events,
        "advisory": advisory,
        "incremental": after_checkpoint_number is not None,
        "pagination": {
            "has_more": has_more,
            "oldest_checkpoint_number": (
                checkpoints[0]["checkpoint_number"] if checkpoints else None
            ),
            "latest_checkpoint_number": (
                checkpoints[-1]["checkpoint_number"]
                if checkpoints
                else after_checkpoint_number
            ),
            "limit": limit,
        },
        "semantics": {
            "probability": "fresh_entry_same_side_same_tp_sl_full_selected_horizon",
            "remaining_time": "original_operation_plan_time_remaining",
            "closure_advisory": (
                "persistent_multi_signal_and_economic_value_observation_only"
            ),
            "automatic_close": False,
            "production_effect": "none",
        },
    }


def unified_predictive_inventory(db) -> dict:
    opening = dict(
        db.execute(
            """
            SELECT
                COUNT(*) AS cases,
                COUNT(DISTINCT le.operation_id) AS episodes
            FROM learning_evaluations le
            WHERE le.recommendation_id IS NOT NULL
            """
        ).fetchone()
    )
    observations = dict(
        db.execute(
            """
            SELECT
                COUNT(*) AS cases,
                COUNT(DISTINCT oc.operation_id) AS episodes,
                COUNT(*) FILTER (
                    WHERE oc.formal_learning_eligible
                ) AS formal_contracts,
                COUNT(*) FILTER (
                    WHERE rce.evaluation_status = 'evaluated'
                ) AS resolved_cases
            FROM operation_observation_checkpoints oc
            LEFT JOIN recommendation_counterfactual_evaluations rce
                ON rce.recommendation_id = oc.recommendation_id
               AND rce.evaluator_version = ?
            """
            ,
            (OBSERVATION_PREDICTIVE_EVALUATOR_VERSION,),
        ).fetchone()
    )
    combined = dict(
        db.execute(
            """
            SELECT COUNT(DISTINCT operation_id) AS distinct_episodes
            FROM (
                SELECT le.operation_id
                FROM learning_evaluations le
                WHERE le.recommendation_id IS NOT NULL
                UNION ALL
                SELECT oc.operation_id
                FROM operation_observation_checkpoints oc
            ) source_episodes
            """
        ).fetchone()
    )
    return {
        "opening": opening,
        "observation": observations,
        "combined_raw_cases": int(opening["cases"]) + int(observations["cases"]),
        "combined_distinct_episodes": int(combined["distinct_episodes"]),
        "counting_policy": {
            "raw_cases": "all comparable analyses",
            "effective_cases": "episode-weighted before rule promotion",
            "production_rule_changes": "manual_review_only",
        },
    }
