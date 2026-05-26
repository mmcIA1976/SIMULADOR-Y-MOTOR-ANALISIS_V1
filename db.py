from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional in local SQLite
    psycopg = None
    dict_row = None


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DEFAULT_DATABASE_URL = f"sqlite:///{DATA_DIR / 'trading_trainer.db'}"


def database_url() -> str:
    supabase_url = os.environ.get("SUPABASE_DATABASE_URL", "").strip()
    if supabase_url:
        return supabase_url
    if os.environ.get("APP_ENV", "").lower() == "production":
        raise RuntimeError("En produccion es obligatorio definir SUPABASE_DATABASE_URL.")
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def is_postgres(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


def sqlite_path() -> Path:
    url = database_url()
    if not url.startswith("sqlite:///"):
        raise RuntimeError(
            "Ruta SQLite invalida. Usa sqlite:///... o una URL postgresql://..."
        )
    return Path(url.replace("sqlite:///", "", 1))


@dataclass
class DbSession:
    connection: object
    engine: str

    def execute(self, query: str, params: tuple | list | None = None):
        if self.engine == "postgres":
            return self.connection.execute(self._q(query), self._p(params))
        if params is None:
            return self.connection.execute(query)
        return self.connection.execute(query, params)

    def executemany(self, query: str, seq_of_params):
        if self.engine == "postgres":
            return self.connection.executemany(self._q(query), seq_of_params)
        return self.connection.executemany(query, seq_of_params)

    def executescript(self, script: str):
        if self.engine == "postgres":
            statements = [s.strip() for s in script.split(";") if s.strip()]
            for statement in statements:
                self.connection.execute(statement)
            return None
        return self.connection.executescript(script)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _q(query: str) -> str:
        # Keep app queries unchanged in this migration phase (? -> %s).
        return query.replace("?", "%s")

    @staticmethod
    def _p(params: tuple | list | None):
        if params is None:
            return ()
        return tuple(params)


@contextmanager
def connect() -> Iterator[DbSession]:
    url = database_url()
    if is_postgres(url):
        if psycopg is None:
            raise RuntimeError("Falta dependencia psycopg para usar PostgreSQL.")
        connection = psycopg.connect(url, row_factory=dict_row)
        session = DbSession(connection=connection, engine="postgres")
    else:
        DATA_DIR.mkdir(exist_ok=True)
        path = sqlite_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        session = DbSession(connection=connection, engine="sqlite")
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return {key: row[key] for key in row.keys()}


def init_db() -> None:
    with connect() as db:
        id_type = "INTEGER PRIMARY KEY AUTOINCREMENT" if db.engine == "sqlite" else "BIGSERIAL PRIMARY KEY"
        fk_type = "INTEGER" if db.engine == "sqlite" else "BIGINT"
        blob_type = "BLOB" if db.engine == "sqlite" else "BYTEA"
        text_timestamp = "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP" if db.engine == "sqlite" else "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP"
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
        ensure_column(db, "operations", "contest_season_id", "INTEGER")
        ensure_column(db, "users", "starting_balance", "REAL NOT NULL DEFAULT 1000")
        ensure_column(db, "users", "cash_balance", "REAL NOT NULL DEFAULT 1000")
        ensure_column(db, "users", "avatar_path", "TEXT")
        ensure_column(db, "users", "avatar_mime_type", "TEXT")
        ensure_column(db, "users", "avatar_data", blob_type)
        ensure_column(db, "users", "avatar_updated_at", "TEXT")
        ensure_column(db, "recommendations", "analysis_json", "TEXT")
        ensure_column(db, "recommendations", "time_horizon", "TEXT NOT NULL DEFAULT 'intraday_short'")
        db.execute("UPDATE users SET starting_balance = 1000 WHERE starting_balance IS NULL")
        db.execute("UPDATE users SET cash_balance = 1000 WHERE cash_balance IS NULL")
        db.execute("UPDATE operations SET mode = 'training' WHERE mode IS NULL OR mode = ''")
        db.execute("UPDATE operations SET time_horizon = 'intraday_short' WHERE time_horizon IS NULL OR time_horizon = ''")
        db.execute("UPDATE recommendations SET time_horizon = 'intraday_short' WHERE time_horizon IS NULL OR time_horizon = ''")
        create_indexes(db)
        backfill_recommendation_links(db)


def ensure_column(db: DbSession, table: str, column: str, definition: str) -> None:
    if db.engine == "postgres":
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
        return
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
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
