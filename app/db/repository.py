"""Repository layer for database operations.

All functions are async and use the unified Database wrapper (MariaDB or SQLite).
SQL is written in **SQLite dialect** (``?`` placeholders, ``ON CONFLICT``).
The Database wrapper translates to MySQL when needed.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.db.database import get_db


# ═══════════════════════════════════════════════════════════════════════
# Users
# ═══════════════════════════════════════════════════════════════════════

async def upsert_user(user_id: str, email: str) -> None:
    """Insert or update a user record."""
    db = await get_db()
    await db.execute(
        "INSERT INTO users (user_id, email) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET email = excluded.email",
        (user_id, email),
    )
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════
# Sessions (OAuth token storage)
# ═══════════════════════════════════════════════════════════════════════

async def save_session(
    session_id: str,
    user_id: str,
    email: str,
    scopes: list[str],
    access_token_ciphertext: str,
    refresh_token_ciphertext: str,
    access_token_expires_at: float,
) -> None:
    """Insert or update a session record (token storage).

    Also upserts the user record so that the FK constraint is satisfied.
    """
    db = await get_db()
    # Ensure the user row exists first (FK prerequisite)
    await db.execute(
        "INSERT INTO users (user_id, email) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET email = excluded.email",
        (user_id, email),
    )
    now = time.time()
    await db.execute(
        "INSERT INTO sessions (session_id, user_id, email, scopes, "
        "access_token_ciphertext, refresh_token_ciphertext, access_token_expires_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET "
        "email = excluded.email, scopes = excluded.scopes, "
        "access_token_ciphertext = excluded.access_token_ciphertext, "
        "refresh_token_ciphertext = excluded.refresh_token_ciphertext, "
        "access_token_expires_at = excluded.access_token_expires_at, "
        "updated_at = excluded.updated_at",
        (
            session_id, user_id, email, json.dumps(scopes),
            access_token_ciphertext, refresh_token_ciphertext,
            access_token_expires_at, now, now,
        ),
    )
    await db.commit()


async def load_session(session_id: str) -> dict[str, Any] | None:
    """Load a session record by ID.  Returns None if not found."""
    db = await get_db()
    result = await db.fetchone(
        "SELECT session_id, user_id, email, scopes, "
        "access_token_ciphertext, refresh_token_ciphertext, access_token_expires_at, "
        "created_at, updated_at "
        "FROM sessions WHERE session_id = ?",
        (session_id,),
    )
    if result is None:
        return None
    result["scopes"] = json.loads(result["scopes"])
    return result


async def delete_session(session_id: str) -> None:
    """Delete a session record."""
    db = await get_db()
    await db.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    await db.commit()


async def list_sessions() -> list[str]:
    """Return all active session IDs."""
    db = await get_db()
    rows = await db.fetchall("SELECT session_id FROM sessions ORDER BY created_at")
    return [r["session_id"] for r in rows]


# ═══════════════════════════════════════════════════════════════════════
# Projects (user + site_url)
# ═══════════════════════════════════════════════════════════════════════

async def upsert_project(user_id: str, site_url: str, permission_level: str = "siteOwner") -> int:
    """Insert or update a project.  Returns the project's internal ID."""
    db = await get_db()
    await db.execute(
        "INSERT INTO projects (user_id, site_url, permission_level) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, site_url) DO UPDATE SET permission_level = excluded.permission_level",
        (user_id, site_url, permission_level),
    )
    await db.commit()
    result = await db.fetchone(
        "SELECT id FROM projects WHERE user_id = ? AND site_url = ?",
        (user_id, site_url),
    )
    return result["id"] if result else 0


async def list_projects_by_user(user_id: str) -> list[dict[str, Any]]:
    """Return all projects (sites) for a user."""
    db = await get_db()
    rows = await db.fetchall(
        "SELECT id, site_url, permission_level FROM projects WHERE user_id = ? ORDER BY created_at",
        (user_id,),
    )
    return [{"id": r["id"], "siteUrl": r["site_url"], "permissionLevel": r["permission_level"]} for r in rows]


async def get_project_id(user_id: str, site_url: str) -> int | None:
    """Get the internal project ID for a user+site combination."""
    db = await get_db()
    result = await db.fetchone(
        "SELECT id FROM projects WHERE user_id = ? AND site_url = ?",
        (user_id, site_url),
    )
    return result["id"] if result else None


