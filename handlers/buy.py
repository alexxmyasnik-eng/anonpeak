from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message, LabeledPrice, PreCheckoutQuery
)

import database as db
from config import BOT_COMMISSION, ADMIN_ID
from keyboards.inline import kb_confirm_delivery, kb_main_menu

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

    # Отправляем инвойс в Telegram Stars
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=product["title"],
        description=product["description"][:255],
        payload=f"buy_{product_id}",
        currency="XTR",           # XTR = Telegram Stars
        prices=[LabeledPrice(label=product["title"], amount=product["price"])],
        provider_token=""          # пустой для Stars
    )
    await call.answer()

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    # Всегда одобряем
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot):
    payload = message.successful_payment.invoice_payload  # "buy_<product_id>"
    product_id = int(payload.split("_")[1])
    product = await db.get_product(product_id)

    if not product:
        return

    buyer_id  = message.from_user.id
    seller_id = product["seller_id"]
    amount    = product["price"]
    commission = int(amount * BOT_COMMISSION)
    seller_gets = amount - commission

    # Создаём заказ — деньги "на удержании"
    order_id = await db.create_order(buyer_id, seller_id, product_id, amount, commission)

    buyer = await db.get_user(buyer_id)
    seller = await db.get_user(seller_id)

    # Уведомляем покупателя
    await message.answer(
        f"✅ Оплата прошла!\n\n"
        f"📦 Товар: <b>{product['title']}</b>\n"
        f"💰 Оплачено: <b>{amount} ⭐</b>\n\n"
        f"⏳ Ожидай — продавец получил уведомление и подтвердит выдачу.",
        parse_mode="HTML"
    )

    # Уведомляем продавца
    await bot.send_message(
        seller_id,
        f"🔔 <b>Новый заказ!</b>\n\n"
        f"📦 Товар: <b>{product['title']}</b>\n"
        f"👤 Покупатель: {buyer['nickname'] or 'Аноним'}\n"
        f"💰 Ты получишь: <b>{seller_gets} ⭐</b> (после подтверждения)\n\n"
        f"После выдачи товара нажми кнопку ниже 👇",
        parse_mode="HTML",
        reply_markup=kb_confirm_delivery(order_id)
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

    seller_gets = order["amount"] - order["commission"]

    # Зачисляем продавцу на баланс бота
    await db.change_balance(order["seller_id"], seller_gets)
    await db.confirm_order(order_id)

    product = await db.get_product(order["product_id"])

    # Уведомляем продавца
    await call.message.edit_text(
        f"✅ Выдача подтверждена!\n"
        f"💰 На твой баланс зачислено <b>{seller_gets} ⭐</b>",
        parse_mode="HTML"
    )

    # Уведомляем покупателя
    await bot.send_message(
        order["buyer_id"],
        f"✅ Продавец подтвердил выдачу товара <b>{product['title']}</b>!\n\n"
        f"Если возникли проблемы — обратись в поддержку.",
        parse_mode="HTML"
    )

    # Уведомляем admin
    await bot.send_message(
        ADMIN_ID,
        f"💸 Заказ #{order_id} выполнен.\n"
        f"Продавец: {order['seller_id']}\n"
        f"Сумма: {order['amount']} ⭐ | Комиссия: {order['commission']} ⭐"
    )
