from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


_PG_POOL: ConnectionPool | None = None
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def load_local_env() -> None:
    for filename in (".env.local", ".env"):
        path = os.path.join(APP_DIR, filename)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)


load_local_env()


def database_url() -> str:
    url = os.environ.get("SUPABASE_DATABASE_URL", "").strip()
    if not url:
        url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "Falta SUPABASE_DATABASE_URL. Esta version solo soporta PostgreSQL/Supabase."
        )
    if not (url.startswith("postgresql://") or url.startswith("postgres://")):
        raise RuntimeError(
            "SUPABASE_DATABASE_URL debe empezar por postgresql:// o postgres://"
        )
    return url


def _get_pg_pool() -> ConnectionPool:
    """Lazy-init a process-wide connection pool to avoid per-request TCP+TLS setup."""
    global _PG_POOL
    if _PG_POOL is None:
        _PG_POOL = ConnectionPool(
            conninfo=database_url(),
            min_size=int(os.environ.get("DB_POOL_MIN_SIZE", "0")),
            max_size=int(os.environ.get("DB_POOL_MAX_SIZE", "5")),
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            open=True,
            timeout=30,
        )
    return _PG_POOL


def close_pool() -> None:
    global _PG_POOL
    if _PG_POOL is not None:
        _PG_POOL.close(timeout=5)
        _PG_POOL = None


class CursorProxy:
    """Wraps a psycopg cursor and exposes a SQLite-style `lastrowid` attribute."""

    __slots__ = ("cursor", "lastrowid")

    def __init__(self, cursor, lastrowid: int | None = None):
        self.cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return self.cursor.rowcount


class DbSession:
    """Thin wrapper around a psycopg connection that translates legacy
    SQLite-style placeholders (`?`) and a few SQLite-only functions to
    PostgreSQL syntax, and emulates `cursor.lastrowid` via `RETURNING id`."""

    __slots__ = ("connection",)

    # Kept for backwards compatibility with callers that branched on engine.
    engine: str = "postgres"

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query: str, params: tuple | list | None = None):
        pg_query = self._q(query)
        if self._should_return_id(pg_query):
            pg_query = f"{pg_query.rstrip().rstrip(';')} RETURNING id"
            cursor = self.connection.execute(pg_query, self._p(params))
            row = cursor.fetchone()
            lastrowid = None
            if row is not None:
                lastrowid = row["id"] if isinstance(row, dict) else row[0]
            return CursorProxy(cursor=cursor, lastrowid=lastrowid)
        return self.connection.execute(pg_query, self._p(params))

    def executemany(self, query: str, seq_of_params):
        return self.connection.executemany(self._q(query), seq_of_params)

    def executescript(self, script: str):
        for statement in (s.strip() for s in script.split(";") if s.strip()):
            self.connection.execute(statement)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    @staticmethod
    def _q(query: str) -> str:
        translated = query.replace("?", "%s")
        translated = re.sub(r"\bGROUP_CONCAT\b", "string_agg", translated, flags=re.IGNORECASE)
        return translated

    @staticmethod
    def _p(params: tuple | list | None):
        if params is None:
            return ()
        return tuple(params)

    @staticmethod
    def _should_return_id(query: str) -> bool:
        lowered = query.strip().lower()
        return lowered.startswith("insert into ") and " returning " not in lowered


@contextmanager
def connect() -> Iterator[DbSession]:
    """Yield a DbSession backed by a pooled PostgreSQL connection.

    `pool.connection()` commits on clean exit, rolls back on exception,
    and returns the connection to the pool automatically.
    """
    pool = _get_pg_pool()
    with pool.connection() as connection:
        yield DbSession(connection=connection)


