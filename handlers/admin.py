from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command

import database as db
from config import ADMIN_ID

router = Router()

def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# Подтвердить вывод: /withdraw_done_<id>
@router.message(F.text.startswith("/withdraw_done_"))
async def withdraw_done(message: Message, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    try:
        withdrawal_id = int(message.text.split("_")[-1])
    except ValueError:
        await message.answer("❌ Неверный формат.")
        return

    withdrawals = await db.get_pending_withdrawals()
    target = next((w for w in withdrawals if w["id"] == withdrawal_id), None)

    if not target:
        await message.answer("❌ Заявка не найдена или уже выполнена.")
        return

    await db.complete_withdrawal(withdrawal_id)

    await message.answer(f"✅ Вывод #{withdrawal_id} помечен как выполненный.")

    # Уведомляем пользователя
    await bot.send_message(
        target["user_id"],
        f"✅ Твой вывод <b>{target['amount']} ⭐</b> выполнен!\n"
        f"Звёзды отправлены.",
        parse_mode="HTML"
    )

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    withdrawals = await db.get_pending_withdrawals()
    if not withdrawals:
        await message.answer("📋 Нет ожидающих выводов.")
        return
    lines = []
    for w in withdrawals:
        lines.append(
            f"#{w['id']} | {w['nickname'] or w['username']} (ID:{w['user_id']}) | {w['amount']} ⭐\n"
            f"  → /withdraw_done_{w['id']}"
        )
    await message.answer("💸 <b>Ожидающие выводы:</b>\n\n" + "\n\n".join(lines), parse_mode="HTML")

@router.message(Command("stats"))
async def stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    async with __import__("aiosqlite").connect(__import__("config").DB_PATH) as db_conn:
        async with db_conn.execute("SELECT COUNT(*) FROM users") as c:
            users = (await c.fetchone())[0]
        async with db_conn.execute("SELECT COUNT(*) FROM products WHERE status='active'") as c:
            products = (await c.fetchone())[0]
        async with db_conn.execute("SELECT COUNT(*) FROM orders WHERE status='confirmed'") as c:
            orders = (await c.fetchone())[0]
        async with db_conn.execute("SELECT SUM(commission) FROM orders WHERE status='confirmed'") as c:
            earned = (await c.fetchone())[0] or 0

    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {users}\n"
        f"📦 Активных товаров: {products}\n"
        f"✅ Выполненных заказов: {orders}\n"
        f"💰 Заработано комиссии: {earned} ⭐",
        parse_mode="HTML"
    )
