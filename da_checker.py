import aiohttp
from config import DA_TOKEN


async def _fetch_donations() -> list:
    """Загружает последние донаты из DonationAlerts API. Возвращает [] при любой ошибке."""
    if not DA_TOKEN:
        return []
    url = "https://www.donationalerts.com/api/v1/alerts/donations"
    headers = {"Authorization": f"Bearer {DA_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return []
                data = await r.json()
                return data.get("data", [])
    except Exception:
        return []


async def get_donation_amount_by_comment(expected_comment: str, expected_amount: float = 1.0) -> float:
    """
    Ищет донат с нужным комментарием и суммой.
    Возвращает сумму найденного доната (float) или 0.0 если не найдено.
    Никогда не возвращает None — только число.
    """
    donations = await _fetch_donations()
    if not donations:
        return 0.0

    comment_lower = expected_comment.lower()
    for d in donations:
        msg = (d.get("message") or "").lower()
        amount = float(d.get("amount") or 0)
        # Ищем совпадение по комментарию и проверяем что сумма не меньше 95% ожидаемой
        if comment_lower in msg and amount >= expected_amount * 0.95:
            return amount
    return 0.0


async def check_donation(expected_comment: str, expected_amount: float = 1.0) -> bool:
    """
    Проверяет наличие доната.
    Возвращает True/False — больше никакого None/ручного режима.
    """
    amount = await get_donation_amount_by_comment(expected_comment, expected_amount)
    return amount > 0


# Старое имя для обратной совместимости
async def _get_donation_amount(expected_comment: str) -> float:
    return await get_donation_amount_by_comment(expected_comment, 1.0)
