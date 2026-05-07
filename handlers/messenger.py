from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards.inline import kb_review, kb_skip_review, kb_main_menu, kb_back

router = Router()

# ─── ВСПОМОГАТЕЛЬНЫЕ ─────────────────────────────────────

def _status_text(s):
    return {"pending_payment":"Ожидает оплаты","paid":"Оплачен",
            "seller_confirmed":"Выдан продавцом","done":"Завершён","cancelled":"Отменён"}.get(s, s)

def _status_emoji(s):
    return {"pending_payment":"💳","paid":"📦","seller_confirmed":"⏳",
            "done":"✅","cancelled":"❌"}.get(s, "💬")

async def _count_unread(order_id: int, user_id: int) -> int:
    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as d:
        async with d.execute(
            "SELECT COUNT(*) FROM messages WHERE order_id=? AND receiver_id=? AND is_read=0",
            (order_id, user_id)
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0

def kb_dialogs_menu(orders_info: list):
    buttons = []
    for oid, label, unread in orders_info:
        badge = f"  🔴{unread}" if unread else ""
        buttons.append([InlineKeyboardButton(text=f"{label}{badge}", callback_data=f"order_chat_{oid}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_open_order(order_id: int, partner_nick: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"💬 Открыть диалог с {partner_nick}", callback_data=f"order_chat_{order_id}")
    ]])

def kb_in_chat(order_id: int, role: str, status: str):
    """Кнопки внутри чата"""
    buttons = []
    if role == "seller" and status == "paid":
        buttons.append([InlineKeyboardButton(text="✅ Подтвердить выдачу товара", callback_data=f"seller_confirm_{order_id}")])
    if role == "buyer" and status in ("paid", "seller_confirmed"):
        buttons.append([InlineKeyboardButton(text="✅ Получил — закрыть заказ", callback_data=f"buyer_confirm_{order_id}")])
    buttons.append([InlineKeyboardButton(text="📋 К диалогам", callback_data="messages")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_new_message_notify(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💬 Открыть чат", callback_data=f"order_chat_{order_id}")
    ]])

# ─── СПИСОК ДИАЛОГОВ ─────────────────────────────────────

@router.callback_query(F.data == "messages")
async def show_messages(call: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = call.from_user.id
    orders = await db.get_orders_for_user(uid)

    if not orders:
        try:
            await call.message.edit_text(
                "✉️ <b>Сообщения</b>\n\nНет активных заказов.",
                parse_mode="HTML", reply_markup=kb_back("main_menu")
            )
        except Exception:
            await call.message.answer(
                "✉️ <b>Сообщения</b>\n\nНет активных заказов.",
                parse_mode="HTML", reply_markup=kb_back("main_menu")
            )
        return

    orders_info = []
    for o in orders:
        partner_id = o["seller_id"] if o["buyer_id"] == uid else o["buyer_id"]
        partner = await db.get_user(partner_id)
        nick = partner["nickname"] if partner else "Аноним"
        unread = await _count_unread(o["id"], uid)
        label = f"{_status_emoji(o['status'])} {nick}"
        orders_info.append((o["id"], label, unread))

    try:
        await call.message.edit_text(
            "✉️ <b>Мои заказы и переписка</b>\n\nВыбери диалог:",
            parse_mode="HTML", reply_markup=kb_dialogs_menu(orders_info)
        )
    except Exception:
        await call.message.answer(
            "✉️ <b>Мои заказы и переписка</b>\n\nВыбери диалог:",
            parse_mode="HTML", reply_markup=kb_dialogs_menu(orders_info)
        )

# ─── ОТКРЫТЬ ДИАЛОГ ──────────────────────────────────────

@router.callback_query(F.data.startswith("order_chat_"))
async def open_order_chat(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[2])
    uid      = call.from_user.id
    order    = await db.get_order(order_id)
    if not order:
        await call.answer("Заказ не найден.", show_alert=True)
        return

    await db.mark_read(order_id, uid)

    role       = "seller" if order["seller_id"] == uid else "buyer"
    partner_id = order["seller_id"] if role == "buyer" else order["buyer_id"]
    partner    = await db.get_user(partner_id)
    me         = await db.get_user(uid)
    product    = await db.get_product(order["product_id"])

    # Закреплённая шапка заказа
    p_nick = partner["nickname"] if partner else "Аноним"
    my_nick = me["nickname"] if me else "Я"
    prod_title = product["title"] if product else "Товар"

    header = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 <b>{prod_title}</b>\n"
        f"👤 Покупатель: <b>{(await db.get_user(order['buyer_id']))['nickname']}</b>\n"
        f"🏪 Продавец: <b>{(await db.get_user(order['seller_id']))['nickname']}</b>\n"
        f"💰 Сумма: <b>{order['amount']:.0f} ₽</b>\n"
        f"📌 Статус: {_status_emoji(order['status'])} {_status_text(order['status'])}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    # История сообщений
    msgs = await db.get_order_messages(order_id)
    lines = [header, ""]

    for m in msgs[-20:]:
        is_me   = m["sender_id"] == uid
        sender  = me if is_me else partner
        nick    = sender["nickname"] if sender else "?"
        time_s  = str(m["created_at"])[11:16] if m["created_at"] else ""
        read_mk = " ✓✓" if (is_me and m["is_read"]) else (" ✓" if is_me else "")

        prefix = "▶" if is_me else "◀"
        if m["text"]:
            lines.append(f"{prefix} <b>{nick}</b> <i>{time_s}</i>{read_mk}")
            lines.append(f"   {m['text']}\n")
        elif m["media_type"]:
            icon = "📸" if m["media_type"] == "photo" else "🎬"
            lines.append(f"{prefix} <b>{nick}</b> {icon} <i>{time_s}</i>{read_mk}\n")

    if not msgs:
        lines.append("💬 <i>Начни переписку — напиши первым!</i>")

    lines.append("\n✏️ Напиши сообщение:")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = header + "\n\n...(старые сообщения скрыты)\n\n" + "\n".join(lines[-15:])

    await state.update_data(active_order_id=order_id, active_partner_id=partner_id)
    await state.set_state(ChatState.writing)

    kb = kb_in_chat(order_id, role, order["status"])
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb)

# ─── FSM СОСТОЯНИЯ ───────────────────────────────────────

class ChatState(StatesGroup):
    writing = State()

# ─── ОТПРАВКА СООБЩЕНИЯ ──────────────────────────────────

@router.message(ChatState.writing, F.text | F.photo | F.video)
async def send_chat_msg(message: Message, state: FSMContext, bot: Bot):
    data       = await state.get_data()
    order_id   = data.get("active_order_id")
    partner_id = data.get("active_partner_id")

    if not order_id or not partner_id:
        await state.clear()
        return

    order = await db.get_order(order_id)
    if not order or order["status"] in ("done", "cancelled"):
        await message.answer("❌ Заказ закрыт.", reply_markup=kb_back("messages"))
        await state.clear()
        return

    me   = await db.get_user(message.from_user.id)
    role = "seller" if order["seller_id"] == message.from_user.id else "buyer"

    # Сохраняем и пересылаем
    if message.photo:
        fid = message.photo[-1].file_id
        await db.send_msg(order_id, message.from_user.id, partner_id, media_id=fid, media_type="photo")
        # Уведомление партнёру
        await bot.send_photo(
            partner_id, fid,
            caption=f"📸 <b>{me['nickname']}</b>\n<i>Заказ #{order_id}</i>",
            parse_mode="HTML",
            reply_markup=kb_new_message_notify(order_id)
        )
    elif message.video:
        fid = message.video.file_id
        await db.send_msg(order_id, message.from_user.id, partner_id, media_id=fid, media_type="video")
        await bot.send_video(
            partner_id, fid,
            caption=f"🎬 <b>{me['nickname']}</b>\n<i>Заказ #{order_id}</i>",
            parse_mode="HTML",
            reply_markup=kb_new_message_notify(order_id)
        )
    elif message.text:
        await db.send_msg(order_id, message.from_user.id, partner_id, text=message.text)
        partner = await db.get_user(partner_id)
        await bot.send_message(
            partner_id,
            f"✉️ <b>Новые сообщения</b>\n\n"
            f"Вы получили новое сообщение от <b>{me['nickname']}</b>",
            parse_mode="HTML",
            reply_markup=kb_new_message_notify(order_id)
        )

    # Просто убираем клавиатуру у предыдущего и показываем кнопки чата
    # БЕЗ текста "Отправлено" — просто обновляем кнопки
    kb = kb_in_chat(order_id, role, order["status"])
    try:
        await message.answer("✓", reply_markup=kb)
    except Exception:
        pass

# ─── ПРОДАВЕЦ ПОДТВЕРЖДАЕТ ВЫДАЧУ ────────────────────────

@router.callback_query(F.data.startswith("seller_confirm_"))
async def seller_confirm(call: CallbackQuery, bot: Bot):
    order_id = int(call.data.split("_")[2])
    order    = await db.get_order(order_id)

    if not order or order["seller_id"] != call.from_user.id:
        await call.answer("❌ Нет доступа.", show_alert=True)
        return
    if order["status"] != "paid":
        await call.answer("Заказ уже обработан.", show_alert=True)
        return

    await db.update_order_status(order_id, "seller_confirmed")
    product = await db.get_product(order["product_id"])

    await call.message.edit_text(
        f"✅ Ты подтвердил выдачу заказа #{order_id}.\n"
        f"Ждём подтверждения от покупателя.",
        reply_markup=kb_back("messages")
    )

    await bot.send_message(
        order["buyer_id"],
        f"📦 <b>Продавец выдал товар!</b>\n\n"
        f"<b>{product['title'] if product else 'Товар'}</b>\n\n"
        f"Всё получил? Подтверди и оставь отзыв 👇",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Получил — закрыть заказ", callback_data=f"buyer_confirm_{order_id}")
        ]])
    )

