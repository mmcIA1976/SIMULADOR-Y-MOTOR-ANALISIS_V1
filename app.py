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
from db import connect, init_db, row_to_dict
from learning_engine import apply_learning_modifier
from security import create_token, hash_password, read_token, verify_password


APP_DIR = Path(__file__).resolve().parent
AVATAR_DIR = APP_DIR / "data" / "avatars"
SESSION_COOKIE = "trading_trainer_session"
MAX_AVATAR_BYTES = 1_000_000
ONE_MINUTE_MS = 60_000
MAX_EXIT_KLINE_PAGES = 5
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
    migrate_file_avatars_to_database()
    finalize_due_observations()
    refresh_learning_conclusions()
    reconcile_all_user_cash_balances()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")


@app.get("/static/{asset_name}")
def static_asset(asset_name: str) -> FileResponse:
    allowed_assets = {"app.js", "styles.css"}
    if asset_name not in allowed_assets:
        raise HTTPException(status_code=404, detail="Asset no encontrado")
    return FileResponse(APP_DIR / asset_name)


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
        entry = get_contest_entry(db, int(user["id"]), int(season["id"]))
        portfolio = calculate_portfolio_from_db(db, int(user["id"]))
        leaderboard = contest_leaderboard(db, int(season["id"]))
        if entry:
            apply_contest_unrealized_to_portfolio(db, portfolio["contest"], int(user["id"]), int(season["id"]))
    return {
        "season": season,
        "entry": entry,
        "participating": entry is not None,
        "portfolio": portfolio["contest"],
        "leaderboard": leaderboard,
    }


