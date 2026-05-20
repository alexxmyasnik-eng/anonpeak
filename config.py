import os
from dotenv import load_dotenv

load_dotenv()

# ── TELEGRAM ──────────────────────────────────────────────
BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
CHANNEL_ID    = os.getenv("CHANNEL_ID", "@AnonPeak")
CHAT_CHANNEL  = os.getenv("CHAT_CHANNEL", "@AnonPeakChat")
CHAT_GROUP_ID = int(os.getenv("CHAT_GROUP_ID", "-1003755595234"))
ADMIN_ID      = int(os.getenv("ADMIN_ID", "780434845"))

# ── DONATIONALERTS ────────────────────────────────────────
DA_LINK  = os.getenv("DA_LINK", "https://www.donationalerts.com/r/anonpeak")
DA_TOKEN = os.getenv("DA_TOKEN", "")   # только через .env, никогда не хардкодить!

# ── БАЗА ДАННЫХ ───────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "bot.db")

# ── ФИНАНСОВЫЕ КОНСТАНТЫ ──────────────────────────────────
SELL_COMM      = 0.16   # комиссия платформы с продажи (16%)
WITHDRAW_COMM  = 0.05   # комиссия при выводе (5%)
STAR_RATE      = 1.4    # курс Stars → рубли
PREMIUM_PRICE  = 9      # стоимость премиум-размещения товара (₽)
MIN_PRICE      = 15     # минимальная цена товара (₽)
MIN_WITHDRAW   = 100    # минимальная сумма вывода (₽)

# ── ПРОЧЕЕ ────────────────────────────────────────────────
BOT_COMMISSION = SELL_COMM   # алиас для совместимости со старым кодом
CHAT_COOLDOWN  = 30 * 60     # кулдаун в глобальном чате (30 минут)
