"""Database initialization and connection management.

Supports two backends:
1. **MariaDB** (via asyncmy) — production, configured in config.toml
2. **SQLite** (via aiosqlite) — local dev / testing fallback

The ``Database`` wrapper provides a unified interface so that repository
functions don't need to care about the underlying driver.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import get_db_config, get_settings

DB: Any = None  # Database wrapper instance
_DIALECT: str = "sqlite"


class Database:
    """Unified async database wrapper (MariaDB or SQLite).

    Repository functions write SQL in **SQLite dialect** (``?`` placeholders,
    ``ON CONFLICT ... DO UPDATE``).  This wrapper translates to MySQL dialect
    (``%s``, ``ON DUPLICATE KEY UPDATE``) when connected to MariaDB.

    For MariaDB, a connection **pool** is used so that concurrent coroutines
    each acquire their own connection, avoiding "readexactly() called while
    another coroutine is already waiting for incoming data" errors.
    """

    def __init__(self, conn: Any, dialect: str, pool: Any = None) -> None:
        self._conn = conn  # SQLite: single connection; MySQL: None (use pool)
        self._pool = pool   # MySQL: asyncmy.Pool; SQLite: None
        self.dialect = dialect  # "mysql" or "sqlite"

    # ── Core operations ───────────────────────────────────────────

    async def execute(self, sql: str, params: tuple = ()) -> Any:
        """Execute a SQL statement, translating dialect if needed.

        Returns a cursor-like object (aiosqlite cursor or asyncmy cursor).
        In MySQL pool mode, returns a ``_CursorResult`` with eagerly-fetched
        rows (the connection is released back to the pool immediately).
        """
        if self.dialect == "mysql":
            sql = self._to_mysql(sql)
            if self._pool is not None:
                # Pool mode: acquire a connection per call (concurrency-safe)
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(sql, params)
                        if cur.description is not None:
                            # SELECT — fetch all rows now
                            rows = await cur.fetchall()
                            cols = [d[0] for d in cur.description]
                            await conn.commit()
                            return _CursorResult(rows, cols)
                        else:
                            # INSERT/UPDATE/DELETE — commit & return metadata
                            await conn.commit()
                            return _CursorResult([], [], cur)
            # Fallback: single connection (not concurrency-safe)
            cur = self._conn.cursor()
            await cur.execute(sql, params)
            return cur
        else:
            return await self._conn.execute(sql, params)

    async def executescript(self, sql: str) -> None:
        """Execute a multi-statement SQL script (DDL)."""
        if self.dialect == "sqlite":
            await self._conn.executescript(sql)
        else:
            if self._pool is not None:
                async with self._pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        for stmt in sql.split(";"):
                            stmt = stmt.strip()
                            if stmt:
                                await cur.execute(stmt)
                    await conn.commit()
            else:
                async with self._conn.cursor() as cur:
                    for stmt in sql.split(";"):
                        stmt = stmt.strip()
                        if stmt:
                            await cur.execute(stmt)
                await self._conn.commit()

    async def commit(self) -> None:
        if self.dialect == "sqlite":
            await self._conn.commit()
        # MySQL pool mode: commits are per-connection (handled in execute)

    async def close(self) -> None:
        if self.dialect == "sqlite":
            await self._conn.close()
        elif self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
        elif self._conn is not None:
            self._conn.close()

    # ── Dialect translation ───────────────────────────────────────

    @staticmethod
    def _to_mysql(sql: str) -> str:
        """Translate SQLite SQL → MySQL SQL."""
        # Placeholders: ? → %s
        sql = sql.replace("?", "%s")
        # UPSERT: ON CONFLICT(...) DO UPDATE SET → ON DUPLICATE KEY UPDATE
        import re
        sql = re.sub(
            r"ON CONFLICT\s*\([^)]+\)\s*DO UPDATE SET",
            "ON DUPLICATE KEY UPDATE",
            sql,
        )
        # excluded. → VALUES()
        sql = re.sub(r"\bexcluded\.(\w+)", r"VALUES(\1)", sql)
        return sql

    # ── Query helpers (return dicts regardless of dialect) ────────

    async def fetchone(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        """Execute a SELECT and return a single row as a dict (or None)."""
        cursor = await self.execute(sql, params)
        if self.dialect == "sqlite":
            row = await cursor.fetchone()
            return dict(row) if row else None
        else:
            if isinstance(cursor, _CursorResult):
                return cursor.fetchone()
            row = await cursor.fetchone()
            if row is None:
                return None
            cols = [desc[0] for desc in cursor.description]
            return dict(zip(cols, row))

    async def fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        """Execute a SELECT and return all rows as a list of dicts."""
        cursor = await self.execute(sql, params)
        if self.dialect == "sqlite":
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        else:
            if isinstance(cursor, _CursorResult):
                return cursor.fetchall()
            rows = await cursor.fetchall()
            cols = [desc[0] for desc in cursor.description]
            return [dict(zip(cols, r)) for r in rows]


class _CursorResult:
    """Eagerly-fetched result wrapper for pool-mode MySQL queries.

    Since the connection/cursor is released back to the pool immediately
    after ``execute``, we read all rows up-front inside the async ``execute``
    call and expose ``fetchone`` / ``fetchall`` synchronously.
    """

    def __init__(self, rows: list[tuple], cols: list[str], cur: Any = None) -> None:
        self._rows = rows
        self._cols = cols
        self._cur = cur  # for INSERT/UPDATE (no description)

    @property
    def description(self) -> list | None:
        return [(c,) for c in self._cols] if self._cols else None

    @property
    def lastrowid(self) -> int | None:
        return self._cur.lastrowid if self._cur is not None else None

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount if self._cur is not None else len(self._rows)

    def fetchone(self) -> dict[str, Any] | None:
        if not self._rows:
            return None
        row = self._rows[0]
        return dict(zip(self._cols, row)) if self._cols else None

    def fetchall(self) -> list[dict[str, Any]]:
        return [dict(zip(self._cols, r)) for r in self._rows] if self._cols else []

    async def afetchone(self) -> dict[str, Any] | None:
        return self.fetchone()

    async def afetchall(self) -> list[dict[str, Any]]:
        return self.fetchall()


# ═══════════════════════════════════════════════════════════════════════
# Connection management
# ═══════════════════════════════════════════════════════════════════════

async def get_db() -> Database:
    """Return the shared Database wrapper, creating the connection if needed."""
    global DB, _DIALECT
    if DB is not None:
        return DB

    db_config = get_db_config()
    settings = get_settings()

    if db_config.use_sqlite:
        # ── SQLite (local dev / testing) ──────────────────────────
        import aiosqlite

        db_path = Path(settings.token_store_path) / "gsc_cache.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(db_path))
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        _DIALECT = "sqlite"
        DB = Database(conn, "sqlite")
        await _create_tables_sqlite(conn)
    else:
        # ── MariaDB (production) — connection pool ───────────────
        import asyncmy

        pool = await asyncmy.create_pool(
            host=db_config.host,
            port=db_config.port,
            user=db_config.user,
            password=db_config.password,
            database=db_config.database,
            autocommit=True,
            minsize=2,
            maxsize=10,
        )
        _DIALECT = "mysql"
        DB = Database(conn=None, dialect="mysql", pool=pool)
        # Create tables using a pooled connection
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await _create_tables_mysql_pool(cur)

    return DB


async def close_db() -> None:
    """Close the database connection (called on app shutdown)."""
    global DB
    if DB is not None:
        await DB.close()
        DB = None


def get_dialect() -> str:
    """Return the current database dialect ('mysql' or 'sqlite')."""
    return _DIALECT


# ═══════════════════════════════════════════════════════════════════════
# DDL — SQLite
# ═══════════════════════════════════════════════════════════════════════

async def _create_tables_sqlite(db: Any) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     TEXT PRIMARY KEY,
            email       TEXT NOT NULL,
            created_at  REAL NOT NULL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            site_url    TEXT NOT NULL,
            permission_level TEXT NOT NULL DEFAULT 'siteOwner',
            created_at  REAL NOT NULL DEFAULT (unixepoch()),
            UNIQUE(user_id, site_url)
        );

        CREATE TABLE IF NOT EXISTS analytics_cache (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            query_hash  TEXT NOT NULL,
            data_json   TEXT NOT NULL,
            fetched_at  REAL NOT NULL DEFAULT (unixepoch()),
            expires_at  REAL NOT NULL,
            UNIQUE(project_id, query_hash)
        );

        CREATE TABLE IF NOT EXISTS sitemaps_cache (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            data_json   TEXT NOT NULL,
            fetched_at  REAL NOT NULL DEFAULT (unixepoch()),
            expires_at  REAL NOT NULL,
            UNIQUE(project_id)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            email       TEXT NOT NULL DEFAULT '',
            scopes      TEXT NOT NULL DEFAULT '[]',
            access_token_ciphertext  TEXT NOT NULL DEFAULT '',
            refresh_token_ciphertext TEXT NOT NULL DEFAULT '',
            access_token_expires_at  REAL NOT NULL DEFAULT 0.0,
            created_at  REAL NOT NULL DEFAULT (unixepoch()),
            updated_at  REAL NOT NULL DEFAULT (unixepoch())
        );

        CREATE TABLE IF NOT EXISTS oauth_states (
            state       TEXT PRIMARY KEY,
            created_at  REAL NOT NULL DEFAULT (unixepoch())
        );

        CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
        CREATE INDEX IF NOT EXISTS idx_analytics_cache_project ON analytics_cache(project_id);
        CREATE INDEX IF NOT EXISTS idx_sitemaps_cache_project ON sitemaps_cache(project_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    """)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════
