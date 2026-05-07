"""
DonationAlerts API checker.

ВАЖНО: DA_TOKEN должен быть OAuth 2.0 access_token со scope oauth-donation-index.
Как получить:
  1. Зайди на https://www.donationalerts.com/application/clients
  2. Создай приложение, укажи redirect URI = https://localhost
  3. Открой в браузере:
     https://www.donationalerts.com/oauth/authorize?client_id=ВАШ_CLIENT_ID&redirect_uri=https://localhost&response_type=token&scope=oauth-user-show+oauth-donation-index
  4. После авторизации в адресной строке будет access_token=XXXXX — скопируй его
  5. Вставь в .env как DA_TOKEN=XXXXX

Токен действует ~1 год. При истечении повтори шаги 3-4.
"""

import aiohttp
import logging
from config import DA_TOKEN

logger = logging.getLogger(__name__)


async def fetch_recent_donations(pages: int = 3) -> list:
    """
    Загружает последние донаты (до pages страниц по 15 штук).
    Возвращает [] при любой ошибке или если токен не настроен.
    """
    if not DA_TOKEN:
        logger.warning("DA_TOKEN не настроен — проверка оплаты невозможна")
        return []

    url = "https://www.donationalerts.com/api/v1/alerts/donations"
    headers = {"Authorization": f"Bearer {DA_TOKEN}"}
    all_donations = []

    try:
        async with aiohttp.ClientSession() as session:
            for page in range(1, pages + 1):
                async with session.get(
                    url,
                    headers=headers,
                    params={"page": page},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 401:
                        logger.error("DA_TOKEN недействителен (401 Unauthorized). "
                                     "Нужно обновить токен — см. комментарий в da_checker.py")
                        return []
                    if resp.status != 200:
                        logger.error(f"DA API вернул статус {resp.status}")
                        return []

                    data = await resp.json()
                    donations = data.get("data", [])
                    if not donations:
                        break
                    all_donations.extend(donations)

                    # Если страниц меньше — не листаем дальше
                    meta = data.get("meta", {})
                    last_page = meta.get("last_page", 1)
                    if page >= last_page:
                        break

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка сети при запросе DA API: {e}")
    except Exception as e:
        logger.error(f"Неизвестная ошибка DA API: {e}")

    return all_donations


async def get_donation_amount_by_comment(expected_comment: str, expected_amount: float = 1.0) -> float:
    """
    Ищет донат с нужным комментарием и суммой.
    Возвращает сумму найденного доната (float > 0) или 0.0 если не найдено.
    Никогда не возвращает None.
    """
    donations = await fetch_recent_donations(pages=3)
    if not donations:
        return 0.0

    comment_lower = expected_comment.lower().strip()
    for d in donations:
        msg = (d.get("message") or "").lower().strip()
        amount = float(d.get("amount") or 0)
        # Точное совпадение комментария и сумма не меньше 95% ожидаемой
        if comment_lower in msg and amount >= expected_amount * 0.95:
            logger.info(f"Найден донат: '{msg}' = {amount} ₽")
            return amount

    return 0.0


async def check_donation(expected_comment: str, expected_amount: float = 1.0) -> bool:
    """True если донат найден, False если нет."""
    amount = await get_donation_amount_by_comment(expected_comment, expected_amount)
    return amount > 0


# Обратная совместимость
async def _get_donation_amount(expected_comment: str) -> float:
    return await get_donation_amount_by_comment(expected_comment, 1.0)
