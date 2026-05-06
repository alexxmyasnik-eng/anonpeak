from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart

import database as db
from keyboards.inline import kb_dialogs, kb_in_dialog, kb_main_menu, kb_back

router = Router()

class MsgFSM(StatesGroup):
    writing = State()

# Открыть список диалогов
@router.callback_query(F.data == "messages")
async def show_dialogs(call: CallbackQuery, state: FSMContext):
    await state.clear()
    dialogs = await db.get_my_dialogs(call.from_user.id)
    if not dialogs:
        await call.message.edit_text(
            "✉️ <b>Сообщения</b>\n\nУ тебя пока нет диалогов.\n"
            "Найди кого-нибудь в чате и напиши им!",
            parse_mode="HTML",
            reply_markup=kb_back("main_menu")
        )
        return

    # Загружаем инфу о собеседниках
    users = {}
    for d in dialogs:
        u = await db.get_user(d["partner_id"])
        if u:
            users[d["partner_id"]] = u

    await call.message.edit_text(
        "✉️ <b>Мои диалоги</b>\n\nВыбери собеседника:",
        parse_mode="HTML",
        reply_markup=kb_dialogs(dialogs, users)
    )

# Открыть диалог
@router.callback_query(F.data.startswith("dialog_"))
async def open_dialog(call: CallbackQuery, state: FSMContext):
    partner_id = int(call.data.split("_")[1])
    partner = await db.get_user(partner_id)
    if not partner:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    history = await db.get_dialog(call.from_user.id, partner_id, limit=20)
    me = await db.get_user(call.from_user.id)

    lines = [f"💬 <b>Диалог с {partner['nickname']}</b>\n"]
    for msg in history:
        sender = me if msg["sender_id"] == call.from_user.id else partner
        nick = sender["nickname"] or "?"
        lines.append(f"<b>{nick}:</b> {msg['text']}")

    lines.append("\n✏️ Напиши сообщение:")

    await state.update_data(partner_id=partner_id)
    await state.set_state(MsgFSM.writing)

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[-4000:]

    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_in_dialog(partner_id))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_in_dialog(partner_id))

# Отправить сообщение
@router.message(MsgFSM.writing, F.text)
async def send_private_msg(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    partner_id = data.get("partner_id")
    if not partner_id:
        await state.clear()
        return

    me = await db.get_user(message.from_user.id)
    partner = await db.get_user(partner_id)
    if not partner:
        await message.answer("Пользователь не найден.", reply_markup=kb_back("messages"))
        await state.clear()
        return

    await db.save_message(message.from_user.id, partner_id, message.text)

    # Уведомляем получателя
    bot_info = await bot.get_me()
    deep_link = f"https://t.me/{bot_info.username}?start=msg_{message.from_user.id}"
    try:
        await bot.send_message(
            partner_id,
            f"✉️ Новое сообщение от <b>{me['nickname']}</b>:\n\n"
            f"{message.text}\n\n"
            f"<a href='{deep_link}'>Ответить</a>",
            parse_mode="HTML"
        )
    except Exception:
        pass  # пользователь заблокировал бота

    await message.answer(
        f"✅ Отправлено <b>{partner['nickname']}</b>\n\nНапиши ещё или вернись назад:",
        parse_mode="HTML",
        reply_markup=kb_in_dialog(partner_id)
    )

# Обработка deep link ?start=msg_<user_id>
@router.message(CommandStart(deep_link=True))
async def deep_link_msg(message: Message, state: FSMContext):
    args = message.text.split()
    if len(args) < 2 or not args[1].startswith("msg_"):
        return
    try:
        target_id = int(args[1].replace("msg_", ""))
    except ValueError:
        return

    me = await db.get_user(message.from_user.id)
    if not me or not me["nickname"]:
        await message.answer("❌ Сначала создай профиль через /start")
        return

    target = await db.get_user(target_id)
    if not target or not target["nickname"]:
        await message.answer("Пользователь не найден.")
        return

    await state.update_data(partner_id=target_id)
    await state.set_state(MsgFSM.writing)
    await message.answer(
        f"✉️ Напиши сообщение для <b>{target['nickname']}</b>:",
        parse_mode="HTML",
        reply_markup=kb_in_dialog(target_id)
    )
