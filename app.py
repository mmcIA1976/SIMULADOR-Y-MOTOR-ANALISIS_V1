from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import market_data
import data_engine
from analysis_engine import ENGINE_VERSION, TradeProposal, analyze_trade, build_explained_metrics
from analysis_engine import time_horizon_profile
from db import close_pool, connect, init_db, row_to_dict
from security import create_token, hash_password, read_token, verify_password


APP_DIR = Path(__file__).resolve().parent
AVATAR_DIR = APP_DIR / "data" / "avatars"
SESSION_COOKIE = "trading_trainer_session"
MAX_AVATAR_BYTES = 1_000_000
ONE_MINUTE_MS = 60_000
MAX_EXIT_KLINE_PAGES = 60
MAX_EXIT_TRADE_PAGES = 8
EXIT_WINDOW_BEFORE_MINUTES = 90
EXIT_WINDOW_AFTER_MINUTES = 30
AVATAR_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
VALID_OPERATION_MODES = {"training", "contest"}
VALID_TIME_HORIZONS = {"intraday_short", "intraday_wide", "short_swing"}
TRAINING_RECHARGE_AMOUNT = 1000.0

app = FastAPI(title="Trading Trainer", version="0.1.0")


class AuthPayload(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=6, max_length=120)


class AvatarPayload(BaseModel):
    filename: str = Field(min_length=1, max_length=160)
    mime_type: str = Field(min_length=5, max_length=40)
    data_base64: str = Field(min_length=1)


class TradePayload(BaseModel):
    symbol: str = Field(min_length=5, max_length=20)
    side: str
    time_horizon: str = Field(min_length=1, max_length=30)
    entry_type: str = Field(default="market", max_length=20)
    trigger_condition: str | None = Field(default=None, max_length=20)
    entry: float = Field(gt=0)
    margin: float = Field(gt=0)
    leverage: float = Field(gt=0, le=10)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)


class CreateOperationPayload(TradePayload):
    recommendation_id: int | None = None
    mode: str = Field(default="training", max_length=20)


class CloseOperationPayload(BaseModel):
    close_price: float = Field(gt=0)
    close_reason: str = Field(default="manual", min_length=2, max_length=40)
    post_emotion: str | None = Field(default=None, max_length=40)
    plan_followed: str | None = Field(default=None, max_length=40)
    closing_note: str | None = Field(default=None, max_length=500)


def validate_trade_plan(side: str, entry: float, stop_loss: float, take_profit: float) -> None:
    if side == "long":
        if stop_loss >= entry:
            raise HTTPException(status_code=400, detail="En una operacion long, el Stop Loss debe estar por debajo de la entrada")
        if take_profit <= entry:
            raise HTTPException(status_code=400, detail="En una operacion long, el Take Profit debe estar por encima de la entrada")
    elif side == "short":
        if stop_loss <= entry:
            raise HTTPException(status_code=400, detail="En una operacion short, el Stop Loss debe estar por encima de la entrada")
        if take_profit >= entry:
            raise HTTPException(status_code=400, detail="En una operacion short, el Take Profit debe estar por debajo de la entrada")
    else:
        raise HTTPException(status_code=400, detail="Direccion no valida")


def validate_entry_order(entry_type: str, trigger_condition: str | None) -> None:
    if entry_type not in {"market", "pending"}:
        raise HTTPException(status_code=400, detail="Tipo de entrada no valido")
    if entry_type == "pending" and trigger_condition not in {"price_lte", "price_gte"}:
        raise HTTPException(status_code=400, detail="Condicion de activacion no valida")


def entry_order_type(side: str, trigger_condition: str | None) -> str | None:
    if trigger_condition is None:
        return None
    if side == "long":
        return "limit_pullback" if trigger_condition == "price_lte" else "stop_breakout"
    return "limit_pullback" if trigger_condition == "price_gte" else "stop_breakdown"


def close_enough(left: float | int | None, right: float | int | None, tolerance: float = 0.01) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def validate_recommendation_matches_operation(
    recommendation: dict,
    payload: CreateOperationPayload,
    entry_type: str,
    trigger_condition: str | None,
) -> None:
    if recommendation.get("symbol") != payload.symbol.upper():
        raise HTTPException(status_code=400, detail="El analisis previo no corresponde al simbolo de la operacion")
    if recommendation.get("side") != payload.side.lower():
        raise HTTPException(status_code=400, detail="El analisis previo no corresponde a la direccion de la operacion")
    if recommendation.get("time_horizon") != payload.time_horizon:
        raise HTTPException(status_code=400, detail="El analisis previo no corresponde al marco temporal de la operacion")

    analysis_payload = parse_exit_evidence(recommendation.get("analysis_json"))
    entry_context = analysis_payload.get("entry_order_context") or analysis_payload.get("snapshot", {}).get("entry_order_context") or {}
    analyzed_entry_type = entry_context.get("entry_type") or "market"
    if analyzed_entry_type != entry_type:
        raise HTTPException(status_code=400, detail="El analisis previo no corresponde al tipo de entrada de la operacion")
    if entry_type != "pending":
        return
    if entry_context.get("trigger_condition") != trigger_condition:
        raise HTTPException(status_code=400, detail="El analisis previo no corresponde a la condicion de activacion")
    expected_order_type = entry_order_type(payload.side.lower(), trigger_condition)
    if entry_context.get("entry_order_type") != expected_order_type:
        raise HTTPException(status_code=400, detail="El analisis previo no corresponde al tipo de orden pendiente")
    if not close_enough(entry_context.get("requested_entry"), payload.entry):
        raise HTTPException(status_code=400, detail="El analisis previo no corresponde al precio de activacion")


