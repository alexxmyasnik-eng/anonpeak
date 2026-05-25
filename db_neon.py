import asyncpg
import asyncio
from contextlib import asynccontextmanager
from config import DATABASE_URL

_pool = None

async def _get_pool():
    global _pool
    if _pool is None or _pool._closed:
        _pool = await asyncpg.create_pool(
            DATABASE_URL, 
            min_size=2, 
            max_size=5,
            # Не давать соединениям протухнуть:
            max_inactive_connection_lifetime=300
        )
    return _pool

# Добавь в lifespan или запусти как background task:
async def keepalive_loop():
    while True:
        await asyncio.sleep(240)  # каждые 4 минуты
        try:
            pool = await _get_pool()
            await pool.fetchval("SELECT 1")
        except Exception:
            pass

@asynccontextmanager
async def get_conn():
    pool = await _get_pool()
    async with pool.acquire() as conn:
        yield conn
