from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any


OBSERVATION_ANALYSIS_TYPE = "operation_observation"
OBSERVATION_CONTRACT_VERSION = "operation-observation-contract-v0.3"
EXIT_COUNTERFACTUAL_VERSION = "operation-exit-counterfactual-v0.1"
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


def finalize_closed_observation_sessions(db) -> int:
    rows = db.execute(
        """
        SELECT session.*, operation.closed_at AS operation_closed_at
        FROM operation_observation_sessions AS session
        JOIN operations AS operation ON operation.id = session.operation_id
        WHERE session.operation_id = operation.id
          AND session.status IN ('active', 'paused')
          AND operation.status = 'CLOSED'
        FOR UPDATE OF session
        """
    ).fetchall()
    finalized = 0
    for raw_session in rows:
        session = dict(raw_session)
        ended_at = session.get("operation_closed_at") or datetime.now(timezone.utc)
        updated = db.execute(
            """
            UPDATE operation_observation_sessions
            SET status = 'completed', paused_at = NULL,
                ended_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status IN ('active', 'paused')
            RETURNING id
            """,
            (utc_iso(ended_at), int(session["id"])),
        ).fetchone()
        if not updated:
            continue
        record_observation_session_event(
            db,
            session_id=int(session["id"]),
            operation_id=int(session["operation_id"]),
            event_type="operation_closed",
            occurred_at=ended_at,
            from_status=str(session["status"]),
            to_status="completed",
            interval_minutes=int(session.get("planned_interval_minutes") or 20),
            details={"operation_status": "CLOSED"},
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
            LEFT JOIN operation_exit_counterfactuals oec
                ON oec.checkpoint_id = oc.id
            WHERE oc.session_id = ?
            """,
            (int(session["id"]),),
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
    if rule_id not in RULE_LABELS:
        return None
    outputs = trace.get("outputs") if isinstance(trace.get("outputs"), dict) else {}
    values = _flatten_numeric_values(outputs)
    probability_effect = str(trace.get("probability_effect") or "")
    category = (
        "observational"
        if "none" in probability_effect or "shadow" in str(trace.get("status") or "")
        else "principal"
    )
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
        score = side_sign * raw if raw is not None else None
        threshold = 0.04
        explanation = "Mide si el recorrido reciente avanza de forma eficiente hacia la dirección de la operación."
    elif rule_id == "M4-RULE-MTF-HIERARCHY-001":
        parts = [
            add("directional_path_efficiency_2h", "Eficiencia 2 h"),
            add("directional_path_efficiency_4h", "Eficiencia 4 h"),
        ]
        usable = [side_sign * value for value in parts if value is not None]
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
        elif displacement is not None:
            score = displacement / 2.0
        threshold = 0.12
        explanation = "Busca absorción real combinando volumen, desplazamiento, mechas y flujo ejecutado."
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
        "label": RULE_LABELS[rule_id],
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
    rule_signals = observation_rule_signals(snapshot)
    probability_trace = snapshot.get("probability_trace")
    stage_count = 0
    horizon_seconds = _finite_number(snapshot.get("evaluation_horizon_seconds"))
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


def observation_closure_advisory(checkpoints: list[dict]) -> dict:
    usable = [
        item
        for item in checkpoints
        if _finite_number(item.get("tp_probability")) is not None
        and _finite_number(item.get("sl_probability")) is not None
    ]
    if not usable:
        return {
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
    reasons: list[str] = []
    level = "hold"
    label = "Mantener bajo observación"
    headline = "No hay evidencia conjunta suficiente para señalar un cierre."

    if persistent_adverse and (deteriorating or len(set(adverse_rules)) >= 2):
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
        "production_effect": "none",
    }


def observation_monitor_report(
    db,
    operation_id: int,
    *,
    checkpoint_limit: int = 120,
    before_checkpoint_number: int | None = None,
) -> dict | None:
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
    before_sql = ""
    if before_checkpoint_number is not None:
        before_sql = "AND checkpoint.checkpoint_number < ?"
        params.append(int(before_checkpoint_number))
    params.append(limit + 1)
    rows = db.execute(
        f"""
        SELECT checkpoint.*, recommendation.snapshot_json,
               recommendation.engine_version
        FROM operation_observation_checkpoints AS checkpoint
        LEFT JOIN recommendations AS recommendation
          ON recommendation.id = checkpoint.recommendation_id
        WHERE checkpoint.session_id = ?
          {before_sql}
        ORDER BY checkpoint.checkpoint_number DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    has_more = len(rows) > limit
    selected_rows = list(rows[:limit])
    checkpoints = [
        observation_checkpoint_view(dict(row)) for row in reversed(selected_rows)
    ]
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
    return {
        "operation": dict(operation),
        "session": session,
        "checkpoints": checkpoints,
        "events": events,
        "advisory": observation_closure_advisory(checkpoints),
        "pagination": {
            "has_more": has_more,
            "oldest_checkpoint_number": (
                checkpoints[0]["checkpoint_number"] if checkpoints else None
            ),
            "limit": limit,
        },
        "semantics": {
            "probability": "fresh_entry_same_side_same_tp_sl_full_selected_horizon",
            "remaining_time": "original_operation_plan_time_remaining",
            "closure_advisory": "persistent_multi_signal_observation_only",
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
            """
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
