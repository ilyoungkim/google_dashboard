"""CSRF state generation and verification for OAuth flows.

State tokens are persisted in the ``oauth_states`` DB table so that they
work correctly across multiple worker processes (unlike an in-memory dict).
Each state has a 10-minute TTL and is consumed (deleted) on first verification.
"""

from __future__ import annotations

import secrets
import time

_TTL_SECONDS = 600  # 10 minutes


async def generate_state() -> str:
    """Create a new CSRF state token, persist it to the DB, and return it."""
    value = secrets.token_urlsafe(32)
    from app.db.database import get_db

    db = await get_db()
    await db.execute(
        "INSERT INTO oauth_states (state, created_at) VALUES (?, ?)",
        (value, time.time()),
    )
    await db.commit()
    return value


async def verify_and_consume(state: str) -> bool:
    """Verify *state* exists and hasn't expired, then remove it.

    Returns ``True`` if valid, ``False`` otherwise.
    """
    from app.db.database import get_db

    db = await get_db()
    result = await db.fetchone(
        "SELECT created_at FROM oauth_states WHERE state = ?",
        (state,),
    )
    if result is None:
        return False
    # Delete the state (one-time use)
    await db.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    await db.commit()
    # Check TTL
    if time.time() - result["created_at"] > _TTL_SECONDS:
        return False
    return True


async def cleanup_expired_states() -> int:
    """Remove expired states from the DB.  Returns the number of rows deleted."""
    from app.db.database import get_db

    db = await get_db()
    cutoff = time.time() - _TTL_SECONDS
    cursor = await db.execute("DELETE FROM oauth_states WHERE created_at < ?", (cutoff,))
    await db.commit()
    return cursor.rowcount if hasattr(cursor, "rowcount") else 0
