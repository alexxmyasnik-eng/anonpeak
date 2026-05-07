from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import MIN_WITHDRAW, ADMIN_ID, DA_LINK
from da_checker import check_donation, get_donation_amount_by_comment
from keyboards.inline import kb_wallet, kb_main_menu, kb_cancel, kb_back

router = Router()

TOPUP_AMOUNTS = [100, 250, 500, 1000, 2500, 5000]

class WithdrawFSM(StatesGroup):
    amount = State()

class TopupFSM(StatesGroup):
    amount_chosen = State()   # пользователь выбрал сумму
    waiting       = State()   # ждём нажатия «Я оплатил»


def kb_topup_amounts():
    rows = []
    for i in range(0, len(TOPUP_AMOUNTS), 3):
        rows.append([
            InlineKeyboardButton(text=f"{a} ₽", callback_data=f"topup_amount_{a}")
            for a in TOPUP_AMOUNTS[i:i+3]
        ])
    rows.append([InlineKeyboardButton(text="✏️ Своя сумма", callback_data="topup_amount_custom")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="wallet")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_topup_pay(order_id=None):
    cb = f"topup_paid_{order_id}" if order_id else "topup_paid"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=cb)],
        [InlineKeyboardButton(text="◀️ Назад",     callback_data="topup")],
    ])


# ─── КОШЕЛЁК ─────────────────────────────────────────────

@router.callback_query(F.data == "wallet")
async def show_wallet(call: CallbackQuery, state: FSMContext):
    await state.clear()
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


# ─── ПОПОЛНЕНИЕ — ШАГ 1: ВЫБОР СУММЫ ────────────────────

@router.callback_query(F.data == "topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text(
            "💳 <b>Пополнение баланса</b>\n\nВыбери сумму или введи свою:",
            parse_mode="HTML",
            reply_markup=kb_topup_amounts()
        )
    except Exception:
        await call.message.answer(
            "💳 <b>Пополнение баланса</b>\n\nВыбери сумму или введи свою:",
            parse_mode="HTML",
            reply_markup=kb_topup_amounts()
        )

@router.callback_query(F.data == "topup_amount_custom")
async def topup_custom_amount(call: CallbackQuery, state: FSMContext):
    await state.set_state(TopupFSM.amount_chosen)
    await call.message.edit_text(
        "✏️ Введи сумму пополнения (минимум 10 ₽):",
        reply_markup=kb_cancel("topup")
    )

@router.message(TopupFSM.amount_chosen)
async def topup_custom_input(message: Message, state: FSMContext):
    txt = message.text.strip() if message.text else ""
    if not txt.isdigit() or int(txt) < 10:
        await message.answer("❌ Введи число от 10:")
        return
    amount = int(txt)
    await _show_payment_instructions(message, state, amount, is_message=True)

@router.callback_query(F.data.startswith("topup_amount_") & ~F.data.in_({"topup_amount_custom"}))
async def topup_amount_chosen(call: CallbackQuery, state: FSMContext):
    amount = int(call.data.split("_")[2])
    await _show_payment_instructions(call, state, amount, is_message=False)


async def _show_payment_instructions(event, state: FSMContext, amount: int, is_message: bool):
    uid = event.from_user.id
    da_comment = f"Топап {uid} {amount}"

    # Сохраняем сумму и комментарий — чтобы при проверке знали точно что искать
    await state.update_data(topup_comment=da_comment, topup_amount=amount)
    await state.set_state(TopupFSM.waiting)

    text = (
        f"💳 <b>Пополнение на {amount} ₽</b>\n\n"
        f"1️⃣ Перейди на DonationAlerts:\n👉 {DA_LINK}\n\n"
        f"2️⃣ В поле «Сообщение» напиши <b>точно</b>:\n"
        f"<code>{da_comment}</code>\n\n"
        f"3️⃣ Сумма доната: <b>{amount} ₽</b>\n\n"
        f"4️⃣ После оплаты нажми кнопку 👇"
    )
    kb = kb_topup_pay()
    if is_message:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        try:
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await event.message.answer(text, parse_mode="HTML", reply_markup=kb)


# ─── ПОПОЛНЕНИЕ — ШАГ 2: ПРОВЕРКА ОПЛАТЫ ────────────────

@router.callback_query(F.data == "topup_paid")
async def topup_check(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    da_comment = data.get("topup_comment")
    expected_amount = data.get("topup_amount", 1)

    # Нет данных в стейте — значит кнопку нажали не из нужного состояния
    if not da_comment:
        await call.answer("❌ Сначала выбери сумму.", show_alert=True)
        return

    # Если токен DA вообще не настроен — честно говорим
    from config import DA_TOKEN
    if not DA_TOKEN:
        await call.answer("⚠️ Автопроверка недоступна — токен DA не настроен.", show_alert=True)
        return

    await call.answer("⏳ Проверяем оплату...", show_alert=False)

    found_amount = await get_donation_amount_by_comment(da_comment, expected_amount)

    if found_amount and found_amount > 0:
        # ✅ Оплата найдена — зачисляем автоматически
        await db.change_balance(call.from_user.id, found_amount)
        await state.clear()
        balance = await db.get_balance(call.from_user.id)
        await call.message.edit_text(
            f"✅ <b>Баланс пополнен на {found_amount:.0f} ₽!</b>\n"
            f"💰 Текущий баланс: <b>{balance:.0f} ₽</b>",
            parse_mode="HTML",
            reply_markup=kb_wallet()
        )
    else:
        # ❌ Оплата не найдена — даём повторить
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить снова", callback_data="topup_paid")],
            [InlineKeyboardButton(text="◀️ Отмена",          callback_data="wallet")],
        ])
        await call.message.edit_text(
            f"❌ <b>Оплата не найдена</b>\n\n"
            f"Убедись что:\n"
            f"• Сумма: <b>{expected_amount} ₽</b>\n"
            f"• В сообщении написано точно:\n<code>{da_comment}</code>\n\n"
            f"Подожди 1–2 минуты и проверь снова 👇",
            parse_mode="HTML",
            reply_markup=kb
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
