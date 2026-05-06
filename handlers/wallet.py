from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import MIN_WITHDRAW, ADMIN_ID, DA_LINK
from keyboards.inline import kb_wallet, kb_main_menu, kb_cancel, kb_back

router = Router()

class WithdrawFSM(StatesGroup):
    amount = State()

@router.callback_query(F.data == "wallet")
async def show_wallet(call: CallbackQuery):
    balance = await db.get_balance(call.from_user.id)
    try:
        await call.message.edit_text(
            f"💰 <b>Кошелёк</b>\n\n"
            f"Баланс: <b>{balance:.0f} ₽</b>\n\n"
            f"Минимальный вывод: {MIN_WITHDRAW} ₽",
            parse_mode="HTML",
            reply_markup=kb_wallet()
        )
    except Exception:
        await call.message.answer(
            f"💰 <b>Кошелёк</b>\n\nБаланс: <b>{balance:.0f} ₽</b>",
            parse_mode="HTML",
            reply_markup=kb_wallet()
        )

@router.callback_query(F.data == "topup")
async def topup_balance(call: CallbackQuery):
    await call.message.edit_text(
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"Перейди по ссылке и сделай донат:\n"
        f"👉 {DA_LINK}\n\n"
        f"В сообщении к донату напиши:\n"
        f"<code>Пополнение {call.from_user.id}</code>\n\n"
        f"После оплаты администратор зачислит средства вручную.\n"
        f"Обычно это занимает до 1 часа.",
        parse_mode="HTML",
        reply_markup=kb_back("wallet")
    )

@router.callback_query(F.data == "request_withdraw")
async def request_withdraw(call: CallbackQuery, state: FSMContext):
    balance = await db.get_balance(call.from_user.id)
    if balance < MIN_WITHDRAW:
        await call.answer(
            f"❌ Минимальный вывод {MIN_WITHDRAW} ₽. У тебя {balance:.0f} ₽.",
            show_alert=True
        )
        return
    await call.message.edit_text(
        f"💸 <b>Вывод средств</b>\n\n"
        f"Баланс: <b>{balance:.0f} ₽</b>\n"
        f"Введи сумму для вывода (мин. {MIN_WITHDRAW} ₽):",
        parse_mode="HTML",
        reply_markup=kb_cancel("wallet")
    )
    await state.set_state(WithdrawFSM.amount)

@router.message(WithdrawFSM.amount)
async def process_withdraw(message: Message, state: FSMContext, bot: Bot):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Введи число:")
        return
    amount = float(message.text)
    balance = await db.get_balance(message.from_user.id)

    if amount < MIN_WITHDRAW:
        await message.answer(f"❌ Минимум {MIN_WITHDRAW} ₽:")
        return
    if amount > balance:
        await message.answer(f"❌ Недостаточно. Баланс: {balance:.0f} ₽:")
        return

    await db.change_balance(message.from_user.id, -amount)
    w_id = await db.create_withdrawal(message.from_user.id, amount)
    await state.clear()

    user = await db.get_user(message.from_user.id)
    await message.answer(
        f"✅ Заявка #{w_id} на вывод <b>{amount:.0f} ₽</b> принята!\n"
        f"⏳ Обработка до 24 часов.",
        parse_mode="HTML",
        reply_markup=kb_main_menu(has_profile=True)
    )

    await bot.send_message(
        ADMIN_ID,
        f"💸 <b>Вывод #{w_id}</b>\n"
        f"👤 {user['nickname']} (ID: {message.from_user.id})\n"
        f"💰 {amount:.0f} ₽\n\n"
        f"✅ /withdraw_done_{w_id}",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "pending_orders")
async def pending_orders(call: CallbackQuery):
    orders = await db.get_pending_orders_for_seller(call.from_user.id)
    if not orders:
        await call.answer("Нет ожидающих заказов.", show_alert=True)
        return
    lines = []
    for o in orders:
        product = await db.get_product(o["product_id"])
        pname = product["title"] if product else "?"
        lines.append(f"• Заказ #{o['id']}: {pname} — {o['amount']:.0f} ₽")
    try:
        await call.message.edit_text(
            "⏳ <b>Ожидающие заказы:</b>\n\n" + "\n".join(lines),
            parse_mode="HTML",
            reply_markup=kb_wallet()
        )
    except Exception:
        await call.message.answer(
            "⏳ <b>Ожидающие заказы:</b>\n\n" + "\n".join(lines),
            parse_mode="HTML",
            reply_markup=kb_wallet()
        )
