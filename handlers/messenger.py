from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards.inline import kb_dialogs, kb_order_chat, kb_review, kb_skip_review, kb_main_menu, kb_back

router = Router()

class ReviewFSM(StatesGroup):
    text = State()

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
        unread = await _count_order_unread(o["id"], uid)
        status_emoji = _order_status_emoji(o["status"])
        orders_info.append((o["id"], f"{status_emoji} {nick}", unread))

    try:
        await call.message.edit_text(
            "✉️ <b>Мои заказы и переписка</b>\n\nВыбери диалог:",
            parse_mode="HTML", reply_markup=kb_dialogs(orders_info)
        )
    except Exception:
        await call.message.answer(
            "✉️ <b>Мои заказы и переписка</b>\n\nВыбери диалог:",
            parse_mode="HTML", reply_markup=kb_dialogs(orders_info)
        )

async def _count_order_unread(order_id: int, user_id: int) -> int:
    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db_:
        async with db_.execute(
            "SELECT COUNT(*) FROM messages WHERE order_id=? AND receiver_id=? AND is_read=0",
            (order_id, user_id)
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0

def _order_status_emoji(status: str) -> str:
    return {
        "pending_payment": "💳",
        "paid": "📦",
        "seller_confirmed": "⏳",
        "done": "✅",
        "cancelled": "❌"
    }.get(status, "💬")

# ─── ОТКРЫТЬ ДИАЛОГ ──────────────────────────────────────

@router.callback_query(F.data.startswith("order_chat_"))
async def open_order_chat(call: CallbackQuery, state: FSMContext):
    order_id = int(call.data.split("_")[2])
    await _render_chat(call, order_id, state)

async def _render_chat(call: CallbackQuery, order_id: int, state: FSMContext):
    uid = call.from_user.id
    order = await db.get_order(order_id)
    if not order:
        await call.answer("Заказ не найден.", show_alert=True)
        return

    # Помечаем прочитанными
    await db.mark_read(order_id, uid)

    role = "seller" if order["seller_id"] == uid else "buyer"
    partner_id = order["seller_id"] if role == "buyer" else order["buyer_id"]
    partner = await db.get_user(partner_id)
    me = await db.get_user(uid)
    product = await db.get_product(order["product_id"])

    msgs = await db.get_order_messages(order_id)

    # Строим чат
    lines = [
        f"{'─' * 20}",
        f"📦 <b>{product['title'] if product else '?'}</b>",
        f"💰 {order['amount']:.0f} ₽ | {_order_status_emoji(order['status'])} {_status_text(order['status'])}",
        f"{'─' * 20}\n"
    ]

    for m in msgs[-25:]:  # последние 25 сообщений
        sender = me if m["sender_id"] == uid else partner
        nick = sender["nickname"] if sender else "?"
        is_me = m["sender_id"] == uid
        read_mark = " ✓✓" if (is_me and m["is_read"]) else (" ✓" if is_me else "")
        time_str = str(m["created_at"])[:16] if m["created_at"] else ""

        if m["text"]:
            lines.append(f"{'▶️' if is_me else '◀️'} <b>{nick}</b> <i>{time_str}</i>{read_mark}")
            lines.append(f"{m['text']}\n")
        elif m["media_type"]:
            lines.append(f"{'▶️' if is_me else '◀️'} <b>{nick}</b> <i>{time_str}</i>{read_mark}")
            lines.append(f"[{'📸 Фото' if m['media_type'] == 'photo' else '🎬 Видео'}]\n")

    if not msgs:
        lines.append("💬 <i>Напиши первым!</i>")

    lines.append(f"\n{'─' * 20}")
    lines.append("✏️ Напиши сообщение:")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[-4000:]

    await state.update_data(active_order_id=order_id, active_partner_id=partner_id)
    await state.set_state(ChatState.writing)

    kb = kb_order_chat(order_id, role)
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
    data = await state.get_data()
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

    me = await db.get_user(message.from_user.id)
    role = "seller" if order["seller_id"] == message.from_user.id else "buyer"

    # Сохраняем сообщение
    if message.photo:
        await db.send_msg(order_id, message.from_user.id, partner_id,
                          media_id=message.photo[-1].file_id, media_type="photo")
        # Пересылаем партнёру
        await bot.send_photo(partner_id, message.photo[-1].file_id,
                             caption=f"📸 от <b>{me['nickname']}</b> (Заказ #{order_id})",
                             parse_mode="HTML",
                             reply_markup=kb_order_chat(order_id, "seller" if role == "buyer" else "buyer"))
    elif message.video:
        await db.send_msg(order_id, message.from_user.id, partner_id,
                          media_id=message.video.file_id, media_type="video")
        await bot.send_video(partner_id, message.video.file_id,
                             caption=f"🎬 от <b>{me['nickname']}</b> (Заказ #{order_id})",
                             parse_mode="HTML",
                             reply_markup=kb_order_chat(order_id, "seller" if role == "buyer" else "buyer"))
    elif message.text:
        await db.send_msg(order_id, message.from_user.id, partner_id, text=message.text)
        await bot.send_message(partner_id,
                               f"✉️ <b>{me['nickname']}</b> (Заказ #{order_id}):\n{message.text}",
                               parse_mode="HTML",
                               reply_markup=kb_order_chat(order_id, "seller" if role == "buyer" else "buyer"))

    # Подтверждение отправки
    await message.answer(
        "✓ Отправлено",
        reply_markup=kb_order_chat(order_id, role)
    )

# ─── ПРОДАВЕЦ ПОДТВЕРЖДАЕТ ВЫДАЧУ ────────────────────────

@router.callback_query(F.data.startswith("seller_confirm_"))
async def seller_confirm(call: CallbackQuery, bot: Bot):
    order_id = int(call.data.split("_")[2])
    order = await db.get_order(order_id)

    if not order or order["seller_id"] != call.from_user.id:
        await call.answer("❌ Нет доступа.", show_alert=True)
        return
    if order["status"] not in ("paid",):
        await call.answer("Заказ уже обработан.", show_alert=True)
        return

    await db.update_order_status(order_id, "seller_confirmed")

    await call.message.edit_text(
        f"✅ Ты подтвердил выдачу заказа #{order_id}.\n"
        f"Ожидаем подтверждения от покупателя.",
        reply_markup=kb_back("messages")
    )

    await bot.send_message(
        order["buyer_id"],
        f"📦 <b>Продавец отправил/выдал товар!</b>\n\n"
        f"Заказ #{order_id} — проверь и подтверди получение 👇",
        parse_mode="HTML",
        reply_markup=kb_order_chat(order_id, "buyer")
    )

# ─── ПОКУПАТЕЛЬ ПОДТВЕРЖДАЕТ ПОЛУЧЕНИЕ ───────────────────

@router.callback_query(F.data.startswith("buyer_confirm_"))
async def buyer_confirm(call: CallbackQuery, bot: Bot):
    order_id = int(call.data.split("_")[2])
    order = await db.get_order(order_id)

    if not order or order["buyer_id"] != call.from_user.id:
        await call.answer("❌ Нет доступа.", show_alert=True)
        return
    if order["status"] not in ("paid", "seller_confirmed"):
        await call.answer("Заказ уже закрыт.", show_alert=True)
        return

    seller_gets = round(order["amount"] - order["commission"], 2)
    await db.change_balance(order["seller_id"], seller_gets)
    await db.update_order_status(order_id, "done")

    # Просим оставить отзыв
    await call.message.edit_text(
        f"✅ <b>Заказ #{order_id} закрыт!</b>\n\n"
        f"Оставь отзыв о продавце — это поможет другим покупателям 👇",
        parse_mode="HTML",
        reply_markup=kb_review(order_id)
    )

    await bot.send_message(
        order["seller_id"],
        f"✅ <b>Покупатель подтвердил заказ #{order_id}!</b>\n"
        f"💰 Зачислено: <b>{seller_gets:.0f} ₽</b>",
        parse_mode="HTML",
        reply_markup=kb_back("wallet")
    )

# ─── ОТЗЫВ — ВЫБОР ЗВЁЗД ────────────────────────────────

@router.callback_query(F.data.startswith("review_"))
async def review_rating(call: CallbackQuery, state: FSMContext):
    parts = call.data.split("_")
    order_id = int(parts[1])
    rating   = int(parts[2])
    await state.update_data(review_order_id=order_id, review_rating=rating)
    await state.set_state(ReviewFSM.text)
    await call.message.edit_text(
        f"{'⭐' * rating} — отлично!\n\nНапиши комментарий к отзыву\n(или нажми «Пропустить»):",
        reply_markup=kb_skip_review(order_id)
    )

@router.message(ReviewFSM.text, F.text)
async def review_text(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data["review_order_id"]
    rating   = data["review_rating"]
    order = await db.get_order(order_id)
    await db.add_review(order_id, order["seller_id"], message.from_user.id, rating, message.text)
    await state.clear()
    await message.answer(
        f"✅ Отзыв сохранён! {'⭐' * rating}",
        reply_markup=kb_main_menu(has_profile=True)
    )

@router.callback_query(F.data.startswith("skip_review_"))
async def skip_review(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("👍 Спасибо! Заказ закрыт.", reply_markup=kb_main_menu(has_profile=True))

# ─── ПРОСМОТР ОТЗЫВОВ ────────────────────────────────────

@router.callback_query(F.data.startswith("reviews_"))
async def show_reviews(call: CallbackQuery):
    seller_id = int(call.data.split("_")[1])
    reviews = await db.get_seller_reviews(seller_id)
    avg, count = await db.get_seller_rating(seller_id)
    seller = await db.get_user(seller_id)

    if not reviews:
        await call.answer("У продавца пока нет отзывов.", show_alert=True)
        return

    lines = [f"⭐ <b>Отзывы о {seller['nickname']}</b>",
             f"Рейтинг: {'⭐' * round(avg)} ({avg}/5, {count} отзывов)\n"]
    for r in reviews[:10]:
        lines.append(f"{'⭐' * r['rating']} <b>{r['buyer_name']}</b>")
        if r["text"]:
            lines.append(f"<i>{r['text']}</i>")
        lines.append("")

    try:
        await call.message.edit_text("\n".join(lines), parse_mode="HTML",
                                     reply_markup=kb_back("market"))
    except Exception:
        await call.message.answer("\n".join(lines), parse_mode="HTML",
                                  reply_markup=kb_back("market"))

def _status_text(status: str) -> str:
    return {
        "pending_payment": "Ожидает оплаты",
        "paid": "Оплачен",
        "seller_confirmed": "Выдан продавцом",
        "done": "Завершён",
        "cancelled": "Отменён"
    }.get(status, status)
