from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import MIN_WITHDRAW, ADMIN_ID, DA_LINK, DA_TOKEN
from da_checker import fetch_recent_donations, find_matching_donation
from keyboards.inline import kb_wallet, kb_main_menu, kb_cancel

router = Router()

TOPUP_AMOUNTS = [100, 250, 500, 1000, 2500, 5000]

class WithdrawFSM(StatesGroup):
    amount = State()

class TopupFSM(StatesGroup):
    amount_chosen = State()   # ввод своей суммы
    waiting       = State()   # ждём «Я оплатил»


def kb_topup_amounts():
    rows = []
    for i in range(0, len(TOPUP_AMOUNTS), 3):
        rows.append([
            InlineKeyboardButton(text=f"{a} ₽", callback_data=f"topup_amount_{a}")
            for a in TOPUP_AMOUNTS[i:i+3]
        ])
    rows.append([InlineKeyboardButton(text="✏️ Своя сумма", callback_data="topup_amount_custom")])
    rows.append([InlineKeyboardButton(text="◀️ Назад",      callback_data="wallet")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_topup_pay():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил",  callback_data="topup_paid")],
        [InlineKeyboardButton(text="◀️ Отмена",     callback_data="wallet")],
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


# ─── ШАГ 1: ВЫБОР СУММЫ ──────────────────────────────────

@router.callback_query(F.data == "topup")
async def topup_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text(
            "💳 <b>Пополнение баланса</b>\n\nВыбери сумму или введи свою:",
            parse_mode="HTML", reply_markup=kb_topup_amounts()
        )
    except Exception:
        await call.message.answer(
            "💳 <b>Пополнение баланса</b>\n\nВыбери сумму:",
            parse_mode="HTML", reply_markup=kb_topup_amounts()
        )

@router.callback_query(F.data == "topup_amount_custom")
async def topup_custom(call: CallbackQuery, state: FSMContext):
    await state.set_state(TopupFSM.amount_chosen)
    await call.message.edit_text(
        "✏️ Введи сумму пополнения (минимум 10 ₽):",
        reply_markup=kb_cancel("topup")
    )

@router.message(TopupFSM.amount_chosen)
async def topup_custom_input(message: Message, state: FSMContext):
    txt = message.text.strip() if message.text else ""
    if not txt.isdigit() or int(txt) < 10:
        await message.answer("❌ Введи целое число от 10:")
        return
    await _show_pay_screen(message, state, int(txt), is_msg=True)

@router.callback_query(F.data.startswith("topup_amount_") & ~F.data.in_({"topup_amount_custom"}))
async def topup_amount_chosen(call: CallbackQuery, state: FSMContext):
    amount = int(call.data.split("_")[2])
    await _show_pay_screen(call, state, amount, is_msg=False)


async def _show_pay_screen(event, state: FSMContext, amount: int, is_msg: bool):
    uid = event.from_user.id
    # Уникальный код — 6 случайных букв+цифр, чтобы не путались донаты
    import random, string
    rand_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    da_comment = f"PAY-{rand_code}"

    # Сохраняем в БД — поллер найдёт сам, даже если кнопку не нажали
    await db.create_topup(uid, amount, da_comment)
    await state.update_data(topup_comment=da_comment, topup_amount=amount)
    await state.set_state(TopupFSM.waiting)

    da_status = "✅ Автопроверка включена" if DA_TOKEN else "⚠️ Токен DA не настроен"
    text = (
        f"💳 <b>Пополнение на {amount} ₽</b>\n\n"
        f"1️⃣ Перейди на DonationAlerts:\n👉 {DA_LINK}\n\n"
        f"2️⃣ В поле «Сообщение» напиши <b>точно</b>:\n"
        f"<code>{da_comment}</code>\n\n"
        f"3️⃣ Сумма доната: <b>{amount} ₽</b>\n\n"
        f"4️⃣ После оплаты нажми кнопку — или подожди, бот проверит сам\n\n"
        f"<i>{da_status}</i>"
    )
    kb = kb_topup_pay()
    if is_msg:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        try:
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await event.message.answer(text, parse_mode="HTML", reply_markup=kb)


# ─── ШАГ 2: КНОПКА «Я ОПЛАТИЛ» (ручная проверка) ────────

@router.callback_query(F.data == "topup_paid")
async def topup_check(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not DA_TOKEN:
        await call.answer(
            "⚠️ Автопроверка недоступна: токен DA не настроен.",
            show_alert=True
        )
        return

    data = await state.get_data()
    da_comment      = data.get("topup_comment")
    expected_amount = data.get("topup_amount", 1)

    if not da_comment:
        await call.answer("❌ Сначала выбери сумму пополнения.", show_alert=True)
        return

    # Проверяем — не закрыт ли уже этот топап
    pending = await db.get_pending_topups()
    topup = next(
        (t for t in pending
         if t["user_id"] == call.from_user.id and t["da_comment"] == da_comment),
        None
    )
    if not topup:
        await call.answer("✅ Этот топап уже обработан.", show_alert=True)
        await state.clear()
        return

    await call.answer("⏳ Проверяем оплату...", show_alert=False)

    donations = await fetch_recent_donations(pages=3)
    used_ids  = await db.get_used_donation_ids()
    don = await find_matching_donation(da_comment, expected_amount, used_ids)

    if don:
        don_id       = don.get("id")
        found_amount = float(don.get("amount") or 0)

        # Защита от гонки: проверяем ещё раз перед записью
        if don_id and await db.is_donation_used(don_id):
            await call.answer("✅ Уже зачислено (поллер успел раньше).", show_alert=True)
            await state.clear()
            return

        # Атомарно помечаем донат и закрываем топап
        if don_id:
            await db.mark_donation_used(don_id)
        await db.complete_topup(topup["id"])
        await db.change_balance(call.from_user.id, found_amount)
        await state.clear()

        balance = await db.get_balance(call.from_user.id)
        await call.message.edit_text(
            f"✅ <b>Баланс пополнен на {found_amount:.0f} ₽!</b>\n"
            f"💰 Текущий баланс: <b>{balance:.0f} ₽</b>",
            parse_mode="HTML", reply_markup=kb_wallet()
        )
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Проверить снова", callback_data="topup_paid")],
            [InlineKeyboardButton(text="◀️ Отмена",          callback_data="wallet")],
        ])
        from config import DA_LINK as _DA_LINK
        await call.message.edit_text(
            f"❌ <b>Оплата не найдена</b>\n\n"
            f"Повтори шаги:\n\n"
            f"1️⃣ Перейди на DonationAlerts:\n"
            f"👉 {_DA_LINK}\n\n"
            f"2️⃣ В поле «Сообщение» скопируй и вставь <b>точно этот код</b>\n"
            f"(нажми на него чтобы скопировать):\n\n"
            f"<code>{da_comment}</code>\n\n"
            f"3️⃣ Сумма доната: <b>{expected_amount} ₽</b>\n\n"
            f"4️⃣ После оплаты нажми «Проверить снова»\n\n"
            f"💡 Бот проверяет автоматически каждые 15 сек.",
            parse_mode="HTML", reply_markup=kb
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
