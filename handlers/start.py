from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BotCommand, BotCommandScopeDefault
from aiogram.filters import CommandStart

import database as db
from config import CHANNEL_ID
from keyboards.inline import kb_check_sub, kb_confirm_age, kb_main_menu

router = Router()

WELCOME = """
👋 Добро пожаловать в <b>AnonPeak</b>!

🛍 Анонимный маркет — сигны, фото, видео, кружки
💬 Общий чат
✉️ Личные сообщения
💰 Оплата через DonationAlerts
"""

async def is_subscribed(bot: Bot, user_id: int, channel: str) -> bool:
    try:
        m = await bot.get_chat_member(channel, user_id)
        return m.status not in ("left", "kicked", "banned")
    except Exception:
        return False

async def setup_menu(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start", description="🏠 Главное меню")
    ])

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    await setup_menu(bot)
    uid = message.from_user.id
    user = await db.get_user(uid)
    if not user:
        await db.create_user(uid, message.from_user.username or "")

    if not await is_subscribed(bot, uid, CHANNEL_ID):
        await message.answer(
            f"📢 Для входа подпишись на канал:\n👉 {CHANNEL_ID}",
            reply_markup=kb_check_sub()
        )
        return

    user = await db.get_user(uid)
    if not user["is_adult"]:
        await message.answer("🔞 Подтверди возраст 18+:", reply_markup=kb_confirm_age())
        return

    unread = await db.count_unread(uid)
    await message.answer(WELCOME, parse_mode="HTML",
                         reply_markup=kb_main_menu(bool(user["nickname"]), unread))

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, bot: Bot):
    if not await is_subscribed(bot, call.from_user.id, CHANNEL_ID):
        await call.answer("❌ Ты ещё не подписан!", show_alert=True)
        return
    await call.message.delete()
    user = await db.get_user(call.from_user.id)
    if not user["is_adult"]:
        await call.message.answer("🔞 Подтверди возраст 18+:", reply_markup=kb_confirm_age())
    else:
        unread = await db.count_unread(call.from_user.id)
        await call.message.answer(WELCOME, parse_mode="HTML",
                                  reply_markup=kb_main_menu(bool(user["nickname"]), unread))

@router.callback_query(F.data == "confirm_age")
async def cb_confirm_age(call: CallbackQuery):
    await db.set_adult(call.from_user.id)
    await call.message.delete()
    user = await db.get_user(call.from_user.id)
    unread = await db.count_unread(call.from_user.id)
    await call.message.answer(WELCOME, parse_mode="HTML",
                               reply_markup=kb_main_menu(bool(user["nickname"]), unread))

@router.callback_query(F.data == "deny_age")
async def cb_deny_age(call: CallbackQuery):
    await call.message.edit_text("🚫 Бот только для 18+.")

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    unread = await db.count_unread(call.from_user.id)
    try:
        await call.message.edit_text(WELCOME, parse_mode="HTML",
                                     reply_markup=kb_main_menu(bool(user["nickname"]), unread))
    except Exception:
        await call.message.answer(WELCOME, parse_mode="HTML",
                                  reply_markup=kb_main_menu(bool(user["nickname"]), unread))
