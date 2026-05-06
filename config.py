import os

BOT_TOKEN   = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID  = os.getenv("CHANNEL_ID", "@AnonPeak")          # канал обязательной подписки
CHAT_ID     = int(os.getenv("CHAT_ID", "-1003755595234"))   # группа-чат куда пересылаются сообщения
ADMIN_ID    = int(os.getenv("ADMIN_ID", "YOUR_ADMIN_ID"))

# DonationAlerts
DA_LINK     = os.getenv("DA_LINK", "https://www.donationalerts.com/r/YOUR_DA_USERNAME")

# Комиссия бота (5%)
BOT_COMMISSION = 0.05

# Минимальные значения
MIN_PRICE    = 15    # рублей
MIN_WITHDRAW = 100   # рублей

DB_PATH = "bot.db"