# ─── ПОКУПАТЕЛЬ ПОДТВЕРЖДАЕТ ПОЛУЧЕНИЕ ───────────────────

@router.callback_query(F.data.startswith("buyer_confirm_"))
async def buyer_confirm(call: CallbackQuery, bot: Bot):
    order_id = int(call.data.split("_")[2])
    order    = await db.get_order(order_id)

    if not order or order["buyer_id"] != call.from_user.id:
        await call.answer("❌ Нет доступа.", show_alert=True)
        return
    if order["status"] not in ("paid", "seller_confirmed"):
        await call.answer("Заказ уже закрыт.", show_alert=True)
        return

    seller_gets = round(order["amount"] - order["commission"], 2)
    await db.change_balance(order["seller_id"], seller_gets)
    await db.update_order_status(order_id, "done")

    await call.message.edit_text(
        f"✅ <b>Заказ #{order_id} завершён!</b>\n\n"
        f"Оставь отзыв о продавце 👇",
        parse_mode="HTML",
        reply_markup=kb_review(order_id)
    )

    await bot.send_message(
        order["seller_id"],
        f"✅ <b>Заказ #{order_id} завершён!</b>\n"
        f"💰 Зачислено: <b>{seller_gets:.0f} ₽</b>",
        parse_mode="HTML",
        reply_markup=kb_back("wallet")
    )

