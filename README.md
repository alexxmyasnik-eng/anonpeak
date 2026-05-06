# AnonymMarket Bot

Телеграм бот-маркет с анонимными продажами, оплатой Telegram Stars и балансовой системой.

## Файловая структура

```
tg_market_bot/
├── main.py
├── config.py
├── database.py
├── requirements.txt
├── Procfile
├── handlers/
│   ├── start.py     # онбординг, 18+, подписка
│   ├── profile.py   # профиль
│   ├── market.py    # каталог товаров
│   ├── sell.py      # выставление товаров
│   ├── buy.py       # покупка + Stars оплата
│   ├── wallet.py    # баланс и вывод
│   └── admin.py     # панель администратора
└── keyboards/
    └── inline.py    # все кнопки
```

## Настройка

### 1. Заполни config.py

```python
BOT_TOKEN = "твой токен от @BotFather"
CHANNEL_ID = "@твой_канал"   # или -100xxxxxxxxxx
ADMIN_ID = 123456789          # твой Telegram ID
```

Или задай через переменные окружения (Railway):
- `BOT_TOKEN`
- `CHANNEL_ID`
- `ADMIN_ID`

### 2. Включи Stars-платежи у бота

В @BotFather → выбери бота → Payments → Stars

### 3. Деплой на Railway

1. Загрузи папку на GitHub
2. Зайди на railway.com → New Project → Deploy from GitHub
3. Добавь переменные: BOT_TOKEN, CHANNEL_ID, ADMIN_ID
4. Railway автоматически запустит бота через Procfile

## Схема оплаты

```
Покупатель платит Stars → Stars уходят тебе (через бота)
       ↓
Заказ висит в статусе "pending"
       ↓
Продавец подтверждает выдачу товара
       ↓
На баланс продавца зачисляется: цена − 5% комиссия
       ↓
Продавец запрашивает вывод → ты вручную отправляешь Stars
```

**Комиссия:** 5% с каждой продажи (+ 15% берёт сам Telegram при продаже Stars)

## Команды администратора

| Команда | Описание |
|---------|----------|
| `/admin` | Список всех ожидающих выводов |
| `/stats` | Статистика бота |
| `/withdraw_done_<id>` | Подтвердить вывод |

## Категории маркета

- 🖊 Сигна
- ☕ Кружки
- 📸 Фото
- 🎬 Видео
