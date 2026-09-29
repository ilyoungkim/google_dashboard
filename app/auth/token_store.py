"""Token persistence layer.

DB-backed token store (MariaDB or SQLite).  All tokens are encrypted
at rest via Fernet.  Delegates to ``app.db.repository`` for CRUD.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.security import encrypt_token, decrypt_token


@dataclass
class TokenRecord:
    session_id: str
    user_id: str = ""
    email: str = ""
    scopes: list[str] = field(default_factory=list)
    access_token_ciphertext: str = ""
    refresh_token_ciphertext: str = ""
    access_token_expires_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # ── Transient (never persisted) ──────────────────────────────
    _access_token_plain: str = field(default="", repr=False, compare=False)
    _refresh_token_plain: str = field(default="", repr=False, compare=False)

    @property
    def access_token(self) -> str:
        if self._access_token_plain:
            return self._access_token_plain
        if self.access_token_ciphertext:
            self._access_token_plain = decrypt_token(self.access_token_ciphertext)
        return self._access_token_plain

    @access_token.setter
    def access_token(self, value: str) -> None:
        self._access_token_plain = value
        self.access_token_ciphertext = encrypt_token(value) if value else ""

    @property
    def refresh_token(self) -> str:
        if self._refresh_token_plain:
            return self._refresh_token_plain
        if self.refresh_token_ciphertext:
            self._refresh_token_plain = decrypt_token(self.refresh_token_ciphertext)
        return self._refresh_token_plain

    @refresh_token.setter
    def refresh_token(self, value: str) -> None:
        self._refresh_token_plain = value
        self.refresh_token_ciphertext = encrypt_token(value) if value else ""

    def is_access_token_expired(self, margin_seconds: int = 60) -> bool:
        return time.time() + margin_seconds >= self.access_token_expires_at

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> TokenRecord:
        """Build a TokenRecord from a DB row dict (as returned by repository)."""
        return cls(
            session_id=row["session_id"],
            user_id=row.get("user_id", ""),
            email=row.get("email", ""),
            scopes=row.get("scopes", []),
            access_token_ciphertext=row.get("access_token_ciphertext", ""),
            refresh_token_ciphertext=row.get("refresh_token_ciphertext", ""),
            access_token_expires_at=row.get("access_token_expires_at", 0.0),
            created_at=row.get("created_at", time.time()),
            updated_at=row.get("updated_at", time.time()),
        )


class TokenStore:
    """DB-backed token store (delegates to ``app.db.repository``)."""

    # ── public API ────────────────────────────────────────────────

    async def save(self, record: TokenRecord) -> None:
        """Persist (insert or update) a token record in the database."""
        from app.db.repository import save_session

        record.updated_at = time.time()
        await save_session(
            session_id=record.session_id,
            user_id=record.user_id,
            email=record.email,
            scopes=record.scopes,
            access_token_ciphertext=record.access_token_ciphertext,
            refresh_token_ciphertext=record.refresh_token_ciphertext,
            access_token_expires_at=record.access_token_expires_at,
        )

    async def load(self, session_id: str) -> TokenRecord | None:
        """Load a token record from the database.  Returns None if missing."""
        from app.db.repository import load_session

        row = await load_session(session_id)
        if row is None:
            return None
        return TokenRecord.from_db_row(row)

    async def delete(self, session_id: str) -> None:
        """Remove a session from the database."""
        from app.db.repository import delete_session

        await delete_session(session_id)

    async def list_sessions(self) -> list[str]:
        """Return all active session IDs."""
        from app.db.repository import list_sessions

        return await list_sessions()


# Singleton
token_store = TokenStore()
