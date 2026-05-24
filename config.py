import os

BOT_TOKEN   = os.getenv("BOT_TOKEN", "8525276997:AAHkDI4OWL-BaEuv_VpdRVoP3P0twrfQDSQ")
CHANNEL_ID  = os.getenv("CHANNEL_ID", "@AnonPeak")          # канал для входа в бота
CHAT_CHANNEL = os.getenv("CHAT_CHANNEL", "@AnonPeakChat")   # канал для входа в чат (другой!)
CHAT_GROUP_ID = int(os.getenv("CHAT_GROUP_ID", "-1003755595234"))  # группа куда пересылаются сообщения
ADMIN_ID    = int(os.getenv("ADMIN_ID", "780434845"))

# DonationAlerts
DA_LINK     = os.getenv("DA_LINK", "https://www.donationalerts.com/r/anonpeak")
DA_TOKEN    = os.getenv("DA_TOKEN", "bcPUVbHJy1WV7RjAgJNgU5E727TtpZjkNq8ywcnf")   # API токен DonationAlerts (из личного кабинета)

BOT_COMMISSION = 0.05
MIN_PRICE    = 15
MIN_WITHDRAW = 100
CHAT_COOLDOWN = 30 * 60   # 30 минут в секундах

DB_PATH = "bot.db"  # оставь пока для database.py если он ещё на sqlite
DATABASE_URL = os.getenv("DATABASE_URL")  # Neon — уже есть в Render
MEDIA_CHANNEL_ID = int(os.getenv("MEDIA_CHANNEL_ID", "0"))  # приватный канал для фото/видео
