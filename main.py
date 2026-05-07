import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
from handlers import start, profile, market, sell, buy, wallet, chat, messenger, admin

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

dp.include_router(messenger.router)   # первым — ловит deep link и order_chat
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
