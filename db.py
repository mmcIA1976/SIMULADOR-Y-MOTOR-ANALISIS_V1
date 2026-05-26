from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DEFAULT_DATABASE_URL = f"sqlite:///{DATA_DIR / 'trading_trainer.db'}"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def sqlite_path() -> Path:
    url = database_url()
    if not url.startswith("sqlite:///"):
        raise RuntimeError(
            "Solo SQLite esta implementado en desarrollo. DATABASE_URL queda preparado para PostgreSQL mas adelante."
        )
    return Path(url.replace("sqlite:///", "", 1))


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(exist_ok=True)
    path = sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def init_db() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                starting_balance REAL NOT NULL DEFAULT 1000,
                cash_balance REAL NOT NULL DEFAULT 1000,
                avatar_path TEXT,
                avatar_mime_type TEXT,
                avatar_data BLOB,
                avatar_updated_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('long', 'short')),
                entry REAL NOT NULL,
                margin REAL NOT NULL,
                leverage REAL NOT NULL,
                time_horizon TEXT NOT NULL DEFAULT 'intraday_short',
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING_ANALYSIS',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
                contest_season_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER,
                user_id INTEGER NOT NULL,
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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE SET NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS price_ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                source TEXT NOT NULL,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS contest_seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                starting_balance REAL NOT NULL DEFAULT 1000,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contest_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                starting_balance REAL NOT NULL DEFAULT 1000,
                cash_balance REAL NOT NULL DEFAULT 1000,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(season_id, user_id),
                FOREIGN KEY(season_id) REFERENCES contest_seasons(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS wallet_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                mode TEXT NOT NULL,
                event_type TEXT NOT NULL,
                amount REAL NOT NULL,
                balance_after REAL,
                operation_id INTEGER,
                contest_season_id INTEGER,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
        ensure_column(db, "users", "avatar_data", "BLOB")
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


def ensure_column(db: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_indexes(db: sqlite3.Connection) -> None:
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


def backfill_recommendation_links(db: sqlite3.Connection) -> None:
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
