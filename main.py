import asyncio
import logging
import threading
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import start, profile, market, sell, buy, wallet, chat, messenger, admin
from payment_poller import payment_polling_loop
from api import app as fastapi_app

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

dp.include_router(messenger.router)
dp.include_router(start.router)
dp.include_router(profile.router)
dp.include_router(market.router)
dp.include_router(sell.router)
dp.include_router(buy.router)
dp.include_router(wallet.router)
dp.include_router(chat.router)
dp.include_router(admin.router)


def run_api():
    """Запускает FastAPI в отдельном потоке."""
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8000, log_level="info")


async def main():
    await init_db()

    # API в отдельном потоке — не мешает боту
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()

    # Поллер и бот в asyncio
    await asyncio.gather(
        payment_polling_loop(bot),
        dp.start_polling(bot),
    )

if __name__ == "__main__":
    asyncio.run(main())