def row_to_dict(row) -> dict | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def init_db() -> None:
    id_type = "BIGSERIAL PRIMARY KEY"
    fk_type = "BIGINT"
    blob_type = "BYTEA"
    text_timestamp = "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"

    with connect() as db:
        db.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS users (
                id {id_type},
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                starting_balance REAL NOT NULL DEFAULT 1000,
                cash_balance REAL NOT NULL DEFAULT 1000,
                avatar_path TEXT,
                avatar_mime_type TEXT,
                avatar_data {blob_type},
                avatar_updated_at TEXT,
                created_at {text_timestamp}
            );

            CREATE TABLE IF NOT EXISTS operations (
                id {id_type},
                user_id {fk_type} NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('long', 'short')),
                entry REAL NOT NULL,
                margin REAL NOT NULL,
                leverage REAL NOT NULL,
                time_horizon TEXT NOT NULL DEFAULT 'intraday_short',
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING_ANALYSIS',
                created_at {text_timestamp},
                started_at TEXT,
                closed_at TEXT,
                close_price REAL,
                close_reason TEXT,
                final_pnl REAL,
                observation_until TEXT,
                observation_status TEXT,
                post_emotion TEXT,
                plan_followed TEXT,
                closing_note TEXT,
                observation_result TEXT,
                observation_result_at TEXT,
                observation_summary TEXT,
                learning_outcome TEXT,
                learning_summary TEXT,
                mode TEXT NOT NULL DEFAULT 'training',
                contest_season_id {fk_type},
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id {id_type},
                operation_id {fk_type},
                user_id {fk_type} NOT NULL,
                analysis_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                tp_probability REAL NOT NULL,
                sl_probability REAL NOT NULL,
                range_probability REAL NOT NULL,
                risk_level TEXT NOT NULL,
                setup_grade TEXT NOT NULL,
                confidence TEXT NOT NULL,
                training_decision TEXT NOT NULL,
                time_horizon TEXT NOT NULL DEFAULT 'intraday_short',
                parameter_advice_json TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                alerts_json TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                analysis_json TEXT,
                engine_version TEXT NOT NULL,
                app_version TEXT,
                scoring_version TEXT,
                learning_schema_version TEXT,
                data_source_version TEXT,
                data_contract_version TEXT,
                created_at {text_timestamp},
                FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE SET NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS price_ticks (
                id {id_type},
                operation_id {fk_type},
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                source TEXT NOT NULL,
                captured_at {text_timestamp},
                FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS contest_seasons (
                id {id_type},
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                starting_balance REAL NOT NULL DEFAULT 1000,
                finalized_at TEXT,
                winner_user_id {fk_type},
                winner_username TEXT,
                winner_equity REAL,
                winner_pnl REAL,
                final_leaderboard_json TEXT,
                created_at {text_timestamp}
            );

            CREATE TABLE IF NOT EXISTS contest_entries (
                id {id_type},
                season_id {fk_type} NOT NULL,
                user_id {fk_type} NOT NULL,
                starting_balance REAL NOT NULL DEFAULT 1000,
                cash_balance REAL NOT NULL DEFAULT 1000,
                created_at {text_timestamp},
                UNIQUE(season_id, user_id),
                FOREIGN KEY(season_id) REFERENCES contest_seasons(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS wallet_events (
                id {id_type},
                user_id {fk_type} NOT NULL,
                mode TEXT NOT NULL,
                event_type TEXT NOT NULL,
                amount REAL NOT NULL,
                balance_after REAL,
                operation_id {fk_type},
                contest_season_id {fk_type},
                note TEXT,
                created_at {text_timestamp},
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE SET NULL,
                FOREIGN KEY(contest_season_id) REFERENCES contest_seasons(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS learning_evaluations (
                id {id_type},
                operation_id {fk_type} NOT NULL UNIQUE,
                user_id {fk_type} NOT NULL,
                recommendation_id {fk_type},
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                time_horizon TEXT NOT NULL,
                mode TEXT NOT NULL,
                close_reason TEXT,
                final_pnl REAL NOT NULL DEFAULT 0,
                plan_result TEXT NOT NULL,
                analysis_verdict TEXT NOT NULL,
                primary_lesson TEXT NOT NULL,
                failure_type TEXT,
                user_decision_quality TEXT,
                max_favorable_pct REAL,
                max_adverse_pct REAL,
                max_favorable_pnl REAL,
                max_adverse_pnl REAL,
                time_to_close_minutes REAL,
                would_hit_tp_after_manual INTEGER NOT NULL DEFAULT 0,
                would_hit_sl_after_manual INTEGER NOT NULL DEFAULT 0,
                setup_grade TEXT,
                risk_level TEXT,
                confidence TEXT,
                training_decision TEXT,
                tp_probability REAL,
                sl_probability REAL,
                range_probability REAL,
                technical_label TEXT,
                technical_score REAL,
                market_regime TEXT,
                direction_score REAL,
                confidence_score REAL,
                risk_reward_ratio REAL,
                risk_margin_pct REAL,
                reward_margin_pct REAL,
                leverage_bucket TEXT,
                app_version TEXT,
                scoring_version TEXT,
                learning_evaluator_version TEXT,
                learning_schema_version TEXT,
                data_source_version TEXT,
                data_contract_version TEXT,
                evidence_version TEXT,
                evidence_source TEXT,
                evidence_quality TEXT,
                evidence_status TEXT,
                evidence_path_resolution TEXT,
                evidence_start_at TEXT,
                evidence_end_at TEXT,
                evidence_candle_count INTEGER,
                evidence_expected_candles INTEGER,
                evidence_coverage_ratio REAL,
                first_plan_touch TEXT,
                first_plan_touch_at TEXT,
                first_post_close_touch TEXT,
                first_post_close_touch_at TEXT,
                reconstructed_plan_result TEXT,
                plan_result_consistency TEXT,
                evidence_reconstructed_at TIMESTAMPTZ,
                evidence_json TEXT,
                economic_normalization_version TEXT,
                economic_normalization_status TEXT,
                economic_exclusion_reason TEXT,
                economic_normalized_at TIMESTAMPTZ,
                closure_type TEXT,
                notional_amount DOUBLE PRECISION,
                initial_risk_pct DOUBLE PRECISION,
                initial_risk_amount DOUBLE PRECISION,
                unleveraged_return_pct DOUBLE PRECISION,
                margin_return_pct DOUBLE PRECISION,
                r_multiple DOUBLE PRECISION,
                economic_plan_outcome TEXT,
                economic_final_pnl DOUBLE PRECISION,
                economic_metrics_json TEXT,
                structured_json TEXT NOT NULL,
                created_at {text_timestamp},
                updated_at {text_timestamp},
                FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY(recommendation_id) REFERENCES recommendations(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS learning_evidence_reconstructions (
                id {id_type},
                operation_id {fk_type} NOT NULL,
                evaluation_id {fk_type} NOT NULL,
                reconstruction_version TEXT NOT NULL,
                status TEXT NOT NULL,
                evidence_source TEXT NOT NULL,
                evidence_quality TEXT NOT NULL,
                path_resolution TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT NOT NULL,
                evidence_json TEXT NOT NULL,
                created_at {text_timestamp},
                updated_at {text_timestamp},
                UNIQUE(operation_id, reconstruction_version),
                FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE,
                FOREIGN KEY(evaluation_id) REFERENCES learning_evaluations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS learning_economic_normalizations (
                id {id_type},
                operation_id {fk_type} NOT NULL,
                evaluation_id {fk_type} NOT NULL,
                normalization_version TEXT NOT NULL,
                status TEXT NOT NULL,
                exclusion_reason TEXT,
                before_json TEXT,
                after_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                created_at {text_timestamp},
                updated_at {text_timestamp},
                UNIQUE(operation_id, normalization_version),
                FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE,
                FOREIGN KEY(evaluation_id) REFERENCES learning_evaluations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS learning_legacy_reevaluations (
                id {id_type},
                operation_id {fk_type} NOT NULL,
                evaluation_id {fk_type} NOT NULL,
                reevaluation_version TEXT NOT NULL,
                review_schema_version TEXT NOT NULL,
                review_status TEXT NOT NULL,
                source_engine_version TEXT,
                source_learning_schema_version TEXT,
                source_data_contract_version TEXT,
                source_evaluation_created_at TIMESTAMPTZ,
                source_evaluation_updated_at TIMESTAMPTZ,
                source_bundle_sha256 TEXT NOT NULL,
                original_interpretation_json TEXT NOT NULL,
                reevaluated_contract_json TEXT NOT NULL,
                missing_fields_json TEXT NOT NULL,
                predictive_eligibility_json TEXT NOT NULL,
                outcome_class TEXT NOT NULL,
                outcome_status TEXT NOT NULL,
                reviewed_at TIMESTAMPTZ NOT NULL,
                created_at {text_timestamp},
                UNIQUE(operation_id, reevaluation_version),
                FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE,
                FOREIGN KEY(evaluation_id) REFERENCES learning_evaluations(id) ON DELETE CASCADE
            );
            """
        )
        ensure_column(db, "operations", "observation_until", "TEXT")
        ensure_column(db, "operations", "observation_status", "TEXT")
        ensure_column(db, "operations", "observation_result", "TEXT")
        ensure_column(db, "operations", "observation_result_at", "TEXT")
        ensure_column(db, "operations", "observation_summary", "TEXT")
        ensure_column(db, "operations", "learning_outcome", "TEXT")
        ensure_column(db, "operations", "learning_summary", "TEXT")
        ensure_column(db, "operations", "exit_evidence_json", "TEXT")
        ensure_column(db, "operations", "time_horizon", "TEXT NOT NULL DEFAULT 'intraday_short'")
        ensure_column(db, "operations", "mode", "TEXT NOT NULL DEFAULT 'training'")
        ensure_column(db, "operations", "contest_season_id", "BIGINT")
        ensure_column(db, "users", "starting_balance", "REAL NOT NULL DEFAULT 1000")
        ensure_column(db, "users", "cash_balance", "REAL NOT NULL DEFAULT 1000")
        ensure_column(db, "users", "avatar_path", "TEXT")
        ensure_column(db, "users", "avatar_mime_type", "TEXT")
        ensure_column(db, "users", "avatar_data", blob_type)
        ensure_column(db, "users", "avatar_updated_at", "TEXT")
        ensure_column(db, "contest_seasons", "finalized_at", "TEXT")
        ensure_column(db, "contest_seasons", "winner_user_id", "BIGINT")
        ensure_column(db, "contest_seasons", "winner_username", "TEXT")
        ensure_column(db, "contest_seasons", "winner_equity", "REAL")
        ensure_column(db, "contest_seasons", "winner_pnl", "REAL")
        ensure_column(db, "contest_seasons", "final_leaderboard_json", "TEXT")
        ensure_column(db, "recommendations", "analysis_json", "TEXT")
        ensure_column(db, "recommendations", "time_horizon", "TEXT NOT NULL DEFAULT 'intraday_short'")
        ensure_column(db, "recommendations", "app_version", "TEXT")
        ensure_column(db, "recommendations", "scoring_version", "TEXT")
        ensure_column(db, "recommendations", "learning_schema_version", "TEXT")
        ensure_column(db, "recommendations", "data_source_version", "TEXT")
        ensure_column(db, "recommendations", "data_contract_version", "TEXT")
        ensure_column(db, "learning_evaluations", "app_version", "TEXT")
        ensure_column(db, "learning_evaluations", "scoring_version", "TEXT")
        ensure_column(db, "learning_evaluations", "learning_evaluator_version", "TEXT")
        ensure_column(db, "learning_evaluations", "learning_schema_version", "TEXT")
        ensure_column(db, "learning_evaluations", "data_source_version", "TEXT")
        ensure_column(db, "learning_evaluations", "data_contract_version", "TEXT")
        ensure_column(db, "learning_evaluations", "evidence_version", "TEXT")
        ensure_column(db, "learning_evaluations", "evidence_source", "TEXT")
        ensure_column(db, "learning_evaluations", "evidence_quality", "TEXT")
        ensure_column(db, "learning_evaluations", "evidence_status", "TEXT")
        ensure_column(db, "learning_evaluations", "evidence_path_resolution", "TEXT")
        ensure_column(db, "learning_evaluations", "evidence_start_at", "TEXT")
        ensure_column(db, "learning_evaluations", "evidence_end_at", "TEXT")
        ensure_column(db, "learning_evaluations", "evidence_candle_count", "INTEGER")
        ensure_column(db, "learning_evaluations", "evidence_expected_candles", "INTEGER")
        ensure_column(db, "learning_evaluations", "evidence_coverage_ratio", "REAL")
        ensure_column(db, "learning_evaluations", "first_plan_touch", "TEXT")
        ensure_column(db, "learning_evaluations", "first_plan_touch_at", "TEXT")
        ensure_column(db, "learning_evaluations", "first_post_close_touch", "TEXT")
        ensure_column(db, "learning_evaluations", "first_post_close_touch_at", "TEXT")
        ensure_column(db, "learning_evaluations", "reconstructed_plan_result", "TEXT")
        ensure_column(db, "learning_evaluations", "plan_result_consistency", "TEXT")
        ensure_column(db, "learning_evaluations", "evidence_reconstructed_at", "TIMESTAMPTZ")
        ensure_column(db, "learning_evaluations", "evidence_json", "TEXT")
        ensure_column(db, "learning_evaluations", "economic_normalization_version", "TEXT")
        ensure_column(db, "learning_evaluations", "economic_normalization_status", "TEXT")
        ensure_column(db, "learning_evaluations", "economic_exclusion_reason", "TEXT")
        ensure_column(db, "learning_evaluations", "economic_normalized_at", "TIMESTAMPTZ")
        ensure_column(db, "learning_evaluations", "closure_type", "TEXT")
        ensure_column(db, "learning_evaluations", "notional_amount", "DOUBLE PRECISION")
        ensure_column(db, "learning_evaluations", "initial_risk_pct", "DOUBLE PRECISION")
        ensure_column(db, "learning_evaluations", "initial_risk_amount", "DOUBLE PRECISION")
        ensure_column(db, "learning_evaluations", "unleveraged_return_pct", "DOUBLE PRECISION")
        ensure_column(db, "learning_evaluations", "margin_return_pct", "DOUBLE PRECISION")
        ensure_column(db, "learning_evaluations", "r_multiple", "DOUBLE PRECISION")
        ensure_column(db, "learning_evaluations", "economic_plan_outcome", "TEXT")
        ensure_column(db, "learning_evaluations", "economic_final_pnl", "DOUBLE PRECISION")
        ensure_column(db, "learning_evaluations", "economic_metrics_json", "TEXT")
        ensure_column(db, "learning_evaluations", "updated_at", text_timestamp)
        db.execute("UPDATE users SET starting_balance = 1000 WHERE starting_balance IS NULL")
        db.execute("UPDATE users SET cash_balance = 1000 WHERE cash_balance IS NULL")
        db.execute("UPDATE operations SET mode = 'training' WHERE mode IS NULL OR mode = ''")
        db.execute("UPDATE operations SET time_horizon = 'intraday_short' WHERE time_horizon IS NULL OR time_horizon = ''")
        db.execute("UPDATE recommendations SET time_horizon = 'intraday_short' WHERE time_horizon IS NULL OR time_horizon = ''")
        create_indexes(db)
        ensure_economic_metric_precision(db)
        secure_internal_learning_tables(db)
        ensure_legacy_reevaluations_append_only(db)
        backfill_recommendation_links(db)


def ensure_column(db: DbSession, table: str, column: str, definition: str) -> None:
    exists = db.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        LIMIT 1
        """,
        (table, column),
    ).fetchone()
    if not exists:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_indexes(db: DbSession) -> None:
    db.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_operations_user_mode_status ON operations(user_id, mode, status);
        CREATE INDEX IF NOT EXISTS idx_operations_contest ON operations(contest_season_id, user_id);
        CREATE INDEX IF NOT EXISTS idx_price_ticks_operation_time ON price_ticks(operation_id, captured_at);
        CREATE INDEX IF NOT EXISTS idx_recommendations_user_operation ON recommendations(user_id, operation_id);
        CREATE INDEX IF NOT EXISTS idx_wallet_events_user_mode ON wallet_events(user_id, mode, created_at);
        CREATE INDEX IF NOT EXISTS idx_contest_entries_season ON contest_entries(season_id, user_id);
        CREATE INDEX IF NOT EXISTS idx_learning_evaluations_user_horizon ON learning_evaluations(user_id, time_horizon, side);
        CREATE INDEX IF NOT EXISTS idx_learning_evaluations_pattern ON learning_evaluations(symbol, side, time_horizon, plan_result);
        CREATE INDEX IF NOT EXISTS idx_learning_evidence_status ON learning_evidence_reconstructions(status, evidence_quality);
        CREATE INDEX IF NOT EXISTS idx_learning_evidence_evaluation ON learning_evidence_reconstructions(evaluation_id);
        CREATE INDEX IF NOT EXISTS idx_learning_economic_status ON learning_economic_normalizations(status, exclusion_reason);
        CREATE INDEX IF NOT EXISTS idx_learning_economic_evaluation ON learning_economic_normalizations(evaluation_id);
        CREATE INDEX IF NOT EXISTS idx_learning_evaluations_economics ON learning_evaluations(economic_normalization_status, closure_type);
        CREATE INDEX IF NOT EXISTS idx_learning_legacy_review_status ON learning_legacy_reevaluations(review_status, outcome_class);
        CREATE INDEX IF NOT EXISTS idx_learning_legacy_review_evaluation ON learning_legacy_reevaluations(evaluation_id);
        """
    )


def secure_internal_learning_tables(db: DbSession) -> None:
    db.executescript(
        """
        ALTER TABLE learning_evidence_reconstructions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE learning_economic_normalizations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE learning_legacy_reevaluations ENABLE ROW LEVEL SECURITY;
        REVOKE ALL PRIVILEGES ON TABLE learning_evidence_reconstructions FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE learning_economic_normalizations FROM anon, authenticated;
        REVOKE ALL PRIVILEGES ON TABLE learning_legacy_reevaluations FROM anon, authenticated;
        REVOKE UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
            ON TABLE learning_legacy_reevaluations FROM service_role;
        GRANT SELECT, INSERT ON TABLE learning_legacy_reevaluations TO service_role;
        GRANT USAGE, SELECT
            ON SEQUENCE learning_legacy_reevaluations_id_seq TO service_role;
        """
    )


def ensure_legacy_reevaluations_append_only(db: DbSession) -> None:
    rules = {
        row_to_dict(row)["rulename"]
        for row in db.execute(
            """
            SELECT rulename
            FROM pg_rules
            WHERE schemaname = 'public'
              AND tablename = 'learning_legacy_reevaluations'
            """
        ).fetchall()
    }
    if "learning_legacy_reevaluations_no_update" not in rules:
        db.execute(
            """
            CREATE RULE learning_legacy_reevaluations_no_update AS
            ON UPDATE TO learning_legacy_reevaluations
            DO INSTEAD NOTHING
            """
        )
    if "learning_legacy_reevaluations_no_delete" not in rules:
        db.execute(
            """
            CREATE RULE learning_legacy_reevaluations_no_delete AS
            ON DELETE TO learning_legacy_reevaluations
            DO INSTEAD NOTHING
            """
        )


def ensure_economic_metric_precision(db: DbSession) -> None:
    for column in (
        "notional_amount",
        "initial_risk_pct",
        "initial_risk_amount",
        "unleveraged_return_pct",
        "margin_return_pct",
        "r_multiple",
        "economic_final_pnl",
    ):
        current = db.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
            LIMIT 1
            """,
            ("learning_evaluations", column),
        ).fetchone()
        if current and current["data_type"] == "double precision":
            continue
        db.execute(
            f"""
            ALTER TABLE learning_evaluations
            ALTER COLUMN {column} TYPE DOUBLE PRECISION
            USING {column}::DOUBLE PRECISION
            """
        )


def backfill_recommendation_links(db: DbSession) -> None:
    operations = db.execute(
        """
        SELECT id, user_id, symbol, side, created_at
        FROM operations
        WHERE id NOT IN (
            SELECT operation_id FROM recommendations WHERE operation_id IS NOT NULL
        )
        """
    ).fetchall()
    for operation in operations:
        recommendation = db.execute(
            """
            SELECT id FROM recommendations
            WHERE user_id = ?
              AND symbol = ?
              AND side = ?
              AND operation_id IS NULL
              AND created_at <= ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (operation["user_id"], operation["symbol"], operation["side"], operation["created_at"]),
        ).fetchone()
        if recommendation:
            db.execute(
                "UPDATE recommendations SET operation_id = ? WHERE id = ?",
                (operation["id"], recommendation["id"]),
            )
