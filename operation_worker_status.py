from __future__ import annotations

from datetime import datetime, timezone


WORKER_NAME = "operation_worker"
WORKER_LIFECYCLE_STATES = ("starting", "running", "degraded", "stopped")


def ensure_worker_status_table(db) -> None:
    """Create the constant-size worker status store used by web and worker."""
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS operation_worker_state (
            worker_name TEXT PRIMARY KEY,
            lifecycle_status TEXT NOT NULL
                CHECK(lifecycle_status IN ('starting', 'running', 'degraded', 'stopped')),
            app_version TEXT NOT NULL,
            engine_version TEXT NOT NULL,
            dry_run BOOLEAN NOT NULL DEFAULT TRUE,
            persist_exit_window BOOLEAN NOT NULL DEFAULT FALSE,
            poll_seconds DOUBLE PRECISION NOT NULL,
            reconcile_seconds DOUBLE PRECISION NOT NULL,
            heartbeat_seconds DOUBLE PRECISION NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            last_heartbeat_at TIMESTAMPTZ NOT NULL,
            last_cycle_at TIMESTAMPTZ,
            last_success_at TIMESTAMPTZ,
            last_reconcile_at TIMESTAMPTZ,
            cycle_count BIGINT NOT NULL DEFAULT 0,
            active_symbols INTEGER NOT NULL DEFAULT 0,
            market_symbols INTEGER NOT NULL DEFAULT 0,
            last_cycle_activated INTEGER NOT NULL DEFAULT 0,
            last_cycle_closed INTEGER NOT NULL DEFAULT 0,
            last_cycle_finalized INTEGER NOT NULL DEFAULT 0,
            last_cycle_failures INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.executescript(
        """
        ALTER TABLE operation_worker_state ENABLE ROW LEVEL SECURITY;
        REVOKE ALL PRIVILEGES ON TABLE operation_worker_state FROM anon, authenticated;
        GRANT ALL PRIVILEGES ON TABLE operation_worker_state TO postgres, service_role;
        """
    )


def upsert_worker_status(
    db,
    *,
    lifecycle_status: str,
    app_version: str,
    engine_version: str,
    dry_run: bool,
    persist_exit_window: bool,
    poll_seconds: float,
    reconcile_seconds: float,
    heartbeat_seconds: float,
    started_at: str,
    heartbeat_at: str,
    result: dict | None = None,
    last_error: str | None = None,
    worker_name: str = WORKER_NAME,
) -> None:
    if lifecycle_status not in WORKER_LIFECYCLE_STATES:
        raise ValueError(f"Estado de worker no valido: {lifecycle_status}")
    result = result or {}
    failures = int(result.get("failures") or 0)
    last_cycle_at = heartbeat_at if result else None
    last_success_at = heartbeat_at if result and failures == 0 else None
    last_reconcile_at = heartbeat_at if result.get("reconciled") else None
    db.execute(
        """
        INSERT INTO operation_worker_state (
            worker_name, lifecycle_status, app_version, engine_version,
            dry_run, persist_exit_window, poll_seconds, reconcile_seconds,
            heartbeat_seconds, started_at, last_heartbeat_at, last_cycle_at,
            last_success_at, last_reconcile_at, cycle_count, active_symbols,
            market_symbols, last_cycle_activated, last_cycle_closed,
            last_cycle_finalized, last_cycle_failures, last_error, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (worker_name) DO UPDATE SET
            lifecycle_status = excluded.lifecycle_status,
            app_version = excluded.app_version,
            engine_version = excluded.engine_version,
            dry_run = excluded.dry_run,
            persist_exit_window = excluded.persist_exit_window,
            poll_seconds = excluded.poll_seconds,
            reconcile_seconds = excluded.reconcile_seconds,
            heartbeat_seconds = excluded.heartbeat_seconds,
            started_at = excluded.started_at,
            last_heartbeat_at = excluded.last_heartbeat_at,
            last_cycle_at = COALESCE(excluded.last_cycle_at, operation_worker_state.last_cycle_at),
            last_success_at = COALESCE(excluded.last_success_at, operation_worker_state.last_success_at),
            last_reconcile_at = COALESCE(
                excluded.last_reconcile_at,
                operation_worker_state.last_reconcile_at
            ),
            cycle_count = excluded.cycle_count,
            active_symbols = excluded.active_symbols,
            market_symbols = excluded.market_symbols,
            last_cycle_activated = excluded.last_cycle_activated,
            last_cycle_closed = excluded.last_cycle_closed,
            last_cycle_finalized = excluded.last_cycle_finalized,
            last_cycle_failures = excluded.last_cycle_failures,
            last_error = excluded.last_error,
            updated_at = excluded.updated_at
        RETURNING worker_name
        """,
        (
            worker_name,
            lifecycle_status,
            app_version,
            engine_version,
            bool(dry_run),
            bool(persist_exit_window),
            float(poll_seconds),
            float(reconcile_seconds),
            float(heartbeat_seconds),
            started_at,
            heartbeat_at,
            last_cycle_at,
            last_success_at,
            last_reconcile_at,
            int(result.get("cycle") or 0),
            int(result.get("active_symbols") or 0),
            int(result.get("market_symbols") or 0),
            int(result.get("activated") or 0),
            int(result.get("closed") or 0),
            int(result.get("finalized_observations") or 0),
            failures,
            str(last_error)[:1000] if last_error else None,
            heartbeat_at,
        ),
    )


def get_worker_status_row(db, worker_name: str = WORKER_NAME) -> dict | None:
    row = db.execute(
        "SELECT * FROM operation_worker_state WHERE worker_name = ?",
        (worker_name,),
    ).fetchone()
    if row is None:
        return None
    return row if isinstance(row, dict) else dict(row)


def _as_utc_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def summarize_worker_status(row: dict | None, now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if row is None:
        return {
            "worker_name": WORKER_NAME,
            "signal_state": "not_started",
            "healthy": False,
            "fresh": False,
            "dry_run": None,
            "last_heartbeat_at": None,
            "heartbeat_age_seconds": None,
            "stale_after_seconds": 180,
            "storage_strategy": "single_row_upsert",
        }

    heartbeat_at = _as_utc_datetime(row.get("last_heartbeat_at"))
    heartbeat_seconds = max(float(row.get("heartbeat_seconds") or 60), 15.0)
    stale_after_seconds = max(int(heartbeat_seconds * 3), 60)
    heartbeat_age_seconds = None
    if heartbeat_at is not None:
        heartbeat_age_seconds = max(0, int((now - heartbeat_at).total_seconds()))

    lifecycle_status = str(row.get("lifecycle_status") or "degraded")
    fresh = heartbeat_age_seconds is not None and heartbeat_age_seconds <= stale_after_seconds
    failures = int(row.get("last_cycle_failures") or 0)
    if lifecycle_status == "stopped":
        signal_state = "stopped"
    elif not fresh:
        signal_state = "stale"
    elif lifecycle_status == "degraded" or failures:
        signal_state = "degraded"
    elif lifecycle_status == "starting":
        signal_state = "starting"
    elif bool(row.get("dry_run")):
        signal_state = "dry_run"
    else:
        signal_state = "running"

    return {
        **row,
        "started_at": _as_utc_datetime(row.get("started_at")).isoformat()
        if row.get("started_at")
        else None,
        "last_heartbeat_at": heartbeat_at.isoformat() if heartbeat_at else None,
        "last_cycle_at": _as_utc_datetime(row.get("last_cycle_at")).isoformat()
        if row.get("last_cycle_at")
        else None,
        "last_success_at": _as_utc_datetime(row.get("last_success_at")).isoformat()
        if row.get("last_success_at")
        else None,
        "last_reconcile_at": _as_utc_datetime(row.get("last_reconcile_at")).isoformat()
        if row.get("last_reconcile_at")
        else None,
        "updated_at": _as_utc_datetime(row.get("updated_at")).isoformat()
        if row.get("updated_at")
        else None,
        "signal_state": signal_state,
        "healthy": fresh and lifecycle_status == "running" and failures == 0,
        "fresh": fresh,
        "heartbeat_age_seconds": heartbeat_age_seconds,
        "stale_after_seconds": stale_after_seconds,
        "storage_strategy": "single_row_upsert",
    }


def add_transition_coverage(status: dict, web_refresh_enabled: bool) -> dict:
    worker_ready = bool(status.get("healthy")) and not bool(status.get("dry_run"))
    if web_refresh_enabled and worker_ready:
        transition_owner = "dual"
        transition_coverage = "warning"
    elif web_refresh_enabled:
        transition_owner = "web"
        transition_coverage = "covered"
    elif worker_ready:
        transition_owner = "worker"
        transition_coverage = "covered"
    else:
        transition_owner = "none"
        transition_coverage = "unprotected"
    return {
        **status,
        "web_operation_refresh_enabled": bool(web_refresh_enabled),
        "worker_ready_for_transitions": worker_ready,
        "transition_owner": transition_owner,
        "transition_coverage": transition_coverage,
    }
