"""
Фоновый сервис автопроверки оплаты.
Каждые 15 секунд проверяет все pending топапы и заказы через DA API.
Если находит донат — сам зачисляет и уведомляет пользователя в Telegram.
"""

import asyncio
import logging
from aiogram import Bot

import database as db
from da_checker import fetch_recent_donations, get_donation_amount_by_comment
from keyboards.inline import kb_wallet, kb_order_chat

logger = logging.getLogger(__name__)

POLL_INTERVAL = 15  # секунд


async def _process_topups(bot: Bot, donations: list):
    """Проверяет все pending топапы по списку донатов."""
    pending = await db.get_pending_topups()
    if not pending:
        return

    for topup in pending:
        topup_id   = topup["id"]
        user_id    = topup["user_id"]
        amount     = topup["amount"]
        da_comment = topup["da_comment"]

        comment_lower = da_comment.lower().strip()
        found_amount = 0.0

        for d in donations:
            msg = (d.get("message") or "").lower().strip()
            don_amount = float(d.get("amount") or 0)
            if comment_lower in msg and don_amount >= amount * 0.95:
                found_amount = don_amount
                break

        if found_amount > 0:
            # Зачисляем и помечаем как выполненный
            await db.change_balance(user_id, found_amount)
            await db.complete_topup(topup_id)
            balance = await db.get_balance(user_id)
            logger.info(f"Топап #{topup_id} для user {user_id}: +{found_amount:.0f} ₽ (автопроверка)")

            try:
                await bot.send_message(
                    user_id,
                    f"✅ <b>Пополнение подтверждено!</b>\n\n"
                    f"💰 Зачислено: <b>+{found_amount:.0f} ₽</b>\n"
                    f"💳 Баланс: <b>{balance:.0f} ₽</b>",
                    parse_mode="HTML",
                    reply_markup=kb_wallet()
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить user {user_id}: {e}")


async def _process_orders(bot: Bot, donations: list):
    """Проверяет все заказы в статусе pending_payment."""
    pending = await db.get_pending_orders_for_payment()
    if not pending:
        return

    for order in pending:
        order_id   = order["id"]
        buyer_id   = order["buyer_id"]
        seller_id  = order["seller_id"]
        amount     = order["amount"]
        commission = order["commission"]
        da_comment = order["da_comment"]

        comment_lower = da_comment.lower().strip()
        found_amount = 0.0

        for d in donations:
            msg = (d.get("message") or "").lower().strip()
            don_amount = float(d.get("amount") or 0)
            if comment_lower in msg and don_amount >= amount * 0.95:
                found_amount = don_amount
                break

        if found_amount > 0:
            await db.update_order_status(order_id, "paid")
            seller_gets = round(amount - commission, 2)
            product = await db.get_product(order["product_id"])
            logger.info(f"Заказ #{order_id} оплачен автоматически: {found_amount:.0f} ₽")

            # Уведомляем покупателя
            try:
                await bot.send_message(
                    buyer_id,
                    f"✅ <b>Оплата подтверждена автоматически!</b>\n\n"
                    f"Заказ #{order_id} активен.\n"
                    f"Переписка с продавцом открыта — жди товар 👇",
                    parse_mode="HTML",
                    reply_markup=kb_order_chat(order_id, "buyer")
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить покупателя {buyer_id}: {e}")

            # Уведомляем продавца
            try:
                title = product["title"] if product else "?"
                await bot.send_message(
                    seller_id,
                    f"🔔 <b>Новый оплаченный заказ #{order_id}!</b>\n\n"
                    f"📦 {title}\n"
                    f"💰 Ты получишь: <b>{seller_gets:.0f} ₽</b>\n\n"
                    f"Отправь товар покупателю и подтверди выдачу 👇",
                    parse_mode="HTML",
                    reply_markup=kb_order_chat(order_id, "seller")
                )
            except Exception as e:
                logger.error(f"Не удалось уведомить продавца {seller_id}: {e}")


async def payment_polling_loop(bot: Bot):
    """
    Бесконечный цикл: каждые 15 сек загружает донаты и проверяет все pending платежи.
    Запускается один раз при старте бота.
    """
    from config import DA_TOKEN
    if not DA_TOKEN:
        logger.warning("DA_TOKEN не настроен — фоновая проверка оплат отключена")
        return

    logger.info("Запущен фоновый polling оплат (каждые 15 сек)")
    while True:
        try:
            donations = await fetch_recent_donations(pages=3)
            if donations:
                await _process_topups(bot, donations)
                await _process_orders(bot, donations)
        except Exception as e:
            logger.error(f"Ошибка в payment_polling_loop: {e}")

        await asyncio.sleep(POLL_INTERVAL)
