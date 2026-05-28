import os

BOT_TOKEN     = os.getenv("BOT_TOKEN", "")
CHANNEL_ID    = os.getenv("CHANNEL_ID", "@AnonPeak")
CHAT_CHANNEL  = os.getenv("CHAT_CHANNEL", "@AnonPeakChat")
CHAT_GROUP_ID = int(os.getenv("CHAT_GROUP_ID", "-1003755595234"))
ADMIN_ID      = int(os.getenv("ADMIN_ID", "780434845"))

# DonationAlerts
DA_LINK  = os.getenv("DA_LINK", "https://www.donationalerts.com/r/anonpeak")
DA_TOKEN = os.getenv("DA_TOKEN", "")

# Neon PostgreSQL (задаётся в Render → Environment Variables)
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Приватный TG-канал для хранения медиафайлов (фото/видео товаров и сообщений)
# Добавь бота (@твой_бот) администратором в этот канал с правом "Post Messages"
# Укажи числовой ID канала (например -1001234567890), не @username
MEDIA_CHANNEL_ID = int(os.getenv("MEDIA_CHANNEL_ID", "0"))

# Комиссии и лимиты
BOT_COMMISSION = 0.05
SELL_COMM      = 0.10
WITHDRAW_COMM  = 0.05
STAR_RATE      = 1.5
PREMIUM_PRICE  = 99.0
MIN_PRICE      = 15
MIN_WITHDRAW   = 250
CHAT_COOLDOWN  = 30 * 60

# Оставляем для обратной совместимости с bot.py если он ещё на SQLite
DB_PATH = "bot.db"
