# AnonPeak — Backend

FastAPI + aiogram3 + Neon (PostgreSQL)

## Структура

```
api.py          — REST API (FastAPI), запускается на Render
main_api.py     — точка входа для API-сервера
main_bot.py     — точка входа для Telegram-бота
database.py     — функции работы с БД
db_neon.py      — пул соединений asyncpg + keepalive
config.py       — конфиг из переменных окружения
da_checker.py   — проверка донатов DonationAlerts
payment_poller.py — фоновый опрос платежей
handlers/       — хендлеры бота (aiogram)
keyboards/      — инлайн-клавиатуры
Dockerfile      — для API-сервиса
Dockerfile.bot  — для бота
```

## Deploy на Render (два сервиса)

### Сервис 1: API
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python main_api.py`
- **Dockerfile:** `Dockerfile`

### Сервис 2: Бот
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python main_bot.py`
- **Dockerfile:** `Dockerfile.bot`

## Keep-alive (обязательно!)

Чтобы Render free tier не засыпал, добавь Cron Job:
- URL: `https://ВАШ-API.onrender.com/health`
- Интервал: `*/14 * * * *` (каждые 14 минут)

Или используй https://cron-job.org (бесплатно).

## Переменные окружения

Скопируй `env.example` в `.env` и заполни:

```
BOT_TOKEN=       # от @BotFather
DA_TOKEN=        # от DonationAlerts
ADMIN_ID=        # твой Telegram ID
DATABASE_URL=    # строка подключения Neon
CHANNEL_ID=      # @твой_канал
CHAT_GROUP_ID=   # числовой ID чат-группы
MEDIA_CHANNEL_ID=# числовой ID канала для хранения медиафайлов
```

## Хранение медиафайлов

Фото и видео товаров хранятся через Telegram (приватный канал).
Бот пересылает медиа в `MEDIA_CHANNEL_ID` и сохраняет `file_id` в БД.
Это бесплатно и без ограничений по размеру.
