import asyncpg
from config import DATABASE_URL

async def get_pool():
    """Возвращает прямое соединение вместо пула — избегает проблем с event loop."""
    return await asyncpg.connect(DATABASE_URL)
