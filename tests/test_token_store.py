"""Tests for the token store (encrypt/decrypt, CRUD).

TokenStore is now DB-backed, so tests use the shared SQLite connection
that is set up by conftest.py (tmp_path + fresh DB per test).
"""

from __future__ import annotations

import time

import pytest

from app.auth.token_store import TokenRecord, TokenStore


@pytest.mark.asyncio
async def test_save_and_load():
    store = TokenStore()
    record = TokenRecord(
        session_id="abc123",
        user_id="user-1",
        email="test@example.com",
        scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        access_token_expires_at=time.time() + 3600,
    )
    record.access_token = "ya29.fake-access-token"
    record.refresh_token = "1//fake-refresh-token"

    await store.save(record)

    loaded = await store.load("abc123")
    assert loaded is not None
    assert loaded.session_id == "abc123"
    assert loaded.email == "test@example.com"
    assert loaded.access_token == "ya29.fake-access-token"
    assert loaded.refresh_token == "1//fake-refresh-token"


@pytest.mark.asyncio
async def test_load_missing():
    store = TokenStore()
    assert await store.load("nonexistent") is None


@pytest.mark.asyncio
async def test_delete():
    store = TokenStore()
    record = TokenRecord(session_id="del-me")
    record.access_token = "x"
    record.refresh_token = "y"
    await store.save(record)

    await store.delete("del-me")
    assert await store.load("del-me") is None


@pytest.mark.asyncio
async def test_list_sessions():
    store = TokenStore()
    for sid in ["a", "b", "c"]:
        r = TokenRecord(session_id=sid)
        r.access_token = "x"
        r.refresh_token = "y"
        await store.save(r)

    sessions = await store.list_sessions()
    assert sorted(sessions) == ["a", "b", "c"]


def test_token_expiry_detection():
    record = TokenRecord(session_id="x")
    record.access_token_expires_at = time.time() + 30  # expires in 30s
    assert record.is_access_token_expired(margin_seconds=60)  # within margin
    assert not record.is_access_token_expired(margin_seconds=10)  # outside margin
