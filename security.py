from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time


SECRET_KEY = os.environ.get("TRADING_TRAINER_SECRET", "dev-secret-change-before-production")
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 180_000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, salt, expected_hex = stored_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 180_000)
    return hmac.compare_digest(digest.hex(), expected_hex)


def _signature(payload: str) -> str:
    return hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_token(user_id: int) -> str:
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    payload = f"{user_id}:{expires_at}"
    signed = f"{payload}:{_signature(payload)}"
    return base64.urlsafe_b64encode(signed.encode("utf-8")).decode("ascii")


def read_token(token: str) -> int | None:
    try:
        signed = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        user_id_text, expires_text, signature = signed.split(":", 2)
    except Exception:
        return None
    payload = f"{user_id_text}:{expires_text}"
    if not hmac.compare_digest(_signature(payload), signature):
        return None
    if int(expires_text) < int(time.time()):
        return None
    return int(user_id_text)