@app.post("/api/contest/join")
def contest_join(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    with connect() as db:
        season = ensure_current_contest_season(db)
        entry = ensure_contest_entry(db, int(user["id"]), int(season["id"]))
        portfolio = sync_user_cash_balance(db, int(user["id"]))
        leaderboard = contest_leaderboard(db, int(season["id"]))
        apply_contest_unrealized_to_portfolio(db, portfolio["contest"], int(user["id"]), int(season["id"]))
    return {
        "season": season,
        "entry": entry,
        "participating": True,
        "portfolio": portfolio["contest"],
        "leaderboard": leaderboard,
    }


@app.get("/api/price")
def price(
    symbol: str = "BTCUSDT",
    record: bool = True,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict:
    symbol = symbol.upper()
    value = market_data.get_price(symbol)
    operation_ids: list[int] = []
    closed_operations: list[dict] = []
    user = None
    if session_token:
        try:
            user = current_user(session_token)
        except HTTPException:
            user = None
    with connect() as db:
        finalize_due_observations(db)
        refresh_learning_conclusions(db)
        if record:
            db.execute(
                "INSERT INTO price_ticks (operation_id, symbol, price, source) VALUES (?, ?, ?, ?)",
                (None, symbol, value, "binance"),
            )
        closed_by_trigger = close_triggered_open_operations(db, symbol, value, int(user["id"])) if user else {}
        if user:
            closed_operations.extend(
                operation for operation in closed_by_trigger.values() if operation.get("user_id") == user["id"]
            )
            rows = db.execute(
                """
                SELECT * FROM operations
                WHERE user_id = ?
                  AND symbol = ?
                  AND (status = 'OPEN' OR observation_status = 'OBSERVING')
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
                        (operation_id, symbol, value, "binance"),
                    )
                if operation_id in closed_by_trigger:
                    closed_operations.append(closed_by_trigger[operation_id])
    return {
        "symbol": symbol,
        "price": value,
        "operation_ids": operation_ids,
        "closed_operations": closed_operations,
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
        "source": "binance_spot_klines_1m",
        "points": points,
    }


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
        db.execute(
            """
            UPDATE operations
            SET status = 'CLOSED', closed_at = CURRENT_TIMESTAMP, close_price = ?,
                close_reason = ?, final_pnl = ?, observation_status = 'PLAN_EXECUTED',
                observation_until = NULL, closing_note = ?, learning_outcome = NULL,
                learning_summary = NULL, exit_evidence_json = ?
            WHERE id = ?
            """,
            (
                close_price,
                reason,
                pnl,
                f"Cierre automatico por cruce detectado en vela {trigger_time}.",
                json.dumps(exit_evidence, ensure_ascii=True),
                operation["id"],
            ),
        )
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
                "binance_1m_exit_window",
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
            r.confidence AS recommendation_confidence
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


def build_learning_conclusion(operation: dict) -> dict:
    pnl = float(operation["final_pnl"] or 0)
    side = str(operation["side"]).upper()
    symbol = str(operation["symbol"]).replace("USDT", "/USDT")
    close_reason = operation.get("close_reason")
    observation_status = operation.get("observation_status")
    observation_summary = operation.get("observation_summary")
    pattern_text = build_learning_pattern_text(operation)

    if close_reason == "take_profit":
        return {
            "outcome": "plan_success",
            "summary": (
                f"Aprendizaje: el plan de {symbol} en {side} funciono y alcanzo TAKE PROFIT. "
                f"Resultado: {pnl:.2f} USDT. Esta operacion refuerza las condiciones del analisis previo como caso ganador. "
                f"{pattern_text}"
            ),
        }
    if close_reason == "stop_loss":
        return {
            "outcome": "plan_failure",
            "summary": (
                f"Aprendizaje: el plan de {symbol} en {side} fallo y alcanzo STOP LOSS. "
                f"Resultado: {pnl:.2f} USDT. Esta operacion debe alimentar los patrones de riesgo que anticiparon o no anticiparon el fallo. "
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
    pieces = [
        f"horizonte {operation.get('time_horizon') or snapshot.get('time_horizon') or 'sin definir'}",
        f"rating tecnico {technical.get('label', 'no disponible')} {technical.get('score', '--')}/100",
        f"regimen {str(regime.get('name', 'no disponible')).replace('_', ' ')}",
        f"direccion {scores.get('direction_score', '--')}/100",
        f"confianza {scores.get('confidence_score', '--')}/100",
        f"derivados {timeframes.get('derivatives_period', 'n/d')}",
        f"niveles {timeframes.get('levels', 'n/d')}",
    ]
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
                "binance_spot_1m_kline",
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
            "binance_spot_ticker",
            "precio_actual",
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
                    "binance_spot_agg_trade",
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


def iso_from_ms(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).isoformat()


def operation_start_time_ms(operation: dict) -> int:
    raw_started_at = operation.get("started_at") or operation.get("created_at")
    started_at = datetime.fromisoformat(str(raw_started_at).replace(" ", "T"))
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return int(started_at.timestamp() * 1000)


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
    proposal = TradeProposal(
        symbol=payload.symbol.upper(),
        side=payload.side.lower(),
        time_horizon=payload.time_horizon,
        entry=payload.entry,
        margin=payload.margin,
        leverage=payload.leverage,
        stop_loss=payload.stop_loss,
        take_profit=payload.take_profit,
    )
    if proposal.side not in {"long", "short"}:
        raise HTTPException(status_code=400, detail="Direccion no valida")
    if proposal.time_horizon not in VALID_TIME_HORIZONS:
        raise HTTPException(status_code=400, detail="Marco temporal no valido")
    result = apply_learning_modifier(user["id"], proposal, analyze_trade(proposal))
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
    if side not in {"long", "short"}:
        raise HTTPException(status_code=400, detail="Direccion no valida")
    if payload.time_horizon not in VALID_TIME_HORIZONS:
        raise HTTPException(status_code=400, detail="Marco temporal no valido")
    if mode not in VALID_OPERATION_MODES:
        raise HTTPException(status_code=400, detail="Modo de operacion no valido")
    with connect() as db:
        season_id = None
        if mode == "contest":
            season = ensure_current_contest_season(db)
            season_id = int(season["id"])
            if get_contest_entry(db, int(user["id"]), season_id) is None:
                raise HTTPException(status_code=409, detail="Primero inicia tu participacion en el concurso mensual")
        portfolio = sync_user_cash_balance(db, int(user["id"]))
        open_count = db.execute(
            "SELECT COUNT(*) AS count FROM operations WHERE user_id = ? AND mode = ? AND status = 'OPEN'",
            (user["id"], mode),
        ).fetchone()["count"]
        if open_count >= 2:
            raise HTTPException(status_code=409, detail="Maximo 2 operaciones abiertas por usuario en este modo")
        cash_balance = float(portfolio[mode]["cash_balance"])
        if payload.margin > cash_balance:
            raise HTTPException(status_code=400, detail="Saldo ficticio insuficiente para bloquear ese margen")
        if payload.recommendation_id is not None:
            recommendation = db.execute(
                """
                SELECT id FROM recommendations
                WHERE id = ? AND user_id = ? AND operation_id IS NULL
                """,
                (payload.recommendation_id, user["id"]),
            ).fetchone()
            if recommendation is None:
                raise HTTPException(status_code=400, detail="Analisis previo no valido para esta operacion")
        cursor = db.execute(
            """
            INSERT INTO operations (
                user_id, symbol, side, time_horizon, entry, margin, leverage, stop_loss, take_profit,
                status, started_at, mode, contest_season_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN', CURRENT_TIMESTAMP, ?, ?)
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
                mode,
                season_id,
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
            note="Margen bloqueado al iniciar operacion simulada.",
        )
    return {"id": operation_id, "status": "OPEN"}


@app.get("/api/operations")
def list_operations(session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = current_user(session_token)
    with connect() as db:
        finalize_due_observations(db)
        refresh_learning_conclusions(db)
        rows = db.execute(
            "SELECT * FROM operations WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
        operations = [row_to_dict(row) for row in rows]
        for operation in operations:
            ensure_closed_exit_window_ticks(db, operation)
            operation["exit_evidence"] = parse_exit_evidence(operation.get("exit_evidence_json"))
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

            # Batch fetch last 240 ticks per operation (1 query instead of N).
            tick_rows = db.execute(
                f"""
                SELECT operation_id, price, source, captured_at
                FROM (
                    SELECT operation_id, price, source, captured_at,
                           ROW_NUMBER() OVER (PARTITION BY operation_id ORDER BY captured_at DESC) AS rn
                    FROM price_ticks
                    WHERE operation_id IN ({placeholders})
                ) ranked
                WHERE rn <= 240
                ORDER BY operation_id, captured_at ASC
                """,
                tuple(op_ids),
            ).fetchall()
            ticks_by_op: dict = {}
            for t in tick_rows:
                td = row_to_dict(t)
                ticks_by_op.setdefault(td["operation_id"], []).append({
                    "price": td["price"],
                    "source": td["source"],
                    "captured_at": td["captured_at"],
                })

            for op in operations:
                rec = rec_by_op.get(op["id"])
                op["recommendation"] = format_recommendation(rec, op) if rec else None
                op["ticks"] = ticks_by_op.get(op["id"], [])
    return {"operations": operations}


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
                "binance_spot_1m_kline",
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
        db.execute(
            """
            UPDATE operations
            SET status = 'CLOSED', closed_at = CURRENT_TIMESTAMP, close_price = ?, close_reason = ?,
                final_pnl = ?, observation_until = ?, observation_status = 'OBSERVING',
                post_emotion = ?, plan_followed = ?, closing_note = ?,
                learning_outcome = NULL, learning_summary = NULL
            WHERE id = ? AND user_id = ?
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


def sync_user_cash_balance(db, user_id: int) -> dict:
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
    open_rows = db.execute(
        f"SELECT margin FROM operations WHERE user_id = ? AND mode = ? AND status = 'OPEN'{season_clause}",
        params,
    ).fetchall()
    closed_pnl = db.execute(
        f"SELECT COALESCE(SUM(final_pnl), 0) AS pnl FROM operations WHERE user_id = ? AND mode = ? AND status = 'CLOSED'{season_clause}",
        params,
    ).fetchone()["pnl"]
    invested_margin = sum(float(row["margin"]) for row in open_rows)
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
        "open_operations": len(open_rows),
        "max_open_operations": 2,
    }


def ensure_current_contest_season(db) -> dict:
    now = datetime.now(timezone.utc)
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
    portfolio["total_pnl"] = round(float(portfolio.get("closed_pnl") or 0) + unrealized_pnl, 4)
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
            COALESCE(SUM(CASE WHEN o.status = 'OPEN' THEN o.margin ELSE 0 END), 0) AS invested_margin,
            COALESCE(SUM(CASE WHEN o.status = 'CLOSED' THEN o.final_pnl ELSE 0 END), 0) AS closed_pnl,
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
    prices = live_prices_for_operations(open_operations)
    unrealized_by_user: dict[int, float] = {}
    for operation in open_operations:
        symbol = operation["symbol"]
        if symbol not in prices:
            continue
        user_id = int(operation["user_id"])
        unrealized_by_user[user_id] = unrealized_by_user.get(user_id, 0) + approximate_pnl(operation, prices[symbol])

    leaderboard = []
    for row in rows:
        item = row_to_dict(row)
        unrealized_pnl = round(unrealized_by_user.get(int(item["user_id"]), 0), 4)
        item["equity_without_unrealized"] = round(float(item["cash_balance"]) + float(item["invested_margin"]), 4)
        item["unrealized_pnl"] = unrealized_pnl
        item["estimated_equity"] = round(float(item["equity_without_unrealized"]) + unrealized_pnl, 4)
        item["pnl_accumulated"] = round(float(item["closed_pnl"]) + unrealized_pnl, 4)
        item["closed_pnl"] = round(float(item["closed_pnl"]), 4)
        item["avatar_url"] = avatar_url(
            {
                "id": item["user_id"],
                "avatar_mime_type": item.get("avatar_mime_type"),
                "avatar_updated_at": item.get("avatar_updated_at"),
            }
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
