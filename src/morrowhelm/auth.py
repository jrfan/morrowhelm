from __future__ import annotations

import hashlib
import hmac
import time


def _digest(password: str) -> bytes:
    return hashlib.sha256(password.encode()).digest()


def create_session(password: str, max_age: int) -> str:
    expires = int(time.time()) + max_age
    payload = f"founder:{expires}"
    signature = hmac.new(_digest(password), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def valid_session(token: str | None, password: str) -> bool:
    if not token:
        return False
    try:
        user, expires, signature = token.split(":", 2)
        if user != "founder" or int(expires) < int(time.time()):
            return False
    except (ValueError, TypeError):
        return False
    payload = f"{user}:{expires}"
    expected = hmac.new(_digest(password), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
