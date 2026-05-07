from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timezone

import database as db
from config import CHANNEL_ID, CHAT_CHANNEL, CHAT_GROUP_ID, CHAT_COOLDOWN
from keyboards.inline import kb_main_menu, kb_chat_check_sub, kb_back

router = Router()

class ChatFSM(StatesGroup):
    writing = State()

async def is_subscribed(bot: Bot, uid: int, channel: str) -> bool:
    try:
        m = await bot.get_chat_member(channel, uid)
        return m.status not in ("left", "kicked", "banned")
    except Exception:
        return False

@router.callback_query(F.data == "open_chat")
async def open_chat(call: CallbackQuery, bot: Bot, state: FSMContext):
    uid = call.from_user.id
    user = await db.get_user(uid)

    if not user or not user["nickname"]:
        await call.answer("❌ Сначала создай профиль!", show_alert=True)
        return

    # Проверяем подписку на чат-канал
    if not await is_subscribed(bot, uid, CHAT_CHANNEL):
        await call.message.edit_text(
            f"💬 Для доступа к чату подпишись на:\n👉 {CHAT_CHANNEL}\n\n"
            f"После подписки нажми кнопку 👇",
            reply_markup=kb_chat_check_sub()
        )
        return

    await _enter_chat(call, state, user)

@router.callback_query(F.data == "chat_sub_check")
async def chat_sub_check(call: CallbackQuery, bot: Bot, state: FSMContext):
    uid = call.from_user.id
    if not await is_subscribed(bot, uid, CHAT_CHANNEL):
        await call.answer("❌ Ты ещё не подписан!", show_alert=True)
        return
    user = await db.get_user(uid)
    if not user or not user["nickname"]:
        await call.answer("❌ Сначала создай профиль!", show_alert=True)
        return
    await _enter_chat(call, state, user)

async def _enter_chat(call: CallbackQuery, state: FSMContext, user):
    uid = call.from_user.id

    # Проверяем кулдаун
    last = await db.get_last_chat_time(uid)
    if last:
        try:
            last_dt = datetime.fromisoformat(str(last)).replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = (now - last_dt).total_seconds()
            if diff < CHAT_COOLDOWN:
                mins = int((CHAT_COOLDOWN - diff) // 60)
                secs = int((CHAT_COOLDOWN - diff) % 60)
                await call.answer(
                    f"⏳ Следующее сообщение через {mins}м {secs}с",
                    show_alert=True
                )
                return
        except Exception:
            pass

    await state.set_state(ChatFSM.writing)
    try:
        await call.message.edit_text(
            "💬 <b>Общий чат</b>\n\n"
            "Напиши сообщение (текст, фото или видео).\n"
            "⏰ Можно писать раз в 30 минут.\n"
            "⚠️ Соблюдай правила — за спам бан.",
            parse_mode="HTML",
            reply_markup=kb_back("main_menu")
        )
    except Exception:
        await call.message.answer(
            "💬 <b>Общий чат</b>\n\nНапиши сообщение:",
            parse_mode="HTML",
            reply_markup=kb_back("main_menu")
        )

@router.message(ChatFSM.writing, F.text | F.photo | F.video | F.sticker)
async def handle_chat_msg(message: Message, bot: Bot, state: FSMContext):
    uid = message.from_user.id
    user = await db.get_user(uid)

    # Проверка кулдауна ещё раз (на случай если отправил несколько)
    last = await db.get_last_chat_time(uid)
    if last:
        try:
            last_dt = datetime.fromisoformat(str(last)).replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = (now - last_dt).total_seconds()
            if diff < CHAT_COOLDOWN:
                mins = int((CHAT_COOLDOWN - diff) // 60)
                await message.answer(
                    f"⏳ Подожди ещё {mins} мин. перед следующим сообщением.",
                    reply_markup=kb_back("main_menu")
                )
                return
        except Exception:
            pass

    nickname = user["nickname"]
    age      = user["age"] or "?"

    # Анонимная ссылка через токен — ID пользователя НЕ виден
    bot_info = await bot.get_me()
    dm_token = await db.get_or_create_dm_token(uid)
    anon_link = f"https://t.me/{bot_info.username}?start=dm_{dm_token}"

    header = (
        f"👤 <b>{nickname}</b>, {age} лет\n"
        f"━━━━━━━━━━━━━━━━\n"
    )
    footer = (
        f"\n━━━━━━━━━━━━━━━━\n"
        f"<a href='{anon_link}'>✉️ Написать анонимно</a>"
    )

    # Аватарка: берём фото профиля из бота (загруженное при регистрации)
    avatar_id = user["avatar_id"] if user else None

    try:
        if message.text:
            msg_text = header + message.text + footer
            if avatar_id:
                await bot.send_photo(CHAT_GROUP_ID, avatar_id, caption=msg_text, parse_mode="HTML")
            else:
                await bot.send_message(CHAT_GROUP_ID, msg_text, parse_mode="HTML")
        elif message.photo:
            cap = header + (message.caption or "") + footer
            if avatar_id:
                # Сначала аватарка с подписью, потом само фото
                await bot.send_photo(CHAT_GROUP_ID, avatar_id, caption=cap, parse_mode="HTML")
                await bot.send_photo(CHAT_GROUP_ID, message.photo[-1].file_id)
            else:
                await bot.send_photo(CHAT_GROUP_ID, message.photo[-1].file_id, caption=cap, parse_mode="HTML")
        elif message.video:
            cap = header + (message.caption or "") + footer
            if avatar_id:
                await bot.send_photo(CHAT_GROUP_ID, avatar_id, caption=cap, parse_mode="HTML")
                await bot.send_video(CHAT_GROUP_ID, message.video.file_id)
            else:
                await bot.send_video(CHAT_GROUP_ID, message.video.file_id, caption=cap, parse_mode="HTML")
        elif message.sticker:
            msg_text = header + "🎭 Стикер" + footer
            if avatar_id:
                await bot.send_photo(CHAT_GROUP_ID, avatar_id, caption=msg_text, parse_mode="HTML")
            else:
                await bot.send_message(CHAT_GROUP_ID, msg_text, parse_mode="HTML")
            await bot.send_sticker(CHAT_GROUP_ID, message.sticker.file_id)

        await db.update_last_chat(uid)

        await message.answer(
            "✅ Отправлено в чат!\n⏰ Следующее сообщение через 30 минут.",
            reply_markup=kb_back("main_menu")
        )
        await state.clear()

    except Exception as e:
        await message.answer(
            f"❌ Ошибка отправки.\nУбедись что бот добавлен в группу как <b>администратор</b>.\n\n<code>{e}</code>",
            parse_mode="HTML",
            reply_markup=kb_back("main_menu")
        )
        await state.clear()
