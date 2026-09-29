"""FastAPI dependency injection.

Provides:
- ``current_session`` → TokenRecord (authenticated user)
- ``gsc_client`` → SearchConsoleClient (ready-to-use API client)
"""

from __future__ import annotations

import time

from fastapi import Depends, Request

from app.api.searchconsole import SearchConsoleClient
from app.auth.oauth import refresh_access_token
from app.auth.token_store import TokenRecord, token_store
from app.config import settings
from app.core.errors import unauthenticated, token_refresh_failed
from app.core.session import unsign_session


async def current_session(request: Request) -> TokenRecord:
    """Extract and validate the session from the request cookie.

    Raises ``401 UNAUTHENTICATED`` if the session is missing or invalid.
    """
    cookie = request.cookies.get(settings.session_cookie_name)
    if not cookie:
        raise unauthenticated()

    session_id = unsign_session(cookie)
    if not session_id:
        raise unauthenticated()

    record = await token_store.load(session_id)
    if not record:
        raise unauthenticated()

    return record


async def gsc_client(session: TokenRecord = Depends(current_session)) -> SearchConsoleClient:
    """Return a SearchConsoleClient with a valid (possibly refreshed) access token.

    Automatically refreshes the token if it's about to expire.
    The client carries the user_id so that results can be cached in the DB.
    """
    # Check if token needs refresh
    if session.is_access_token_expired(margin_seconds=120):
        try:
            new_tokens = refresh_access_token(session.refresh_token)
            session.access_token = new_tokens["access_token"]
            # Keep existing refresh token if Google didn't send a new one
            if new_tokens.get("refresh_token"):
                session.refresh_token = new_tokens["refresh_token"]
            # Update expiry
            expires_in = new_tokens.get("expires_in", 3600)
            try:
                session.access_token_expires_at = time.time() + float(expires_in) - 60
            except (ValueError, TypeError):
                session.access_token_expires_at = time.time() + 3599
            await token_store.save(session)
        except Exception:
            raise token_refresh_failed()

    return SearchConsoleClient(access_token=session.access_token, user_id=session.user_id)
