from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery

import database as db
from config import DA_LINK, BOT_COMMISSION, ADMIN_ID
from keyboards.inline import kb_confirm_delivery, kb_main_menu, kb_back

router = Router()

@router.callback_query(F.data.startswith("buy_"))
async def start_buy(call: CallbackQuery, bot: Bot):
    product_id = int(call.data.split("_")[1])
    product = await db.get_product(product_id)

    if not product or product["status"] != "active":
        await call.answer("❌ Товар недоступен.", show_alert=True)
        return
    if product["seller_id"] == call.from_user.id:
        await call.answer("❌ Нельзя купить свой товар.", show_alert=True)
        return

    buyer = await db.get_user(call.from_user.id)
    seller = await db.get_user(product["seller_id"])
    commission = round(product["price"] * BOT_COMMISSION, 2)
    seller_gets = round(product["price"] - commission, 2)

    # Создаём заказ
    order_id = await db.create_order(
        call.from_user.id, product["seller_id"],
        product_id, product["price"], commission
    )

    instructions = (
        f"💳 <b>Покупка: {product['title']}</b>\n\n"
        f"💰 Сумма: <b>{product['price']:.0f} ₽</b>\n\n"
        f"📋 <b>Инструкция:</b>\n"
        f"1️⃣ Перейди по ссылке и пополни баланс продавца:\n"
        f"👉 {DA_LINK}\n\n"
        f"2️⃣ В сообщении к донату обязательно напиши:\n"
        f"<code>Заказ #{order_id}</code>\n\n"
        f"3️⃣ После оплаты нажми кнопку «Я оплатил»\n\n"
        f"⚠️ Продавец получит <b>{seller_gets:.0f} ₽</b> после подтверждения выдачи товара."
    )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"paid_{order_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="market")]
    ])

    try:
        await call.message.edit_text(instructions, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await call.message.answer(instructions, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("paid_"))
async def buyer_paid(call: CallbackQuery, bot: Bot):
    order_id = int(call.data.split("_")[1])
    order = await db.get_order(order_id)

    if not order or order["buyer_id"] != call.from_user.id:
        await call.answer("Заказ не найден.", show_alert=True)
        return

    product = await db.get_product(order["product_id"])
    buyer = await db.get_user(call.from_user.id)
    seller_gets = round(order["amount"] - order["commission"], 2)

    await call.message.edit_text(
        f"⏳ Оплата отправлена на проверку.\n\n"
        f"Продавец получит уведомление и выдаст товар после подтверждения.",
        reply_markup=kb_main_menu(has_profile=True)
    )

    # Уведомляем продавца
    await bot.send_message(
        order["seller_id"],
        f"🔔 <b>Новый заказ #{order_id}!</b>\n\n"
        f"📦 Товар: <b>{product['title']}</b>\n"
        f"👤 Покупатель: {buyer['nickname'] or 'Аноним'}\n"
        f"💰 Ты получишь: <b>{seller_gets:.0f} ₽</b>\n\n"
        f"Проверь DonationAlerts — после получения доната нажми кнопку 👇",
        parse_mode="HTML",
        reply_markup=kb_confirm_delivery(order_id)
    )

    # Уведомляем админа
    await bot.send_message(
        ADMIN_ID,
        f"🛒 Новый заказ #{order_id}\n"
        f"Покупатель: {call.from_user.id}\n"
        f"Продавец: {order['seller_id']}\n"
        f"Сумма: {order['amount']:.0f} ₽"
    )

@router.callback_query(F.data.startswith("deliver_"))
async def confirm_delivery(call: CallbackQuery, bot: Bot):
    order_id = int(call.data.split("_")[1])
    order = await db.get_order(order_id)

    if not order:
        await call.answer("Заказ не найден.", show_alert=True)
        return
    if order["seller_id"] != call.from_user.id:
        await call.answer("❌ Это не твой заказ.", show_alert=True)
        return
    if order["status"] != "pending":
        await call.answer("Заказ уже обработан.", show_alert=True)
        return

    seller_gets = round(order["amount"] - order["commission"], 2)
    await db.change_balance(order["seller_id"], seller_gets)
    await db.confirm_order(order_id)

    product = await db.get_product(order["product_id"])

    await call.message.edit_text(
        f"✅ Выдача подтверждена!\n"
        f"💰 На баланс зачислено <b>{seller_gets:.0f} ₽</b>",
        parse_mode="HTML"
    )

    await bot.send_message(
        order["buyer_id"],
        f"✅ Продавец подтвердил выдачу товара <b>{product['title']}</b>!\n"
        f"Если возникли проблемы — обратись в поддержку.",
        parse_mode="HTML"
    )
