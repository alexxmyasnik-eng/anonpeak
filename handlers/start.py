from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

import database as db
from config import CHANNEL_ID
from keyboards.inline import kb_check_sub, kb_confirm_age, kb_main_menu

router = Router()

WELCOME_TEXT = """
👋 Добро пожаловать в <b>AnonymMarket</b>!

Здесь ты можешь анонимно:
• 🖊 Заказать сигну
• ☕ Купить кружку с принтом
• 📸 Приобрести фото
• 🎬 Купить видео

Оплата — Telegram Stars ⭐
Продавцы сами выставляют свои товары.

Для начала — подпишись на наш канал 👇
"""

async def check_subscription(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception:
        return False

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    user = await db.get_user(message.from_user.id)
    if not user:
        await db.create_user(message.from_user.id, message.from_user.username or "")

    is_subbed = await check_subscription(bot, message.from_user.id)
    if not is_subbed:
        await message.answer(
            f"📢 Сначала подпишись на наш канал: {CHANNEL_ID}\n\n"
            "После подписки нажми кнопку ниже 👇",
            reply_markup=kb_check_sub()
        )
        return

    user = await db.get_user(message.from_user.id)
    if not user["is_adult"]:
        await message.answer(
            "🔞 Подтверди, что тебе есть 18 лет:",
            reply_markup=kb_confirm_age()
        )
        return

    has_profile = bool(user["nickname"])
    await message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=kb_main_menu(has_profile))

@router.callback_query(F.data == "check_sub")
async def callback_check_sub(call: CallbackQuery, bot: Bot):
    is_subbed = await check_subscription(bot, call.from_user.id)
    if not is_subbed:
        await call.answer("❌ Ты ещё не подписан!", show_alert=True)
        return

    await call.message.delete()
    user = await db.get_user(call.from_user.id)
    if not user["is_adult"]:
        await call.message.answer(
            "🔞 Подтверди, что тебе есть 18 лет:",
            reply_markup=kb_confirm_age()
        )
    else:
        has_profile = bool(user["nickname"])
        await call.message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=kb_main_menu(has_profile))

@router.callback_query(F.data == "confirm_age")
async def callback_confirm_age(call: CallbackQuery):
    await db.set_adult(call.from_user.id)
    await call.message.delete()
    user = await db.get_user(call.from_user.id)
    has_profile = bool(user["nickname"])
    await call.message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=kb_main_menu(has_profile))

@router.callback_query(F.data == "deny_age")
async def callback_deny_age(call: CallbackQuery):
    await call.message.edit_text("🚫 К сожалению, этот бот только для лиц 18+.")

@router.callback_query(F.data == "main_menu")
async def callback_main_menu(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    has_profile = bool(user["nickname"])
    await call.message.edit_text(WELCOME_TEXT, parse_mode="HTML", reply_markup=kb_main_menu(has_profile))
