"""
db_neon.py — пул подключений к Neon (PostgreSQL через asyncpg).
Импортируй get_pool() везде вместо aiosqlite.connect(DB_PATH).
"""
import asyncpg
from config import DATABASE_URL

_pool = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    # Если пул есть но закрыт — пересоздаём
    if _pool is None or _pool._closed:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
