from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import DA_LINK, BOT_COMMISSION, ADMIN_ID
from da_checker import get_donation_amount_by_comment
from keyboards.inline import kb_main_menu

router = Router()

class BuyFSM(StatesGroup):
    waiting_payment = State()

def kb_insufficient(product_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup")],
        [InlineKeyboardButton(text="◀️ Назад",            callback_data=f"product_{product_id}")]
    ])

def kb_pay_da(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил — проверить", callback_data=f"check_payment_{order_id}")],
        [InlineKeyboardButton(text="❌ Отмена",                callback_data="market")]
    ])

def kb_not_paid(order_id: int, da_comment: str, amount: float):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить снова", callback_data=f"check_payment_{order_id}")],
        [InlineKeyboardButton(text="❌ Отмена",           callback_data="market")]
    ])

@router.callback_query(F.data.startswith("buy_"))
async def start_buy(call: CallbackQuery, state: FSMContext, bot: Bot):
    product_id = int(call.data.split("_")[1])
    product = await db.get_product(product_id)

    if not product or product["status"] != "active":
        await call.answer("❌ Товар недоступен.", show_alert=True)
        return
    if product["seller_id"] == call.from_user.id:
        await call.answer("❌ Нельзя купить свой товар.", show_alert=True)
        return

    price      = product["price"]
    commission = round(price * BOT_COMMISSION, 2)
    seller_gets = round(price - commission, 2)
    balance    = await db.get_balance(call.from_user.id)

    # ── Достаточно средств на балансе — платим с баланса ──
    if balance >= price:
        await db.change_balance(call.from_user.id, -price)
        order_id = await db.create_order(
            call.from_user.id, product["seller_id"],
            product_id, price, commission, ""
        )
        await db.update_order_status(order_id, "paid")

        seller = await db.get_user(product["seller_id"])
        s_nick = seller["nickname"] if seller else "продавец"
        new_balance = balance - price
        await call.message.edit_text(
            f"✅ <b>Товар приобретён!</b>\n\n"
            f"📦 {product['title']}\n"
            f"💰 Списано: <b>{price:.0f} ₽</b>\n"
            f"💳 Ваш баланс: <b>{new_balance:.0f} ₽</b>\n\n"
            f"Диалог с продавцом открыт — он получил уведомление.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=f"💬 Открыть диалог с {s_nick}", callback_data=f"order_chat_{order_id}")
            ]])
        )
        seller = await db.get_user(product["seller_id"])
        buyer  = await db.get_user(call.from_user.id)
        await bot.send_message(
            product["seller_id"],
            f"💸 <b>Новый заказ!</b>\n\n"
            f"Вы получили новый заказ от <b>{buyer['nickname']}</b>\n\n"
            f"📦 {product['title']}\n"
            f"💰 Вы получите: <b>{seller_gets:.0f} ₽</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📦 Открыть заказ", callback_data=f"order_chat_{order_id}")
            ]])
        )
        await bot.send_message(ADMIN_ID,
            f"✅ Заказ #{order_id} оплачен с баланса\n"
            f"Покупатель: {call.from_user.id} | Сумма: {price:.0f} ₽")
        return

    # ── Недостаточно средств — предлагаем пополнить ──
    if balance > 0 and balance < price:
        need = price - balance
        try:
            await call.message.edit_text(
                f"❌ <b>Недостаточно средств</b>\n\n"
                f"💰 Цена товара: <b>{price:.0f} ₽</b>\n"
                f"💳 Твой баланс: <b>{balance:.0f} ₽</b>\n"
                f"📉 Не хватает: <b>{need:.0f} ₽</b>\n\n"
                f"Пополни баланс и вернись к покупке 👇",
                parse_mode="HTML",
                reply_markup=kb_insufficient(product_id)
            )
        except Exception:
            await call.message.answer(
                f"❌ <b>Недостаточно средств</b>\n\nНе хватает: <b>{need:.0f} ₽</b>",
                parse_mode="HTML",
                reply_markup=kb_insufficient(product_id)
            )
        return

    # ── Баланс 0 — оплата через DonationAlerts ──
    import random, string
    rand_code  = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    da_comment = f"PAY-{rand_code}"

    order_id = await db.create_order(
        call.from_user.id, product["seller_id"],
        product_id, price, commission, da_comment
    )
    await db.update_order_status(order_id, "pending_payment")
    await state.update_data(order_id=order_id, amount=price, da_comment=da_comment)
    await state.set_state(BuyFSM.waiting_payment)

    text = (
        f"💳 <b>Оплата заказа #{order_id}</b>\n\n"
        f"📦 {product['title']}\n"
        f"💰 Сумма: <b>{price:.0f} ₽</b>\n\n"
        f"<b>Как оплатить:</b>\n"
        f"1️⃣ Перейди на DonationAlerts:\n👉 {DA_LINK}\n\n"
        f"2️⃣ В поле «Сообщение» скопируй и вставь:\n\n"
        f"<code>{da_comment}</code>\n\n"
        f"3️⃣ Сумма доната: <b>{price:.0f} ₽</b>\n\n"
        f"4️⃣ После оплаты нажми кнопку 👇"
    )
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_pay_da(order_id))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_pay_da(order_id))


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(call: CallbackQuery, state: FSMContext, bot: Bot):
    order_id = int(call.data.split("_")[2])
    order    = await db.get_order(order_id)

    if not order or order["buyer_id"] != call.from_user.id:
        await call.answer("Заказ не найден.", show_alert=True)
        return
    if order["status"] != "pending_payment":
        await call.answer("Заказ уже обработан.", show_alert=True)
        return

    from config import DA_TOKEN
    if not DA_TOKEN:
        await call.answer("⚠️ Автопроверка недоступна — токен DA не настроен.", show_alert=True)
        return

    await call.answer("⏳ Проверяем оплату...", show_alert=False)

    used_ids = await db.get_used_donation_ids()
    from da_checker import find_matching_donation
    don = await find_matching_donation(order["da_comment"], order["amount"], used_ids)
    product = await db.get_product(order["product_id"])

    if don:
        don_id = don.get("id")
        if don_id and await db.is_donation_used(don_id):
            await call.answer("✅ Уже зачислено.", show_alert=True)
            await state.clear()
            return
        if don_id:
            await db.mark_donation_used(don_id)

        await db.update_order_status(order_id, "paid")
        seller_gets = round(order["amount"] - order["commission"], 2)
        await state.clear()

        seller = await db.get_user(order["seller_id"])
        s_nick = seller["nickname"] if seller else "продавец"
        await call.message.edit_text(
            f"✅ <b>Товар приобретён!</b>\n\n"
            f"📦 {product['title'] if product else '?'}\n"
            f"💰 Оплачено: <b>{order['amount']:.0f} ₽</b>\n\n"
            f"Диалог с продавцом открыт — он получил уведомление.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=f"💬 Открыть диалог с {s_nick}", callback_data=f"order_chat_{order_id}")
            ]])
        )
        buyer = await db.get_user(call.from_user.id)
        await bot.send_message(
            order["seller_id"],
            f"💸 <b>Новый заказ!</b>\n\n"
            f"Вы получили новый заказ от <b>{buyer['nickname']}</b>\n\n"
            f"📦 {product['title'] if product else '?'}\n"
            f"💰 Вы получите: <b>{seller_gets:.0f} ₽</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📦 Открыть заказ", callback_data=f"order_chat_{order_id}")
            ]])
        )
        await bot.send_message(ADMIN_ID,
            f"✅ Заказ #{order_id} оплачен через DA\n"
            f"Покупатель: {call.from_user.id} | Сумма: {order['amount']:.0f} ₽")
    else:
        da_comment = order["da_comment"]
        amount     = order["amount"]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить снова", callback_data=f"check_payment_{order_id}")],
            [InlineKeyboardButton(text="❌ Отмена",           callback_data="market")]
        ])
        await call.message.edit_text(
            f"❌ <b>Оплата не найдена</b>\n\n"
            f"Повтори шаги:\n\n"
            f"1️⃣ Перейди: {DA_LINK}\n\n"
            f"2️⃣ Скопируй код (нажми чтобы скопировать):\n\n"
            f"<code>{da_comment}</code>\n\n"
            f"3️⃣ Сумма: <b>{amount:.0f} ₽</b>\n\n"
            f"💡 Бот проверяет автоматически каждые 15 сек.",
            parse_mode="HTML", reply_markup=kb
        )
