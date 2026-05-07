from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import MIN_WITHDRAW, ADMIN_ID, DA_LINK
from da_checker import check_donation
from keyboards.inline import kb_wallet, kb_main_menu, kb_cancel, kb_back, kb_topup_confirm

router = Router()

class WithdrawFSM(StatesGroup):
    amount = State()

class TopupFSM(StatesGroup):
    waiting = State()

@router.callback_query(F.data == "wallet")
async def show_wallet(call: CallbackQuery):
    balance = await db.get_balance(call.from_user.id)
    try:
        await call.message.edit_text(
            f"💰 <b>Кошелёк</b>\n\nБаланс: <b>{balance:.0f} ₽</b>\n\nМин. вывод: {MIN_WITHDRAW} ₽",
            parse_mode="HTML", reply_markup=kb_wallet()
        )
    except Exception:
        await call.message.answer(
            f"💰 <b>Кошелёк</b>\n\nБаланс: <b>{balance:.0f} ₽</b>",
            parse_mode="HTML", reply_markup=kb_wallet()
        )

# ─── ПОПОЛНЕНИЕ ──────────────────────────────────────────

@router.callback_query(F.data == "topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    da_comment = f"Топап {uid}"
    await state.update_data(topup_comment=da_comment)
    await state.set_state(TopupFSM.waiting)

    await call.message.edit_text(
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"1️⃣ Перейди на DonationAlerts:\n👉 {DA_LINK}\n\n"
        f"2️⃣ В поле «Сообщение» напиши точно:\n"
        f"<code>{da_comment}</code>\n\n"
        f"3️⃣ Укажи сумму пополнения\n\n"
        f"4️⃣ После оплаты нажми «Я оплатил» 👇",
        parse_mode="HTML",
        reply_markup=kb_topup_confirm()
    )

@router.callback_query(F.data == "topup_paid", TopupFSM.waiting)
async def topup_check(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    da_comment = data.get("topup_comment", f"Топап {call.from_user.id}")

    await call.answer("⏳ Проверяем...", show_alert=False)
    result = await check_donation(da_comment, 1.0)  # минимум 1 руб

    if result is True:
        # Ищем сумму доната
        from da_checker import _get_donation_amount
        amount = await _get_donation_amount(da_comment)
        if amount and amount > 0:
            await db.change_balance(call.from_user.id, amount)
            await state.clear()
            balance = await db.get_balance(call.from_user.id)
            await call.message.edit_text(
                f"✅ Баланс пополнен на <b>{amount:.0f} ₽</b>!\n"
                f"Текущий баланс: <b>{balance:.0f} ₽</b>",
                parse_mode="HTML",
                reply_markup=kb_wallet()
            )
        else:
            await call.message.edit_text(
                "✅ Донат найден! Обращайся к администратору для зачисления.\n"
                f"/topup_help",
                reply_markup=kb_wallet()
            )
            await state.clear()
    elif result is False:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить снова", callback_data="topup_paid")],
            [InlineKeyboardButton(text="◀️ Назад",           callback_data="wallet")]
        ])
        await call.message.edit_text(
            f"❌ Донат не найден.\n\n"
            f"Убедись что в сообщении написано: <code>{da_comment}</code>\n\n"
            f"Попробуй через минуту 👇",
            parse_mode="HTML", reply_markup=kb
        )
    else:
        # Ручная проверка
        await state.clear()
        await call.message.edit_text(
            f"⏳ Заявка отправлена на проверку.\nАдминистратор зачислит средства в течение 1 часа.",
            reply_markup=kb_wallet()
        )
        await bot.send_message(
            ADMIN_ID,
            f"💳 Пополнение от {call.from_user.id}\n"
            f"Комментарий: <code>{da_comment}</code>\n\n"
            f"Зачислить: /addbalance_{call.from_user.id}_<сумма>",
            parse_mode="HTML"
        )

# ─── ВЫВОД ───────────────────────────────────────────────

@router.callback_query(F.data == "request_withdraw")
async def request_withdraw(call: CallbackQuery, state: FSMContext):
    balance = await db.get_balance(call.from_user.id)
    if balance < MIN_WITHDRAW:
        await call.answer(f"❌ Мин. вывод {MIN_WITHDRAW} ₽. У тебя {balance:.0f} ₽.", show_alert=True)
        return
    await state.set_state(WithdrawFSM.amount)
    await call.message.edit_text(
        f"💸 Баланс: <b>{balance:.0f} ₽</b>\nВведи сумму вывода (мин. {MIN_WITHDRAW} ₽):",
        parse_mode="HTML", reply_markup=kb_cancel("wallet")
    )

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
        await message.answer(f"❌ Недостаточно средств. Баланс: {balance:.0f} ₽:")
        return

    await db.change_balance(message.from_user.id, -amount)
    w_id = await db.create_withdrawal(message.from_user.id, amount)
    await state.clear()

    user = await db.get_user(message.from_user.id)
    await message.answer(
        f"✅ Заявка #{w_id} принята!\n💸 {amount:.0f} ₽ — до 24 часов.",
        parse_mode="HTML", reply_markup=kb_main_menu(has_profile=True)
    )
    await bot.send_message(
        ADMIN_ID,
        f"💸 Вывод #{w_id}\n{user['nickname']} (ID:{message.from_user.id})\n"
        f"Сумма: {amount:.0f} ₽\n✅ /withdraw_done_{w_id}",
        parse_mode="HTML"
    )
