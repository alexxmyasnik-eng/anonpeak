import aiohttp
from datetime import datetime, timezone, timedelta
from config import DA_TOKEN

CHECK_WINDOW_MINUTES = 15

async def _fetch_donations():
    if not DA_TOKEN:
        return None
    url = "https://www.donationalerts.com/api/v1/alerts/donations"
    headers = {"Authorization": f"Bearer {DA_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status == 401:
                    return "invalid_token"
                if r.status != 200:
                    return None
                data = await r.json()
                return data.get("data", [])
    except Exception:
        return None

async def check_donation(expected_comment: str, expected_amount: float = 1.0):
    """
    True  = донат найден
    False = не найден за последние 15 минут
    None  = токен не настроен / ошибка (ручная проверка)
    """
    donations = await _fetch_donations()
    if donations is None or donations == "invalid_token":
        return None
    if not isinstance(donations, list):
        return None

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=CHECK_WINDOW_MINUTES)

    for d in donations:
        # Фильтр по времени
        created_at_str = d.get("created_at") or d.get("shown_at") or ""
        if created_at_str:
            try:
                dt = datetime.strptime(created_at_str[:19], "%Y-%m-%d %H:%M:%S")
                dt = dt.replace(tzinfo=timezone.utc)
                if dt < window_start:
                    continue
            except Exception:
                pass

        comment = (d.get("message") or "").lower().strip()
        amount  = float(d.get("amount") or 0)

        if expected_comment.lower() in comment and amount >= expected_amount * 0.95:
            return True

    return False

async def _get_donation_amount(expected_comment: str) -> float:
    donations = await _fetch_donations()
    if not donations or not isinstance(donations, list):
        return 0.0

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=CHECK_WINDOW_MINUTES)

    for d in donations:
        created_at_str = d.get("created_at") or d.get("shown_at") or ""
        if created_at_str:
            try:
                dt = datetime.strptime(created_at_str[:19], "%Y-%m-%d %H:%M:%S")
                dt = dt.replace(tzinfo=timezone.utc)
                if dt < window_start:
                    continue
            except Exception:
                pass
        comment = (d.get("message") or "").lower().strip()
        if expected_comment.lower() in comment:
            return float(d.get("amount") or 0)
    return 0.0
