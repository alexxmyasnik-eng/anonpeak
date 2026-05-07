from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ─── ОНБОРДИНГ ───────────────────────────────────────────

def kb_check_sub():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")
    ]])

def kb_confirm_age():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Мне 18+", callback_data="confirm_age"),
        InlineKeyboardButton(text="❌ Нет", callback_data="deny_age")
    ]])

# ─── ГЛАВНОЕ МЕНЮ ────────────────────────────────────────

def kb_main_menu(has_profile: bool, unread: int = 0):
    msg_label = f"✉️ Сообщения {'🔴' + str(unread) if unread else ''}"
    if has_profile:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Маркет",       callback_data="market")],
            [InlineKeyboardButton(text="💬 Общий чат",    callback_data="open_chat"),
             InlineKeyboardButton(text=msg_label,         callback_data="messages")],
            [InlineKeyboardButton(text="👤 Профиль",      callback_data="my_profile"),
             InlineKeyboardButton(text="💰 Кошелёк",      callback_data="wallet")],
            [InlineKeyboardButton(text="📦 Мои товары",   callback_data="my_products")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Создать профиль", callback_data="create_profile")]
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

def kb_product_list(products):
    buttons = []
    for p in products:
        buttons.append([InlineKeyboardButton(
            text=f"{p['title']} — {p['price']:.0f}₽",
            callback_data=f"product_{p['id']}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="market")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_product_detail(product_id: int, is_own: bool, seller_id: int = 0):
    if is_own:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_product_{product_id}")],
            [InlineKeyboardButton(text="⭐ Отзывы", callback_data=f"reviews_{seller_id}")],
            [InlineKeyboardButton(text="◀️ Назад",  callback_data="market")]
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить",   callback_data=f"buy_{product_id}")],
        [InlineKeyboardButton(text="⭐ Отзывы",   callback_data=f"reviews_{seller_id}")],
        [InlineKeyboardButton(text="◀️ Назад",    callback_data="market")]
    ])

# ─── ПРОДАЖА ─────────────────────────────────────────────

def kb_categories_sell():
    buttons = [[InlineKeyboardButton(text=v, callback_data=f"sell_cat_{k}")] for k, v in CATEGORIES.items()]
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_skip_or_back(cb_back="main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_media")],
        [InlineKeyboardButton(text="◀️ Назад",      callback_data=cb_back)]
    ])

def kb_avatar_skip():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip_avatar")],
        [InlineKeyboardButton(text="◀️ Назад",      callback_data="main_menu")]
    ])

def kb_cancel(cb="main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отмена", callback_data=cb)
    ]])

def kb_back(cb="main_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Назад", callback_data=cb)
    ]])

# ─── ПРОФИЛЬ ─────────────────────────────────────────────

def kb_profile():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать",  callback_data="edit_profile")],
        [InlineKeyboardButton(text="➕ Выставить товар", callback_data="sell_item")],
        [InlineKeyboardButton(text="◀️ Назад",          callback_data="main_menu")]
    ])

# ─── ЧАТ ─────────────────────────────────────────────────

def kb_chat_check_sub():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подписался на чат", callback_data="chat_sub_check")
    ]])

# ─── ЗАКАЗЫ / ПЕРЕПИСКА ──────────────────────────────────

def kb_order_chat(order_id: int, role: str):
    """role = 'seller' или 'buyer'"""
    buttons = []
    if role == "seller":
        buttons.append([InlineKeyboardButton(
            text="✅ Подтвердить выдачу товара",
            callback_data=f"seller_confirm_{order_id}"
        )])
    if role == "buyer":
        buttons.append([InlineKeyboardButton(
            text="✅ Получил, закрыть заказ",
            callback_data=f"buyer_confirm_{order_id}"
        )])
    buttons.append([InlineKeyboardButton(text="◀️ К диалогам", callback_data="messages")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_review(order_id: int):
    stars = []
    for i in range(1, 6):
        stars.append(InlineKeyboardButton(text="⭐" * i, callback_data=f"review_{order_id}_{i}"))
    return InlineKeyboardMarkup(inline_keyboard=[stars[:3], stars[3:]])

def kb_skip_review(order_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить отзыв", callback_data=f"skip_review_{order_id}")],
    ])

# ─── КОШЕЛЁК ─────────────────────────────────────────────

def kb_wallet():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить",        callback_data="topup")],
        [InlineKeyboardButton(text="📤 Вывести",          callback_data="request_withdraw")],
        [InlineKeyboardButton(text="◀️ Назад",            callback_data="main_menu")]
    ])

def kb_topup_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил",        callback_data="topup_paid")],
        [InlineKeyboardButton(text="◀️ Назад",            callback_data="wallet")]
    ])

# ─── СООБЩЕНИЯ ───────────────────────────────────────────

def kb_dialogs(orders_info: list):
    """orders_info = [(order_id, partner_nick, unread), ...]"""
    buttons = []
    for oid, nick, unread in orders_info:
        label = f"💬 {nick}" + (f"  🔴{unread}" if unread else "")
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"order_chat_{oid}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
