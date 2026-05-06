import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import start, profile, market, sell, buy, wallet, admin, chat, messages

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# Порядок важен — messages раньше start чтобы deep_link перехватился
dp.include_router(messages.router)
dp.include_router(start.router)
dp.include_router(profile.router)
dp.include_router(market.router)
dp.include_router(sell.router)
dp.include_router(buy.router)
dp.include_router(wallet.router)
dp.include_router(chat.router)
dp.include_router(admin.router)

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
