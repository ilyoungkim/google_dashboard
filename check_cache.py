"""Check and optionally clear cached projects/users."""
import asyncio
from app.db.database import get_db


async def main():
    db = await get_db()

    print("=== users ===")
    rows = await db.fetchall("SELECT * FROM users")
    for r in rows:
        print(dict(r) if hasattr(r, "keys") else r)

    print("\n=== projects ===")
    rows = await db.fetchall("SELECT * FROM projects")
    for r in rows:
        print(dict(r) if hasattr(r, "keys") else r)

    print("\n=== analytics_cache count ===")
    row = await db.fetchone("SELECT COUNT(*) as cnt FROM analytics_cache")
    print(row)


asyncio.run(main())