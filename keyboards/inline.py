from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ─── ОНБОРДИНГ ───────────────────────────────────────────

def kb_check_sub():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")
    ]])

def kb_confirm_age():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Мне есть 18 лет", callback_data="confirm_age"),
        InlineKeyboardButton(text="❌ Нет, мне нет 18", callback_data="deny_age")
    ]])

# ─── ГЛАВНОЕ МЕНЮ ────────────────────────────────────────

def kb_main_menu(has_profile: bool):
    buttons = []
    if has_profile:
        buttons.append([InlineKeyboardButton(text="🛍 Маркет", callback_data="market")])
        buttons.append([
            InlineKeyboardButton(text="👤 Мой профиль", callback_data="my_profile"),
            InlineKeyboardButton(text="💰 Кошелёк", callback_data="wallet")
        ])
        buttons.append([InlineKeyboardButton(text="📦 Мои товары", callback_data="my_products")])
    else:
        buttons.append([InlineKeyboardButton(text="👤 Создать профиль", callback_data="create_profile")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

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
            text=f"{p['title']} — {p['price']}⭐",
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

def kb_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")
    ]])

# ─── ЗАКАЗЫ ──────────────────────────────────────────────

def kb_confirm_delivery(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить выдачу", callback_data=f"deliver_{order_id}")
    ]])

# ─── КОШЕЛЁК ─────────────────────────────────────────────

def kb_wallet():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Запросить вывод", callback_data="request_withdraw")],
        [InlineKeyboardButton(text="📋 Мои ожидающие заказы", callback_data="pending_orders")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

# ─── ПРОФИЛЬ ─────────────────────────────────────────────

def kb_profile(has_profile: bool):
    if has_profile:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile")],
            [InlineKeyboardButton(text="➕ Выставить товар", callback_data="sell_item")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✏️ Создать профиль", callback_data="create_profile")
    ]])