def current_user(session_token: str | None) -> dict:
    if not session_token:
        raise HTTPException(status_code=401, detail="No autenticado")
    user_id = read_token(session_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Sesion no valida")
    with connect() as db:
        user = row_to_dict(db.execute("SELECT id, username, starting_balance, cash_balance, avatar_path, avatar_mime_type, avatar_updated_at, created_at FROM users WHERE id = ?", (user_id,)).fetchone())
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return public_user(user)


def avatar_url(user: dict) -> str | None:
    if not user.get("avatar_mime_type"):
        return None
    version = user.get("avatar_updated_at") or ""
    return f"/avatars/user_{user['id']}?v={version}"


def public_user(user: dict) -> dict:
    return {
        **user,
        "avatar_data": None,
        "avatar_url": avatar_url(user),
    }


def is_valid_image_bytes(content: bytes, mime_type: str) -> bool:
    if mime_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if mime_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


def migrate_file_avatars_to_database() -> None:
    if not AVATAR_DIR.exists():
        return
    extension_to_mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
    with connect() as db:
        rows = db.execute(
            """
            SELECT id, avatar_path
            FROM users
            WHERE avatar_path IS NOT NULL
              AND avatar_data IS NULL
            """
        ).fetchall()
        for row in rows:
            avatar_path = str(row["avatar_path"])
            file_path = AVATAR_DIR / Path(avatar_path).name
            extension = file_path.suffix.lower().lstrip(".")
            mime_type = extension_to_mime.get(extension)
            if not mime_type or not file_path.exists():
                continue
            content = file_path.read_bytes()
            if len(content) > MAX_AVATAR_BYTES or not is_valid_image_bytes(content, mime_type):
                continue
            db.execute(
                """
                UPDATE users
                SET avatar_mime_type = ?, avatar_data = ?, avatar_updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (mime_type, content, row["id"]),
            )


def set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        create_token(user_id),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )


@app.on_event("startup")
def startup() -> None:
    init_db()
    ensure_pending_entry_columns()
    migrate_file_avatars_to_database()
    finalize_due_observations()
    refresh_learning_conclusions()
    refresh_learning_evaluations()
    reconcile_all_user_cash_balances()


@app.on_event("shutdown")
def shutdown() -> None:
    close_pool()


def ensure_pending_entry_columns() -> None:
    columns = {
        "entry_type": "TEXT NOT NULL DEFAULT 'market'",
        "requested_entry": "REAL",
        "trigger_condition": "TEXT",
        "entry_order_type": "TEXT",
        "triggered_at": "TEXT",
        "trigger_price": "REAL",
        "activation_evidence_json": "TEXT",
    }
    with connect() as db:
        for column, definition in columns.items():
            exists = db.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = ? AND column_name = ?
                LIMIT 1
                """,
                ("operations", column),
            ).fetchone()
            if not exists:
                db.execute(f"ALTER TABLE operations ADD COLUMN {column} {definition}")
        db.execute("UPDATE operations SET entry_type = 'market' WHERE entry_type IS NULL OR entry_type = ''")
        db.execute("UPDATE operations SET requested_entry = entry WHERE requested_entry IS NULL")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")


@app.get("/static/{asset_name}")
def static_asset(asset_name: str) -> FileResponse:
    allowed_assets = {"app.js", "styles.css"}
    if asset_name not in allowed_assets:
        raise HTTPException(status_code=404, detail="Asset no encontrado")
    return FileResponse(APP_DIR / asset_name, headers={"Cache-Control": "no-store"})


@app.get("/avatars/{file_name}")
def avatar_asset(file_name: str) -> FileResponse:
    safe_name = Path(file_name).name
    if safe_name != file_name or not safe_name.startswith("user_"):
        raise HTTPException(status_code=404, detail="Avatar no encontrado")
    try:
        user_id = int(safe_name.replace("user_", "", 1).split(".", 1)[0])
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Avatar no encontrado") from exc
    with connect() as db:
        row = db.execute("SELECT avatar_mime_type, avatar_data FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or row["avatar_data"] is None or row["avatar_mime_type"] is None:
        raise HTTPException(status_code=404, detail="Avatar no encontrado")
    return Response(content=row["avatar_data"], media_type=row["avatar_mime_type"])


@app.post("/api/auth/register")
def register(payload: AuthPayload, response: Response) -> dict:
    username = payload.username.strip().lower()
    if not username:
        raise HTTPException(status_code=400, detail="Nombre de usuario requerido")
    try:
        with connect() as db:
            cursor = db.execute(
                "INSERT INTO users (username, password_hash, starting_balance, cash_balance) VALUES (?, ?, 1000, 1000)",
                (username, hash_password(payload.password)),
            )
            user_id = int(cursor.lastrowid)
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(status_code=409, detail="El usuario ya existe") from exc
        raise
    set_session_cookie(response, user_id)
    return {"id": user_id, "username": username, "avatar_url": None}


@app.post("/api/auth/login")
def login(payload: AuthPayload, response: Response) -> dict:
    username = payload.username.strip().lower()
    with connect() as db:
        row = db.execute("SELECT id, username, password_hash, avatar_path, avatar_mime_type, avatar_updated_at FROM users WHERE username = ?", (username,)).fetchone()
    user = row_to_dict(row)
    if user is None or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Usuario o contrasena incorrectos")
    set_session_cookie(response, int(user["id"]))
    return public_user({
        "id": user["id"],
        "username": user["username"],
        "avatar_path": user.get("avatar_path"),
        "avatar_mime_type": user.get("avatar_mime_type"),
        "avatar_updated_at": user.get("avatar_updated_at"),
    })


@app.post("/api/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    return {**user, "portfolio": get_portfolio(user["id"])}


@app.post("/api/me/avatar")
def update_avatar(payload: AvatarPayload, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    mime_type = payload.mime_type.lower()
    extension = AVATAR_MIME_TO_EXT.get(mime_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="Formato no permitido. Usa JPG, PNG o WEBP.")
    try:
        content = base64.b64decode(payload.data_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Imagen no valida.") from exc
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=400, detail="La imagen supera el maximo de 1 MB.")
    if not is_valid_image_bytes(content, mime_type):
        raise HTTPException(status_code=400, detail="El archivo no coincide con el formato declarado.")

    avatar_name = f"user_{user['id']}.{extension}"
    with connect() as db:
        db.execute(
            """
            UPDATE users
            SET avatar_path = ?, avatar_mime_type = ?, avatar_data = ?, avatar_updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (avatar_name, mime_type, content, user["id"]),
        )
        updated = row_to_dict(
            db.execute(
                "SELECT id, username, avatar_path, avatar_mime_type, avatar_updated_at FROM users WHERE id = ?",
                (user["id"],),
            ).fetchone()
        )
    return public_user(updated or {**user, "avatar_path": avatar_name, "avatar_mime_type": mime_type})


@app.get("/api/portfolio")
def portfolio(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    return get_portfolio(user["id"])


@app.get("/api/contest/current")
def contest_current(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    with connect() as db:
        season = ensure_current_contest_season(db)
        active_refresh = refresh_contest_active_operations(db, int(season["id"]))
        entry = get_contest_entry(db, int(user["id"]), int(season["id"]))
        portfolio = calculate_portfolio_from_db(db, int(user["id"]))
        leaderboard = contest_leaderboard(db, int(season["id"]))
        history = contest_history(db)
        if entry:
            apply_contest_unrealized_to_portfolio(db, portfolio["contest"], int(user["id"]), int(season["id"]))
    return {
        "season": season,
        "entry": entry,
        "participating": entry is not None,
        "portfolio": portfolio["contest"],
        "leaderboard": leaderboard,
        "history": history,
        "active_refresh": active_refresh,
    }


@app.post("/api/contest/join")
def contest_join(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    with connect() as db:
        season = ensure_current_contest_season(db)
        entry = ensure_contest_entry(db, int(user["id"]), int(season["id"]))
        active_refresh = refresh_contest_active_operations(db, int(season["id"]))
        portfolio = sync_user_cash_balance(db, int(user["id"]))
        leaderboard = contest_leaderboard(db, int(season["id"]))
        history = contest_history(db)
        apply_contest_unrealized_to_portfolio(db, portfolio["contest"], int(user["id"]), int(season["id"]))
    return {
        "season": season,
        "entry": entry,
        "participating": True,
        "portfolio": portfolio["contest"],
        "leaderboard": leaderboard,
        "history": history,
        "active_refresh": active_refresh,
    }


def latest_recorded_symbol_price(db, symbol: str) -> dict | None:
    row = db.execute(
        """
        SELECT price, source, captured_at
        FROM price_ticks
        WHERE symbol = ?
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        (symbol.upper(),),
    ).fetchone()
    return row_to_dict(row)


def stale_price_fallback(symbol: str, error: Exception) -> dict | None:
    cached = market_data.get_cached_price(symbol, None)
    if cached:
        return {
            "symbol": symbol.upper(),
            "price": float(cached["price"]),
            "source": cached.get("source") or "binance_usdm_futures_memory_cache",
            "captured_at": cached.get("captured_at"),
            "stale": True,
            "price_error": str(error),
            "binance_backoff_until_ms": market_data.futures_backoff_until_ms(),
        }
    with connect() as db:
        recorded = latest_recorded_symbol_price(db, symbol)
    if not recorded:
        return None
    return {
        "symbol": symbol.upper(),
        "price": float(recorded["price"]),
        "source": f"stored_price_tick:{recorded.get('source') or 'unknown'}",
        "captured_at": recorded.get("captured_at"),
        "stale": True,
        "price_error": str(error),
        "binance_backoff_until_ms": market_data.futures_backoff_until_ms(),
    }


@app.get("/api/price")
def price(
    symbol: str = "BTCUSDT",
    record: bool = True,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    symbol = symbol.upper()
    stale_response: dict | None = None
    try:
        value = market_data.get_price(symbol)
    except Exception as exc:
        stale_response = stale_price_fallback(symbol, exc)
        if stale_response is None:
            raise HTTPException(
                status_code=502,
                detail=f"No se pudo consultar precio Binance Futures para {symbol}: {exc}",
            ) from exc
        value = float(stale_response["price"])
    if not record:
        return {
            "symbol": symbol,
            "price": value,
            "operation_ids": [],
            "activated_operations": [],
            "closed_operations": [],
            "source": stale_response["source"] if stale_response else "binance_usdm_futures_ticker",
            "stale": bool(stale_response),
            "captured_at": stale_response.get("captured_at") if stale_response else None,
            "price_error": stale_response.get("price_error") if stale_response else None,
            "binance_backoff_until_ms": stale_response.get("binance_backoff_until_ms") if stale_response else 0,
        }
    if stale_response:
        return {
            "symbol": symbol,
            "price": value,
            "operation_ids": [],
            "activated_operations": [],
            "closed_operations": [],
            "source": stale_response["source"],
            "stale": True,
            "captured_at": stale_response.get("captured_at"),
            "price_error": stale_response.get("price_error"),
            "binance_backoff_until_ms": stale_response.get("binance_backoff_until_ms"),
        }
    operation_ids: list[int] = []
    activated_operations: list[dict] = []
    closed_operations: list[dict] = []
    user = None
    if session_token:
        try:
            user = current_user(session_token)
        except HTTPException:
            user = None
    with connect() as db:
        finalize_due_observations(db)
        activated_by_trigger, closed_by_trigger = refresh_symbol_active_operations(db, symbol, value)
        if closed_by_trigger:
            refresh_learning_conclusions(db)
            refresh_learning_evaluations(db)
        if user:
            activated_operations.extend(
                operation for operation in activated_by_trigger.values() if operation.get("user_id") == user["id"]
            )
            closed_operations.extend(
                operation for operation in closed_by_trigger.values() if operation.get("user_id") == user["id"]
            )
            rows = db.execute(
                """
                SELECT * FROM operations
                WHERE user_id = ?
                  AND symbol = ?
                  AND (status IN ('OPEN', 'PENDING_ENTRY') OR observation_status = 'OBSERVING')
                """,
                (user["id"], symbol),
            ).fetchall()
            for row in rows:
                operation = row_to_dict(row)
                operation_id = int(operation["id"])
                if record:
                    operation_ids.append(operation_id)
                    db.execute(
                        "INSERT INTO price_ticks (operation_id, symbol, price, source) VALUES (?, ?, ?, ?)",
                        (operation_id, symbol, value, "binance_usdm_futures"),
                    )
    return {
        "symbol": symbol,
        "price": value,
        "operation_ids": operation_ids,
        "activated_operations": activated_operations,
        "closed_operations": closed_operations,
        "source": "binance_usdm_futures_ticker",
        "stale": False,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "price_error": None,
        "binance_backoff_until_ms": market_data.futures_backoff_until_ms(),
    }


@app.get("/api/market-history")
def market_history(symbol: str = "BTCUSDT", minutes: int = 60) -> dict:
    symbol = symbol.upper()
    limit = min(max(minutes, 10), 240)
    try:
        klines = market_data.get_klines(symbol, "1m", limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"No se pudo cargar el historial de Binance: {exc}") from exc
    points = []
    for kline in klines:
        points.append(
            {
                "price": float(kline[4]),
                "time": iso_from_ms(int(kline[6])),
            }
        )
    return {
        "symbol": symbol,
        "interval": "1m",
        "minutes": limit,
        "source": "binance_usdm_futures_klines_1m",
        "points": points,
    }


@app.get("/api/diagnostics/binance-futures")
def binance_futures_diagnostics(symbol: str = "ETHUSDT") -> dict:
    symbol = symbol.upper()
    return {
        "symbol": symbol,
        "provider": "binance_usdm_futures",
        "results": market_data.diagnose_futures_hosts(symbol),
    }


@app.post("/api/operations/check-exits")
def check_operation_exits(
    symbol: str = "BTCUSDT",
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    user = current_user(session_token)
    symbol = symbol.upper()
    try:
        current_price = market_data.get_price(symbol)
    except Exception as exc:
        stale_response = stale_price_fallback(symbol, exc)
        if stale_response is None:
            raise HTTPException(
                status_code=502,
                detail=f"No se pudo consultar precio Binance Futures para {symbol}: {exc}",
            ) from exc
        return {
            "symbol": symbol,
            "price": float(stale_response["price"]),
            "activated_operations": [],
            "closed_operations": [],
            "source": stale_response["source"],
            "stale": True,
            "captured_at": stale_response.get("captured_at"),
            "price_error": stale_response.get("price_error"),
            "binance_backoff_until_ms": stale_response.get("binance_backoff_until_ms"),
        }
    with connect() as db:
        activated_by_trigger, closed_by_trigger = refresh_symbol_active_operations(db, symbol, current_price)
        if closed_by_trigger:
            refresh_learning_conclusions(db)
            refresh_learning_evaluations(db)
    return {
        "symbol": symbol,
        "price": current_price,
        "activated_operations": [
            operation for operation in activated_by_trigger.values() if operation.get("user_id") == user["id"]
        ],
        "closed_operations": [
            operation for operation in closed_by_trigger.values() if operation.get("user_id") == user["id"]
        ],
        "source": "binance_usdm_futures_ticker",
        "stale": False,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "price_error": None,
        "binance_backoff_until_ms": market_data.futures_backoff_until_ms(),
    }


def refresh_symbol_active_operations(
    db,
    symbol: str,
    current_price: float,
    user_id: int | None = None,
) -> tuple[dict[int, dict], dict[int, dict]]:
    activated = activate_triggered_pending_operations(db, symbol, current_price, user_id)
    closed = close_triggered_open_operations(db, symbol, current_price, user_id)
    return activated, closed


def refresh_contest_active_operations(db, season_id: int) -> dict[str, list[dict]]:
    rows = db.execute(
        """
        SELECT DISTINCT symbol
        FROM operations
        WHERE mode = 'contest'
          AND contest_season_id = ?
          AND status IN ('OPEN', 'PENDING_ENTRY')
        """,
        (season_id,),
    ).fetchall()
    activated: dict[int, dict] = {}
    closed: dict[int, dict] = {}
    for row in rows:
        symbol = str(row["symbol"]).upper()
        try:
            current_price = market_data.get_price(symbol)
        except Exception:
            continue
        activated_for_symbol, closed_for_symbol = refresh_symbol_active_operations(db, symbol, current_price)
        activated.update(activated_for_symbol)
        closed.update(closed_for_symbol)
    if closed:
        refresh_learning_conclusions(db)
        refresh_learning_evaluations(db)
    return {
        "activated_operations": list(activated.values()),
        "closed_operations": list(closed.values()),
    }


def activate_triggered_pending_operations(
    db,
    symbol: str,
    current_price: float,
    user_id: int | None = None,
) -> dict[int, dict]:
    if user_id is None:
        rows = db.execute(
            "SELECT * FROM operations WHERE symbol = ? AND status = 'PENDING_ENTRY'",
            (symbol,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM operations WHERE symbol = ? AND status = 'PENDING_ENTRY' AND user_id = ?",
            (symbol, user_id),
        ).fetchall()
    activated: dict[int, dict] = {}
    for row in rows:
        operation = row_to_dict(row)
        trigger = triggered_entry_from_market_path(operation, current_price)
        if not trigger:
            continue
        entry_price, trigger_time, activation_evidence = trigger
        update_cursor = db.execute(
            """
            UPDATE operations
            SET status = 'OPEN',
                started_at = ?,
                triggered_at = ?,
                trigger_price = ?,
                entry = ?,
                activation_evidence_json = ?
            WHERE id = ? AND status = 'PENDING_ENTRY'
            """,
            (
                trigger_time,
                trigger_time,
                entry_price,
                entry_price,
                json.dumps(activation_evidence, ensure_ascii=True),
                operation["id"],
            ),
        )
        if update_cursor.rowcount == 0:
            continue
        db.execute(
            "INSERT INTO price_ticks (operation_id, symbol, price, source, captured_at) VALUES (?, ?, ?, ?, ?)",
            (operation["id"], operation["symbol"], entry_price, "auto_entry", trigger_time),
        )
        mode = operation.get("mode") or "training"
        portfolio = sync_user_cash_balance(db, int(operation["user_id"]))
        record_wallet_event(
            db,
            user_id=int(operation["user_id"]),
            mode=mode,
            event_type="pending_entry_activated",
            amount=0,
            balance_after=float(portfolio[mode]["cash_balance"]),
            operation_id=int(operation["id"]),
            contest_season_id=operation.get("contest_season_id"),
            note=f"Orden pendiente activada en {entry_price}.",
        )
        activated[int(operation["id"])] = {
            "id": int(operation["id"]),
            "user_id": int(operation["user_id"]),
            "entry_price": entry_price,
            "trigger_time": trigger_time,
            "activation_evidence": activation_evidence,
        }
    return activated


def close_triggered_open_operations(
    db,
    symbol: str,
    current_price: float,
    user_id: int | None = None,
) -> dict[int, dict]:
    if user_id is None:
        rows = db.execute(
            "SELECT * FROM operations WHERE symbol = ? AND status = 'OPEN'",
            (symbol,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM operations WHERE symbol = ? AND status = 'OPEN' AND user_id = ?",
            (symbol, user_id),
        ).fetchall()
    closed: dict[int, dict] = {}
    for row in rows:
        operation = row_to_dict(row)
        trigger = triggered_exit_from_market_path(operation, current_price)
        if not trigger:
            continue
        reason, close_price, trigger_time, exit_evidence = trigger
        pnl = approximate_pnl(operation, close_price)
        closed_at = trigger_time if trigger_time != "precio_actual" else datetime.now(timezone.utc).isoformat()
        update_cursor = db.execute(
            """
            UPDATE operations
            SET status = 'CLOSED', closed_at = ?, close_price = ?,
                close_reason = ?, final_pnl = ?, observation_status = 'PLAN_EXECUTED',
                observation_until = NULL, closing_note = ?, learning_outcome = NULL,
                learning_summary = NULL, exit_evidence_json = ?
            WHERE id = ? AND status = 'OPEN'
            """,
            (
                closed_at,
                close_price,
                reason,
                pnl,
                f"Cierre automatico por cruce detectado en vela {trigger_time}.",
                json.dumps(exit_evidence, ensure_ascii=True),
                operation["id"],
            ),
        )
        if update_cursor.rowcount == 0:
            continue
        record_exit_window_ticks(db, operation, close_price, trigger_time)
        portfolio = sync_user_cash_balance(db, int(operation["user_id"]))
        mode = operation.get("mode") or "training"
        record_wallet_event(
            db,
            user_id=int(operation["user_id"]),
            mode=mode,
            event_type="operation_closed",
            amount=float(pnl),
            balance_after=float(portfolio[mode]["cash_balance"]),
            operation_id=int(operation["id"]),
            contest_season_id=operation.get("contest_season_id"),
            note=f"Cierre automatico por {reason}.",
        )
        closed[int(operation["id"])] = {
            "id": int(operation["id"]),
            "user_id": int(operation["user_id"]),
            "reason": reason,
            "close_price": close_price,
            "final_pnl": pnl,
            "trigger_time": trigger_time,
            "exit_evidence": exit_evidence,
        }
    return closed


def record_exit_window_ticks(db, operation: dict, close_price: float, trigger_time: str) -> None:
    trigger_ms = timestamp_ms_from_trigger_time(trigger_time)
    if trigger_ms is None:
        db.execute(
            """
            INSERT INTO price_ticks (operation_id, symbol, price, source)
            VALUES (?, ?, ?, ?)
            """,
            (operation["id"], operation["symbol"], close_price, "auto_exit"),
        )
        return

    start_ms = max(operation_start_time_ms(operation), trigger_ms - EXIT_WINDOW_BEFORE_MINUTES * ONE_MINUTE_MS)
    end_ms = min(
        int(datetime.now(timezone.utc).timestamp() * 1000),
        trigger_ms + EXIT_WINDOW_AFTER_MINUTES * ONE_MINUTE_MS,
    )
    try:
        klines = market_data.get_klines(operation["symbol"], "1m", 200, start_time_ms=start_ms, end_time_ms=end_ms)
    except Exception:
        klines = []

    for kline in klines:
        db.execute(
            """
            INSERT INTO price_ticks (operation_id, symbol, price, source, captured_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                operation["id"],
                operation["symbol"],
                float(kline[4]),
                "binance_usdm_futures_1m_exit_window",
                iso_from_ms(int(kline[6])),
            ),
        )

    db.execute(
        """
        INSERT INTO price_ticks (operation_id, symbol, price, source, captured_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (operation["id"], operation["symbol"], close_price, "auto_exit", iso_from_ms(trigger_ms)),
    )


def timestamp_ms_from_trigger_time(trigger_time: str) -> int | None:
    if trigger_time == "precio_actual":
        return None
    try:
        parsed = datetime.fromisoformat(str(trigger_time).replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def trigger_time_from_closing_note(operation: dict) -> str | None:
    note = str(operation.get("closing_note") or "")
    match = re.search(r"vela\s+([0-9T:\-+.Z]+)", note)
    if match:
        return match.group(1).rstrip(".")
    return None


def finalize_due_observations(existing_db=None) -> list[dict]:
    if existing_db is not None:
        return finalize_due_observations_with_db(existing_db)
    with connect() as db:
        return finalize_due_observations_with_db(db)


def finalize_due_observations_with_db(db) -> list[dict]:
    rows = db.execute(
        """
        SELECT * FROM operations
        WHERE status = 'CLOSED'
          AND observation_status = 'OBSERVING'
          AND observation_until IS NOT NULL
          AND observation_until::timestamptz <= CURRENT_TIMESTAMP
        ORDER BY closed_at ASC
        """
    ).fetchall()
    finalized: list[dict] = []
    for row in rows:
        operation = row_to_dict(row)
        result = build_observation_result(db, operation)
        db.execute(
            """
            UPDATE operations
            SET observation_status = 'OBSERVATION_CLOSED',
                observation_result = ?,
                observation_result_at = CURRENT_TIMESTAMP,
                observation_summary = ?,
                learning_outcome = NULL,
                learning_summary = NULL
            WHERE id = ?
            """,
            (result["result"], result["summary"], operation["id"]),
        )
        finalized.append({"id": int(operation["id"]), **result})
    return finalized


def refresh_learning_conclusions(existing_db=None) -> list[dict]:
    if existing_db is not None:
        return refresh_learning_conclusions_with_db(existing_db)
    with connect() as db:
        return refresh_learning_conclusions_with_db(db)


def refresh_learning_conclusions_with_db(db) -> list[dict]:
    rows = db.execute(
        """
        SELECT
            o.*,
            r.snapshot_json AS recommendation_snapshot_json,
            r.engine_version AS recommendation_engine_version,
            r.setup_grade AS recommendation_setup_grade,
            r.risk_level AS recommendation_risk_level,
            r.confidence AS recommendation_confidence,
            r.training_decision AS recommendation_training_decision,
            r.tp_probability AS recommendation_tp_probability,
            r.sl_probability AS recommendation_sl_probability,
            r.range_probability AS recommendation_range_probability
        FROM operations o
        LEFT JOIN recommendations r ON r.id = (
            SELECT r2.id
            FROM recommendations r2
            WHERE r2.operation_id = o.id
            ORDER BY r2.created_at DESC, r2.id DESC
            LIMIT 1
        )
        WHERE o.status = 'CLOSED'
          AND (o.learning_summary IS NULL OR o.learning_summary = '')
        ORDER BY o.closed_at ASC, o.id ASC
        """
    ).fetchall()
    conclusions: list[dict] = []
    for row in rows:
        operation = row_to_dict(row)
        conclusion = build_learning_conclusion(operation)
        db.execute(
            """
            UPDATE operations
            SET learning_outcome = ?, learning_summary = ?
            WHERE id = ?
            """,
            (conclusion["outcome"], conclusion["summary"], operation["id"]),
        )
        conclusions.append({"id": int(operation["id"]), **conclusion})
    return conclusions


def refresh_learning_evaluations(existing_db=None) -> list[dict]:
    if existing_db is not None:
        return refresh_learning_evaluations_with_db(existing_db)
    with connect() as db:
        return refresh_learning_evaluations_with_db(db)


def refresh_learning_evaluations_with_db(db) -> list[dict]:
    rows = db.execute(
        """
        SELECT
            o.*,
            r.id AS recommendation_id,
            r.setup_grade AS recommendation_setup_grade,
            r.risk_level AS recommendation_risk_level,
            r.confidence AS recommendation_confidence,
            r.training_decision AS recommendation_training_decision,
            r.tp_probability AS recommendation_tp_probability,
            r.sl_probability AS recommendation_sl_probability,
            r.range_probability AS recommendation_range_probability,
            r.snapshot_json AS recommendation_snapshot_json
        FROM operations o
        LEFT JOIN recommendations r ON r.id = (
            SELECT r2.id
            FROM recommendations r2
            WHERE r2.operation_id = o.id
            ORDER BY r2.created_at DESC, r2.id DESC
            LIMIT 1
        )
        WHERE o.status = 'CLOSED'
          AND COALESCE(o.observation_status, '') != 'OBSERVING'
          AND NOT EXISTS (
              SELECT 1
              FROM learning_evaluations le
              WHERE le.operation_id = o.id
          )
        ORDER BY o.closed_at ASC, o.id ASC
        """
    ).fetchall()
    evaluations = []
    for row in rows:
        operation = row_to_dict(row)
        ticks = [
            row_to_dict(tick)
            for tick in db.execute(
                """
                SELECT price, captured_at
                FROM price_ticks
                WHERE operation_id = ?
                ORDER BY captured_at ASC
                """,
                (operation["id"],),
            ).fetchall()
        ]
        evaluation = build_structured_learning_evaluation(operation, ticks)
        save_learning_evaluation(db, evaluation)
        evaluations.append(evaluation)
    return evaluations


@app.get("/api/learning/fibonacci-audit")
def fibonacci_audit(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    with connect() as db:
        return build_fibonacci_audit_report(db, int(user["id"]))


@app.get("/api/learning/pending-zone-audit")
def pending_zone_audit(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    with connect() as db:
        return build_pending_zone_audit_report(db, int(user["id"]))


def build_fibonacci_audit_report(db, user_id: int) -> dict:
    recommendation_stats = row_to_dict(db.execute(
        """
        SELECT
            COUNT(*) AS total_v07,
            COUNT(CASE WHEN operation_id IS NULL THEN 1 END) AS pending_operations,
            COUNT(CASE WHEN operation_id IS NOT NULL THEN 1 END) AS linked_operations
        FROM recommendations
        WHERE user_id = ?
          AND engine_version = 'rules-v0.7-fibonacci-confluence'
        """,
        (user_id,),
    ).fetchone()) or {}
    rows = db.execute(
        """
        SELECT
            le.operation_id,
            le.symbol,
            le.side,
            le.time_horizon,
            le.final_pnl,
            le.plan_result,
            le.analysis_verdict,
            le.structured_json,
            r.engine_version
        FROM learning_evaluations le
        LEFT JOIN recommendations r ON r.id = le.recommendation_id
        WHERE le.user_id = ?
          AND r.engine_version = 'rules-v0.7-fibonacci-confluence'
        ORDER BY le.updated_at DESC, le.operation_id DESC
        """,
        (user_id,),
    ).fetchall()
    cases = [fibonacci_case_from_evaluation(row_to_dict(row)) for row in rows]
    cases = [case for case in cases if case is not None]
    resolved_cases = [case for case in cases if case["plan_result"] in {"plan_success", "plan_failure", "plan_would_succeed", "plan_would_fail"}]
    return {
        "engine_version": "rules-v0.7-fibonacci-confluence",
        "user_id": user_id,
        "recommendations": {
            "total_v07": int(recommendation_stats.get("total_v07") or 0),
            "pending_operations": int(recommendation_stats.get("pending_operations") or 0),
            "linked_operations": int(recommendation_stats.get("linked_operations") or 0),
        },
        "sample": {
            "evaluated_cases": len(cases),
            "resolved_cases": len(resolved_cases),
            "minimum_for_review": 30,
            "ready_for_weight_review": len(resolved_cases) >= 30,
        },
        "summary": summarize_fibonacci_cases(resolved_cases),
        "by_bias": group_fibonacci_cases(resolved_cases, "bias"),
        "by_entry_zone": group_fibonacci_cases(resolved_cases, "entry_zone"),
        "by_time_horizon": group_fibonacci_cases(resolved_cases, "time_horizon"),
        "by_side": group_fibonacci_cases(resolved_cases, "side"),
        "recent_cases": cases[:12],
    }


def fibonacci_case_from_evaluation(row: dict) -> dict | None:
    try:
        structured = json.loads(row.get("structured_json") or "{}")
    except json.JSONDecodeError:
        structured = {}
    context = structured.get("analysis_context") if isinstance(structured.get("analysis_context"), dict) else {}
    fibonacci = context.get("fibonacci") if isinstance(context.get("fibonacci"), dict) else {}
    if not fibonacci or fibonacci.get("bias") is None:
        return None
    plan_result = row.get("plan_result")
    success = plan_result in {"plan_success", "plan_would_succeed"}
    failure = plan_result in {"plan_failure", "plan_would_fail"}
    return {
        "operation_id": int(row["operation_id"]),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "time_horizon": row.get("time_horizon"),
        "final_pnl": round(float(row.get("final_pnl") or 0), 4),
        "plan_result": plan_result,
        "analysis_verdict": row.get("analysis_verdict"),
        "resolved": success or failure,
        "success": success,
        "failure": failure,
        "bias": fibonacci.get("bias") or "sin_bias",
        "score": safe_float(fibonacci.get("score")),
        "entry_zone": fibonacci.get("entry_zone") or "sin_zona",
        "target_zone": fibonacci.get("target_zone") or "sin_zona",
        "stop_zone": fibonacci.get("stop_zone") or "sin_zona",
        "probability_adjustment": safe_float(fibonacci.get("probability_adjustment")),
    }


def summarize_fibonacci_cases(cases: list[dict]) -> dict:
    if not cases:
        return {
            "available": False,
            "message": "Aun no hay operaciones cerradas evaluables con Fibonacci v0.7.",
        }
    successes = sum(1 for case in cases if case["success"])
    failures = sum(1 for case in cases if case["failure"])
    total_pnl = sum(float(case["final_pnl"]) for case in cases)
    return {
        "available": True,
        "cases": len(cases),
        "successes": successes,
        "failures": failures,
        "success_rate": round(successes / len(cases), 4),
        "total_pnl": round(total_pnl, 4),
        "avg_pnl": round(total_pnl / len(cases), 4),
    }


def group_fibonacci_cases(cases: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for case in cases:
        groups.setdefault(str(case.get(key) or "sin_dato"), []).append(case)
    result = []
    for name, items in groups.items():
        successes = sum(1 for item in items if item["success"])
        total_pnl = sum(float(item["final_pnl"]) for item in items)
        scores = [float(item["score"]) for item in items if item.get("score") is not None]
        result.append({
            "name": name,
            "cases": len(items),
            "successes": successes,
            "failures": sum(1 for item in items if item["failure"]),
            "success_rate": round(successes / len(items), 4) if items else 0,
            "total_pnl": round(total_pnl, 4),
            "avg_pnl": round(total_pnl / len(items), 4) if items else 0,
            "avg_fibonacci_score": round(sum(scores) / len(scores), 4) if scores else None,
        })
    return sorted(result, key=lambda item: (-item["cases"], item["name"]))


def build_pending_zone_audit_report(db, user_id: int) -> dict:
    recommendation_stats = row_to_dict(db.execute(
        """
        SELECT
            COUNT(*) AS total_v09,
            COUNT(CASE WHEN operation_id IS NULL THEN 1 END) AS pending_operations,
            COUNT(CASE WHEN operation_id IS NOT NULL THEN 1 END) AS linked_operations
        FROM recommendations
        WHERE user_id = ?
          AND engine_version = 'rules-v0.9-pending-zone-adjusted'
        """,
        (user_id,),
    ).fetchone()) or {}
    rows = db.execute(
        """
        SELECT
            le.operation_id,
            le.symbol,
            le.side,
            le.time_horizon,
            le.final_pnl,
            le.plan_result,
            le.analysis_verdict,
            le.structured_json,
            r.engine_version
        FROM learning_evaluations le
        LEFT JOIN recommendations r ON r.id = le.recommendation_id
        WHERE le.user_id = ?
          AND r.engine_version = 'rules-v0.9-pending-zone-adjusted'
        ORDER BY le.updated_at DESC, le.operation_id DESC
        """,
        (user_id,),
    ).fetchall()
    cases = [pending_zone_case_from_evaluation(row_to_dict(row)) for row in rows]
    cases = [case for case in cases if case is not None]
    resolved_cases = [
        case for case in cases
        if case["plan_result"] in {"plan_success", "plan_failure", "plan_would_succeed", "plan_would_fail"}
    ]
    return {
        "engine_version": "rules-v0.9-pending-zone-adjusted",
        "user_id": user_id,
        "recommendations": {
            "total_v09": int(recommendation_stats.get("total_v09") or 0),
            "pending_operations": int(recommendation_stats.get("pending_operations") or 0),
            "linked_operations": int(recommendation_stats.get("linked_operations") or 0),
        },
        "sample": {
            "evaluated_cases": len(cases),
            "resolved_cases": len(resolved_cases),
            "minimum_for_review": 30,
            "ready_for_weight_review": len(resolved_cases) >= 30,
        },
        "summary": summarize_pending_zone_cases(resolved_cases),
        "by_entry_order_type": group_pending_zone_cases(resolved_cases, "entry_order_type"),
        "by_entry_zone_type": group_pending_zone_cases(resolved_cases, "entry_zone_type"),
        "by_reaction_bias": group_pending_zone_cases(resolved_cases, "reaction_bias"),
        "by_sweep_risk": group_pending_zone_cases(resolved_cases, "liquidity_sweep_risk"),
        "by_probability_adjustment": group_pending_zone_cases(resolved_cases, "probability_adjustment_bucket"),
        "by_zone_learning_category": group_pending_zone_cases(resolved_cases, "zone_learning_category"),
        "by_time_horizon": group_pending_zone_cases(resolved_cases, "time_horizon"),
        "by_side": group_pending_zone_cases(resolved_cases, "side"),
        "recent_cases": cases[:12],
    }


def pending_zone_case_from_evaluation(row: dict) -> dict | None:
    try:
        structured = json.loads(row.get("structured_json") or "{}")
    except json.JSONDecodeError:
        structured = {}
    analysis_context = structured.get("analysis_context") if isinstance(structured.get("analysis_context"), dict) else {}
    pending_context = structured.get("pending_entry_context") if isinstance(structured.get("pending_entry_context"), dict) else {}
    zone = analysis_context.get("zone") if isinstance(analysis_context.get("zone"), dict) else {}
    zone_learning = analysis_context.get("zone_learning") if isinstance(analysis_context.get("zone_learning"), dict) else {}
    if not zone.get("available"):
        return None
    plan_result = row.get("plan_result")
    success = plan_result in {"plan_success", "plan_would_succeed"}
    failure = plan_result in {"plan_failure", "plan_would_fail"}
    probability_adjustment = safe_float(zone.get("probability_adjustment"))
    return {
        "operation_id": int(row["operation_id"]),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "time_horizon": row.get("time_horizon"),
        "final_pnl": round(float(row.get("final_pnl") or 0), 4),
        "plan_result": plan_result,
        "analysis_verdict": row.get("analysis_verdict"),
        "resolved": success or failure,
        "success": success,
        "failure": failure,
        "activated": bool(pending_context.get("activated")),
        "entry_order_type": zone.get("entry_order_type") or pending_context.get("entry_order_type") or "sin_tipo",
        "entry_zone_type": zone.get("entry_zone_type") or "sin_zona",
        "reaction_bias": zone.get("reaction_bias") or "sin_reaccion",
        "liquidity_sweep_risk": zone.get("liquidity_sweep_risk") or "sin_riesgo",
        "zone_learning_category": zone_learning.get("category") or "sin_categoria",
        "zone_confluence_score": safe_float(zone.get("zone_confluence_score")),
        "activation_probability": safe_float(zone.get("activation_probability")),
        "target_path_quality": safe_float(zone.get("target_path_quality")),
        "invalidation_quality": safe_float(zone.get("invalidation_quality")),
        "probability_adjustment": probability_adjustment,
        "probability_adjustment_bucket": signed_value_bucket(probability_adjustment),
        "risk_score_addition": safe_float(zone.get("risk_score_addition")),
        "range_probability_adjustment": safe_float(zone.get("range_probability_adjustment")),
    }


def summarize_pending_zone_cases(cases: list[dict]) -> dict:
    if not cases:
        return {
            "available": False,
            "message": "Aun no hay operaciones pendientes cerradas evaluables con motor v0.9.",
        }
    successes = sum(1 for case in cases if case["success"])
    failures = sum(1 for case in cases if case["failure"])
    activated = sum(1 for case in cases if case["activated"])
    total_pnl = sum(float(case["final_pnl"]) for case in cases)
    confluence_scores = [float(case["zone_confluence_score"]) for case in cases if case.get("zone_confluence_score") is not None]
    activation_probabilities = [float(case["activation_probability"]) for case in cases if case.get("activation_probability") is not None]
    return {
        "available": True,
        "cases": len(cases),
        "successes": successes,
        "failures": failures,
        "success_rate": round(successes / len(cases), 4),
        "activated_cases": activated,
        "activation_rate": round(activated / len(cases), 4),
        "total_pnl": round(total_pnl, 4),
        "avg_pnl": round(total_pnl / len(cases), 4),
        "avg_zone_confluence_score": round(sum(confluence_scores) / len(confluence_scores), 4) if confluence_scores else None,
        "avg_activation_probability": round(sum(activation_probabilities) / len(activation_probabilities), 4) if activation_probabilities else None,
    }


def group_pending_zone_cases(cases: list[dict], key: str) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for case in cases:
        groups.setdefault(str(case.get(key) or "sin_dato"), []).append(case)
    result = []
    for name, items in groups.items():
        successes = sum(1 for item in items if item["success"])
        activated = sum(1 for item in items if item["activated"])
        total_pnl = sum(float(item["final_pnl"]) for item in items)
        confluence_scores = [float(item["zone_confluence_score"]) for item in items if item.get("zone_confluence_score") is not None]
        activation_probabilities = [float(item["activation_probability"]) for item in items if item.get("activation_probability") is not None]
        result.append({
            "name": name,
            "cases": len(items),
            "successes": successes,
            "failures": sum(1 for item in items if item["failure"]),
            "success_rate": round(successes / len(items), 4) if items else 0,
            "activated_cases": activated,
            "activation_rate": round(activated / len(items), 4) if items else 0,
            "total_pnl": round(total_pnl, 4),
            "avg_pnl": round(total_pnl / len(items), 4) if items else 0,
            "avg_zone_confluence_score": round(sum(confluence_scores) / len(confluence_scores), 4) if confluence_scores else None,
            "avg_activation_probability": round(sum(activation_probabilities) / len(activation_probabilities), 4) if activation_probabilities else None,
        })
    return sorted(result, key=lambda item: (-item["cases"], item["name"]))


def build_structured_learning_evaluation(operation: dict, ticks: list[dict]) -> dict:
    snapshot = parse_snapshot_json(operation.get("recommendation_snapshot_json"))
    technical = snapshot.get("technical_rating") if isinstance(snapshot.get("technical_rating"), dict) else {}
    regime = snapshot.get("market_regime") if isinstance(snapshot.get("market_regime"), dict) else {}
    scores = snapshot.get("layered_scores") if isinstance(snapshot.get("layered_scores"), dict) else {}
    fibonacci = snapshot.get("fibonacci_context") if isinstance(snapshot.get("fibonacci_context"), dict) else {}
    entry_context = snapshot.get("entry_order_context") if isinstance(snapshot.get("entry_order_context"), dict) else {}
    zone_analysis = snapshot.get("zone_analysis") if isinstance(snapshot.get("zone_analysis"), dict) else {}
    zone_probability = snapshot.get("zone_probability_context") if isinstance(snapshot.get("zone_probability_context"), dict) else {}
    rr_ratio = safe_float(snapshot.get("risk_reward_ratio"))
    risk_margin_pct = safe_float(snapshot.get("risk_margin_pct"))
    reward_margin_pct = safe_float(snapshot.get("reward_margin_pct"))
    close_reason = operation.get("close_reason")
    plan_result = plan_result_from_operation(operation)
    manual_trigger = first_plan_trigger_after_close(operation, ticks_after_close(operation, ticks))
    would_hit_sl_after_manual = bool(manual_trigger and manual_trigger[0] == "stop_loss")
    would_hit_tp_after_manual = bool(manual_trigger and manual_trigger[0] == "take_profit")
    mfe_mae = excursion_metrics(operation, ticks)
    time_to_close = minutes_between(operation.get("started_at"), operation.get("closed_at"))
    tp_probability = safe_float(operation.get("recommendation_tp_probability"))
    sl_probability = safe_float(operation.get("recommendation_sl_probability"))
    setup_grade = operation.get("recommendation_setup_grade")
    confidence = operation.get("recommendation_confidence")
    analysis_verdict = classify_analysis_verdict(
        plan_result=plan_result,
        tp_probability=tp_probability,
        sl_probability=sl_probability,
        setup_grade=setup_grade,
        confidence=confidence,
        training_decision=operation.get("recommendation_training_decision"),
        expected_value_usdt=expected_value_from_snapshot(snapshot),
        fibonacci_bias=fibonacci.get("bias"),
        zone_analysis=zone_analysis,
        zone_probability=zone_probability,
    )
    user_decision_quality = classify_user_decision_quality(operation, manual_trigger)
    failure_type = classify_failure_type(operation, snapshot, mfe_mae, plan_result)
    learning_signal = build_learning_signal(
        operation=operation,
        snapshot=snapshot,
        plan_result=plan_result,
        analysis_verdict=analysis_verdict,
        failure_type=failure_type,
    )
    primary_lesson = build_primary_lesson(
        operation=operation,
        plan_result=plan_result,
        analysis_verdict=analysis_verdict,
        failure_type=failure_type,
        user_decision_quality=user_decision_quality,
        technical_label=technical.get("label"),
        market_regime=regime.get("name"),
    )
    structured = {
        "operation_id": int(operation["id"]),
        "plan_result": plan_result,
        "analysis_verdict": analysis_verdict,
        "primary_lesson": primary_lesson,
        "failure_type": failure_type,
        "learning_signal": learning_signal,
        "user_decision_quality": user_decision_quality,
        "excursion": mfe_mae,
        "manual_counterfactual": {
            "would_hit_tp_after_manual": would_hit_tp_after_manual,
            "would_hit_sl_after_manual": would_hit_sl_after_manual,
            "first_plan_trigger_after_close": {
                "reason": manual_trigger[0],
                "price": manual_trigger[1],
                "captured_at": manual_trigger[2],
            } if manual_trigger else None,
        },
        "pending_entry_context": {
            "entry_type": entry_context.get("entry_type"),
            "trigger_condition": entry_context.get("trigger_condition"),
            "entry_order_type": entry_context.get("entry_order_type"),
            "requested_entry": safe_float(entry_context.get("requested_entry")),
            "activated": bool(operation.get("triggered_at") or operation.get("activation_evidence_json")),
            "triggered_at": operation.get("triggered_at"),
            "trigger_price": safe_float(operation.get("trigger_price")),
        },
        "analysis_context": {
            "setup_grade": setup_grade,
            "risk_level": operation.get("recommendation_risk_level"),
            "confidence": confidence,
            "training_decision": operation.get("recommendation_training_decision"),
            "tp_probability": tp_probability,
            "sl_probability": sl_probability,
            "range_probability": safe_float(operation.get("recommendation_range_probability")),
            "technical_label": technical.get("label"),
            "technical_score": safe_float(technical.get("score")),
            "market_regime": regime.get("name"),
            "direction_score": safe_float(scores.get("direction_score")),
            "confidence_score": safe_float(scores.get("confidence_score")),
            "risk_reward_ratio": rr_ratio,
            "risk_margin_pct": risk_margin_pct,
            "reward_margin_pct": reward_margin_pct,
            "fibonacci": {
                "bias": fibonacci.get("bias"),
                "score": safe_float(fibonacci.get("score")),
                "entry_zone": fibonacci.get("entry_zone"),
                "target_zone": fibonacci.get("target_zone"),
                "stop_zone": fibonacci.get("stop_zone"),
                "probability_adjustment": safe_float(fibonacci.get("probability_adjustment")),
            },
            "zone": {
                "available": bool(zone_analysis.get("available")),
                "entry_order_type": zone_analysis.get("entry_order_type") or entry_context.get("entry_order_type"),
                "entry_zone_type": zone_analysis.get("entry_zone_type"),
                "reaction_bias": zone_analysis.get("reaction_bias"),
                "liquidity_sweep_risk": zone_analysis.get("liquidity_sweep_risk"),
                "zone_confluence_score": safe_float(zone_analysis.get("zone_confluence_score")),
                "activation_probability": safe_float(zone_analysis.get("activation_probability")),
                "pullback_quality": safe_float(zone_analysis.get("pullback_quality")),
                "breakout_quality": safe_float(zone_analysis.get("breakout_quality")),
                "invalidation_quality": safe_float(zone_analysis.get("invalidation_quality")),
                "target_path_quality": safe_float(zone_analysis.get("target_path_quality")),
                "probability_adjustment": safe_float(zone_probability.get("probability_adjustment")),
                "range_probability_adjustment": safe_float(zone_probability.get("range_probability_adjustment")),
                "risk_score_addition": safe_float(zone_probability.get("risk_score_addition")),
                "zone_summary": zone_analysis.get("zone_summary"),
                "probability_summary": zone_probability.get("summary"),
            },
            "zone_learning": build_zone_learning_context(
                plan_result=plan_result,
                zone_analysis=zone_analysis,
                zone_probability=zone_probability,
                operation=operation,
            ),
        },
    }
    return {
        "operation_id": int(operation["id"]),
        "user_id": int(operation["user_id"]),
        "recommendation_id": operation.get("recommendation_id"),
        "symbol": operation["symbol"],
        "side": operation["side"],
        "time_horizon": operation.get("time_horizon") or "intraday_short",
        "mode": operation.get("mode") or "training",
        "close_reason": close_reason,
        "final_pnl": round(float(operation.get("final_pnl") or 0), 4),
        "plan_result": plan_result,
        "analysis_verdict": analysis_verdict,
        "primary_lesson": primary_lesson,
        "failure_type": failure_type,
        "user_decision_quality": user_decision_quality,
        "max_favorable_pct": mfe_mae["max_favorable_pct"],
        "max_adverse_pct": mfe_mae["max_adverse_pct"],
        "max_favorable_pnl": mfe_mae["max_favorable_pnl"],
        "max_adverse_pnl": mfe_mae["max_adverse_pnl"],
        "time_to_close_minutes": time_to_close,
        "would_hit_tp_after_manual": int(would_hit_tp_after_manual),
        "would_hit_sl_after_manual": int(would_hit_sl_after_manual),
        "setup_grade": setup_grade,
        "risk_level": operation.get("recommendation_risk_level"),
        "confidence": confidence,
        "training_decision": operation.get("recommendation_training_decision"),
        "tp_probability": tp_probability,
        "sl_probability": sl_probability,
        "range_probability": safe_float(operation.get("recommendation_range_probability")),
        "technical_label": technical.get("label"),
        "technical_score": safe_float(technical.get("score")),
        "market_regime": regime.get("name"),
        "direction_score": safe_float(scores.get("direction_score")),
        "confidence_score": safe_float(scores.get("confidence_score")),
        "risk_reward_ratio": rr_ratio,
        "risk_margin_pct": risk_margin_pct,
        "reward_margin_pct": reward_margin_pct,
        "leverage_bucket": leverage_bucket(float(operation.get("leverage") or 0)),
        "structured_json": json.dumps(structured, ensure_ascii=True),
    }


def save_learning_evaluation(db, evaluation: dict) -> None:
    db.execute(
        """
        INSERT INTO learning_evaluations (
            operation_id, user_id, recommendation_id, symbol, side, time_horizon, mode,
            close_reason, final_pnl, plan_result, analysis_verdict, primary_lesson,
            failure_type, user_decision_quality, max_favorable_pct, max_adverse_pct,
            max_favorable_pnl, max_adverse_pnl, time_to_close_minutes,
            would_hit_tp_after_manual, would_hit_sl_after_manual, setup_grade, risk_level,
            confidence, training_decision, tp_probability, sl_probability, range_probability,
            technical_label, technical_score, market_regime, direction_score, confidence_score,
            risk_reward_ratio, risk_margin_pct, reward_margin_pct, leverage_bucket, structured_json,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT (operation_id) DO UPDATE SET
            recommendation_id = EXCLUDED.recommendation_id,
            close_reason = EXCLUDED.close_reason,
            final_pnl = EXCLUDED.final_pnl,
            plan_result = EXCLUDED.plan_result,
            analysis_verdict = EXCLUDED.analysis_verdict,
            primary_lesson = EXCLUDED.primary_lesson,
            failure_type = EXCLUDED.failure_type,
            user_decision_quality = EXCLUDED.user_decision_quality,
            max_favorable_pct = EXCLUDED.max_favorable_pct,
            max_adverse_pct = EXCLUDED.max_adverse_pct,
            max_favorable_pnl = EXCLUDED.max_favorable_pnl,
            max_adverse_pnl = EXCLUDED.max_adverse_pnl,
            time_to_close_minutes = EXCLUDED.time_to_close_minutes,
            would_hit_tp_after_manual = EXCLUDED.would_hit_tp_after_manual,
            would_hit_sl_after_manual = EXCLUDED.would_hit_sl_after_manual,
            setup_grade = EXCLUDED.setup_grade,
            risk_level = EXCLUDED.risk_level,
            confidence = EXCLUDED.confidence,
            training_decision = EXCLUDED.training_decision,
            tp_probability = EXCLUDED.tp_probability,
            sl_probability = EXCLUDED.sl_probability,
            range_probability = EXCLUDED.range_probability,
            technical_label = EXCLUDED.technical_label,
            technical_score = EXCLUDED.technical_score,
            market_regime = EXCLUDED.market_regime,
            direction_score = EXCLUDED.direction_score,
            confidence_score = EXCLUDED.confidence_score,
            risk_reward_ratio = EXCLUDED.risk_reward_ratio,
            risk_margin_pct = EXCLUDED.risk_margin_pct,
            reward_margin_pct = EXCLUDED.reward_margin_pct,
            leverage_bucket = EXCLUDED.leverage_bucket,
            structured_json = EXCLUDED.structured_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            evaluation["operation_id"],
            evaluation["user_id"],
            evaluation["recommendation_id"],
            evaluation["symbol"],
            evaluation["side"],
            evaluation["time_horizon"],
            evaluation["mode"],
            evaluation["close_reason"],
            evaluation["final_pnl"],
            evaluation["plan_result"],
            evaluation["analysis_verdict"],
            evaluation["primary_lesson"],
            evaluation["failure_type"],
            evaluation["user_decision_quality"],
            evaluation["max_favorable_pct"],
            evaluation["max_adverse_pct"],
            evaluation["max_favorable_pnl"],
            evaluation["max_adverse_pnl"],
            evaluation["time_to_close_minutes"],
            evaluation["would_hit_tp_after_manual"],
            evaluation["would_hit_sl_after_manual"],
            evaluation["setup_grade"],
            evaluation["risk_level"],
            evaluation["confidence"],
            evaluation["training_decision"],
            evaluation["tp_probability"],
            evaluation["sl_probability"],
            evaluation["range_probability"],
            evaluation["technical_label"],
            evaluation["technical_score"],
            evaluation["market_regime"],
            evaluation["direction_score"],
            evaluation["confidence_score"],
            evaluation["risk_reward_ratio"],
            evaluation["risk_margin_pct"],
            evaluation["reward_margin_pct"],
            evaluation["leverage_bucket"],
            evaluation["structured_json"],
        ),
    )


def parse_snapshot_json(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def plan_result_from_operation(operation: dict) -> str:
    close_reason = operation.get("close_reason")
    if close_reason == "take_profit":
        return "plan_success"
    if close_reason == "stop_loss":
        return "plan_failure"
    if operation.get("observation_result") == "manual_protected":
        return "plan_would_fail"
    if operation.get("observation_result") in {"manual_left_profit", "manual_better_than_plan"}:
        return "plan_would_succeed"
    if operation.get("observation_result") == "plan_unresolved":
        return "plan_unresolved"
    if close_reason == "contest_expired":
        return "contest_expiry_mark_to_market"
    return "manual_pending_or_unclassified"


def ticks_after_close(operation: dict, ticks: list[dict]) -> list[dict]:
    closed_at = parse_timestamp(operation.get("closed_at"))
    if closed_at is None:
        return ticks
    result = []
    for tick in ticks:
        captured_at = parse_timestamp(str(tick.get("captured_at")) if tick.get("captured_at") is not None else None)
        if captured_at is None or captured_at >= closed_at:
            result.append(tick)
    return result


def excursion_metrics(operation: dict, ticks: list[dict]) -> dict:
    entry = float(operation["entry"])
    margin = float(operation["margin"])
    leverage = float(operation["leverage"])
    side_multiplier = -1 if operation["side"] == "short" else 1
    variations = []
    for tick in ticks:
        try:
            price = float(tick["price"])
        except (TypeError, ValueError):
            continue
        variations.append(((price - entry) / entry) * side_multiplier)
    if not variations and operation.get("close_price") is not None:
        variations.append(((float(operation["close_price"]) - entry) / entry) * side_multiplier)
    if not variations:
        return {
            "max_favorable_pct": None,
            "max_adverse_pct": None,
            "max_favorable_pnl": None,
            "max_adverse_pnl": None,
        }
    max_favorable = max(variations)
    max_adverse = min(variations)
    return {
        "max_favorable_pct": round(max_favorable * 100, 4),
        "max_adverse_pct": round(max_adverse * 100, 4),
        "max_favorable_pnl": round(margin * leverage * max_favorable, 4),
        "max_adverse_pnl": round(margin * leverage * max_adverse, 4),
    }


def minutes_between(start_value: str | None, end_value: str | None) -> float | None:
    start = parse_timestamp(start_value)
    end = parse_timestamp(end_value)
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() / 60, 2)


def classify_analysis_verdict(
    plan_result: str,
    tp_probability: float | None,
    sl_probability: float | None,
    setup_grade: str | None,
    confidence: str | None,
    training_decision: str | None = None,
    expected_value_usdt: float | None = None,
    fibonacci_bias: str | None = None,
    zone_analysis: dict | None = None,
    zone_probability: dict | None = None,
) -> str:
    tp = tp_probability if tp_probability is not None else 0
    sl = sl_probability if sl_probability is not None else 0
    decision = str(training_decision or "").lower()
    fib_bias = str(fibonacci_bias or "").lower()
    zone_analysis = zone_analysis or {}
    zone_probability = zone_probability or {}
    zone_delta = safe_float(zone_probability.get("probability_adjustment")) or 0
    zone_risk = safe_float(zone_probability.get("risk_score_addition")) or 0
    zone_sweep = str(zone_analysis.get("liquidity_sweep_risk") or "").lower()
    weak_setup = setup_grade in {"D", "E"} or confidence in {"baja", "media-baja"}
    analysis_warned = (
        weak_setup
        or decision == "observar"
        or tp < sl
        or (expected_value_usdt is not None and expected_value_usdt < 0)
        or fib_bias in {"alerta", "desfavorable"}
        or zone_delta < 0
        or zone_risk >= 0.02
        or zone_sweep == "alto"
    )
    if plan_result in {"plan_success", "plan_would_succeed"}:
        if not analysis_warned and (tp >= sl or setup_grade in {"A", "B", "C"}):
            return "analysis_supported_success"
        return "success_against_analysis"
    if plan_result in {"plan_failure", "plan_would_fail"}:
        if analysis_warned or sl >= tp:
            return "analysis_warned_risk"
        return "analysis_missed_risk"
    return "analysis_unresolved"


def expected_value_from_snapshot(snapshot: dict) -> float | None:
    expected_value = snapshot.get("expected_value")
    if isinstance(expected_value, dict):
        return safe_float(expected_value.get("expected_value_usdt"))
    return None


def analysis_warning_reasons(operation: dict) -> list[str]:
    snapshot = parse_snapshot_json(operation.get("recommendation_snapshot_json"))
    fibonacci = snapshot.get("fibonacci_context") if isinstance(snapshot.get("fibonacci_context"), dict) else {}
    zone_analysis = snapshot.get("zone_analysis") if isinstance(snapshot.get("zone_analysis"), dict) else {}
    zone_probability = snapshot.get("zone_probability_context") if isinstance(snapshot.get("zone_probability_context"), dict) else {}
    expected_value_usdt = expected_value_from_snapshot(snapshot)
    setup_grade = operation.get("recommendation_setup_grade")
    training_decision = str(operation.get("recommendation_training_decision") or "").lower()
    tp_probability = safe_float(operation.get("recommendation_tp_probability"))
    sl_probability = safe_float(operation.get("recommendation_sl_probability"))
    fibonacci_bias = str(fibonacci.get("bias") or "").lower()

    reasons = []
    if training_decision == "observar":
        reasons.append("decision previa observar")
    if setup_grade in {"D", "E"}:
        reasons.append(f"setup {setup_grade}")
    if tp_probability is not None and sl_probability is not None and tp_probability < sl_probability:
        reasons.append("probabilidad de TP inferior a SL")
    if expected_value_usdt is not None and expected_value_usdt < 0:
        reasons.append("EV negativa")
    if fibonacci_bias in {"alerta", "desfavorable"}:
        reasons.append(f"Fibonacci {fibonacci_bias}")
    zone_delta = safe_float(zone_probability.get("probability_adjustment"))
    zone_risk = safe_float(zone_probability.get("risk_score_addition"))
    if zone_delta is not None and zone_delta < 0:
        reasons.append(f"zona pendiente ajuste {zone_delta:+.3f}")
    if zone_risk is not None and zone_risk >= 0.02:
        reasons.append("zona pendiente con riesgo anadido")
    if str(zone_analysis.get("liquidity_sweep_risk") or "").lower() == "alto":
        reasons.append("riesgo alto de barrida en zona")
    return reasons


def analysis_support_reasons(operation: dict) -> list[str]:
    snapshot = parse_snapshot_json(operation.get("recommendation_snapshot_json"))
    fibonacci = snapshot.get("fibonacci_context") if isinstance(snapshot.get("fibonacci_context"), dict) else {}
    zone_analysis = snapshot.get("zone_analysis") if isinstance(snapshot.get("zone_analysis"), dict) else {}
    zone_probability = snapshot.get("zone_probability_context") if isinstance(snapshot.get("zone_probability_context"), dict) else {}
    expected_value_usdt = expected_value_from_snapshot(snapshot)
    setup_grade = operation.get("recommendation_setup_grade")
    training_decision = str(operation.get("recommendation_training_decision") or "").lower()
    tp_probability = safe_float(operation.get("recommendation_tp_probability"))
    sl_probability = safe_float(operation.get("recommendation_sl_probability"))
    fibonacci_bias = str(fibonacci.get("bias") or "").lower()

    reasons = []
    if training_decision in {"simular", "simular con ajustes"}:
        reasons.append(f"decision previa {training_decision}")
    if setup_grade in {"A", "B", "C"}:
        reasons.append(f"setup {setup_grade}")
    if tp_probability is not None and sl_probability is not None and tp_probability >= sl_probability:
        reasons.append("probabilidad de TP igual o superior a SL")
    if expected_value_usdt is not None and expected_value_usdt >= 0:
        reasons.append("EV no negativa")
    if fibonacci_bias in {"favorable", "neutral"}:
        reasons.append(f"Fibonacci {fibonacci_bias}")
    zone_delta = safe_float(zone_probability.get("probability_adjustment"))
    if zone_delta is not None and zone_delta > 0:
        reasons.append(f"zona pendiente favorable {zone_delta:+.3f}")
    if safe_float(zone_analysis.get("zone_confluence_score")) is not None and safe_float(zone_analysis.get("zone_confluence_score")) >= 65:
        reasons.append("confluencia de zona pendiente alta")
    return reasons


def build_learning_signal(
    operation: dict,
    snapshot: dict,
    plan_result: str,
    analysis_verdict: str,
    failure_type: str | None,
) -> dict:
    technical = snapshot.get("technical_rating") if isinstance(snapshot.get("technical_rating"), dict) else {}
    regime = snapshot.get("market_regime") if isinstance(snapshot.get("market_regime"), dict) else {}
    scores = snapshot.get("layered_scores") if isinstance(snapshot.get("layered_scores"), dict) else {}
    fibonacci = snapshot.get("fibonacci_context") if isinstance(snapshot.get("fibonacci_context"), dict) else {}
    entry_context = snapshot.get("entry_order_context") if isinstance(snapshot.get("entry_order_context"), dict) else {}
    zone_analysis = snapshot.get("zone_analysis") if isinstance(snapshot.get("zone_analysis"), dict) else {}
    zone_probability = snapshot.get("zone_probability_context") if isinstance(snapshot.get("zone_probability_context"), dict) else {}
    expected_value_usdt = expected_value_from_snapshot(snapshot)
    zone_learning = build_zone_learning_context(
        plan_result=plan_result,
        zone_analysis=zone_analysis,
        zone_probability=zone_probability,
        operation=operation,
    )
    category_by_verdict = {
        "analysis_supported_success": "reinforce_supported_success",
        "success_against_analysis": "investigate_underestimated_opportunity",
        "analysis_warned_risk": "reinforce_warned_risk",
        "analysis_missed_risk": "investigate_underestimated_risk",
    }
    interpretation_by_verdict = {
        "analysis_supported_success": "El resultado confirma una lectura favorable previa; util solo agregado con casos comparables.",
        "success_against_analysis": "El resultado fue positivo pese a advertencias; no refuerza automaticamente el analisis, senala posible oportunidad infravalorada.",
        "analysis_warned_risk": "El resultado negativo confirma advertencias previas; util para reforzar senales de riesgo si se repite.",
        "analysis_missed_risk": "El resultado negativo ocurrio pese a apoyo del analisis; senala riesgo subestimado.",
    }
    return {
        "category": category_by_verdict.get(analysis_verdict, "unresolved_context"),
        "analysis_verdict": analysis_verdict,
        "plan_result": plan_result,
        "failure_type": failure_type,
        "interpretation": interpretation_by_verdict.get(
            analysis_verdict,
            "Caso no concluyente; conservar como contexto sin ajustar pesos.",
        ),
        "actionability": "aggregate_only",
        "minimum_comparable_cases": 30,
        "comparable_case_key": {
            "symbol": operation.get("symbol"),
            "side": operation.get("side"),
            "time_horizon": operation.get("time_horizon") or "intraday_short",
            "setup_grade": operation.get("recommendation_setup_grade"),
            "training_decision": operation.get("recommendation_training_decision"),
            "risk_level": operation.get("recommendation_risk_level"),
            "technical_label": technical.get("label"),
            "market_regime": regime.get("name"),
            "direction_score_bucket": score_bucket(safe_float(scores.get("direction_score"))),
            "expected_value_bucket": value_bucket(expected_value_usdt),
            "fibonacci_bias": fibonacci.get("bias"),
            "fibonacci_entry_zone": fibonacci.get("entry_zone"),
            "entry_type": entry_context.get("entry_type"),
            "entry_order_type": zone_analysis.get("entry_order_type") or entry_context.get("entry_order_type"),
            "zone_reaction_bias": zone_analysis.get("reaction_bias"),
            "zone_sweep_risk": zone_analysis.get("liquidity_sweep_risk"),
            "zone_confluence_bucket": score_bucket(safe_float(zone_analysis.get("zone_confluence_score"))),
            "zone_probability_adjustment_bucket": signed_value_bucket(safe_float(zone_probability.get("probability_adjustment"))),
            "zone_learning_category": zone_learning.get("category"),
        },
    }


def build_zone_learning_context(plan_result: str, zone_analysis: dict, zone_probability: dict, operation: dict) -> dict:
    if not zone_analysis.get("available"):
        return {
            "available": False,
            "category": "not_pending_zone",
            "interpretation": "Operacion sin zona pendiente evaluable.",
        }
    zone_delta = safe_float(zone_probability.get("probability_adjustment")) or 0
    risk_addition = safe_float(zone_probability.get("risk_score_addition")) or 0
    activated = bool(operation.get("triggered_at") or operation.get("activation_evidence_json"))
    favorable_zone = zone_delta > 0 and str(zone_analysis.get("liquidity_sweep_risk") or "").lower() != "alto"
    warned_zone = zone_delta < 0 or risk_addition >= 0.02 or str(zone_analysis.get("liquidity_sweep_risk") or "").lower() == "alto"

    if not activated and plan_result in {"manual_pending_or_unclassified", "plan_unresolved"}:
        category = "pending_zone_not_activated"
        interpretation = "La orden pendiente no aporta lectura direccional suficiente; conservar para medir probabilidad de activacion."
    elif plan_result in {"plan_success", "plan_would_succeed"} and favorable_zone:
        category = "reinforce_favorable_pending_zone"
        interpretation = "Zona pendiente favorable respaldada por resultado positivo; usar solo con casos comparables."
    elif plan_result in {"plan_failure", "plan_would_fail"} and favorable_zone:
        category = "investigate_failed_favorable_pending_zone"
        interpretation = "Zona pendiente favorable fallo; revisar barrida, invalidacion, camino al TP o timing."
    elif plan_result in {"plan_failure", "plan_would_fail"} and warned_zone:
        category = "reinforce_warned_pending_zone_risk"
        interpretation = "El fallo confirma advertencias de zona pendiente; puede reforzar riesgo si se repite."
    elif plan_result in {"plan_success", "plan_would_succeed"} and warned_zone:
        category = "investigate_success_against_pending_zone_warning"
        interpretation = "El plan gano pese a advertencias de zona; no reforzar automaticamente, investigar infravaloracion."
    else:
        category = "pending_zone_context_only"
        interpretation = "Zona pendiente sin conclusion fuerte; conservar como contexto agregado."
    return {
        "available": True,
        "category": category,
        "interpretation": interpretation,
        "activated": activated,
        "entry_order_type": zone_analysis.get("entry_order_type"),
        "entry_zone_type": zone_analysis.get("entry_zone_type"),
        "reaction_bias": zone_analysis.get("reaction_bias"),
        "liquidity_sweep_risk": zone_analysis.get("liquidity_sweep_risk"),
        "zone_confluence_score": safe_float(zone_analysis.get("zone_confluence_score")),
        "activation_probability": safe_float(zone_analysis.get("activation_probability")),
        "probability_adjustment": zone_delta,
        "range_probability_adjustment": safe_float(zone_probability.get("range_probability_adjustment")),
        "risk_score_addition": risk_addition,
        "minimum_comparable_cases": 30,
    }


def signed_value_bucket(value: float | None) -> str:
    if value is None:
        return "sin_dato"
    if value > 0.003:
        return "positivo"
    if value < -0.003:
        return "negativo"
    return "neutral"


def score_bucket(value: float | None) -> str:
    if value is None:
        return "sin_dato"
    if value < 35:
        return "muy_bajo"
    if value < 45:
        return "bajo"
    if value < 55:
        return "neutral"
    if value < 65:
        return "favorable"
    return "fuerte"


def value_bucket(value: float | None) -> str:
    if value is None:
        return "sin_dato"
    if value < 0:
        return "negativa"
    if value == 0:
        return "neutral"
    return "positiva"


def classify_user_decision_quality(operation: dict, manual_trigger) -> str | None:
    close_reason = operation.get("close_reason")
    if close_reason not in {"manual", "cut_loss", "take_partial", "emotion", "invalidated"}:
        return None
    observation_result = operation.get("observation_result")
    if observation_result == "manual_protected":
        return "protected_capital"
    if observation_result in {"manual_left_profit", "manual_worse_than_plan"}:
        return "premature_or_worse_exit"
    if observation_result == "manual_better_than_plan":
        return "better_than_plan"
    if manual_trigger is None:
        return "inconclusive"
    return "pending_classification"


def classify_failure_type(operation: dict, snapshot: dict, mfe_mae: dict, plan_result: str) -> str | None:
    if plan_result not in {"plan_failure", "plan_would_fail"}:
        return None
    technical = snapshot.get("technical_rating") if isinstance(snapshot.get("technical_rating"), dict) else {}
    scores = snapshot.get("layered_scores") if isinstance(snapshot.get("layered_scores"), dict) else {}
    zone_analysis = snapshot.get("zone_analysis") if isinstance(snapshot.get("zone_analysis"), dict) else {}
    zone_probability = snapshot.get("zone_probability_context") if isinstance(snapshot.get("zone_probability_context"), dict) else {}
    rr = safe_float(snapshot.get("risk_reward_ratio"))
    direction_score = safe_float(scores.get("direction_score"))
    max_favorable_pct = mfe_mae.get("max_favorable_pct")
    if zone_analysis.get("available"):
        if str(zone_analysis.get("liquidity_sweep_risk") or "").lower() == "alto":
            return "pending_zone_liquidity_sweep"
        if (safe_float(zone_probability.get("risk_score_addition")) or 0) >= 0.02:
            return "pending_zone_risk_confirmed"
        if (safe_float(zone_analysis.get("target_path_quality")) or 100) <= 40:
            return "pending_zone_target_path_blocked"
    if technical.get("label") == "desfavorable" or (direction_score is not None and direction_score <= 40):
        return "direction_against_structure"
    if rr is not None and rr < 1.15:
        return "weak_reward_for_risk"
    if max_favorable_pct is not None and max_favorable_pct > 0.6:
        return "management_or_target_issue"
    return "unclassified_risk"


def leverage_bucket(leverage: float) -> str:
    if leverage >= 8:
        return "alto"
    if leverage >= 4:
        return "medio"
    return "bajo"


def build_primary_lesson(
    operation: dict,
    plan_result: str,
    analysis_verdict: str,
    failure_type: str | None,
    user_decision_quality: str | None,
    technical_label: str | None,
    market_regime: str | None,
) -> str:
    side = str(operation["side"]).upper()
    horizon = operation.get("time_horizon") or "sin temporalidad"
    if plan_result in {"plan_success", "plan_would_succeed"}:
        if analysis_verdict == "success_against_analysis":
            return (
                f"El plan {side} en {horizon} gano, pero contra advertencias del analisis previo. "
                f"No debe reforzar automaticamente la lectura inicial; revisar que senal infravaloro el movimiento real."
            )
        return (
            f"El plan {side} en {horizon} quedo respaldado por el resultado. "
            f"Contexto tecnico: {technical_label or 'n/d'}, regimen {market_regime or 'n/d'}."
        )
    if plan_result in {"plan_failure", "plan_would_fail"}:
        if analysis_verdict == "analysis_missed_risk":
            return (
                f"El plan {side} en {horizon} fallo pese a no estar advertido por el analisis previo. "
                f"No debe reforzar patrones favorables; revisar que riesgo fue subestimado."
            )
        return (
            f"El plan {side} en {horizon} fallo o habria fallado. "
            f"Lectura: {analysis_verdict}; causa candidata: {failure_type or 'sin clasificar'}."
        )
    if user_decision_quality:
        return f"La decision manual queda clasificada como {user_decision_quality}; requiere mas casos comparables."
    return "Resultado no concluyente para aprendizaje; conservar como caso de contexto."


def build_learning_conclusion(operation: dict) -> dict:
    pnl = float(operation["final_pnl"] or 0)
    side = str(operation["side"]).upper()
    symbol = str(operation["symbol"]).replace("USDT", "/USDT")
    close_reason = operation.get("close_reason")
    observation_status = operation.get("observation_status")
    observation_summary = operation.get("observation_summary")
    pattern_text = build_learning_pattern_text(operation)

    if close_reason == "take_profit":
        warnings = analysis_warning_reasons(operation)
        if warnings:
            warning_text = ", ".join(warnings)
            return {
                "outcome": "plan_success",
                "summary": (
                    f"Aprendizaje: el plan de {symbol} en {side} funciono y alcanzo TAKE PROFIT. "
                    f"Resultado: {pnl:.2f} USDT. Sin embargo, el analisis previo contenia advertencias "
                    f"({warning_text}); por tanto este caso debe guardarse como operacion ganadora contra advertencias, "
                    f"no como refuerzo automatico de todas las condiciones del analisis. {pattern_text}"
                ),
            }
        return {
            "outcome": "plan_success",
            "summary": (
                f"Aprendizaje: el plan de {symbol} en {side} funciono y alcanzo TAKE PROFIT. "
                f"Resultado: {pnl:.2f} USDT. Esta operacion refuerza las condiciones del analisis previo como caso ganador. "
                f"{pattern_text}"
            ),
        }
    if close_reason == "stop_loss":
        warnings = analysis_warning_reasons(operation)
        if warnings:
            warning_text = ", ".join(warnings)
            return {
                "outcome": "plan_failure",
                "summary": (
                    f"Aprendizaje: el plan de {symbol} en {side} fallo y alcanzo STOP LOSS. "
                    f"Resultado: {pnl:.2f} USDT. El analisis previo ya contenia advertencias "
                    f"({warning_text}); este caso debe reforzar esas senales de riesgo. {pattern_text}"
                ),
            }
        support = analysis_support_reasons(operation)
        support_text = f" El analisis previo lo apoyaba ({', '.join(support)})." if support else ""
        return {
            "outcome": "plan_failure",
            "summary": (
                f"Aprendizaje: el plan de {symbol} en {side} fallo y alcanzo STOP LOSS. "
                f"Resultado: {pnl:.2f} USDT.{support_text} "
                f"Este caso debe guardarse como fallo no anticipado o riesgo subestimado, "
                f"no como refuerzo de las condiciones favorables del analisis. "
                f"{pattern_text}"
            ),
        }
    if observation_status == "OBSERVATION_CLOSED" and observation_summary:
        if operation.get("observation_result") == "manual_protected":
            outcome = "manual_protected_capital"
            lesson = "El cierre manual protegió capital frente a mantener el plan."
        elif operation.get("observation_result") == "manual_left_profit":
            outcome = "manual_left_profit"
            lesson = "El cierre manual salió peor que respetar el objetivo original."
        elif operation.get("observation_result") == "manual_better_than_plan":
            outcome = "manual_better_than_plan"
            lesson = "El cierre manual superó el resultado del plan original."
        else:
            outcome = "manual_inconclusive"
            lesson = "La observación no permite decidir si cerrar fue mejor o peor que mantener el plan."
        return {
            "outcome": outcome,
            "summary": f"Aprendizaje: {lesson} {observation_summary} {pattern_text}",
        }
    return {
        "outcome": "manual_pending_observation",
        "summary": (
            f"Aprendizaje pendiente: la operacion de {symbol} en {side} fue cerrada manualmente con resultado {pnl:.2f} USDT. "
            f"Aun falta completar la observacion de 2 dias para comparar la decision del usuario contra el plan original. {pattern_text}"
        ),
    }


def build_learning_pattern_text(operation: dict) -> str:
    raw = operation.get("recommendation_snapshot_json")
    if not raw:
        return "Patron guardado: sin snapshot tecnico asociado."
    try:
        snapshot = json.loads(raw)
    except json.JSONDecodeError:
        return "Patron guardado: snapshot tecnico no legible."
    timeframes = snapshot.get("analysis_timeframes") or {}
    technical = snapshot.get("technical_rating") or {}
    regime = snapshot.get("market_regime") or {}
    scores = snapshot.get("layered_scores") or {}
    fibonacci = snapshot.get("fibonacci_context") or {}
    entry_context = snapshot.get("entry_order_context") or {}
    zone = snapshot.get("zone_analysis") or {}
    zone_probability = snapshot.get("zone_probability_context") or {}
    pieces = [
        f"horizonte {operation.get('time_horizon') or snapshot.get('time_horizon') or 'sin definir'}",
        f"rating tecnico {technical.get('label', 'no disponible')} {technical.get('score', '--')}/100",
        f"regimen {str(regime.get('name', 'no disponible')).replace('_', ' ')}",
        f"direccion {scores.get('direction_score', '--')}/100",
        f"confianza {scores.get('confidence_score', '--')}/100",
        f"fibonacci {fibonacci.get('bias', 'n/d')} {fibonacci.get('score', '--')}/100 zona {fibonacci.get('entry_zone', 'n/d')}",
        f"derivados {timeframes.get('derivatives_period', 'n/d')}",
        f"niveles {timeframes.get('levels', 'n/d')}",
    ]
    if entry_context.get("entry_type") == "pending" or zone.get("available"):
        pieces.extend([
            f"orden {zone.get('entry_order_type') or entry_context.get('entry_order_type') or 'pendiente'}",
            f"zona {zone.get('entry_zone_type', 'n/d')} confluencia {zone.get('zone_confluence_score', '--')}/100",
            f"reaccion {zone.get('reaction_bias', 'n/d')}",
            f"barrida {zone.get('liquidity_sweep_risk', 'n/d')}",
            f"ajuste zona {zone_probability.get('probability_adjustment', 'n/d')}",
        ])
    return f"Patron guardado para aprendizaje: {', '.join(pieces)}."


def build_observation_result(db, operation: dict) -> dict:
    ticks = db.execute(
        """
        SELECT price, captured_at
        FROM price_ticks
        WHERE operation_id = ? AND captured_at >= COALESCE(?, captured_at)
        ORDER BY captured_at ASC
        """,
        (operation["id"], operation["closed_at"]),
    ).fetchall()
    trigger = first_plan_trigger_after_close(operation, [row_to_dict(tick) for tick in ticks])
    manual_pnl = float(operation["final_pnl"] or 0)
    close_reason = operation.get("close_reason")
    if trigger is None:
        summary = (
            f"Observacion cerrada: durante los 2 dias posteriores al cierre manual no se detecto TP ni SL. "
            f"El cierre del usuario queda como decision no concluyente frente al plan original. PnL manual: {manual_pnl:.2f} USDT."
        )
        return {"result": "plan_unresolved", "summary": summary}

    reason, price, captured_at = trigger
    plan_pnl = approximate_pnl(operation, price)
    if reason == "stop_loss":
        result = "manual_protected" if manual_pnl > plan_pnl else "manual_worse_than_plan"
        summary = (
            f"Observacion cerrada: el plan original habria terminado en STOP LOSS en {price:.2f} "
            f"({captured_at}). Cierre manual: {manual_pnl:.2f} USDT; plan original: {plan_pnl:.2f} USDT."
        )
    else:
        result = "manual_left_profit" if manual_pnl < plan_pnl else "manual_better_than_plan"
        summary = (
            f"Observacion cerrada: el plan original habria terminado en TAKE PROFIT en {price:.2f} "
            f"({captured_at}). Cierre manual: {manual_pnl:.2f} USDT; plan original: {plan_pnl:.2f} USDT."
        )
    if close_reason == "cut_loss" and result == "manual_protected":
        summary = f"{summary} Conclusion: el corte manual protegió capital frente a mantener la operacion."
    elif result == "manual_left_profit":
        summary = f"{summary} Conclusion: el cierre manual salio peor que respetar el objetivo."
    return {"result": result, "summary": summary}


def first_plan_trigger_after_close(operation: dict, ticks: list[dict]) -> tuple[str, float, str] | None:
    for tick in ticks:
        price = float(tick["price"])
        reason = triggered_exit_reason(operation, price)
        if reason:
            return reason, triggered_exit_price(operation, reason), str(tick["captured_at"])
    return None


def triggered_exit_from_market_path(operation: dict, current_price: float) -> tuple[str, float, str, dict] | None:
    start_time_ms = operation_start_time_ms(operation)
    end_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    klines = get_operation_klines_1m(operation["symbol"], start_time_ms, end_time_ms)
    for kline in klines:
        open_time_ms = int(kline[0])
        close_time_ms = int(kline[6])
        open_time = iso_from_ms(open_time_ms)
        high = float(kline[2])
        low = float(kline[3])
        reason = triggered_exit_reason_from_range(operation, low, high)
        if reason:
            if range_hits_both_exits(operation, low, high):
                trade_trigger = triggered_exit_from_trades(operation, open_time_ms, close_time_ms)
                if trade_trigger:
                    return trade_trigger
            return reason, triggered_exit_price(operation, reason), open_time, build_exit_evidence(
                operation,
                reason,
                "binance_usdm_futures_1m_kline",
                open_time,
                {
                    "open": float(kline[1]),
                    "high": high,
                    "low": low,
                    "close": float(kline[4]),
                    "volume": float(kline[5]),
                    "open_time": open_time,
                    "close_time": iso_from_ms(close_time_ms),
                },
            )

    immediate_reason = triggered_exit_reason(operation, current_price)
    if immediate_reason:
        return immediate_reason, triggered_exit_price(operation, immediate_reason), "precio_actual", build_exit_evidence(
            operation,
            immediate_reason,
            "binance_usdm_futures_ticker",
            "precio_actual",
            {"price": current_price},
        )
    return None


def triggered_entry_from_market_path(operation: dict, current_price: float) -> tuple[float, str, dict] | None:
    start_time_ms = timestamp_ms_from_operation_creation(operation)
    end_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    entry_price = float(operation.get("requested_entry") or operation["entry"])
    klines = get_operation_klines_1m(operation["symbol"], start_time_ms, end_time_ms)
    for kline in klines:
        open_time = iso_from_ms(int(kline[0]))
        high = float(kline[2])
        low = float(kline[3])
        if triggered_entry_condition_from_range(operation, low, high):
            return entry_price, open_time, build_activation_evidence(
                operation,
                "binance_usdm_futures_1m_kline",
                open_time,
                {
                    "open": float(kline[1]),
                    "high": high,
                    "low": low,
                    "close": float(kline[4]),
                    "volume": float(kline[5]),
                    "open_time": open_time,
                    "close_time": iso_from_ms(int(kline[6])),
                },
            )
    if triggered_entry_condition(operation, current_price):
        trigger_time = datetime.now(timezone.utc).isoformat()
        return entry_price, trigger_time, build_activation_evidence(
            operation,
            "binance_usdm_futures_ticker",
            trigger_time,
            {"price": current_price},
        )
    return None


def get_operation_klines_1m(symbol: str, start_time_ms: int, end_time_ms: int) -> list[list]:
    klines: list[list] = []
    next_start = start_time_ms
    for _ in range(MAX_EXIT_KLINE_PAGES):
        batch = market_data.get_klines(
            symbol,
            "1m",
            1000,
            start_time_ms=next_start,
            end_time_ms=end_time_ms,
        )
        if not batch:
            break
        klines.extend(batch)
        last_open_time = int(batch[-1][0])
        next_start = last_open_time + ONE_MINUTE_MS
        if next_start > end_time_ms or len(batch) < 1000:
            break
    return klines


def triggered_exit_from_trades(operation: dict, start_time_ms: int, end_time_ms: int) -> tuple[str, float, str, dict] | None:
    next_start = start_time_ms
    for _ in range(MAX_EXIT_TRADE_PAGES):
        trades = market_data.get_agg_trades(
            operation["symbol"],
            1000,
            start_time_ms=next_start,
            end_time_ms=end_time_ms,
        )
        if not trades:
            break
        for trade in trades:
            price = float(trade.get("p", 0))
            reason = triggered_exit_reason(operation, price)
            if reason:
                trigger_time = iso_from_ms(int(trade.get("T", start_time_ms)))
                return reason, triggered_exit_price(operation, reason), trigger_time, build_exit_evidence(
                    operation,
                    reason,
                    "binance_usdm_futures_agg_trade",
                    trigger_time,
                    {
                        "price": price,
                        "trade_time": trigger_time,
                        "quantity": float(trade.get("q", 0)),
                    },
                )
        last_trade_time = int(trades[-1].get("T", next_start))
        next_start = last_trade_time + 1
        if next_start > end_time_ms or len(trades) < 1000:
            break
    return None


def build_exit_evidence(operation: dict, reason: str, source: str, trigger_time: str, market_data_payload: dict) -> dict:
    level = triggered_exit_price(operation, reason)
    return {
        "source": source,
        "symbol": operation["symbol"],
        "side": operation["side"],
        "reason": reason,
        "trigger_time": trigger_time,
        "level": level,
        "entry": float(operation["entry"]),
        "stop_loss": float(operation["stop_loss"]),
        "take_profit": float(operation["take_profit"]),
        "market_data": market_data_payload,
    }


def build_activation_evidence(operation: dict, source: str, trigger_time: str, market_data_payload: dict) -> dict:
    entry_price = float(operation.get("requested_entry") or operation["entry"])
    return {
        "source": source,
        "symbol": operation["symbol"],
        "side": operation["side"],
        "trigger_time": trigger_time,
        "entry_type": operation.get("entry_type") or "pending",
        "entry_order_type": operation.get("entry_order_type"),
        "trigger_condition": operation.get("trigger_condition"),
        "requested_entry": entry_price,
        "stop_loss": float(operation["stop_loss"]),
        "take_profit": float(operation["take_profit"]),
        "market_data": market_data_payload,
    }


def iso_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def operation_start_time_ms(operation: dict) -> int:
    raw_started_at = operation.get("started_at") or operation.get("created_at")
    started_at = datetime.fromisoformat(str(raw_started_at).replace(" ", "T"))
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return int(started_at.timestamp() * 1000)


def timestamp_ms_from_operation_creation(operation: dict) -> int:
    raw_created_at = operation.get("created_at") or operation.get("started_at")
    created_at = datetime.fromisoformat(str(raw_created_at).replace(" ", "T"))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return int(created_at.timestamp() * 1000)


def operation_age_minutes(operation: dict) -> float:
    return (datetime.now(timezone.utc).timestamp() * 1000 - operation_start_time_ms(operation)) / 60000


def triggered_exit_price(operation: dict, reason: str) -> float:
    if reason == "stop_loss":
        return float(operation["stop_loss"])
    return float(operation["take_profit"])


def triggered_exit_reason(operation: dict, price_value: float) -> str | None:
    side = operation["side"]
    stop_loss = float(operation["stop_loss"])
    take_profit = float(operation["take_profit"])
    if side == "long":
        if price_value <= stop_loss:
            return "stop_loss"
        if price_value >= take_profit:
            return "take_profit"
    else:
        if price_value >= stop_loss:
            return "stop_loss"
        if price_value <= take_profit:
            return "take_profit"
    return None


def triggered_exit_reason_from_range(operation: dict, low: float, high: float) -> str | None:
    side = operation["side"]
    stop_loss = float(operation["stop_loss"])
    take_profit = float(operation["take_profit"])
    if side == "long":
        hit_stop = low <= stop_loss
        hit_target = high >= take_profit
    else:
        hit_stop = high >= stop_loss
        hit_target = low <= take_profit
    if hit_stop and hit_target:
        return "stop_loss"
    if hit_stop:
        return "stop_loss"
    if hit_target:
        return "take_profit"
    return None


def triggered_entry_condition(operation: dict, price_value: float) -> bool:
    entry_price = float(operation.get("requested_entry") or operation["entry"])
    if operation.get("trigger_condition") == "price_gte":
        return price_value >= entry_price
    return price_value <= entry_price


def triggered_entry_condition_from_range(operation: dict, low: float, high: float) -> bool:
    entry_price = float(operation.get("requested_entry") or operation["entry"])
    if operation.get("trigger_condition") == "price_gte":
        return high >= entry_price
    return low <= entry_price


def range_hits_both_exits(operation: dict, low: float, high: float) -> bool:
    side = operation["side"]
    stop_loss = float(operation["stop_loss"])
    take_profit = float(operation["take_profit"])
    if side == "long":
        return low <= stop_loss and high >= take_profit
    return high >= stop_loss and low <= take_profit


@app.get("/api/assets/top")
def top_assets(limit: int = 100) -> dict:
    capped_limit = min(max(limit, 10), 250)
    return {"assets": market_data.get_top_crypto_assets(capped_limit)}


@app.get("/api/market/snapshot")
def market_snapshot(symbol: str = "BTCUSDT") -> dict:
    return data_engine.build_market_snapshot(symbol)


@app.post("/api/analyze")
def analyze(payload: TradePayload, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    entry_type = payload.entry_type.lower()
    trigger_condition = payload.trigger_condition if entry_type == "pending" else None
    side = payload.side.lower()
    validate_entry_order(entry_type, trigger_condition)
    if side not in {"long", "short"}:
        raise HTTPException(status_code=400, detail="Direccion no valida")
    proposal = TradeProposal(
        symbol=payload.symbol.upper(),
        side=side,
        time_horizon=payload.time_horizon,
        entry=payload.entry,
        margin=payload.margin,
        leverage=payload.leverage,
        stop_loss=payload.stop_loss,
        take_profit=payload.take_profit,
        entry_type=entry_type,
        trigger_condition=trigger_condition,
        entry_order_type=entry_order_type(side, trigger_condition),
    )
    if proposal.time_horizon not in VALID_TIME_HORIZONS:
        raise HTTPException(status_code=400, detail="Marco temporal no valido")
    validate_trade_plan(proposal.side, proposal.entry, proposal.stop_loss, proposal.take_profit)
    result = analyze_trade(proposal)
    entry_context = {
        "entry_type": entry_type,
        "trigger_condition": trigger_condition,
        "entry_order_type": entry_order_type(proposal.side, trigger_condition),
        "requested_entry": proposal.entry,
        "activation_rule": (
            "activate_when_price_reaches_or_exceeds_entry"
            if trigger_condition == "price_gte"
            else "activate_when_price_reaches_or_falls_below_entry"
            if trigger_condition == "price_lte"
            else "market_entry_at_current_price"
        ),
    }
    result["entry_order_context"] = entry_context
    result.setdefault("snapshot", {})["entry_order_context"] = entry_context
    with connect() as db:
        cursor = db.execute(
            """
            INSERT INTO recommendations (
                operation_id, user_id, analysis_type, symbol, side,
                tp_probability, sl_probability, range_probability, risk_level,
                setup_grade, confidence, training_decision, time_horizon, parameter_advice_json,
                reasons_json, alerts_json, snapshot_json, analysis_json, engine_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                user["id"],
                result["analysis_type"],
                proposal.symbol,
                proposal.side,
                result["tp_probability"],
                result["sl_probability"],
                result["range_probability"],
                result["risk_level"],
                result["setup_grade"],
                result["confidence"],
                result["training_decision"],
                proposal.time_horizon,
                json.dumps(result["parameter_advice"]),
                json.dumps(result["reasons"]),
                json.dumps(result["alerts"]),
                json.dumps(result["snapshot"]),
                json.dumps(result),
                ENGINE_VERSION,
            ),
        )
        recommendation_id = int(cursor.lastrowid)
    return {"recommendation_id": recommendation_id, **result}


@app.post("/api/operations")
def create_operation(payload: CreateOperationPayload, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    side = payload.side.lower()
    mode = payload.mode.lower()
    entry_type = payload.entry_type.lower()
    trigger_condition = payload.trigger_condition if entry_type == "pending" else None
    if side not in {"long", "short"}:
        raise HTTPException(status_code=400, detail="Direccion no valida")
    if payload.time_horizon not in VALID_TIME_HORIZONS:
        raise HTTPException(status_code=400, detail="Marco temporal no valido")
    validate_entry_order(entry_type, trigger_condition)
    validate_trade_plan(side, payload.entry, payload.stop_loss, payload.take_profit)
    if mode not in VALID_OPERATION_MODES:
        raise HTTPException(status_code=400, detail="Modo de operacion no valido")
    with connect() as db:
        season_id = None
        if mode == "contest":
            season = ensure_current_contest_season(db)
            season_id = int(season["id"])
            if get_contest_entry(db, int(user["id"]), season_id) is None:
                raise HTTPException(status_code=409, detail="Primero inicia tu participacion en el concurso mensual")
        if mode == "training":
            ensure_training_wallet_funded(
                db,
                int(user["id"]),
                note="Recarga automatica de entrenamiento antes de abrir una nueva operacion.",
            )
        portfolio = sync_user_cash_balance(db, int(user["id"]))
        active_count = db.execute(
            "SELECT COUNT(*) AS count FROM operations WHERE user_id = ? AND mode = ? AND status IN ('OPEN', 'PENDING_ENTRY')",
            (user["id"], mode),
        ).fetchone()["count"]
        if active_count >= 2:
            raise HTTPException(status_code=409, detail="Maximo 2 operaciones activas o pendientes por usuario en este modo")
        cash_balance = float(portfolio[mode]["cash_balance"])
        if payload.margin > cash_balance:
            raise HTTPException(status_code=400, detail="Saldo ficticio insuficiente para bloquear ese margen")
        if payload.recommendation_id is not None:
            recommendation = row_to_dict(db.execute(
                """
                SELECT id, symbol, side, time_horizon, analysis_json
                FROM recommendations
                WHERE id = ? AND user_id = ? AND operation_id IS NULL
                """,
                (payload.recommendation_id, user["id"]),
            ).fetchone())
            if recommendation is None:
                raise HTTPException(status_code=400, detail="Analisis previo no valido para esta operacion")
            validate_recommendation_matches_operation(recommendation, payload, entry_type, trigger_condition)
        cursor = db.execute(
            """
            INSERT INTO operations (
                user_id, symbol, side, time_horizon, entry, margin, leverage, stop_loss, take_profit,
                status, started_at, mode, contest_season_id, entry_type, requested_entry, trigger_condition, entry_order_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                payload.symbol.upper(),
                side,
                payload.time_horizon,
                payload.entry,
                payload.margin,
                payload.leverage,
                payload.stop_loss,
                payload.take_profit,
                "PENDING_ENTRY" if entry_type == "pending" else "OPEN",
                None if entry_type == "pending" else datetime.now(timezone.utc).isoformat(),
                mode,
                season_id,
                entry_type,
                payload.entry,
                trigger_condition,
                entry_order_type(side, trigger_condition),
            ),
        )
        operation_id = int(cursor.lastrowid)
        if payload.recommendation_id is not None:
            db.execute(
                "UPDATE recommendations SET operation_id = ? WHERE id = ? AND user_id = ?",
                (operation_id, payload.recommendation_id, user["id"]),
            )
        # Compute balance-after locally without re-syncing the whole portfolio:
        # we already validated cash_balance above and now reserve `payload.margin`.
        balance_after = round(cash_balance - float(payload.margin), 4)
        record_wallet_event(
            db,
            user_id=int(user["id"]),
            mode=mode,
            event_type="margin_reserved",
            amount=-float(payload.margin),
            balance_after=balance_after,
            operation_id=operation_id,
            contest_season_id=season_id,
            note="Margen bloqueado al crear orden pendiente." if entry_type == "pending" else "Margen bloqueado al iniciar operacion simulada.",
        )
    return {"id": operation_id, "status": "PENDING_ENTRY" if entry_type == "pending" else "OPEN"}


@app.get("/api/operations")
def list_operations(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    with connect() as db:
        finalize_due_observations(db)
        refresh_learning_conclusions(db)
        rows = db.execute(
            "SELECT * FROM operations WHERE user_id = ? ORDER BY created_at DESC",
            (user["id"],),
        ).fetchall()
        operations = [row_to_dict(row) for row in rows]
        for operation in operations:
            ensure_closed_exit_window_ticks(db, operation)
            operation["exit_evidence"] = parse_exit_evidence(operation.get("exit_evidence_json"))
            operation["activation_evidence"] = parse_exit_evidence(operation.get("activation_evidence_json"))
            operation["recommendation"] = None
            operation["ticks"] = []

        if operations:
            op_ids = [op["id"] for op in operations]
            placeholders = ",".join(["?"] * len(op_ids))

            # Batch fetch latest recommendation per operation (1 query instead of N).
            rec_rows = db.execute(
                f"""
                SELECT DISTINCT ON (operation_id) *
                FROM recommendations
                WHERE user_id = ? AND operation_id IN ({placeholders})
                ORDER BY operation_id, created_at DESC
                """,
                (user["id"], *op_ids),
            ).fetchall()
            rec_by_op = {row_to_dict(r)["operation_id"]: row_to_dict(r) for r in rec_rows}

            for op in operations:
                rec = rec_by_op.get(op["id"])
                op["recommendation"] = format_recommendation(rec, op) if rec else None
    return {"operations": operations}


@app.get("/api/operations/{operation_id}/ticks")
def operation_ticks(
    operation_id: int,
    limit: int = 240,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    user = current_user(session_token)
    safe_limit = min(max(int(limit or 120), 20), 240)
    with connect() as db:
        operation = db.execute(
            "SELECT * FROM operations WHERE id = ? AND user_id = ?",
            (operation_id, user["id"]),
        ).fetchone()
        if operation is None:
            raise HTTPException(status_code=404, detail="Operacion no encontrada")
        operation_dict = row_to_dict(operation)
        ensure_closed_exit_window_ticks(db, operation_dict)
        rows = db.execute(
            """
            SELECT price, source, captured_at
            FROM (
                SELECT price, source, captured_at,
                       ROW_NUMBER() OVER (ORDER BY captured_at DESC) AS rn
                FROM price_ticks
                WHERE operation_id = ?
            ) ranked
            WHERE rn <= ?
            ORDER BY captured_at ASC
            """,
            (operation_id, safe_limit),
        ).fetchall()
    return {
        "operation_id": operation_id,
        "limit": safe_limit,
        "ticks": [
            {
                "price": row["price"],
                "source": row["source"],
                "captured_at": row["captured_at"],
            }
            for row in rows
        ],
    }


def parse_exit_evidence(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def ensure_closed_exit_window_ticks(db, operation: dict) -> None:
    if operation.get("status") != "CLOSED" or operation.get("close_reason") not in {"stop_loss", "take_profit"}:
        return
    ensure_exit_evidence(db, operation)
    exists = db.execute(
        """
        SELECT 1
        FROM price_ticks
        WHERE operation_id = ? AND source = 'auto_exit'
        LIMIT 1
        """,
        (operation["id"],),
    ).fetchone()
    if exists:
        return
    close_price = operation.get("close_price")
    if close_price is None:
        return
    trigger_time = trigger_time_from_closing_note(operation) or str(operation.get("closed_at") or "precio_actual")
    record_exit_window_ticks(db, operation, float(close_price), trigger_time)


def ensure_exit_evidence(db, operation: dict) -> None:
    existing_evidence = parse_exit_evidence(operation.get("exit_evidence_json"))
    if existing_evidence and existing_evidence.get("source") != "recorded_close_price":
        return
    trigger_time = trigger_time_from_closing_note(operation) or str(operation.get("closed_at") or "precio_actual")
    trigger_ms = timestamp_ms_from_trigger_time(trigger_time)
    reason = str(operation.get("close_reason") or "")
    evidence = None
    if trigger_ms is not None:
        try:
            klines = market_data.get_klines(
                operation["symbol"],
                "1m",
                1,
                start_time_ms=trigger_ms,
                end_time_ms=trigger_ms + ONE_MINUTE_MS - 1,
            )
        except Exception:
            klines = []
        if klines:
            kline = klines[0]
            evidence = build_exit_evidence(
                operation,
                reason,
                "binance_usdm_futures_1m_kline",
                iso_from_ms(int(kline[0])),
                {
                    "open": float(kline[1]),
                    "high": float(kline[2]),
                    "low": float(kline[3]),
                    "close": float(kline[4]),
                    "volume": float(kline[5]),
                    "open_time": iso_from_ms(int(kline[0])),
                    "close_time": iso_from_ms(int(kline[6])),
                },
            )
    if evidence is None and operation.get("close_price") is not None:
        evidence = build_exit_evidence(
            operation,
            reason,
            "recorded_close_price",
            trigger_time,
            {"price": float(operation["close_price"])},
        )
    if evidence:
        db.execute(
            "UPDATE operations SET exit_evidence_json = ? WHERE id = ?",
            (json.dumps(evidence, ensure_ascii=True), operation["id"]),
        )
        operation["exit_evidence_json"] = json.dumps(evidence, ensure_ascii=True)


def format_recommendation(recommendation: dict | None, operation: dict | None = None) -> dict | None:
    if recommendation is None:
        return None
    analysis_json = recommendation.get("analysis_json")
    if analysis_json:
        payload = json.loads(analysis_json)
        payload["id"] = recommendation["id"]
        payload["recommendation_id"] = recommendation["id"]
        payload["operation_id"] = recommendation["operation_id"]
        payload["time_horizon"] = recommendation.get("time_horizon") or payload.get("time_horizon") or payload.get("snapshot", {}).get("time_horizon", "intraday_short")
        payload["created_at"] = recommendation["created_at"]
        return payload
    snapshot = json.loads(recommendation["snapshot_json"])
    payload = {
        "id": recommendation["id"],
        "recommendation_id": recommendation["id"],
        "operation_id": recommendation["operation_id"],
        "analysis_type": recommendation["analysis_type"],
        "symbol": recommendation["symbol"],
        "side": recommendation["side"],
        "time_horizon": recommendation.get("time_horizon") or snapshot.get("time_horizon", "intraday_short"),
        "tp_probability": recommendation["tp_probability"],
        "sl_probability": recommendation["sl_probability"],
        "range_probability": recommendation["range_probability"],
        "risk_level": recommendation["risk_level"],
        "setup_grade": recommendation["setup_grade"],
        "confidence": recommendation["confidence"],
        "training_decision": recommendation["training_decision"],
        "parameter_advice": json.loads(recommendation["parameter_advice_json"]),
        "reasons": json.loads(recommendation["reasons_json"]),
        "alerts": json.loads(recommendation["alerts_json"]),
        "snapshot": snapshot,
        "probability_ranges": snapshot.get("probability_ranges"),
        "expected_value": snapshot.get("expected_value"),
        "layered_scores": snapshot.get("layered_scores"),
        "market_regime": snapshot.get("market_regime"),
        "invalidation_rules": snapshot.get("invalidation_rules", []),
        "plain_summary": build_snapshot_summary(recommendation, snapshot),
        "explained_metrics": rebuild_explained_metrics_from_snapshot(snapshot, operation),
        "engine_version": recommendation["engine_version"],
        "created_at": recommendation["created_at"],
    }
    return payload


def build_snapshot_summary(recommendation: dict, snapshot: dict) -> str:
    rr_ratio = snapshot.get("risk_reward_ratio")
    risk_distance = snapshot.get("risk_distance_pct")
    reward_distance = snapshot.get("reward_distance_pct")
    setup = recommendation["setup_grade"]
    risk = recommendation["risk_level"]
    confidence = recommendation["confidence"]
    horizon = snapshot.get("time_horizon_profile", {}).get("label") or (recommendation.get("time_horizon") or "intraday_short")
    tp_probability = float(recommendation["tp_probability"])
    sl_probability = float(recommendation["sl_probability"])
    return (
            f"Lectura operativa {horizon}: setup {setup}, riesgo {risk} y confianza {confidence}. "
        f"TP estimado {tp_probability:.0%}, SL {sl_probability:.0%}. "
        f"R/R {rr_ratio:.2f}; riesgo de precio {risk_distance:.2f}% frente a recompensa {reward_distance:.2f}%."
        if rr_ratio is not None and risk_distance is not None and reward_distance is not None
        else f"Lectura operativa {horizon}: setup {setup}, riesgo {risk} y confianza {confidence}."
    )


def rebuild_explained_metrics_from_snapshot(snapshot: dict, operation: dict | None) -> list[dict]:
    if operation is None:
        return []
    try:
        proposal = TradeProposal(
            symbol=operation["symbol"],
            side=operation["side"],
            time_horizon=operation.get("time_horizon") or snapshot.get("time_horizon", "intraday_short"),
            entry=float(operation["entry"]),
            margin=float(operation["margin"]),
            leverage=float(operation["leverage"]),
            stop_loss=float(operation["stop_loss"]),
            take_profit=float(operation["take_profit"]),
        )
        return build_explained_metrics(
            timeframes=snapshot["timeframes"],
            levels=snapshot["levels"],
            tf_5m=snapshot["timeframes"]["5m"],
            tf_1h=snapshot["timeframes"]["1h"],
            order_book=snapshot["order_book"],
            trade_flow=snapshot["trade_flow"],
            ticker_24h=snapshot["ticker_24h"],
            derivatives=snapshot["derivatives"],
            sentiment=snapshot["sentiment"],
            global_market=snapshot["global_market"],
            market_breadth=snapshot.get("market_breadth", {}),
            rr_ratio=float(snapshot.get("risk_reward_ratio", 0)),
            proposal=proposal,
            horizon_profile=snapshot.get("time_horizon_profile") or time_horizon_profile(proposal.time_horizon),
            risk_distance=float(snapshot.get("risk_distance_pct", 0)),
            reward_distance=float(snapshot.get("reward_distance_pct", 0)),
        )
    except Exception:
        return []


@app.post("/api/operations/{operation_id}/close")
def close_operation(
    operation_id: int,
    payload: CloseOperationPayload,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    user = current_user(session_token)
    with connect() as db:
        row = db.execute(
            "SELECT * FROM operations WHERE id = ? AND user_id = ?",
            (operation_id, user["id"]),
        ).fetchone()
        operation = row_to_dict(row)
        if operation is None:
            raise HTTPException(status_code=404, detail="Operacion no encontrada")
        if operation["status"] != "OPEN":
            raise HTTPException(status_code=409, detail="La operacion ya esta cerrada")
        pnl = approximate_pnl(operation, payload.close_price)
        update_cursor = db.execute(
            """
            UPDATE operations
            SET status = 'CLOSED', closed_at = CURRENT_TIMESTAMP, close_price = ?, close_reason = ?,
                final_pnl = ?, observation_until = ?, observation_status = 'OBSERVING',
                post_emotion = ?, plan_followed = ?, closing_note = ?,
                learning_outcome = NULL, learning_summary = NULL
            WHERE id = ? AND user_id = ? AND status = 'OPEN'
            """,
            (
                payload.close_price,
                payload.close_reason,
                pnl,
                (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                payload.post_emotion,
                payload.plan_followed,
                payload.closing_note,
                operation_id,
                user["id"],
            ),
        )
        if update_cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail="La operacion ya esta cerrada")
        portfolio = sync_user_cash_balance(db, int(user["id"]))
        mode = operation.get("mode") or "training"
        record_wallet_event(
            db,
            user_id=int(user["id"]),
            mode=mode,
            event_type="operation_closed_manual",
            amount=float(pnl),
            balance_after=float(portfolio[mode]["cash_balance"]),
            operation_id=operation_id,
            contest_season_id=operation.get("contest_season_id"),
            note=payload.close_reason,
        )
    return {"id": operation_id, "status": "CLOSED", "final_pnl": pnl}


@app.post("/api/operations/{operation_id}/cancel")
def cancel_pending_operation(operation_id: int, session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    with connect() as db:
        operation = row_to_dict(db.execute(
            "SELECT * FROM operations WHERE id = ? AND user_id = ?",
            (operation_id, user["id"]),
        ).fetchone())
        if operation is None:
            raise HTTPException(status_code=404, detail="Operacion no encontrada")
        if operation.get("status") != "PENDING_ENTRY":
            raise HTTPException(status_code=400, detail="Solo se pueden cancelar ordenes pendientes")
        update_cursor = db.execute(
            """
            UPDATE operations
            SET status = 'CANCELLED',
                closed_at = CURRENT_TIMESTAMP,
                close_reason = 'pending_cancelled',
                final_pnl = 0
            WHERE id = ? AND user_id = ? AND status = 'PENDING_ENTRY'
            """,
            (operation_id, user["id"]),
        )
        if update_cursor.rowcount == 0:
            raise HTTPException(status_code=400, detail="Solo se pueden cancelar ordenes pendientes")
        portfolio = sync_user_cash_balance(db, int(user["id"]))
        mode = operation.get("mode") or "training"
        record_wallet_event(
            db,
            user_id=int(user["id"]),
            mode=mode,
            event_type="pending_entry_cancelled",
            amount=float(operation.get("margin") or 0),
            balance_after=float(portfolio[mode]["cash_balance"]),
            operation_id=operation_id,
            contest_season_id=operation.get("contest_season_id"),
            note="Margen liberado al cancelar orden pendiente.",
        )
    return {"id": operation_id, "status": "CANCELLED", "final_pnl": 0}


def approximate_pnl(operation: dict, close_price: float) -> float:
    entry = float(operation["entry"])
    margin = float(operation["margin"])
    leverage = float(operation["leverage"])
    raw_variation = (close_price - entry) / entry
    if operation["side"] == "short":
        raw_variation *= -1
    return round(margin * leverage * raw_variation, 4)


def get_portfolio(user_id: int) -> dict:
    with connect() as db:
        return sync_user_cash_balance(db, user_id)


def reconcile_all_user_cash_balances() -> None:
    with connect() as db:
        user_ids = [int(row["id"]) for row in db.execute("SELECT id FROM users").fetchall()]
        for user_id in user_ids:
            sync_user_cash_balance(db, user_id)
        reconcile_all_contest_entry_balances(db)
        refresh_closed_contest_results(db)


def sync_user_cash_balance(db, user_id: int) -> dict:
    ensure_training_wallet_funded(
        db,
        user_id,
        note="Recarga automatica de entrenamiento por saldo agotado.",
    )
    portfolio = calculate_portfolio_from_db(db, user_id)
    db.execute(
        "UPDATE users SET cash_balance = ? WHERE id = ?",
        (portfolio["training"]["cash_balance"], user_id),
    )
    contest = portfolio.get("contest")
    if contest and contest.get("entry_id"):
        db.execute(
            "UPDATE contest_entries SET cash_balance = ? WHERE id = ?",
            (contest["cash_balance"], contest["entry_id"]),
        )
    return portfolio


def ensure_training_wallet_funded(
    db,
    user_id: int,
    note: str = "Recarga automatica de entrenamiento.",
) -> int:
    user = db.execute("SELECT starting_balance FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    starting_balance = float(user["starting_balance"])
    portfolio = calculate_mode_portfolio(db, user_id, "training", starting_balance, None)
    cash_balance = float(portfolio["cash_balance"])
    recharge_count = 0
    while cash_balance < 0.01:
        starting_balance = round(starting_balance + TRAINING_RECHARGE_AMOUNT, 4)
        recharge_count += 1
        portfolio = calculate_mode_portfolio(db, user_id, "training", starting_balance, None)
        cash_balance = float(portfolio["cash_balance"])
        db.execute(
            "UPDATE users SET starting_balance = ?, cash_balance = ? WHERE id = ?",
            (starting_balance, cash_balance, user_id),
        )
        record_wallet_event(
            db,
            user_id=user_id,
            mode="training",
            event_type="training_recharge",
            amount=TRAINING_RECHARGE_AMOUNT,
            balance_after=cash_balance,
            note=note,
        )
    return recharge_count


def reconcile_all_contest_entry_balances(db) -> None:
    entries = db.execute("SELECT id, season_id, user_id, starting_balance FROM contest_entries").fetchall()
    for entry in entries:
        portfolio = calculate_mode_portfolio(
            db,
            int(entry["user_id"]),
            "contest",
            float(entry["starting_balance"]),
            int(entry["season_id"]),
        )
        db.execute(
            "UPDATE contest_entries SET cash_balance = ? WHERE id = ?",
            (portfolio["cash_balance"], entry["id"]),
        )


def refresh_closed_contest_results(db) -> None:
    rows = db.execute("SELECT * FROM contest_seasons WHERE status = 'CLOSED' ORDER BY ends_at ASC").fetchall()
    for row in rows:
        season = row_to_dict(row)
        leaderboard = contest_leaderboard(db, int(season["id"]))
        winner = leaderboard[0] if leaderboard else {}
        db.execute(
            """
            UPDATE contest_seasons
            SET winner_user_id = ?,
                winner_username = ?,
                winner_equity = ?,
                winner_pnl = ?,
                final_leaderboard_json = ?
            WHERE id = ?
            """,
            (
                winner.get("user_id"),
                winner.get("username"),
                winner.get("estimated_equity"),
                winner.get("pnl_accumulated"),
                json.dumps(leaderboard, ensure_ascii=True),
                season["id"],
            ),
        )


def calculate_portfolio_from_db(db, user_id: int) -> dict:
    user = db.execute("SELECT starting_balance FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    training = calculate_mode_portfolio(db, user_id, "training", float(user["starting_balance"]), None)
    season = ensure_current_contest_season(db)
    entry = get_contest_entry(db, user_id, int(season["id"]))
    if entry:
        contest = calculate_mode_portfolio(db, user_id, "contest", float(entry["starting_balance"]), int(season["id"]))
        contest["entry_id"] = entry["id"]
    else:
        contest = {
            "mode": "contest",
            "starting_balance": float(season["starting_balance"]),
            "cash_balance": 0,
            "invested_margin": 0,
            "total_equity_without_unrealized": 0,
            "closed_pnl": 0,
            "open_operations": 0,
            "max_open_operations": 2,
            "entry_id": None,
        }
    contest["season"] = season
    return {
        **training,
        "training": training,
        "contest": contest,
        "active_mode": "training",
        "max_open_operations": 2,
    }


def calculate_mode_portfolio(db, user_id: int, mode: str, starting_balance: float, season_id: int | None) -> dict:
    params: tuple = (user_id, mode) if season_id is None else (user_id, mode, season_id)
    season_clause = "" if season_id is None else " AND contest_season_id = ?"
    active_rows = db.execute(
        f"SELECT margin FROM operations WHERE user_id = ? AND mode = ? AND status IN ('OPEN', 'PENDING_ENTRY'){season_clause}",
        params,
    ).fetchall()
    closed_pnl = db.execute(
        f"SELECT COALESCE(SUM(final_pnl), 0) AS pnl FROM operations WHERE user_id = ? AND mode = ? AND status = 'CLOSED'{season_clause}",
        params,
    ).fetchone()["pnl"]
    invested_margin = sum(float(row["margin"]) for row in active_rows)
    closed_pnl_value = float(closed_pnl)
    cash_balance = starting_balance + closed_pnl_value - invested_margin
    total_equity = cash_balance + invested_margin
    return {
        "mode": mode,
        "starting_balance": round(starting_balance, 4),
        "cash_balance": round(cash_balance, 4),
        "invested_margin": round(invested_margin, 4),
        "total_equity_without_unrealized": round(total_equity, 4),
        "closed_pnl": round(closed_pnl_value, 4),
        "open_operations": len(active_rows),
        "max_open_operations": 2,
    }


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def timestamp_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def ensure_current_contest_season(db) -> dict:
    now = datetime.now(timezone.utc)
    finalize_expired_contest_seasons(db, now)
    code = now.strftime("%Y-%m")
    row = db.execute("SELECT * FROM contest_seasons WHERE code = ?", (code,)).fetchone()
    if row is None:
        starts_at = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        if now.month == 12:
            ends_at = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            ends_at = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
        cursor = db.execute(
            """
            INSERT INTO contest_seasons (code, name, starts_at, ends_at, status, starting_balance)
            VALUES (?, ?, ?, ?, 'ACTIVE', 1000)
            """,
            (code, f"Concurso {code}", starts_at.isoformat(), ends_at.isoformat()),
        )
        row = db.execute("SELECT * FROM contest_seasons WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
    return row_to_dict(row)


def finalize_expired_contest_seasons(db, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = db.execute(
        """
        SELECT *
        FROM contest_seasons
        WHERE status = 'ACTIVE'
        ORDER BY starts_at ASC
        """
    ).fetchall()
    finalized: list[dict] = []
    for row in rows:
        season = row_to_dict(row)
        ends_at = parse_timestamp(season.get("ends_at"))
        if ends_at is None or ends_at > now:
            continue
        finalized.append(finalize_contest_season(db, season, ends_at))
    return finalized


def finalize_contest_season(db, season: dict, ends_at: datetime) -> dict:
    season_id = int(season["id"])
    open_rows = db.execute(
        """
        SELECT *
        FROM operations
        WHERE mode = 'contest'
          AND contest_season_id = ?
          AND status = 'OPEN'
        ORDER BY id ASC
        """,
        (season_id,),
    ).fetchall()
    operations = [row_to_dict(row) for row in open_rows]
    for operation in operations:
        close_price, close_source = contest_expiry_price(db, operation, ends_at)
        pnl = approximate_pnl(operation, close_price)
        db.execute(
            """
            UPDATE operations
            SET status = 'CLOSED',
                closed_at = ?,
                close_price = ?,
                close_reason = 'contest_expired',
                final_pnl = ?,
                observation_until = NULL,
                observation_status = 'CONTEST_FINALIZED',
                closing_note = ?,
                learning_outcome = NULL,
                learning_summary = NULL
            WHERE id = ?
            """,
            (
                ends_at.isoformat(),
                close_price,
                pnl,
                "Cierre automatico por finalizacion del concurso mensual.",
                operation["id"],
            ),
        )
        db.execute(
            "INSERT INTO price_ticks (operation_id, symbol, price, source, captured_at) VALUES (?, ?, ?, ?, ?)",
            (operation["id"], operation["symbol"], close_price, close_source, ends_at.isoformat()),
        )
        entry = get_contest_entry(db, int(operation["user_id"]), season_id)
        starting_balance = float(entry["starting_balance"] if entry else season.get("starting_balance") or 1000)
        portfolio = calculate_mode_portfolio(db, int(operation["user_id"]), "contest", starting_balance, season_id)
        db.execute(
            "UPDATE contest_entries SET cash_balance = ? WHERE season_id = ? AND user_id = ?",
            (portfolio["cash_balance"], season_id, operation["user_id"]),
        )
        record_wallet_event(
            db,
            user_id=int(operation["user_id"]),
            mode="contest",
            event_type="contest_monthly_close",
            amount=float(pnl),
            balance_after=float(portfolio["cash_balance"]),
            operation_id=int(operation["id"]),
            contest_season_id=season_id,
            note="Cierre por fin de concurso mensual.",
        )

    leaderboard = contest_leaderboard(db, season_id)
    winner = leaderboard[0] if leaderboard else {}
    db.execute(
        """
        UPDATE contest_seasons
        SET status = 'CLOSED',
            finalized_at = CURRENT_TIMESTAMP,
            winner_user_id = ?,
            winner_username = ?,
            winner_equity = ?,
            winner_pnl = ?,
            final_leaderboard_json = ?
        WHERE id = ?
        """,
        (
            winner.get("user_id"),
            winner.get("username"),
            winner.get("estimated_equity"),
            winner.get("pnl_accumulated"),
            json.dumps(leaderboard, ensure_ascii=True),
            season_id,
        ),
    )
    refreshed = db.execute("SELECT * FROM contest_seasons WHERE id = ?", (season_id,)).fetchone()
    return row_to_dict(refreshed)


def contest_expiry_price(db, operation: dict, ends_at: datetime) -> tuple[float, str]:
    symbol = str(operation["symbol"]).upper()
    try:
        klines = market_data.get_klines(
            symbol,
            interval="1m",
            limit=1,
            start_time_ms=timestamp_ms(ends_at - timedelta(minutes=1)),
            end_time_ms=timestamp_ms(ends_at + timedelta(minutes=1)),
        )
        if klines:
            return round(float(klines[0][4]), 8), "contest_expiry_binance_usdm_futures_1m"
    except Exception:
        pass

    tick = db.execute(
        """
        SELECT price
        FROM price_ticks
        WHERE symbol = ?
          AND captured_at <= ?
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        (symbol, ends_at.isoformat()),
    ).fetchone()
    if tick:
        return round(float(tick["price"]), 8), "contest_expiry_last_tick"

    return round(float(market_data.get_price(symbol)), 8), "contest_expiry_binance_usdm_futures_live_fallback"


def contest_history(db, limit: int = 12) -> list[dict]:
    rows = db.execute(
        """
        SELECT *
        FROM contest_seasons
        WHERE status = 'CLOSED'
        ORDER BY ends_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    history = []
    for row in rows:
        item = row_to_dict(row)
        try:
            item["final_leaderboard"] = json.loads(item.get("final_leaderboard_json") or "[]")
        except json.JSONDecodeError:
            item["final_leaderboard"] = []
        history.append(item)
    return history


def ensure_contest_entry(db, user_id: int, season_id: int) -> dict:
    row = get_contest_entry(db, user_id, season_id)
    if row is None:
        cursor = db.execute(
            """
            INSERT INTO contest_entries (season_id, user_id, starting_balance, cash_balance)
            VALUES (?, ?, 1000, 1000)
            """,
            (season_id, user_id),
        )
        record_wallet_event(
            db,
            user_id=user_id,
            mode="contest",
            event_type="contest_monthly_start",
            amount=1000,
            balance_after=1000,
            contest_season_id=season_id,
            note="Asignacion mensual de capital ficticio para concurso.",
        )
        row = db.execute("SELECT * FROM contest_entries WHERE id = ?", (int(cursor.lastrowid),)).fetchone()
    return row_to_dict(row) if not isinstance(row, dict) else row


def get_contest_entry(db, user_id: int, season_id: int) -> dict | None:
    row = db.execute(
        "SELECT * FROM contest_entries WHERE season_id = ? AND user_id = ?",
        (season_id, user_id),
    ).fetchone()
    return row_to_dict(row)


def live_prices_for_operations(operations: list[dict]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for symbol in sorted({str(operation["symbol"]).upper() for operation in operations}):
        try:
            prices[symbol] = float(market_data.get_price(symbol))
        except Exception:
            continue
    return prices


def apply_contest_unrealized_to_portfolio(db, portfolio: dict, user_id: int, season_id: int) -> None:
    rows = db.execute(
        """
        SELECT *
        FROM operations
        WHERE user_id = ?
          AND mode = 'contest'
          AND contest_season_id = ?
          AND status = 'OPEN'
        """,
        (user_id, season_id),
    ).fetchall()
    operations = [row_to_dict(row) for row in rows]
    prices = live_prices_for_operations(operations)
    unrealized_pnl = sum(
        approximate_pnl(operation, prices[operation["symbol"]])
        for operation in operations
        if operation["symbol"] in prices
    )
    portfolio["unrealized_pnl"] = round(unrealized_pnl, 4)
    portfolio["total_pnl"] = round(float(portfolio.get("closed_pnl") or 0), 4)
    portfolio["estimated_total_pnl"] = round(float(portfolio.get("closed_pnl") or 0) + unrealized_pnl, 4)
    portfolio["estimated_equity"] = round(float(portfolio.get("total_equity_without_unrealized") or 0) + unrealized_pnl, 4)


def contest_leaderboard(db, season_id: int) -> list[dict]:
    rows = db.execute(
        """
        SELECT
            ce.user_id,
            u.username,
            u.avatar_mime_type,
            u.avatar_updated_at,
            ce.starting_balance,
            ce.cash_balance,
            COALESCE(SUM(CASE WHEN o.status IN ('OPEN', 'PENDING_ENTRY') THEN o.margin ELSE 0 END), 0) AS invested_margin,
            COALESCE(SUM(CASE WHEN o.status = 'CLOSED' THEN o.final_pnl ELSE 0 END), 0) AS closed_pnl,
            COALESCE(SUM(CASE WHEN o.status = 'CLOSED' AND COALESCE(o.final_pnl, 0) > 0 THEN 1 ELSE 0 END), 0) AS closed_wins,
            COALESCE(SUM(CASE WHEN o.status = 'CLOSED' AND COALESCE(o.final_pnl, 0) < 0 THEN 1 ELSE 0 END), 0) AS closed_losses,
            COUNT(o.id) AS operation_count,
            COALESCE(
                GROUP_CONCAT(
                    CASE
                        WHEN o.id IS NOT NULL THEN '#' || o.id || ' ' || o.symbol || ' ' || UPPER(o.side) || ' ' || o.status
                        ELSE NULL
                    END,
                    ' | '
                ),
                ''
            ) AS operations_description
        FROM contest_entries ce
        JOIN users u ON u.id = ce.user_id
        LEFT JOIN operations o ON o.user_id = ce.user_id
            AND o.mode = 'contest'
            AND o.contest_season_id = ce.season_id
        WHERE ce.season_id = ?
        GROUP BY ce.user_id, u.username, u.avatar_mime_type, u.avatar_updated_at, ce.starting_balance, ce.cash_balance
        LIMIT 50
        """,
        (season_id,),
    ).fetchall()
    open_rows = db.execute(
        """
        SELECT *
        FROM operations
        WHERE mode = 'contest'
          AND contest_season_id = ?
          AND status = 'OPEN'
        """,
        (season_id,),
    ).fetchall()
    open_operations = [row_to_dict(row) for row in open_rows]
    operation_rows = db.execute(
        """
        SELECT
            o.id,
            o.user_id,
            o.symbol,
            o.side,
            o.status,
            o.entry,
            o.stop_loss,
            o.take_profit,
            o.margin,
            o.leverage,
            o.final_pnl,
            o.close_price,
            o.close_reason,
            o.created_at,
            o.triggered_at,
            o.closed_at,
            o.time_horizon,
            o.entry_type,
            o.requested_entry,
            o.trigger_condition,
            o.entry_order_type,
            r.id AS recommendation_id,
            r.tp_probability AS recommendation_tp_probability,
            r.created_at AS recommendation_created_at
        FROM operations o
        LEFT JOIN recommendations r ON r.id = (
            SELECT r2.id
            FROM recommendations r2
            WHERE r2.operation_id = o.id
            ORDER BY r2.created_at DESC
            LIMIT 1
        )
        WHERE o.mode = 'contest'
          AND o.contest_season_id = ?
        ORDER BY
            CASE WHEN o.status = 'OPEN' THEN 0 WHEN o.status = 'PENDING_ENTRY' THEN 1 ELSE 2 END,
            o.id DESC
        """,
        (season_id,),
    ).fetchall()
    operations_by_user: dict[int, list[dict]] = {}
    for operation_row in operation_rows:
        operation = row_to_dict(operation_row)
        for key, value in list(operation.items()):
            if isinstance(value, datetime):
                operation[key] = value.isoformat()
        operations_by_user.setdefault(int(operation["user_id"]), []).append(operation)
    prices = live_prices_for_operations(open_operations)
    unrealized_by_user: dict[int, float] = {}
    unrealized_by_operation: dict[int, float] = {}
    for operation in open_operations:
        symbol = operation["symbol"]
        if symbol not in prices:
            continue
        user_id = int(operation["user_id"])
        operation_pnl = approximate_pnl(operation, prices[symbol])
        unrealized_by_operation[int(operation["id"])] = round(operation_pnl, 4)
        unrealized_by_user[user_id] = unrealized_by_user.get(user_id, 0) + operation_pnl

    for operations in operations_by_user.values():
        for operation in operations:
            if str(operation.get("status") or "").upper() == "OPEN":
                operation["unrealized_pnl"] = unrealized_by_operation.get(int(operation["id"]))

    leaderboard = []
    for row in rows:
        item = row_to_dict(row)
        unrealized_pnl = round(unrealized_by_user.get(int(item["user_id"]), 0), 4)
        starting_balance = float(item["starting_balance"])
        closed_pnl = float(item["closed_pnl"])
        invested_margin = float(item["invested_margin"])
        computed_cash_balance = round(starting_balance + closed_pnl - invested_margin, 4)
        item["cash_balance"] = computed_cash_balance
        item["invested_margin"] = round(invested_margin, 4)
        item["equity_without_unrealized"] = round(computed_cash_balance + invested_margin, 4)
        item["unrealized_pnl"] = unrealized_pnl
        item["estimated_equity"] = round(float(item["equity_without_unrealized"]) + unrealized_pnl, 4)
        item["estimated_total_pnl"] = round(closed_pnl + unrealized_pnl, 4)
        item["pnl_accumulated"] = round(closed_pnl, 4)
        item["closed_pnl"] = round(closed_pnl, 4)
        closed_wins = int(item.get("closed_wins") or 0)
        closed_losses = int(item.get("closed_losses") or 0)
        closed_resolved = closed_wins + closed_losses
        item["closed_wins"] = closed_wins
        item["closed_losses"] = closed_losses
        item["closed_win_rate"] = round(closed_wins / closed_resolved, 4) if closed_resolved else None
        item["contest_operations"] = operations_by_user.get(int(item["user_id"]), [])
        item["avatar_url"] = avatar_url(
            {
                "id": item["user_id"],
                "avatar_mime_type": item.get("avatar_mime_type"),
                "avatar_updated_at": item.get("avatar_updated_at"),
            }
        )
        db.execute(
            "UPDATE contest_entries SET cash_balance = ? WHERE season_id = ? AND user_id = ?",
            (computed_cash_balance, season_id, item["user_id"]),
        )
        leaderboard.append(item)
    leaderboard.sort(key=lambda item: item["estimated_equity"], reverse=True)
    for index, item in enumerate(leaderboard, start=1):
        item["rank"] = index
    return leaderboard


def record_wallet_event(
    db,
    user_id: int,
    mode: str,
    event_type: str,
    amount: float,
    balance_after: float | None = None,
    operation_id: int | None = None,
    contest_season_id: int | None = None,
    note: str | None = None,
) -> None:
    db.execute(
        """
        INSERT INTO wallet_events (
            user_id, mode, event_type, amount, balance_after, operation_id, contest_season_id, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, mode, event_type, amount, balance_after, operation_id, contest_season_id, note),
    )
