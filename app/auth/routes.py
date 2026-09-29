"""Auth routes: /auth/login, /auth/callback, /auth/status, /auth/logout."""

from __future__ import annotations

import time
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse

from app.auth.oauth import make_authorization_url, exchange_code
from app.auth.state import generate_state, verify_and_consume
from app.auth.token_store import TokenRecord, token_store
from app.config import settings
from app.core.session import sign_session, unsign_session

router = APIRouter(prefix="/auth", tags=["auth"])

# Use secure cookies in production (HTTPS), non-secure in dev (HTTP)
_COOKIE_SECURE = not settings.dry_run


# ── /auth/login ────────────────────────────────────────────────────────

@router.get("/login")
async def login(request: Request):
    """Initiate Google OAuth 2.0 flow.  Redirects the browser to Google."""
    state = await generate_state()

    # Store state in a signed cookie so we can verify it in the callback
    # without needing a server-side session store.
    authorization_url = make_authorization_url(state)

    response = RedirectResponse(url=authorization_url, status_code=302)
    response.set_cookie(
        key="oauth_state",
        value=sign_session(state),
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=600,  # 10 min
        path="/auth/callback",
    )
    return response


# ── /auth/callback ─────────────────────────────────────────────────────

@router.get("/callback")
async def callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """Handle the Google OAuth callback.

    Exchanges the authorization code for tokens, encrypts them, and sets a
    session cookie before redirecting to the frontend.
    """
    # ── Handle user-denied / error from Google ────────────────────
    if error:
        return RedirectResponse(url=f"/login?error={error}", status_code=302)

    # ── CSRF check (DB-based, works across Vite→backend redirect) ──
    if not state:
        raise HTTPException(status_code=400, detail="Missing state parameter.")
    if not await verify_and_consume(state):
        raise HTTPException(status_code=400, detail="Invalid or expired state.")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code.")

    # ── Exchange code for tokens ──────────────────────────────────
    try:
        tokens = exchange_code(code, state=state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {exc}")

    # ── Fetch user info (email, user_id) ──────────────────────────
    email = ""
    user_id = ""
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                email = data.get("email", "")
                user_id = data.get("id", "")
    except Exception:
        pass  # non-critical

    # ── Parse expiry ──────────────────────────────────────────────
    expires_in = tokens.get("expires_in", 3600)
    try:
        expires_at = time.time() + float(expires_in) - 60
    except (ValueError, TypeError):
        expires_at = time.time() + 3599

    # ── Persist encrypted token record ────────────────────────────
    session_id = uuid.uuid4().hex
    record = TokenRecord(
        session_id=session_id,
        user_id=user_id,
        email=email,
        scopes=tokens.get("scope", "").split(),
        access_token_expires_at=expires_at,
        created_at=time.time(),
        updated_at=time.time(),
    )
    record.access_token = tokens["access_token"]
    record.refresh_token = tokens.get("refresh_token", "")
    await token_store.save(record)

    # ── Fetch & cache sites from GSC (best-effort) ────────────────
    if user_id:
        try:
            from app.api.searchconsole import SearchConsoleClient
            search_console_client = SearchConsoleClient(
                access_token=tokens["access_token"], user_id=user_id
            )
            await search_console_client.list_sites()  # this will populate the projects table
        except Exception:
            pass  # non-critical; sites will be fetched on first API call

    # ── Set session cookie & redirect to frontend ─────────────────
    # Dev: redirect to the Vite dev server. Prod: same origin ("/").
    frontend_url = settings.frontend_url
    response = RedirectResponse(url=frontend_url, status_code=302)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=sign_session(session_id),
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=settings.session_max_age,
        path="/",
    )
    response.delete_cookie("oauth_state", path="/auth/callback")
    return response


# ── /auth/status ───────────────────────────────────────────────────────

@router.get("/status")
async def auth_status(request: Request):
    """Return the current authentication status."""
    cookie = request.cookies.get(settings.session_cookie_name)
    if not cookie:
        return JSONResponse({"authenticated": False})

    session_id = unsign_session(cookie)
    if not session_id:
        return JSONResponse({"authenticated": False})

    record = await token_store.load(session_id)
    if not record:
        return JSONResponse({"authenticated": False})

    return JSONResponse(
        {
            "authenticated": True,
            "email": record.email,
            "scopes": record.scopes,
        }
    )


# ── /auth/logout ───────────────────────────────────────────────────────

@router.post("/logout")
async def logout(request: Request):
    """Clear the session and remove stored tokens."""
    cookie = request.cookies.get(settings.session_cookie_name)
    if cookie:
        session_id = unsign_session(cookie)
        if session_id:
            await token_store.delete(session_id)

    response = JSONResponse({"ok": True})
    response.delete_cookie(settings.session_cookie_name, path="/")
    return response
