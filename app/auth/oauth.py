"""OAuth 2.0 flow helpers for Google Identity."""

from __future__ import annotations

import time
from typing import Optional

from google_auth_oauthlib.flow import Flow

from app.config import settings

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# ── In-memory store of Flow instances keyed by state ──────────────
# The Flow object holds the PKCE code_verifier generated during the
# authorization step, which must be replayed when exchanging the code.
# Entries expire after 10 minutes to bound memory usage.
_FLOW_STORE: dict[str, tuple[Flow, float]] = {}
_FLOW_TTL = 600  # seconds


def _get_client_config() -> dict:
    """Return OAuth client config (lazy-loaded to avoid stale settings)."""
    return {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def make_flow(redirect_uri: str | None = None) -> Flow:
    """Build a Google OAuth Flow instance.

    *redirect_uri* overrides the configured default (useful for testing).
    """
    return Flow.from_client_config(
        client_config=_get_client_config(),
        scopes=SCOPES,
        redirect_uri=redirect_uri or settings.google_redirect_uri,
    )


def _purge_expired() -> None:
    """Remove expired Flow entries."""
    now = time.time()
    expired = [k for k, (_, ts) in _FLOW_STORE.items() if now - ts > _FLOW_TTL]
    for k in expired:
        _FLOW_STORE.pop(k, None)


def make_authorization_url(state: str, redirect_uri: str | None = None) -> str:
    """Return the Google OAuth authorization URL for the given *state*.

    The Flow instance (which holds the PKCE code_verifier) is retained so
    that :func:`exchange_code` can replay it during the token exchange.
    """
    flow = make_flow(redirect_uri)
    url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    _purge_expired()
    _FLOW_STORE[state] = (flow, time.time())
    return url


def exchange_code(code: str, state: str, redirect_uri: str | None = None) -> dict:
    """Exchange an authorization *code* for tokens.

    The Flow stored under *state* is reused so the PKCE code_verifier
    matches the code_challenge sent during authorization.  Falls back to
    a fresh Flow when no stored entry is found (non-PKCE / tests).

    Returns a dict with keys: access_token, refresh_token, expires_in,
    token_type, scope, id_token (optional).
    """
    _purge_expired()
    flow: Optional[Flow] = None
    if state in _FLOW_STORE:
        flow, _ = _FLOW_STORE.pop(state)
    if flow is None:
        flow = make_flow(redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    # Compute expires_in as seconds from now (consistent numeric value)
    expires_in = 3600
    if creds.expiry:
        try:
            import datetime
            expires_in = int((creds.expiry - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
        except Exception:
            pass
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expires_in": expires_in,
        "token_type": getattr(creds, "token_type", None) or "Bearer",
        "scope": " ".join(creds.scopes) if creds.scopes else "",
        "id_token": getattr(creds, "id_token", None),
    }


def refresh_access_token(refresh_token: str) -> dict:
    """Use a *refresh_token* to obtain a new access token.

    Returns the same shape as :func:`exchange_code`.
    """
    import google.oauth2.credentials

    creds = google.oauth2.credentials.Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
    )
    from google.auth.transport.requests import Request

    creds.refresh(Request())
    # Compute expires_in as seconds from now (consistent numeric value)
    expires_in = 3600
    if creds.expiry:
        try:
            import datetime
            expires_in = int((creds.expiry - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
        except Exception:
            pass
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token or refresh_token,
        "expires_in": expires_in,
        "token_type": getattr(creds, "token_type", None) or "Bearer",
        "scope": " ".join(creds.scopes) if creds.scopes else "",
    }
