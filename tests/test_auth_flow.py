"""Tests for the OAuth flow (state, URL generation, token exchange mock)."""

from __future__ import annotations

import pytest

from app.auth.state import generate_state, verify_and_consume


@pytest.mark.asyncio
async def test_state_generation_and_verification():
    state = await generate_state()
    assert len(state) > 0
    assert await verify_and_consume(state) is True


@pytest.mark.asyncio
async def test_state_consumed_only_once():
    state = await generate_state()
    assert await verify_and_consume(state) is True
    assert await verify_and_consume(state) is False  # already consumed


@pytest.mark.asyncio
async def test_state_invalid():
    assert await verify_and_consume("nonexistent") is False


def test_authorization_url_contains_required_params():
    from app.auth.oauth import make_authorization_url

    url = make_authorization_url("test-state-123")
    assert "accounts.google.com/o/oauth2/v2/auth" in url
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=test-state-123" in url
    assert "response_type=code" in url
