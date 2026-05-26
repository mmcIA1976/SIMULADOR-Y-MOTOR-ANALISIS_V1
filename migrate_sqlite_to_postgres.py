from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

import psycopg


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = APP_DIR / "data" / "trading_trainer.db"


TABLES_IN_ORDER = [
    "users",
    "contest_seasons",
    "operations",
    "recommendations",
    "price_ticks",
    "contest_entries",
    "wallet_events",
]


def sqlite_connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def pg_connect(url: str):
    return psycopg.connect(url)


def clear_target_tables(pg_conn) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE TABLE
                wallet_events,
                contest_entries,
                price_ticks,
                recommendations,
                operations,
                contest_seasons,
                users
            RESTART IDENTITY CASCADE
            """
        )


def fetch_rows(sqlite_conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return sqlite_conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()


def insert_rows(pg_conn, table: str, rows: list[sqlite3.Row]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    cols_sql = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})"
    values = [tuple(row[col] for col in columns) for row in rows]
    with pg_conn.cursor() as cur:
        cur.executemany(sql, values)
        if "id" in columns:
            cur.execute(
                f"""
                SELECT setval(
                    pg_get_serial_sequence(%s, 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1),
                    (SELECT COUNT(*) > 0 FROM {table})
                )
                """,
                (table,),
            )


def migrate(sqlite_path: Path, postgres_url: str) -> None:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"No existe SQLite en: {sqlite_path}")

    with sqlite_connect(sqlite_path) as sqlite_conn, pg_connect(postgres_url) as pg_conn:
        pg_conn.autocommit = False
        try:
            clear_target_tables(pg_conn)
            for table in TABLES_IN_ORDER:
                rows = fetch_rows(sqlite_conn, table)
                insert_rows(pg_conn, table, rows)
                print(f"[OK] {table}: {len(rows)} filas")
            pg_conn.commit()
            print("[OK] Migracion completada")
        except Exception:
            pg_conn.rollback()
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migra datos de SQLite a PostgreSQL.")
    parser.add_argument(
        "--sqlite-path",
        default=str(DEFAULT_SQLITE_PATH),
        help="Ruta al archivo SQLite origen.",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.environ.get("SUPABASE_DATABASE_URL", "") or os.environ.get("DATABASE_URL", ""),
        help="URL PostgreSQL/Supabase destino (postgresql://...).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    postgres_url = args.postgres_url.strip()
    if not postgres_url:
        raise SystemExit("Falta --postgres-url o DATABASE_URL")
    migrate(sqlite_path, postgres_url)