# DDL — MariaDB
# ═══════════════════════════════════════════════════════════════════════

async def _create_tables_mysql(conn: Any) -> None:
    """Create tables on MariaDB using a cursor (legacy single-conn mode)."""
    cur = conn.cursor()
    try:
        await _create_tables_mysql_inner(cur)
    finally:
        await cur.close()


async def _create_tables_mysql_pool(cur: Any) -> None:
    """Create tables on MariaDB using a cursor from the pool."""
    await _create_tables_mysql_inner(cur)


async def _create_tables_mysql_inner(cur: Any) -> None:
    """Shared DDL for MariaDB (works with any cursor)."""
    await cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     VARCHAR(255) PRIMARY KEY,
            email       VARCHAR(255) NOT NULL,
            created_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP())
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    await cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id          INT PRIMARY KEY AUTO_INCREMENT,
            user_id     VARCHAR(255) NOT NULL,
            site_url    TEXT NOT NULL,
            permission_level VARCHAR(50) NOT NULL DEFAULT 'siteOwner',
            created_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
            UNIQUE KEY uq_user_site (user_id, site_url(255)),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    await cur.execute("""
        CREATE TABLE IF NOT EXISTS analytics_cache (
            id          INT PRIMARY KEY AUTO_INCREMENT,
            project_id  INT NOT NULL,
            query_hash  VARCHAR(64) NOT NULL,
            data_json   LONGTEXT NOT NULL,
            fetched_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
            expires_at  DOUBLE NOT NULL,
            UNIQUE KEY uq_project_hash (project_id, query_hash),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    await cur.execute("""
        CREATE TABLE IF NOT EXISTS sitemaps_cache (
            id          INT PRIMARY KEY AUTO_INCREMENT,
            project_id  INT NOT NULL,
            data_json   LONGTEXT NOT NULL,
            fetched_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
            expires_at  DOUBLE NOT NULL,
            UNIQUE KEY (project_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    await cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id  VARCHAR(64) PRIMARY KEY,
            user_id     VARCHAR(255) NOT NULL,
            email       VARCHAR(255) NOT NULL DEFAULT '',
            scopes      TEXT NOT NULL DEFAULT '[]',
            access_token_ciphertext  TEXT NOT NULL DEFAULT '',
            refresh_token_ciphertext TEXT NOT NULL DEFAULT '',
            access_token_expires_at  DOUBLE NOT NULL DEFAULT 0.0,
            created_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
            updated_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP()),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    await cur.execute("""
        CREATE TABLE IF NOT EXISTS oauth_states (
            state       VARCHAR(64) PRIMARY KEY,
            created_at  DOUBLE NOT NULL DEFAULT (UNIX_TIMESTAMP())
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    # Indexes — MariaDB doesn't support IF NOT EXISTS for CREATE INDEX,
    # so we catch duplicate key errors gracefully.
    for idx_sql in [
        "CREATE INDEX idx_projects_user ON projects(user_id)",
        "CREATE INDEX idx_analytics_cache_project ON analytics_cache(project_id)",
        "CREATE INDEX idx_sitemaps_cache_project ON sitemaps_cache(project_id)",
        "CREATE INDEX idx_sessions_user ON sessions(user_id)",
    ]:
        try:
            await cur.execute(idx_sql)
        except Exception:
            pass  # index already exists
