import asyncpg
from contextlib import asynccontextmanager
from config import DATABASE_URL

@asynccontextmanager
async def get_conn():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()
