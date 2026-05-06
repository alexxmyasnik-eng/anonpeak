from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ─── ОНБОРДИНГ ───────────────────────────────────────────

def kb_check_sub():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")
    ]])

def kb_confirm_age():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтверждаю — мне 18+", callback_data="confirm_age"),
        InlineKeyboardButton(text="❌ Нет", callback_data="deny_age")
    ]])

# ─── ГЛАВНОЕ МЕНЮ ────────────────────────────────────────

def kb_main_menu(has_profile: bool):
    if has_profile:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Маркет",        callback_data="market")],
            [InlineKeyboardButton(text="💬 Общий чат",     callback_data="open_chat"),
             InlineKeyboardButton(text="✉️ Сообщения",     callback_data="messages")],
            [InlineKeyboardButton(text="👤 Профиль",       callback_data="my_profile"),
             InlineKeyboardButton(text="💰 Кошелёк",       callback_data="wallet")],
            [InlineKeyboardButton(text="📦 Мои товары",    callback_data="my_products")],
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 Создать профиль", callback_data="create_profile")],
        ])

# ─── МАРКЕТ ──────────────────────────────────────────────

CATEGORIES = {
    "signa":  "🖊 Сигна",
    "mugs":   "☕ Кружки",
    "photos": "📸 Фото",
    "videos": "🎬 Видео",
}

def kb_market():
    buttons = [[InlineKeyboardButton(text=v, callback_data=f"cat_{k}")] for k, v in CATEGORIES.items()]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_product_list(products, category):
    buttons = []
    for p in products:
        buttons.append([InlineKeyboardButton(
            text=f"{p['title']} — {p['price']:.0f}₽",
            callback_data=f"product_{p['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="market")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_product_detail(product_id: int, is_own: bool):
    if is_own:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить товар", callback_data=f"del_product_{product_id}")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="market")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить", callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="market")]
    ])

# ─── ПРОДАЖА ─────────────────────────────────────────────

def kb_categories_sell():
    buttons = [[InlineKeyboardButton(text=v, callback_data=f"sell_cat_{k}")] for k, v in CATEGORIES.items()]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_skip_or_back(back_to: str = "main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_media")],
        [InlineKeyboardButton(text="◀️ Назад",      callback_data=back_to)]
    ])

def kb_cancel(back_to: str = "main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data=back_to)
    ]])

def kb_back(back_to: str = "main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data=back_to)
    ]])

# ─── ПРОФИЛЬ ─────────────────────────────────────────────

def kb_profile():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать",  callback_data="edit_profile")],
        [InlineKeyboardButton(text="➕ Выставить товар", callback_data="sell_item")],
        [InlineKeyboardButton(text="◀️ Назад",          callback_data="main_menu")]
    ])

def kb_avatar_skip():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_avatar")],
        [InlineKeyboardButton(text="◀️ Назад",      callback_data="profile_age")]
    ])

# ─── ЗАКАЗЫ ──────────────────────────────────────────────

def kb_confirm_delivery(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить выдачу", callback_data=f"deliver_{order_id}")
    ]])

# ─── КОШЕЛЁК ─────────────────────────────────────────────

def kb_wallet():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Пополнить баланс",   callback_data="topup")],
        [InlineKeyboardButton(text="📤 Запросить вывод",    callback_data="request_withdraw")],
        [InlineKeyboardButton(text="📋 Ожидающие заказы",   callback_data="pending_orders")],
        [InlineKeyboardButton(text="◀️ Назад",              callback_data="main_menu")]
    ])

# ─── ЧАТ ─────────────────────────────────────────────────

def kb_chat_confirm_sub():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Я подписался на чат", callback_data="chat_sub_confirmed")
    ]])

# ─── СООБЩЕНИЯ ───────────────────────────────────────────

def kb_dialogs(dialogs, users):
    buttons = []
    for d in dialogs:
        partner = users.get(d["partner_id"])
        name = partner["nickname"] if partner else f"ID:{d['partner_id']}"
        buttons.append([InlineKeyboardButton(
            text=f"💬 {name}",
            callback_data=f"dialog_{d['partner_id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_in_dialog(partner_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ К списку диалогов", callback_data="messages")]
    ])
