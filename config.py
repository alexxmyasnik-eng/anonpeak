import os

# ===== ВСТАВЬ СВОИ ДАННЫЕ =====
BOT_TOKEN = os.getenv("BOT_TOKEN", "8525276997:AAGyRtyV1JeQIrQWdALmYvVUo5_lfPE3v-I")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@AnonPeak")  # или -100xxxxxxxxxx
ADMIN_ID = int(os.getenv("ADMIN_ID", "780434845"))       # твой Telegram ID

# Комиссия бота (5% = 0.05)
BOT_COMMISSION = 0.05

# Минимальная сумма для вывода (в звёздах)
MIN_WITHDRAW = 50

# БД
DB_PATH = "bot.db"
