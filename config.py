import os

BOT_TOKEN   = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID  = os.getenv("CHANNEL_ID", "@AnonPeak")          # канал для входа в бота
CHAT_CHANNEL = os.getenv("CHAT_CHANNEL", "@AnonPeakChat")   # канал для входа в чат (другой!)
CHAT_GROUP_ID = int(os.getenv("CHAT_GROUP_ID", "-1003755595234"))  # группа куда пересылаются сообщения
ADMIN_ID    = int(os.getenv("ADMIN_ID", "123456789"))

# DonationAlerts
DA_LINK     = os.getenv("DA_LINK", "https://www.donationalerts.com/r/YOUR_USERNAME")
DA_TOKEN    = os.getenv("DA_TOKEN", "")   # API токен DonationAlerts (из личного кабинета)

BOT_COMMISSION = 0.05
MIN_PRICE    = 15
MIN_WITHDRAW = 100
CHAT_COOLDOWN = 30 * 60   # 30 минут в секундах

DB_PATH = "bot.db"