# ═══════════════════════════════════════════════════════════════════════
# Analytics cache
# ═══════════════════════════════════════════════════════════════════════

def _make_query_hash(
    start_date: str,
    end_date: str,
    dimensions: list[str],
    row_limit: int,
    dimension_filter_groups: list[dict[str, Any]] | None = None,
    aggregation_type: str = "auto",
    data_state: str = "all",
) -> str:
    """Create a deterministic hash for an analytics query."""
    raw = json.dumps(
        {
            "start": start_date,
            "end": end_date,
            "dim": sorted(dimensions),
            "limit": row_limit,
            "filters": dimension_filter_groups or [],
            "aggregation": aggregation_type,
            "data_state": data_state,
        },
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_cached_analytics(
    project_id: int,
    start_date: str,
    end_date: str,
    dimensions: list[str],
    row_limit: int,
    dimension_filter_groups: list[dict[str, Any]] | None = None,
    aggregation_type: str = "auto",
    data_state: str = "all",
) -> dict[str, Any] | None:
    """Return cached analytics data if it exists and hasn't expired."""
    db = await get_db()
    query_hash = _make_query_hash(
        start_date,
        end_date,
        dimensions,
        row_limit,
        dimension_filter_groups,
        aggregation_type,
        data_state,
    )
    result = await db.fetchone(
        "SELECT data_json, expires_at FROM analytics_cache WHERE project_id = ? AND query_hash = ?",
        (project_id, query_hash),
    )
    if result is None:
        return None
    if time.time() > result["expires_at"]:
        return None  # expired
    return json.loads(result["data_json"])


async def set_cached_analytics(
    project_id: int,
    start_date: str,
    end_date: str,
    dimensions: list[str],
    row_limit: int,
    data: dict[str, Any],
    dimension_filter_groups: list[dict[str, Any]] | None = None,
    aggregation_type: str = "auto",
    data_state: str = "all",
    ttl_seconds: int = 6 * 3600,  # 6 hours default
) -> None:
    """Cache analytics data with a TTL."""
    db = await get_db()
    query_hash = _make_query_hash(
        start_date,
        end_date,
        dimensions,
        row_limit,
        dimension_filter_groups,
        aggregation_type,
        data_state,
    )
    now = time.time()
    await db.execute(
        "INSERT INTO analytics_cache (project_id, query_hash, data_json, fetched_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(project_id, query_hash) DO UPDATE SET "
        "data_json = excluded.data_json, fetched_at = excluded.fetched_at, expires_at = excluded.expires_at",
        (project_id, query_hash, json.dumps(data), now, now + ttl_seconds),
    )
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════
# Sitemaps cache
# ═══════════════════════════════════════════════════════════════════════

async def get_cached_sitemaps(project_id: int) -> dict[str, Any] | None:
    """Return cached sitemaps data if fresh."""
    db = await get_db()
    result = await db.fetchone(
        "SELECT data_json, expires_at FROM sitemaps_cache WHERE project_id = ?",
        (project_id,),
    )
    if result is None:
        return None
    if time.time() > result["expires_at"]:
        return None
    return json.loads(result["data_json"])


async def set_cached_sitemaps(
    project_id: int, data: dict[str, Any], ttl_seconds: int = 24 * 3600
) -> None:
    """Cache sitemaps data with a TTL (default 24h)."""
    db = await get_db()
    now = time.time()
    await db.execute(
        "INSERT INTO sitemaps_cache (project_id, data_json, fetched_at, expires_at) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(project_id) DO UPDATE SET "
        "data_json = excluded.data_json, fetched_at = excluded.fetched_at, expires_at = excluded.expires_at",
        (project_id, json.dumps(data), now, now + ttl_seconds),
    )
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════
# Bulk sync: refresh all projects for a user from GSC
# ═══════════════════════════════════════════════════════════════════════

async def sync_projects_from_gsc(user_id: str, sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sync the projects table with the latest sites from GSC.

    - Adds new sites
    - Updates permission levels for existing sites
    - Returns the full project list
    """
    for site in sites:
        await upsert_project(
            user_id=user_id,
            site_url=site.get("siteUrl", ""),
            permission_level=site.get("permissionLevel", "siteOwner"),
        )
    return await list_projects_by_user(user_id)
