import aiohttp
from config import DA_TOKEN

async def _fetch_donations():
    if not DA_TOKEN:
        return None
    url = "https://www.donationalerts.com/api/v1/alerts/donations"
    headers = {"Authorization": f"Bearer {DA_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                return data.get("data", [])
    except Exception:
        return None

async def _get_donation_amount(expected_comment: str) -> float:
    donations = await _fetch_donations()
    if not donations:
        return 0.0
    for d in donations:
        if expected_comment.lower() in (d.get("message") or "").lower():
            return float(d.get("amount") or 0)
    return 0.0

async def check_donation(expected_comment: str, expected_amount: float = 1.0):
    """
    Проверяет последние донаты через DonationAlerts API.
    Ищет донат с нужным комментарием и суммой.
    
    Получи токен: https://www.donationalerts.com/application/clients
    → Create Application → получи access_token
    """
    if not DA_TOKEN:
        # Если токен не настроен — пропускаем проверку (ручной режим)
        return None  # None = не проверяли (токен не настроен)

    url = "https://www.donationalerts.com/api/v1/alerts/donations"
    headers = {"Authorization": f"Bearer {DA_TOKEN}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

        donations = data.get("data", [])
        for d in donations:
            comment = (d.get("message") or "").lower()
            amount  = float(d.get("amount") or 0)
            # Ищем донат где в комментарии есть нужный текст и сумма совпадает
            if expected_comment.lower() in comment and amount >= expected_amount * 0.95:
                return True
        return False
    except Exception:
        return None  # ошибка сети — не можем проверить
