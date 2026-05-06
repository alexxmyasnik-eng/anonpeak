import os

# ===== ВСТАВЬ СВОИ ДАННЫЕ =====
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@your_channel_username")  # или -100xxxxxxxxxx
ADMIN_ID = int(os.getenv("ADMIN_ID", "YOUR_TELEGRAM_ID"))       # твой Telegram ID

# Комиссия бота (5% = 0.05)
BOT_COMMISSION = 0.05

# Минимальная сумма для вывода (в звёздах)
MIN_WITHDRAW = 50

# БД
DB_PATH = "bot.db"
