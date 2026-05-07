"""
DonationAlerts API checker.
Защита от двойного зачисления — через ID доната в таблице used_donation_ids.
"""

import aiohttp
import logging
from config import DA_TOKEN

logger = logging.getLogger(__name__)


async def fetch_recent_donations(pages: int = 3) -> list:
    if not DA_TOKEN:
        return []

    url = "https://www.donationalerts.com/api/v1/alerts/donations"
    headers = {"Authorization": f"Bearer {DA_TOKEN}"}
    all_donations = []

    try:
        async with aiohttp.ClientSession() as session:
            for page in range(1, pages + 1):
                async with session.get(
                    url, headers=headers,
                    params={"page": page},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 401:
                        logger.error("DA_TOKEN недействителен (401)")
                        return []
                    if resp.status != 200:
                        logger.error(f"DA API статус {resp.status}")
                        return []
                    data = await resp.json()
                    donations = data.get("data", [])
                    if not donations:
                        break
                    all_donations.extend(donations)
                    meta = data.get("meta", {})
                    if page >= meta.get("last_page", 1):
                        break
    except Exception as e:
        logger.error(f"Ошибка DA API: {e}")

    return all_donations


async def find_matching_donation(expected_comment: str, expected_amount: float, used_ids: set) -> dict | None:
    """
    Ищет донат по комментарию и сумме, пропуская уже использованные ID.
    Возвращает dict доната или None.
    """
    donations = await fetch_recent_donations(pages=3)
    comment_lower = expected_comment.lower().strip()

    for d in donations:
        don_id = d.get("id")
        # Пропускаем уже использованные
        if don_id and don_id in used_ids:
            continue
        msg = (d.get("message") or "").lower().strip()
        amount = float(d.get("amount") or 0)
        if comment_lower in msg and amount >= expected_amount * 0.95:
            return d

    return None


async def get_donation_amount_by_comment(expected_comment: str, expected_amount: float = 1.0) -> float:
    """Обратная совместимость — без проверки использованных ID."""
    d = await find_matching_donation(expected_comment, expected_amount, set())
    return float(d.get("amount") or 0) if d else 0.0


async def check_donation(expected_comment: str, expected_amount: float = 1.0) -> bool:
    return (await get_donation_amount_by_comment(expected_comment, expected_amount)) > 0


async def _get_donation_amount(expected_comment: str) -> float:
    return await get_donation_amount_by_comment(expected_comment, 1.0)
