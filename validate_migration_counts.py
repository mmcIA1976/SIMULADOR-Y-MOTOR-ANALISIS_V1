from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

import psycopg


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SQLITE_PATH = APP_DIR / "data" / "trading_trainer.db"
TABLES = [
    "users",
    "contest_seasons",
    "operations",
    "recommendations",
    "price_ticks",
    "contest_entries",
    "wallet_events",
]


def sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
    return int(row["c"])


def pg_count(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return int(cur.fetchone()[0])


def compare_counts(sqlite_path: Path, postgres_url: str) -> int:
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = psycopg.connect(postgres_url)
    try:
        mismatches = 0
        print("Tabla | SQLite | PostgreSQL")
        print("--- | ---:| ---:")
        for table in TABLES:
            src = sqlite_count(sqlite_conn, table)
            dst = pg_count(pg_conn, table)
            print(f"{table} | {src} | {dst}")
            if src != dst:
                mismatches += 1
        if mismatches == 0:
            print("[OK] Conteos consistentes")
        else:
            print(f"[WARN] {mismatches} tablas con diferencias")
        return mismatches
    finally:
        sqlite_conn.close()
        pg_conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida conteos SQLite vs PostgreSQL.")
    parser.add_argument("--sqlite-path", default=str(DEFAULT_SQLITE_PATH))
    parser.add_argument("--postgres-url", default=os.environ.get("DATABASE_URL", ""))
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sqlite_path = Path(args.sqlite_path)
    postgres_url = args.postgres_url.strip()
    if not sqlite_path.exists():
        raise SystemExit(f"No existe SQLite: {sqlite_path}")
    if not postgres_url:
        raise SystemExit("Falta --postgres-url o DATABASE_URL")
    raise SystemExit(compare_counts(sqlite_path, postgres_url))
