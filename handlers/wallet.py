from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import MIN_WITHDRAW, ADMIN_ID
from keyboards.inline import kb_wallet, kb_main_menu, kb_cancel

router = Router()

class WithdrawFSM(StatesGroup):
    amount = State()

@router.callback_query(F.data == "wallet")
async def show_wallet(call: CallbackQuery):
    balance = await db.get_balance(call.from_user.id)
    await call.message.edit_text(
        f"💰 <b>Кошелёк</b>\n\n"
        f"Баланс: <b>{balance} ⭐</b>\n\n"
        f"Минимальный вывод: {MIN_WITHDRAW} ⭐",
        parse_mode="HTML",
        reply_markup=kb_wallet()
    )

@router.callback_query(F.data == "request_withdraw")
async def request_withdraw(call: CallbackQuery, state: FSMContext):
    balance = await db.get_balance(call.from_user.id)
    if balance < MIN_WITHDRAW:
        await call.answer(
            f"❌ Минимальный вывод {MIN_WITHDRAW} ⭐. У тебя {balance} ⭐.",
            show_alert=True
        )
        return
    await call.message.edit_text(
        f"💸 <b>Вывод средств</b>\n\n"
        f"Твой баланс: <b>{balance} ⭐</b>\n"
        f"Введи сумму для вывода (мин. {MIN_WITHDRAW}):",
        parse_mode="HTML",
        reply_markup=kb_cancel()
    )
    await state.set_state(WithdrawFSM.amount)

@router.message(WithdrawFSM.amount)
async def process_withdraw(message: Message, state: FSMContext, bot: Bot):
    if not message.text.isdigit():
        await message.answer("❌ Введи число:")
        return
    amount = int(message.text)
    balance = await db.get_balance(message.from_user.id)

    if amount < MIN_WITHDRAW:
        await message.answer(f"❌ Минимум {MIN_WITHDRAW} ⭐:")
        return
    if amount > balance:
        await message.answer(f"❌ Недостаточно средств. Баланс: {balance} ⭐:")
        return

    # Списываем с баланса
    await db.change_balance(message.from_user.id, -amount)
    withdrawal_id = await db.create_withdrawal(message.from_user.id, amount)

    await state.clear()

    user = await db.get_user(message.from_user.id)
    await message.answer(
        f"✅ Заявка на вывод <b>{amount} ⭐</b> принята!\n"
        f"⏳ Обработка в течение 24 часов.",
        parse_mode="HTML",
        reply_markup=kb_main_menu(has_profile=True)
    )

    # Уведомляем админа
    await bot.send_message(
        ADMIN_ID,
        f"💸 <b>Запрос на вывод #{withdrawal_id}</b>\n\n"
        f"👤 Пользователь: {user['nickname']} (ID: {message.from_user.id})\n"
        f"💰 Сумма: <b>{amount} ⭐</b>\n\n"
        f"Подтверди: /withdraw_done_{withdrawal_id}",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "pending_orders")
async def pending_orders(call: CallbackQuery):
    orders = await db.get_pending_orders_for_seller(call.from_user.id)
    if not orders:
        await call.answer("У тебя нет ожидающих заказов.", show_alert=True)
        return
    lines = []
    for o in orders:
        product = await db.get_product(o["product_id"])
        lines.append(f"• Заказ #{o['id']}: {product['title']} — {o['amount']} ⭐")
    await call.message.edit_text(
        "⏳ <b>Ожидающие заказы:</b>\n\n" + "\n".join(lines),
        parse_mode="HTML",
        reply_markup=kb_wallet()
    )
