from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import DA_LINK, BOT_COMMISSION, ADMIN_ID
from da_checker import check_donation
from keyboards.inline import kb_main_menu, kb_back, kb_order_chat

router = Router()

class BuyFSM(StatesGroup):
    waiting_payment = State()

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

    buyer = await db.get_user(call.from_user.id)
    commission = round(product["price"] * BOT_COMMISSION, 2)
    seller_gets = round(product["price"] - commission, 2)
    da_comment = f"Заказ {call.from_user.id}"

    # Создаём заказ в статусе pending_payment
    order_id = await db.create_order(
        call.from_user.id, product["seller_id"],
        product_id, product["price"], commission, da_comment
    )
    await db.update_order_status(order_id, "pending_payment")

    await state.update_data(order_id=order_id, amount=product["price"], da_comment=da_comment)
    await state.set_state(BuyFSM.waiting_payment)

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил — проверить", callback_data=f"check_payment_{order_id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="market")]
    ])

    text = (
        f"💳 <b>Оплата заказа #{order_id}</b>\n\n"
        f"📦 {product['title']}\n"
        f"💰 Сумма: <b>{product['price']:.0f} ₽</b>\n\n"
        f"<b>Как оплатить:</b>\n"
        f"1️⃣ Перейди на DonationAlerts:\n👉 {DA_LINK}\n\n"
        f"2️⃣ В поле «Сообщение» напиши точно:\n"
        f"<code>{da_comment}</code>\n\n"
        f"3️⃣ Сумма доната: <b>{product['price']:.0f} ₽</b>\n\n"
        f"4️⃣ После оплаты нажми кнопку ниже 👇"
    )
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(call: CallbackQuery, state: FSMContext, bot: Bot):
    order_id = int(call.data.split("_")[2])
    order = await db.get_order(order_id)

    if not order or order["buyer_id"] != call.from_user.id:
        await call.answer("Заказ не найден.", show_alert=True)
        return

    await call.answer("⏳ Проверяем оплату...", show_alert=False)

    product = await db.get_product(order["product_id"])
    result = await check_donation(order["da_comment"], order["amount"])

    if result is True:
        # Оплата подтверждена
        await db.update_order_status(order_id, "paid")
        seller_gets = round(order["amount"] - order["commission"], 2)
        buyer = await db.get_user(call.from_user.id)
        await state.clear()

        # Уведомляем покупателя
        await call.message.edit_text(
            f"✅ <b>Оплата подтверждена!</b>\n\n"
            f"Заказ #{order_id} активен.\n"
            f"Переписка с продавцом открыта — жди товар 👇",
            parse_mode="HTML",
            reply_markup=kb_order_chat(order_id, "buyer")
        )

        # Уведомляем продавца
        await bot.send_message(
            order["seller_id"],
            f"🔔 <b>Новый оплаченный заказ #{order_id}!</b>\n\n"
            f"📦 {product['title']}\n"
            f"💰 Ты получишь: <b>{seller_gets:.0f} ₽</b>\n\n"
            f"Отправь товар покупателю в этом чате и подтверди выдачу 👇",
            parse_mode="HTML",
            reply_markup=kb_order_chat(order_id, "seller")
        )

        await bot.send_message(ADMIN_ID,
            f"✅ Заказ #{order_id} оплачен\nПокупатель: {call.from_user.id}\n"
            f"Продавец: {order['seller_id']}\nСумма: {order['amount']:.0f} ₽")

    elif result is False:
        # Оплата не найдена
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить снова", callback_data=f"check_payment_{order_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="market")]
        ])
        await call.message.edit_text(
            f"❌ <b>Оплата не найдена</b>\n\n"
            f"Убедись что:\n"
            f"• Сумма: <b>{order['amount']:.0f} ₽</b>\n"
            f"• В сообщении написано: <code>{order['da_comment']}</code>\n\n"
            f"Попробуй снова через минуту 👇",
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        # Токен DA не настроен — сообщаем что нужно настроить
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
        ])
        await call.message.edit_text(
            "⚠️ Автоматическая проверка оплаты временно недоступна.\n"
            "Попробуй снова позже.",
            reply_markup=kb
        )
        await state.clear()
