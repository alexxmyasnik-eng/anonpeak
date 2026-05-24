import asyncpg
from contextlib import asynccontextmanager
from config import DATABASE_URL

@asynccontextmanager
async def get_conn():
    """
    Каждый раз создаёт новое соединение и закрывает после использования.
    Нет глобального пула — нет проблем с event loop между uvicorn и aiogram.
    """
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        await conn.close()
