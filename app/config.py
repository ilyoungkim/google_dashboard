"""Application configuration via pydantic-settings.

All settings are loaded from environment variables or a .env file.
Database settings are loaded from config.toml.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """MariaDB connection settings (loaded from config.toml)."""

    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = "google"
    use_sqlite: bool = False


def _load_db_config() -> DatabaseConfig:
    """Load database config from config.toml (or env vars)."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

    # Look for config.toml in the project root
    config_path = Path(os.environ.get("CONFIG_PATH", "config.toml"))
    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        db_section = data.get("database", {})
        return DatabaseConfig(**db_section)
    return DatabaseConfig()


class Settings(BaseSettings):
    """Typed settings for the Google Search Console Dashboard."""

    # ── Google OAuth ──────────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8100/auth/callback"
    google_scopes: list[str] = [
        "https://www.googleapis.com/auth/webmasters.readonly"
    ]

    # ── Security keys ────────────────────────────────────────────
    token_encryption_key: str = ""  # Fernet key (urlsafe base64)
    session_secret_key: str = ""  # itsdangerous / signed-cookie secret

    # ── Session ──────────────────────────────────────────────────
    session_cookie_name: str = "gsc_session"
    session_max_age: int = 60 * 60 * 24 * 30  # 30 days

    # ── Frontend URL (where to redirect after OAuth callback) ────
    # Dev: Vite dev server. Prod: same origin ("/").
    frontend_url: str = "http://localhost:5173/"

    # ── Token store ──────────────────────────────────────────────
    token_store_path: str = ".tokens"

    # ── CORS ─────────────────────────────────────────────────────
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # Comma-separated private or loopback IPs permitted for robots.txt checks.
    robots_allowed_local_hosts: str = ""

    # ── Dry-run / test mode ──────────────────────────────────────
    dry_run: bool = False
    # When True the Search Console client returns canned data instead of
    # calling the real Google API.  Useful for local development without
    # a Google Cloud project.

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        extra="ignore",
    )


if TYPE_CHECKING:
    settings: Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    The cache can be cleared for testing via ``get_settings.cache_clear()``.
    """
    return Settings()


@lru_cache(maxsize=1)
def get_db_config() -> DatabaseConfig:
    """Return a cached DatabaseConfig instance."""
    return _load_db_config()


# Convenience module-level accessors (use cached getters)
def __getattr__(name: str):
    if name == "settings":
        return get_settings()
    if name == "db_config":
        return get_db_config()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

