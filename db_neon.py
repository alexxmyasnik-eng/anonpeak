import asyncpg
from contextlib import asynccontextmanager
from config import DATABASE_URL

_pool = None

async def _get_pool():
    global _pool
    if _pool is None or _pool._closed:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=5)
    return _pool

@asynccontextmanager
async def get_conn():
    pool = await _get_pool()
    async with pool.acquire() as conn:
        yield conn
