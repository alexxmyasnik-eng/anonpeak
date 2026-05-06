from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BotCommand, BotCommandScopeDefault
from aiogram.filters import CommandStart

import database as db
from config import CHANNEL_ID
from keyboards.inline import kb_check_sub, kb_confirm_age, kb_main_menu

router = Router()

WELCOME_TEXT = """
👋 Добро пожаловать в <b>AnonPeak</b>!

Здесь ты можешь анонимно:
• 🖊 Заказать сигну
• ☕ Купить кружку с принтом
• 📸 Приобрести фото
• 🎬 Купить видео
• 💬 Общаться в чате

Оплата — рубли через DonationAlerts 💳
"""

async def check_subscription(bot: Bot, user_id: int, channel: str) -> bool:
    try:
        member = await bot.get_chat_member(channel, user_id)
        return member.status not in ("left", "kicked", "banned")
    except Exception:
        return False

async def setup_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🏠 Главное меню"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    await setup_commands(bot)

    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, message.from_user.username or "")

    # Проверяем подписку на канал
    is_subbed = await check_subscription(bot, user_id, CHANNEL_ID)
    if not is_subbed:
        await message.answer(
            f"📢 Для использования бота подпишись на наш канал:\n"
            f"👉 {CHANNEL_ID}\n\n"
            f"После подписки нажми кнопку ниже 👇",
            reply_markup=kb_check_sub()
        )
        return

    user = await db.get_user(user_id)

    # Если не подтверждал 18+ — показываем один раз
    if not user["is_adult"]:
        await message.answer(
            "🔞 Подтверди, что тебе есть 18 лет.\n"
            "Бот содержит контент для взрослых.",
            reply_markup=kb_confirm_age()
        )
        return

    has_profile = bool(user["nickname"])
    await message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=kb_main_menu(has_profile))

# ── Колбэки ──────────────────────────────────────────────

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, bot: Bot):
    is_subbed = await check_subscription(bot, call.from_user.id, CHANNEL_ID)
    if not is_subbed:
        await call.answer("❌ Ты ещё не подписан!", show_alert=True)
        return

    await call.message.delete()
    user = await db.get_user(call.from_user.id)
    if not user["is_adult"]:
        await call.message.answer(
            "🔞 Подтверди, что тебе есть 18 лет.",
            reply_markup=kb_confirm_age()
        )
    else:
        has_profile = bool(user["nickname"])
        await call.message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=kb_main_menu(has_profile))

@router.callback_query(F.data == "confirm_age")
async def cb_confirm_age(call: CallbackQuery):
    await db.set_adult(call.from_user.id)
    await call.message.delete()
    user = await db.get_user(call.from_user.id)
    has_profile = bool(user["nickname"])
    await call.message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=kb_main_menu(has_profile))

@router.callback_query(F.data == "deny_age")
async def cb_deny_age(call: CallbackQuery):
    await call.message.edit_text("🚫 Бот только для лиц 18+. До свидания!")

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    has_profile = bool(user["nickname"])
    try:
        await call.message.edit_text(WELCOME_TEXT, parse_mode="HTML", reply_markup=kb_main_menu(has_profile))
    except Exception:
        await call.message.answer(WELCOME_TEXT, parse_mode="HTML", reply_markup=kb_main_menu(has_profile))
