from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter

import database as db
from config import CHANNEL_ID, CHAT_ID
from keyboards.inline import kb_main_menu, kb_chat_confirm_sub, kb_back

router = Router()

CHAT_CHANNEL = "@AnonPeak"   # тот же канал или отдельный — меняй под себя

class ChatFSM(StatesGroup):
    writing = State()

async def check_sub(bot: Bot, user_id: int, channel: str) -> bool:
    try:
        m = await bot.get_chat_member(channel, user_id)
        return m.status not in ("left", "kicked", "banned")
    except Exception:
        return False

@router.callback_query(F.data == "open_chat")
async def open_chat(call: CallbackQuery, bot: Bot, state: FSMContext):
    # Проверяем подписку
    is_subbed = await check_sub(bot, call.from_user.id, CHANNEL_ID)
    if not is_subbed:
        await call.message.edit_text(
            f"💬 Для доступа к чату нужно подписаться на канал:\n"
            f"👉 {CHANNEL_ID}\n\n"
            f"После подписки нажми кнопку ниже 👇",
            reply_markup=kb_chat_confirm_sub()
        )
        return

    user = await db.get_user(call.from_user.id)
    if not user or not user["nickname"]:
        await call.answer("❌ Сначала создай профиль!", show_alert=True)
        return

    await call.message.edit_text(
        "💬 <b>Общий чат</b>\n\n"
        "Напиши своё сообщение — оно появится в чате с твоим профилем.\n\n"
        "⚠️ Соблюдай правила. За спам — бан.",
        parse_mode="HTML",
        reply_markup=kb_back("main_menu")
    )
    await state.set_state(ChatFSM.writing)

@router.callback_query(F.data == "chat_sub_confirmed")
async def chat_sub_confirmed(call: CallbackQuery, bot: Bot, state: FSMContext):
    is_subbed = await check_sub(bot, call.from_user.id, CHANNEL_ID)
    if not is_subbed:
        await call.answer("❌ Ты ещё не подписан!", show_alert=True)
        return
    user = await db.get_user(call.from_user.id)
    if not user or not user["nickname"]:
        await call.answer("❌ Сначала создай профиль!", show_alert=True)
        return
    await call.message.edit_text(
        "💬 <b>Общий чат</b>\n\nНапиши своё сообщение:",
        parse_mode="HTML",
        reply_markup=kb_back("main_menu")
    )
    await state.set_state(ChatFSM.writing)

@router.message(ChatFSM.writing, F.text | F.photo | F.video | F.sticker)
async def handle_chat_message(message: Message, bot: Bot, state: FSMContext):
    user = await db.get_user(message.from_user.id)
    if not user or not user["nickname"]:
        await state.clear()
        return

    nickname = user["nickname"]
    age      = user["age"] or "?"
    user_id  = message.from_user.id

    # Ссылка на лс в боте — через start параметр
    bot_info = await bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start=msg_{user_id}"

    header = (
        f"👤 <b>{nickname}</b> | {age} лет\n"
        f"──────────────\n"
    )
    footer = f"\n──────────────\n📩 <a href='{deep_link}'>Написать в ЛС</a>"

    try:
        if message.text:
            await bot.send_message(
                CHAT_ID,
                header + message.text + footer,
                parse_mode="HTML"
            )
        elif message.photo:
            caption = (header + (message.caption or "") + footer)
            await bot.send_photo(CHAT_ID, message.photo[-1].file_id, caption=caption, parse_mode="HTML")
        elif message.video:
            caption = (header + (message.caption or "") + footer)
            await bot.send_video(CHAT_ID, message.video.file_id, caption=caption, parse_mode="HTML")
        elif message.sticker:
            await bot.send_message(CHAT_ID, header + "🎭 Стикер" + footer, parse_mode="HTML")
            await bot.send_sticker(CHAT_ID, message.sticker.file_id)

        await message.answer(
            "✅ Сообщение отправлено в чат!\n\nНапиши ещё или вернись в меню:",
            reply_markup=kb_back("main_menu")
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка отправки. Проверь что бот добавлен в группу как администратор.\n{e}",
            reply_markup=kb_back("main_menu")
        )
        await state.clear()