# ─── ОТЗЫВ ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("review_"))
async def review_rating(call: CallbackQuery, state: FSMContext):
    parts    = call.data.split("_")
    order_id = int(parts[1])
    rating   = int(parts[2])
    await state.update_data(review_order_id=order_id, review_rating=rating)
    await state.set_state(ReviewFSM.text)
    await call.message.edit_text(
        f"{'⭐' * rating}\n\nНапиши комментарий к отзыву или нажми «Пропустить»:",
        reply_markup=kb_skip_review(order_id)
    )

class ReviewFSM(StatesGroup):
    text = State()

@router.message(ReviewFSM.text, F.text)
async def review_text(message: Message, state: FSMContext):
    data     = await state.get_data()
    order_id = data["review_order_id"]
    rating   = data["review_rating"]
    order    = await db.get_order(order_id)
    await db.add_review(order_id, order["seller_id"], message.from_user.id, rating, message.text)
    await state.clear()
    await message.answer(f"✅ Отзыв сохранён! {'⭐' * rating}", reply_markup=kb_main_menu(has_profile=True))

@router.callback_query(F.data.startswith("skip_review_"))
async def skip_review(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("👍 Заказ закрыт.", reply_markup=kb_main_menu(has_profile=True))

# ─── ПРОСМОТР ОТЗЫВОВ ────────────────────────────────────

@router.callback_query(F.data.startswith("reviews_"))
async def show_reviews(call: CallbackQuery):
    seller_id = int(call.data.split("_")[1])
    reviews   = await db.get_seller_reviews(seller_id)
    avg, count = await db.get_seller_rating(seller_id)
    seller    = await db.get_user(seller_id)

    if not reviews:
        await call.answer("У продавца пока нет отзывов.", show_alert=True)
        return

    lines = [
        f"⭐ <b>Отзывы о {seller['nickname']}</b>",
        f"Рейтинг: {'⭐' * round(avg)} ({avg}/5, отзывов: {count})\n"
    ]
    for r in reviews[:10]:
        lines.append(f"{'⭐' * r['rating']} <b>{r['buyer_name']}</b>")
        if r["text"]:
            lines.append(f"<i>{r['text']}</i>")
        lines.append("")

    try:
        await call.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb_back("market"))
    except Exception:
        await call.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb_back("market"))
