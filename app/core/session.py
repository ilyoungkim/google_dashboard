"""Signed-cookie session helpers using itsdangerous."""

from __future__ import annotations

from itsdangerous import URLSafeTimedSerializer

from app.config import settings


def _get_serializer() -> URLSafeTimedSerializer:
    key = settings.session_secret_key
    if not key:
        raise RuntimeError(
            "SESSION_SECRET_KEY is not set. "
            "Run 'python scripts/gen_key.py' to generate one."
        )
    return URLSafeTimedSerializer(key)


def sign_session(session_id: str) -> str:
    """Create a signed, timestamped cookie value for *session_id*."""
    return _get_serializer().dumps(session_id)


def unsign_session(cookie_value: str, max_age: int | None = None) -> str | None:
    """Verify and return the session_id from a signed cookie value.

    Returns ``None`` when the signature is invalid or the cookie has expired.
    """
    if max_age is None:
        max_age = settings.session_max_age
    try:
        return _get_serializer().loads(cookie_value, max_age=max_age)
    except Exception:
        return None
