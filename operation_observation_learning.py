from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any


OBSERVATION_ANALYSIS_TYPE = "operation_observation"
OBSERVATION_CONTRACT_VERSION = "operation-observation-contract-v0.1"
EXIT_COUNTERFACTUAL_VERSION = "operation-exit-counterfactual-v0.1"
OBSERVATION_PRODUCTION_EFFECT = "none"

SESSION_STATUSES = {"active", "completed", "cancelled"}
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
PROBABILITY_TOLERANCE = 1.1e-6


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
                CHECK(status IN ('active', 'completed', 'cancelled')),
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
                (status = 'active' AND ended_at IS NULL)
                OR (status <> 'active' AND ended_at IS NOT NULL)
            ),
            CHECK(
                (capture_mode = 'live' AND evidence_quality = 'exact')
                OR (capture_mode = 'reconstructed'
                    AND evidence_quality = 'reconstructed_partial')
            )
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
        CREATE INDEX IF NOT EXISTS idx_observation_checkpoints_learning
            ON operation_observation_checkpoints(
                formal_learning_eligible, contract_quality, observed_at
            );
        CREATE INDEX IF NOT EXISTS idx_exit_counterfactual_operation
            ON operation_exit_counterfactuals(operation_id, evaluated_at);

        ALTER TABLE operation_observation_sessions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE operation_observation_checkpoints ENABLE ROW LEVEL SECURITY;
        ALTER TABLE operation_exit_counterfactuals ENABLE ROW LEVEL SECURITY;
        REVOKE ALL PRIVILEGES ON TABLE operation_observation_sessions
            FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE operation_observation_checkpoints
            FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE operation_exit_counterfactuals
            FROM anon, authenticated;
        REVOKE DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE operation_observation_sessions FROM service_role;
        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE operation_observation_checkpoints FROM service_role;
        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE operation_exit_counterfactuals FROM service_role;
        GRANT SELECT, INSERT, UPDATE ON TABLE operation_observation_sessions
            TO service_role;
        GRANT SELECT, INSERT ON TABLE operation_observation_checkpoints
            TO service_role;
        GRANT SELECT, INSERT ON TABLE operation_exit_counterfactuals
            TO service_role;
        GRANT USAGE, SELECT ON SEQUENCE operation_observation_sessions_id_seq
            TO service_role;
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
        planned_interval_minutes = int(planned_interval_minutes)
        if not 1 <= planned_interval_minutes <= 1_440:
            raise ValueError("observation_interval_invalid")
    started = utc_iso(started_at or datetime.now(timezone.utc))
    ended = utc_iso(ended_at) if ended_at is not None else None
    if status == "active" and ended is not None:
        raise ValueError("active_observation_cannot_have_end")
    if status != "active" and ended is None:
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
        return dict(inserted)
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
    if existing["contract_version"] != OBSERVATION_CONTRACT_VERSION:
        raise RuntimeError("observation_session_contract_version_mismatch")
    return existing


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
    cursor = db.execute(
        """
        UPDATE operation_observation_sessions AS session
        SET status = 'completed',
            ended_at = COALESCE(operation.closed_at::timestamptz, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        FROM operations AS operation
        WHERE session.operation_id = operation.id
          AND session.status = 'active'
          AND operation.status = 'CLOSED'
        """
    )
    rowcount = getattr(cursor, "rowcount", 0)
    return max(int(rowcount), 0) if isinstance(rowcount, (int, float)) else 0


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
                COUNT(oec.id) AS exit_counterfactuals
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
    return session


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
