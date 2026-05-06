from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command

import database as db
from config import ADMIN_ID, DB_PATH

router = Router()

def is_admin(uid): return uid == ADMIN_ID

@router.message(F.text.startswith("/withdraw_done_"))
async def withdraw_done(message: Message, bot: Bot):
    if not is_admin(message.from_user.id): return
    try:
        w_id = int(message.text.split("_")[-1])
    except ValueError:
        await message.answer("❌ Неверный формат.")
        return

    pending = await db.get_pending_withdrawals()
    target = next((w for w in pending if w["id"] == w_id), None)
    if not target:
        await message.answer("❌ Заявка не найдена или уже выполнена.")
        return

    await db.complete_withdrawal(w_id)
    await message.answer(f"✅ Вывод #{w_id} выполнен.")
    await bot.send_message(
        target["user_id"],
        f"✅ Твой вывод <b>{target['amount']:.0f} ₽</b> выполнен!",
        parse_mode="HTML"
    )

@router.message(F.text.startswith("/addbalance_"))
async def add_balance(message: Message, bot: Bot):
    """Пополнить баланс пользователя вручную: /addbalance_<user_id>_<amount>"""
    if not is_admin(message.from_user.id): return
    try:
        parts = message.text.split("_")
        uid = int(parts[1])
        amount = float(parts[2])
    except (IndexError, ValueError):
        await message.answer("❌ Формат: /addbalance_<user_id>_<сумма>")
        return
    await db.change_balance(uid, amount)
    await message.answer(f"✅ Пользователю {uid} зачислено {amount:.0f} ₽")
    try:
        await bot.send_message(uid, f"💰 На твой баланс зачислено <b>{amount:.0f} ₽</b>!", parse_mode="HTML")
    except Exception:
        pass

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id): return
    pending = await db.get_pending_withdrawals()
    if not pending:
        await message.answer("📋 Нет ожидающих выводов.")
        return
    lines = []
    for w in pending:
        lines.append(f"#{w['id']} | {w['nickname'] or w['username']} (ID:{w['user_id']}) | {w['amount']:.0f} ₽\n→ /withdraw_done_{w['id']}")
    await message.answer("💸 <b>Ожидающие выводы:</b>\n\n" + "\n\n".join(lines), parse_mode="HTML")

@router.message(Command("stats"))
async def stats(message: Message):
    if not is_admin(message.from_user.id): return
    async with __import__("aiosqlite").connect(DB_PATH) as d:
        users    = (await (await d.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        products = (await (await d.execute("SELECT COUNT(*) FROM products WHERE status='active'")).fetchone())[0]
        orders   = (await (await d.execute("SELECT COUNT(*) FROM orders WHERE status='confirmed'")).fetchone())[0]
        earned   = (await (await d.execute("SELECT SUM(commission) FROM orders WHERE status='confirmed'")).fetchone())[0] or 0
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {users}\n"
        f"📦 Активных товаров: {products}\n"
        f"✅ Выполненных заказов: {orders}\n"
        f"💰 Заработано: {earned:.0f} ₽",
        parse_mode="HTML"
    )
