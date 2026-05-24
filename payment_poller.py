"""
Фоновый сервис автопроверки оплаты.
Каждые 15 секунд проверяет pending топапы и заказы через DA API.
Защита от двойного зачисления через used_donation_ids.
"""

import asyncio
import logging
from aiogram import Bot

import database as db
from db_neon import get_conn
from da_checker import fetch_recent_donations
from keyboards.inline import kb_wallet, kb_order_chat

logger = logging.getLogger(__name__)
POLL_INTERVAL = 15  # секунд


def _find_donation(donations: list, da_comment: str, amount: float, used_ids: set) -> dict | None:
    """Ищет подходящий донат, пропуская уже использованные."""
    comment_lower = da_comment.lower().strip()
    for d in donations:
        don_id = d.get("id")
        if don_id in used_ids:
            continue
        msg = (d.get("message") or "").lower().strip()
        don_amount = float(d.get("amount") or 0)
        if comment_lower in msg and don_amount >= amount * 0.95:
            return d
    return None


async def _process_topups(bot: Bot, donations: list, used_ids: set):
    pending = await db.get_pending_topups()
    if not pending:
        return

    for topup in pending:
        don = _find_donation(donations, topup["da_comment"], topup["amount"], used_ids)
        if not don:
            continue

        don_id      = don.get("id")
        found_amount = float(don.get("amount") or 0)

        # Атомарно: помечаем донат использованным И закрываем топап
        if don_id:
            if await db.is_donation_used(don_id):
                continue  # уже использован другим процессом
            await db.mark_donation_used(don_id)
            used_ids.add(don_id)  # обновляем локальный сет

        await db.complete_topup(topup["id"])
        await db.change_balance(topup["user_id"], found_amount)
        balance = await db.get_balance(topup["user_id"])

        logger.info(f"Топап #{topup['id']} user {topup['user_id']}: +{found_amount:.0f} ₽ (донат #{don_id})")

        try:
            await bot.send_message(
                topup["user_id"],
                f"✅ <b>Пополнение подтверждено!</b>\n\n"
                f"💰 Зачислено: <b>+{found_amount:.0f} ₽</b>\n"
                f"💳 Баланс: <b>{balance:.0f} ₽</b>",
                parse_mode="HTML",
                reply_markup=kb_wallet()
            )
        except Exception as e:
            logger.error(f"Не удалось уведомить user {topup['user_id']}: {e}")


async def _process_orders(bot: Bot, donations: list, used_ids: set):
    pending = await db.get_pending_orders_for_payment()
    if not pending:
        return

    for order in pending:
        don = _find_donation(donations, order["da_comment"], order["amount"], used_ids)
        if not don:
            continue

        don_id = don.get("id")

        # Атомарно: помечаем донат использованным
        if don_id:
            if await db.is_donation_used(don_id):
                continue
            await db.mark_donation_used(don_id)
            used_ids.add(don_id)

        await db.update_order_status(order["id"], "paid")
        seller_gets = round(order["amount"] - order["commission"], 2)
        product = await db.get_product(order["product_id"])
        logger.info(f"Заказ #{order['id']} оплачен (донат #{don_id})")

        try:
            await bot.send_message(
                order["buyer_id"],
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"Заказ #{order['id']} активен.\n"
                f"Переписка с продавцом открыта 👇",
                parse_mode="HTML",
                reply_markup=kb_order_chat(order["id"], "buyer")
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления покупателя: {e}")

        try:
            title = product["title"] if product else "?"
            await bot.send_message(
                order["seller_id"],
                f"🔔 <b>Новый оплаченный заказ #{order['id']}!</b>\n\n"
                f"📦 {title}\n"
                f"💰 Ты получишь: <b>{seller_gets:.0f} ₽</b>\n\n"
                f"Отправь товар и подтверди выдачу 👇",
                parse_mode="HTML",
                reply_markup=kb_order_chat(order["id"], "seller")
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления продавца: {e}")


async def payment_polling_loop(bot: Bot):
    from config import DA_TOKEN
    if not DA_TOKEN:
        logger.warning("DA_TOKEN не настроен — фоновая проверка отключена")
        return

    logger.info("Запущен фоновый polling оплат (каждые 15 сек)")
    while True:
        try:
            donations = await fetch_recent_donations(pages=3)
            if donations:
                used_ids = await db.get_used_donation_ids()
                await _process_topups(bot, donations, used_ids)
                await _process_orders(bot, donations, used_ids)
        except Exception as e:
            logger.error(f"Ошибка polling: {e}")

        await asyncio.sleep(POLL_INTERVAL)
