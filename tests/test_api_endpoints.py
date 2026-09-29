"""Integration tests for the FastAPI application (dry-run mode).

These tests use httpx.AsyncClient against the FastAPI TestClient, with
DRY_RUN=true so no real Google API calls are made.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app, lifespan


@pytest.fixture
async def client():
    """Create a test client with lifespan events properly handled."""
    async with lifespan(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.mark.asyncio
async def test_healthz(client: AsyncClient):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["dry_run"] is True


@pytest.mark.asyncio
async def test_auth_status_unauthenticated(client: AsyncClient):
    resp = await client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is False


@pytest.mark.asyncio
async def test_auth_login_redirects(client: AsyncClient):
    resp = await client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 302
    assert "accounts.google.com" in resp.headers["location"]


@pytest.mark.asyncio
async def test_auth_callback_missing_code(client: AsyncClient):
    resp = await client.get("/auth/callback")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_sites_requires_auth(client: AsyncClient):
    resp = await client.get("/api/sites")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_searchanalytics_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/searchanalytics/query",
        json={
            "siteUrl": "https://example.com/",
            "startDate": "2026-06-01",
            "endDate": "2026-06-30",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_sitemaps_requires_auth(client: AsyncClient):
    resp = await client.get("/api/sitemaps?siteUrl=https://example.com/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_kpi_requires_auth(client: AsyncClient):
    resp = await client.get(
        "/api/kpi?siteUrl=https://example.com/&startDate=2026-06-01&endDate=2026-06-30"
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_robots_txt_requires_auth(client: AsyncClient):
    resp = await client.get("/api/robots-txt?siteUrl=https://example.com/")
    assert resp.status_code == 401


def test_analytics_cache_hash_includes_all_query_parameters():
    from app.db.repository import _make_query_hash

    base = _make_query_hash("2026-01-01", "2026-01-31", ["query"], 50)
    filtered = _make_query_hash(
        "2026-01-01",
        "2026-01-31",
        ["query"],
        50,
        [{"groupType": "and", "filters": [{"dimension": "country", "expression": "KOR"}]}],
    )
    final_data = _make_query_hash(
        "2026-01-01", "2026-01-31", ["query"], 50, data_state="final"
    )

    assert base != filtered
    assert base != final_data


@pytest.mark.asyncio
async def test_full_auth_flow_dry_run(client: AsyncClient):
    """Simulate a complete OAuth flow using dry-run mode.

    Since we can't actually call Google, we manually create a session
    and verify the API endpoints work.
    """
    import time
    import uuid

    from app.auth.token_store import TokenRecord, token_store
    from app.core.session import sign_session

    # Create a fake authenticated session
    session_id = uuid.uuid4().hex
    record = TokenRecord(
        session_id=session_id,
        user_id="test-user",
        email="test@example.com",
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        access_token_expires_at=time.time() + 3600,
    )
    record.access_token = "ya29.fake-token"
    record.refresh_token = "1//fake-refresh"
    await token_store.save(record)

    # Set the session cookie
    cookie_value = sign_session(session_id)
    client.cookies.set("gsc_session", cookie_value)

    # ── /auth/status ────────────────────────────────────────────
    resp = await client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["authenticated"] is True
    assert data["email"] == "test@example.com"

    # ── /api/sites ─────────────────────────────────────────────
    resp = await client.get("/api/sites")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["siteEntry"]) == 3
    assert data["siteEntry"][0]["siteUrl"] == "https://example.com/"

    # ── /api/searchanalytics/query ─────────────────────────────
    resp = await client.post(
        "/api/searchanalytics/query",
        json={
            "siteUrl": "https://example.com/",
            "startDate": "2026-06-01",
            "endDate": "2026-06-30",
            "dimensions": ["query", "date"],
            "rowLimit": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "rows" in data
    assert len(data["rows"]) <= 10

    # ── /api/sitemaps ──────────────────────────────────────────
    resp = await client.get("/api/sitemaps?siteUrl=https://example.com/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sitemap"]) == 1
    assert data["sitemap"][0]["path"] == "https://example.com/sitemap.xml"

    # ── /api/urlinspection/index ───────────────────────────────
    resp = await client.post(
        "/api/urlinspection/index",
        json={
            "siteUrl": "https://example.com/",
            "inspectionUrl": "https://example.com/",
            "languageCode": "ko",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["inspectionResult"]["indexStatusResult"]["verdict"] == "PASS"

    # ── /api/kpi ───────────────────────────────────────────────
    resp = await client.get(
        "/api/kpi?siteUrl=https://example.com/&startDate=2026-06-01&endDate=2026-06-30"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "totalClicks" in data
    assert "totalImpressions" in data

    # ── /auth/logout ───────────────────────────────────────────
    resp = await client.post("/auth/logout")
    assert resp.status_code == 200

    # After logout, API should return 401
    resp = await client.get("/api/sites")
    assert resp.status_code == 401

    # Cleanup
    await token_store.delete(session_id)


@pytest.mark.asyncio
async def test_sqlite_cache_sites(client: AsyncClient):
    """Verify that sites are cached in SQLite and returned on subsequent calls."""
    import time
    import uuid

    from app.auth.token_store import TokenRecord, token_store
    from app.core.session import sign_session
    from app.db.repository import upsert_user, upsert_project, list_projects_by_user

    # Create a fake authenticated session
    session_id = uuid.uuid4().hex
    user_id = "cache-test-user"
    record = TokenRecord(
        session_id=session_id,
        user_id=user_id,
        email="cache@example.com",
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        access_token_expires_at=time.time() + 3600,
    )
    record.access_token = "ya29.fake-token"
    record.refresh_token = "1//fake-refresh"
    await token_store.save(record)

    # Pre-populate the SQLite cache with a user and project
    await upsert_user(user_id, "cache@example.com")
    await upsert_project(user_id, "https://cached-site.com/", "siteOwner")

    # Verify the project is in the DB
    projects = await list_projects_by_user(user_id)
    assert len(projects) == 1
    assert projects[0]["siteUrl"] == "https://cached-site.com/"

    # Set the session cookie
    cookie_value = sign_session(session_id)
    client.cookies.set("gsc_session", cookie_value)

    # ── /api/sites should return the cached project ──────────────
    resp = await client.get("/api/sites")
    assert resp.status_code == 200
    data = resp.json()
    # In dry-run mode with a cached user, the cached projects take precedence
    assert len(data["siteEntry"]) >= 1
    urls = [s["siteUrl"] for s in data["siteEntry"]]
    assert "https://cached-site.com/" in urls

    # Cleanup
    await token_store.delete(session_id)


@pytest.mark.asyncio
async def test_sqlite_cache_analytics(client: AsyncClient):
    """Verify that analytics queries are cached and reused."""
    import time
    import uuid

    from app.auth.token_store import TokenRecord, token_store
    from app.core.session import sign_session
    from app.db.repository import upsert_user, upsert_project, set_cached_analytics

    # Create a fake authenticated session
    session_id = uuid.uuid4().hex
    user_id = "analytics-cache-user"
    record = TokenRecord(
        session_id=session_id,
        user_id=user_id,
        email="analytics@example.com",
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        access_token_expires_at=time.time() + 3600,
    )
    record.access_token = "ya29.fake-token"
    record.refresh_token = "1//fake-refresh"
    await token_store.save(record)

    # Pre-populate cache
    await upsert_user(user_id, "analytics@example.com")
    project_id = await upsert_project(user_id, "https://example.com/", "siteOwner")

    cached_data = {
        "rows": [
            {"keys": ["cached-query"], "clicks": 999, "impressions": 9999, "ctr": 0.1, "position": 1.0}
        ],
        "responseAggregationType": "auto",
    }
    await set_cached_analytics(
        project_id, "2026-06-01", "2026-06-30", ["query"], 10, cached_data
    )

    # Set the session cookie
    cookie_value = sign_session(session_id)
    client.cookies.set("gsc_session", cookie_value)

    # ── /api/searchanalytics/query should return cached data ────
    resp = await client.post(
        "/api/searchanalytics/query",
        json={
            "siteUrl": "https://example.com/",
            "startDate": "2026-06-01",
            "endDate": "2026-06-30",
            "dimensions": ["query"],
            "rowLimit": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 1
    assert data["rows"][0]["clicks"] == 999
    assert data["rows"][0]["keys"] == ["cached-query"]

    # Cleanup
    await token_store.delete(session_id)
