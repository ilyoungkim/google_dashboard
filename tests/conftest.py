"""Shared test fixtures and configuration."""

from __future__ import annotations

import os

import pytest


def pytest_configure(config):
    """Set environment variables before any test module is imported."""
    os.environ.setdefault("DRY_RUN", "true")
    os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "yNZIdZyzfsRTIoA2jsZ_xoDyueR0AUkgdHYLwuwh1qc=")
    os.environ.setdefault("SESSION_SECRET_KEY", "test-session-secret-key-for-testing")
    os.environ.setdefault("GOOGLE_SCOPES", '["https://www.googleapis.com/auth/webmasters.readonly"]')
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
    os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
    os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8100/auth/callback")
    os.environ.setdefault("ALLOWED_ORIGINS", '["http://localhost:5173"]')


@pytest.fixture(autouse=True)
def _env_setup(tmp_path, monkeypatch):
    """Ensure every test has a clean token store path and DB.

    Forces SQLite mode so tests don't need a real MariaDB server.
    """
    monkeypatch.setenv("TOKEN_STORE_PATH", str(tmp_path / ".tokens"))

    # Create a temp config.toml that forces SQLite mode
    config_path = tmp_path / "config.toml"
    config_path.write_text("[database]\nuse_sqlite = true\n")
    monkeypatch.setenv("CONFIG_PATH", str(config_path))

    # Clear all cached config so the new values take effect
    from app.config import get_settings, get_db_config
    get_settings.cache_clear()
    get_db_config.cache_clear()

    # Reset the Fernet singleton so it picks up the test encryption key
    from app.core.security import reset_fernet
    reset_fernet()

    # Reset the global DB connection so each test gets a fresh SQLite file
    from app.db import database
    database.DB = None
