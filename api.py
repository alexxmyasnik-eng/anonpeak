import random, string, math, aiosqlite, asyncio, json, hmac, hashlib, urllib.parse, time
from collections import defaultdict
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import database as db

# Настройка часового пояса (МСК, UTC+3)
MSK = timezone(timedelta(hours=3))

from config import (
    BOT_TOKEN, ADMIN_ID, DA_LINK, DB_PATH,
    SELL_COMM, WITHDRAW_COMM, STAR_RATE,
    PREMIUM_PRICE, MIN_PRICE, MIN_WITHDRAW
)

CATEGORIES = {
    "photos":    {"name": "📸 Фото",       "subs": ["Тематика"]},
    "videos": {"name": "🎬 Видео", "subs": ["Кошки","Собаки"]},
    "domik":{"name": "⛓️ Домик",   "subs": ["Оценка"]},
    "fish":    {"name": "🧎 Рыба",      "subs": ["Лёгкие"]},
    "audio":     {"name": "🎧 Аудио",       "subs": ["Собака"]},
    "signa":     {"name": "🖊 Сигны",       "subs": ["Обычная"]},
}

async def migrate():
    async with aiosqlite.connect(DB_PATH) as d:
        for sql in [
            "ALTER TABLE dm_messages ADD COLUMN reply_to_text TEXT DEFAULT ''",
            "ALTER TABLE users ADD COLUMN gender TEXT DEFAULT ''",
            "ALTER TABLE users ADD COLUMN earn_balance REAL DEFAULT 0",
            "ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN is_premium INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN premium_at TIMESTAMP",
            """CREATE TABLE IF NOT EXISTS global_chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, nickname TEXT, message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS support_chat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, from_admin INTEGER DEFAULT 0,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, friend_id INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, friend_id)
            )""",
            """CREATE TABLE IF NOT EXISTS muted_users (
                user_id INTEGER, muted_id INTEGER,
                PRIMARY KEY(user_id, muted_id)
            )""",
            """CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS frozen_funds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                order_id INTEGER,
                amount REAL,
                unfreeze_at TIMESTAMP,
                is_released INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            "ALTER TABLE products ADD COLUMN subcategory TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN preview_url TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN delivery_files TEXT DEFAULT '[]'",
        ]:
            try: await d.execute(sql)
            except Exception: pass
        await d.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await migrate()
    yield

app = FastAPI(lifespan=lifespan)

ALLOWED_ORIGINS = [
    "https://alexxmyasnik-eng.github.io",
    "https://t.me",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)

def gen_code():
    c = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ''.join(random.choices(c,k=4))+'-'+''.join(random.choices(c,k=4))

def nick_of(u): return (u["nickname"] if u and u["nickname"] else "Аноним")

async def notify(chat_id, text):
    if not BOT_TOKEN or not chat_id or not HAS_AIOHTTP: return
    try:
        async with aiohttp.ClientSession() as s:
            await asyncio.wait_for(s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id":chat_id,"text":text,"parse_mode":"HTML",
                      "reply_markup":{"inline_keyboard":[[{"text":"Открыть","web_app":{"url":"https://alexxmyasnik-eng.github.io/anonminiapp"}}]]}}
            ), timeout=5)
    except Exception:
        pass

def verify_telegram_init_data(init_data: str) -> Optional[int]:
    """Верифицирует подпись Telegram initData. Возвращает user_id или None."""
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_hash, received_hash):
            return None
        user_data = json.loads(parsed.get("user", "{}"))
        return user_data.get("id")
    except Exception:
        return None

# Rate limiting для глобального чата
_chat_ratelimit: dict = defaultdict(list)

def check_rate_limit(user_id: int, max_msgs: int = 5, window_sec: int = 10) -> bool:
    """True если лимит не превышен (5 сообщений за 10 секунд)."""
    now = time.time()
    _chat_ratelimit[user_id] = [t for t in _chat_ratelimit[user_id] if now - t < window_sec]
    if len(_chat_ratelimit[user_id]) >= max_msgs:
        return False
    _chat_ratelimit[user_id].append(now)
    return True

async def require_uid(
    uid: Optional[str] = Query(default=None),
    init_data: Optional[str] = Query(default=None)
) -> int:
    # Верификация через Telegram initData (продакшен)
    if init_data:
        verified_id = verify_telegram_init_data(init_data)
        if verified_id:
            if not await db.get_user(verified_id):
                await db.create_user(verified_id, "")
            return verified_id
    # Фоллбэк по uid (для разработки)
    if not uid or not uid.isdigit():
        raise HTTPException(401, "Unauthorized")
    user_id = int(uid)
    if not await db.get_user(user_id):
        await db.create_user(user_id, "")
    return user_id

# ── HEALTH ───────────────────────────────────────────────
@app.api_route("/health", methods=["GET", "HEAD"])
async def health(): return {"ok": True}

# ── CATEGORIES ───────────────────────────────────────────
@app.get("/categories")
async def get_categories():
    return [{"id":k,"name":v["name"],"subs":v["subs"]} for k,v in CATEGORIES.items()]

# ── PRODUCTS ─────────────────────────────────────────────
@app.post("/products/create")
async def create_product(
    uid: int = Query(...), title: str = Query(...),
    description: str = Query(default=""), price: float = Query(...),
    category: str = Query(...), subcategory: str = Query(default=""),
    is_premium: bool = Query(default=False)
):
    if category not in CATEGORIES: raise HTTPException(400,"Неверная категория")
    if not title or len(title)>100: raise HTTPException(400,"Название от 1 до 100 символов")
    if price!=0 and price<MIN_PRICE: raise HTTPException(400,f"Минимальная цена {MIN_PRICE} ₽")
    # Лимит товаров у продавца
    async with aiosqlite.connect(DB_PATH) as d:
        async with d.execute("SELECT COUNT(*) FROM products WHERE seller_id=? AND status='active'",(uid,)) as c:
            row = await c.fetchone()
            if row and row[0] >= 50:
                raise HTTPException(400,"Максимум 50 активных товаров")
    if is_premium:
        balance = await db.get_balance(uid)
        if balance<PREMIUM_PRICE:
            raise HTTPException(400,f"Недостаточно средств для премиум ({PREMIUM_PRICE} ₽).\nБаланс: {balance:.0f} ₽")
        await db.change_balance(uid,-PREMIUM_PRICE)
    product_id = await db.add_product(uid,category,title,description or "",price,None,None)
    async with aiosqlite.connect(DB_PATH) as d:
        try: await d.execute("ALTER TABLE products ADD COLUMN subcategory TEXT DEFAULT ''")
        except Exception: pass
        await d.execute("UPDATE products SET subcategory=? WHERE id=?",(subcategory.strip(),product_id))
        if is_premium:
            await d.execute("UPDATE products SET is_premium=1, premium_at=? WHERE id=?",
                 (datetime.now(MSK).isoformat(),product_id))
        await d.commit()
    return {"ok":True,"product_id":product_id,"seller_gets":round(price*(1-SELL_COMM),2)}

@app.post("/products/delete")
async def delete_product(uid: int = Query(...), product_id: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute("SELECT seller_id FROM products WHERE id=?", (product_id,)) as c:
            row = await c.fetchone()
        if not row: raise HTTPException(404,"Товар не найден")
        if row["seller_id"] != uid: raise HTTPException(403,"Нет доступа")
        await d.execute("UPDATE products SET status='deleted' WHERE id=?", (product_id,))
        await d.commit()
    return {"ok": True}

@app.post("/products/{product_id}/set_preview")
async def set_product_preview(product_id: int, uid: int = Query(...), request: Request = None):
    data_url = await request.body()
    data_url = data_url.decode("utf-8", errors="ignore")
    if not data_url.startswith("data:image/"):
        raise HTTPException(400, "Только изображения")
    if len(data_url) > 5_000_000:
        raise HTTPException(400, "Файл слишком большой (макс 3.7 МБ)")
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute("SELECT seller_id FROM products WHERE id=?", (product_id,)) as c:
            row = await c.fetchone()
        if not row: raise HTTPException(404, "Товар не найден")
        if row["seller_id"] != uid: raise HTTPException(403, "Нет доступа")
        await d.execute("UPDATE products SET preview_url=? WHERE id=?", (data_url, product_id))
        await d.commit()
    return {"ok": True}

@app.post("/products/{product_id}/add_delivery_file")
async def add_delivery_file(product_id: int, uid: int = Query(...), request: Request = None):
    data_url = (await request.body()).decode("utf-8", errors="ignore")
    if not data_url.startswith("data:image/"):
        raise HTTPException(400, "Только изображения")
    if len(data_url) > 5_000_000:
        raise HTTPException(400, "Файл слишком большой (макс ~3.7 МБ)")
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute("SELECT seller_id, delivery_files FROM products WHERE id=?", (product_id,)) as c:
            row = await c.fetchone()
        if not row: raise HTTPException(404, "Товар не найден")
        if row["seller_id"] != uid: raise HTTPException(403, "Нет доступа")
        try:
            files = json.loads(row["delivery_files"] or "[]")
        except:
            files = []
        if len(files) >= 20: raise HTTPException(400, "Максимум 20 файлов")
        files.append(data_url)
        await d.execute("UPDATE products SET delivery_files=? WHERE id=?", (json.dumps(files), product_id))
        await d.commit()
    return {"ok": True}

@app.get("/products/{product_id}/delivery_files")
async def get_product_delivery_files(product_id: int, uid: int = Query(default=0)):
    # Verify that uid has purchased this product
    if uid:
        async with aiosqlite.connect(DB_PATH) as d:
            d.row_factory = aiosqlite.Row
            async with d.execute(
                "SELECT id FROM orders WHERE buyer_id=? AND product_id=? AND status IN ('paid','seller_confirmed','done')",
                (uid, product_id)
            ) as c:
                purchase = await c.fetchone()
            # Also allow seller to see their own files
            async with d.execute("SELECT seller_id FROM products WHERE id=?", (product_id,)) as c:
                prod = await c.fetchone()
            if not purchase and (not prod or prod["seller_id"] != uid):
                raise HTTPException(403, "Нет доступа: сначала купи товар")
    else:
        raise HTTPException(401, "Unauthorized")
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute("SELECT delivery_files FROM products WHERE id=?", (product_id,)) as c:
            row = await c.fetchone()
        if not row: raise HTTPException(404, "Товар не найден")
        try:
            files = json.loads(row["delivery_files"] or "[]")
        except:
            files = []
    return {"files": files}

@app.get("/products/{category}")
async def get_products(category: str, sub: str = Query(default=""), seller: int = Query(default=0)):
    if category not in CATEGORIES: raise HTTPException(404,"Не найдено")
    async with aiosqlite.connect(DB_PATH) as d:
        try: await d.execute("ALTER TABLE products ADD COLUMN subcategory TEXT DEFAULT ''")
        except Exception: pass
        await d.commit()
        d.row_factory = aiosqlite.Row
        q = "SELECT * FROM products WHERE category=? AND status='active'"
        params = [category]
        if sub and sub.strip():
            q += " AND TRIM(subcategory)=?"
            params.append(sub.strip())
        if seller:
            q += " AND seller_id=?"
            params.append(seller)
        q += " ORDER BY COALESCE(is_premium,0) DESC, created_at DESC"
        async with d.execute(q, params) as c:
            rows = await c.fetchall()
    result = []
    for p in rows:
        s = await db.get_user(p["seller_id"])
        avg,_ = await db.get_seller_rating(p["seller_id"])
        is_prem = bool(p["is_premium"]) if "is_premium" in dict(p) else False
        sub_val = p["subcategory"] if "subcategory" in dict(p) else ""
        prev_url = p["preview_url"] if "preview_url" in dict(p) else ""
        result.append({"id":p["id"],"title":p["title"],"description":p["description"],
            "price":p["price"],"category":p["category"],"subcategory":sub_val or "",
            "media_id":p["media_id"],"media_type":p["media_type"],
            "preview_url":prev_url or "",
            "seller_id":p["seller_id"],"seller_nick":nick_of(s),
            "seller_rating":round(avg,1),"is_premium":is_prem,
            "seller_gets":round(p["price"]*(1-SELL_COMM),2)})
    return result

@app.get("/product/{product_id}")
async def get_product(product_id: int):
    p = await db.get_product(product_id)
    if not p: raise HTTPException(404,"Не найдено")
    s = await db.get_user(p["seller_id"])
    avg,cnt = await db.get_seller_rating(p["seller_id"])
    prev_url = ""
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            async with d.execute("SELECT preview_url FROM products WHERE id=?", (product_id,)) as c:
                row = await c.fetchone()
                if row and row[0]: prev_url = row[0]
    except Exception: pass
    return {"id":p["id"],"title":p["title"],"description":p["description"],
        "price":p["price"],"category":p["category"],"media_id":p["media_id"],
        "preview_url":prev_url,
        "media_type":p["media_type"],"seller_id":p["seller_id"],
        "seller_nick":nick_of(s),"seller_rating":round(avg,1),"seller_reviews":cnt,
        "seller_gets":round(p["price"]*(1-SELL_COMM),2)}

# ── ME ────────────────────────────────────────────────────
@app.get("/me")
async def get_me(uid: int = Query(...)):
    if not await db.get_user(uid): await db.create_user(uid,"")
    u = await db.get_user(uid)
    gender = ""
    earn_bal = 0.0
    avatar_url = ""
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            async with d.execute(
                "SELECT gender, earn_balance, avatar_url FROM users WHERE user_id=?", (uid,)
            ) as c:
                row = await c.fetchone()
                if row:
                    gender = row[0] or ""
                    earn_bal = float(row[1]) if row[1] else 0.0
                    avatar_url = row[2] or ""
    except Exception: pass
    return {"uid":uid,"nickname":u["nickname"] if u else "",
            "age":u["age"] if u else None,
            "balance":float(u["balance"]) if u else 0.0,
            "earn_balance":earn_bal,
            "total_balance":(float(u["balance"]) if u else 0.0) + earn_bal,
            "avatar_url":avatar_url,
            "avatar_id":u["avatar_id"] if u else None,"gender":gender,
            "is_admin": uid == ADMIN_ID}

@app.post("/me/update")
async def update_me(
    uid: int = Query(...), nickname: str = Query(...),
    age: int = Query(...), gender: str = Query(default="")
):
    if not nickname or len(nickname)>30: raise HTTPException(400,"Никнейм от 1 до 30 символов")
    if age<18 or age>120: raise HTTPException(400,"Минимальный возраст — 18 лет")
    # Проверка уникальности никнейма
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute("SELECT user_id FROM users WHERE nickname=? AND user_id!=?",(nickname,uid)) as c:
            if await c.fetchone():
                raise HTTPException(400,"Этот никнейм уже занят")
    u = await db.get_user(uid)
    await db.update_profile(uid,nickname,age,u["avatar_id"] if u else None)
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            await d.execute("UPDATE users SET gender=? WHERE user_id=?",(gender,uid))
            await d.commit()
    except Exception: pass
    return {"ok":True}

# ── ORDERS ────────────────────────────────────────────────
@app.get("/orders")
async def get_orders(uid: int = Query(...)):
    orders = await db.get_orders_for_user(uid)
    result = []
    for o in orders:
        pid = o["seller_id"] if o["buyer_id"]==uid else o["buyer_id"]
        partner = await db.get_user(pid)
        p = await db.get_product(o["product_id"])
        unread = 0
        try:
            async with aiosqlite.connect(DB_PATH) as d:
                async with d.execute(
                    "SELECT COUNT(*) FROM messages WHERE order_id=? AND receiver_id=? AND is_read=0",
                    (o["id"],uid)
                ) as c:
                    row = await c.fetchone(); unread = row[0] if row else 0
        except Exception: pass
        result.append({"id":o["id"],"short_id":o["short_id"] or f"#{o['id']}",
            "product_title":p["title"] if p else "Удалён","amount":o["amount"],
            "status":o["status"],"buyer_id":o["buyer_id"],"seller_id":o["seller_id"],
            "partner_nick":nick_of(partner),"role":"buyer" if o["buyer_id"]==uid else "seller",
            "commission":o["commission"],"unread":unread, "product_id":o["product_id"]})
    return result

@app.get("/orders/{order_id}/messages")
async def get_messages(order_id: int, uid: int = Query(...)):
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"],order["seller_id"]):
        raise HTTPException(403,"Нет доступа")
    await db.mark_read(order_id,uid)
    msgs = await db.get_order_messages(order_id)
    return [{"id":m["id"],"sender_id":m["sender_id"],"text":m["text"],
             "media_type":m["media_type"],"created_at":str(m["created_at"])} for m in msgs]

@app.post("/send_msg")
async def send_msg(order_id: int = Query(...), uid: int = Query(...), text: str = Query(...)):
    if not text.strip(): raise HTTPException(400,"Пустое сообщение")
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"],order["seller_id"]):
        raise HTTPException(403,"Нет доступа")
    partner_id = order["seller_id"] if order["buyer_id"]==uid else order["buyer_id"]
    await db.send_msg(order_id,uid,partner_id,text=text.strip())
    me = await db.get_user(uid)
    short = order["short_id"] or f"#{order_id}"
    asyncio.create_task(notify(partner_id,
        f"💬 Сообщение от <b>{nick_of(me)}</b>\nЗаказ {short}: {text.strip()[:80]}"))
    return {"ok":True}

@app.post("/buy")
async def buy(product_id: int = Query(...), uid: int = Query(...)):
    p = await db.get_product(product_id)
    if not p or p["status"]!="active": raise HTTPException(400,"Товар недоступен")
    if p["seller_id"]==uid: raise HTTPException(400,"Нельзя купить свой товар")
    balance = await db.get_balance(uid)
    if balance < p["price"]: return {"ok":False,"reason":"insufficient","balance":balance,"price":p["price"]}
    commission = round(p["price"]*SELL_COMM,2)
    await db.change_balance(uid,-p["price"])
    order_id = await db.create_order(uid,p["seller_id"],product_id,p["price"],commission,"")
    await db.update_order_status(order_id,"paid")
    order = await db.get_order(order_id)
    short = order["short_id"] or f"#{order_id}"
    seller_gets = round(p["price"]-commission,2)
    buyer = await db.get_user(uid)
    asyncio.create_task(notify(p["seller_id"],
        f"💰 <b>Новый заказ!</b>\nПокупатель: {nick_of(buyer)}\nТовар: {p['title']}\nВы получите: {seller_gets} ₽\nЗаказ: {short}"))
    return {"ok":True,"short_id":short}

@app.post("/confirm_order")
async def confirm_order(order_id: int = Query(...), uid: int = Query(...)):
    order = await db.get_order(order_id)
    if not order or order["buyer_id"]!=uid: raise HTTPException(403,"Нет доступа")
    if order["status"] not in ("paid","seller_confirmed"): raise HTTPException(400,"Нельзя закрыть")
    seller_gets = round(order["amount"]-order["commission"],2)
    unfreeze_at = (datetime.now(MSK) + timedelta(days=2)).isoformat()
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute(
            "INSERT INTO frozen_funds (user_id,order_id,amount,unfreeze_at) VALUES (?,?,?,?)",
            (order["seller_id"], order_id, seller_gets, unfreeze_at))
        # Записываем транзакцию для покупателя
        await d.execute(
            "INSERT INTO transactions (user_id,type,amount,description) VALUES (?,?,?,?)",
            (order["buyer_id"], "purchase", -order["amount"],
             f"Покупка: {(await db.get_product(order['product_id']) or {}).get('title','товар')}"))
        await d.commit()
    await db.update_order_status(order_id,"done")
    asyncio.create_task(notify(order["seller_id"],
        f"💰 Продажа завершена!\n{seller_gets} ₽ заморожены на 2 дня и поступят на баланс {unfreeze_at[:10]}"))
    return {"ok":True}

@app.post("/topup/create")
async def topup_create(amount: int = Query(...), uid: int = Query(...)):
    if amount<10: raise HTTPException(400,"Минимум 10 ₽")
    code = gen_code()
    topup_id = await db.create_topup(uid,amount,code)
    return {"topup_id":topup_id,"code":code,"da_link":DA_LINK,"amount":amount}

@app.post("/withdraw")
async def withdraw(
    uid: int = Query(...), amount: float = Query(...), username: str = Query(...)
):
    if amount<MIN_WITHDRAW: raise HTTPException(400,f"Минимум {MIN_WITHDRAW} ₽")
    if not username or not username.startswith("@"): raise HTTPException(400,"Укажи @username")
    earn_bal = await db.get_earn_balance(uid)
    if earn_bal<amount: raise HTTPException(400,f"Недостаточно заработанных средств. Доступно: {earn_bal:.0f} ₽")
    after = round(amount*(1-WITHDRAW_COMM),2)
    stars = math.ceil(after/STAR_RATE)
    await db.change_earn_balance(uid,-amount)
    w_id = await db.create_withdrawal(uid,amount)
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            await d.execute(
                "INSERT INTO transactions (user_id,type,amount,description) VALUES (?,?,?,?)",
                (uid, "withdraw", -amount, f"Вывод ⭐{stars} · комиссия {round(amount*WITHDRAW_COMM,2)} ₽"))
            await d.commit()
    except Exception: pass
    u = await db.get_user(uid)
    asyncio.create_task(notify(ADMIN_ID,
        f"💸 <b>Вывод #{w_id}</b>\n👤 {nick_of(u)} (ID:{uid})\n"
        f"💰 {amount:.0f} ₽ → {after:.0f} ₽ → ⭐{stars}\n📱 {username}"))
    return {"ok":True,"w_id":w_id,"after_commission":after,"stars":stars}

# ── TRANSACTIONS ──────────────────────────────────────────
@app.get("/transactions")
async def get_transactions(uid: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        try:
            await d.execute("""CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, type TEXT, amount REAL, description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            await d.execute("""CREATE TABLE IF NOT EXISTS frozen_funds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, order_id INTEGER, amount REAL,
                unfreeze_at TIMESTAMP, is_released INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            await d.commit()
        except Exception: pass
        now = datetime.now(MSK).isoformat()
        async with d.execute(
            "SELECT * FROM frozen_funds WHERE user_id=? AND is_released=0 AND unfreeze_at<=?",
            (uid, now)
        ) as c: due = await c.fetchall()
        for f in due:
            # Размороженные средства идут на earn_balance (заработанное — для вывода)
            await db.change_earn_balance(uid, f["amount"])
            await d.execute("UPDATE frozen_funds SET is_released=1 WHERE id=?",(f["id"],))
            await d.execute(
                "INSERT INTO transactions (user_id,type,amount,description) VALUES (?,?,?,?)",
                (uid, "sale", f["amount"], "Продажа разморожена (заказ #"+str(f["order_id"])+")"))
        if due: await d.commit()
        async with d.execute(
            "SELECT * FROM frozen_funds WHERE user_id=? AND is_released=0 ORDER BY unfreeze_at ASC",(uid,)
        ) as c: frozen = await c.fetchall()
        async with d.execute(
            "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 50",(uid,)
        ) as c: txs = await c.fetchall()
    frozen_list = [{"id":f["id"],"amount":f["amount"],"order_id":f["order_id"],
                    "unfreeze_at":str(f["unfreeze_at"]),
                    "description":"❄️ Заморожено до "+str(f["unfreeze_at"])[:10]}
                  for f in frozen]
    tx_list = [{"id":t["id"],"type":t["type"],"amount":t["amount"],
                "description":t["description"],"created_at":str(t["created_at"])} for t in txs]
    return {"transactions": tx_list, "frozen": frozen_list}

@app.get("/support")
async def support(uid: int = Query(...), message: str = Query(...)):
    if not message.strip(): raise HTTPException(400,"Пустое сообщение")
    try:
        ticket_id = await db.create_support_ticket(uid, message.strip())
    except Exception as e:
        raise HTTPException(500, f"DB error: {e}")
    try:
        u = await db.get_user(uid)
        await notify(ADMIN_ID,
            f"[SUPPORT #{ticket_id}] {nick_of(u)} (ID:{uid}) - {message.strip()}")
    except Exception:
        pass
    return {"ok": True, "ticket_id": ticket_id}

# ── GLOBAL CHAT ───────────────────────────────────────────
@app.post("/me/set_avatar")
async def set_avatar_post(request: Request, uid: int = Query(...)):
    try:
        body = await request.body()
        avatar_data = body.decode('utf-8')[:15000000]
        async with aiosqlite.connect(DB_PATH) as d:
            try: await d.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''")
            except Exception: pass
            await d.execute("UPDATE users SET avatar_url=? WHERE user_id=?", (avatar_data, uid))
            await d.commit()
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}

@app.get("/me/set_avatar")
async def set_avatar(uid: int = Query(...), avatar_url: str = Query(default="")):
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            try: await d.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT DEFAULT ''")
            except Exception: pass
            await d.execute("UPDATE users SET avatar_url=? WHERE user_id=?", (avatar_url, uid))
            await d.commit()
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}

@app.get("/user/{user_id}")
async def get_user_profile(user_id: int):
    u = await db.get_user(user_id)
    if not u: raise HTTPException(404, "Не найден")
    avg, cnt = await db.get_seller_rating(user_id)
    gender = ""
    avatar_url = ""
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            async with d.execute("SELECT gender, avatar_url FROM users WHERE user_id=?",(user_id,)) as c:
                row = await c.fetchone()
                if row: gender, avatar_url = row[0] or "", row[1] or ""
    except Exception: pass
    return {
        "uid": user_id, "nickname": u["nickname"] or "Аноним",
        "age": u["age"], "gender": gender, "avatar_url": avatar_url,
        "rating": round(avg,1), "reviews": cnt,
    }

# ── SUPPORT CHAT ──────────────────────────────────────────
@app.get("/support/messages")
async def support_messages(uid: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute(
            "SELECT * FROM support_chat WHERE user_id=? ORDER BY created_at ASC LIMIT 100",(uid,)
        ) as c: rows = await c.fetchall()
    return [{"id":r["id"],"from_admin":bool(r["from_admin"]),
             "message":r["message"],"created_at":str(r["created_at"])} for r in rows]

@app.post("/support/send")
async def support_send(uid: int = Query(...), message: str = Query(...)):
    if not message.strip(): raise HTTPException(400,"Пустое")
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute("INSERT INTO support_chat (user_id,from_admin,message) VALUES (?,0,?)",
            (uid, message.strip()))
        await d.commit()
    u = await db.get_user(uid)
    asyncio.create_task(notify(ADMIN_ID,
        f"[SUPPORT] {nick_of(u)} (ID:{uid}): {message.strip()[:100]}"))
    return {"ok": True}

@app.post("/support/reply")
async def support_reply(uid: int = Query(...), user_id: int = Query(...), message: str = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403,"Нет доступа")
    if not message.strip(): raise HTTPException(400,"Пустое")
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute("INSERT INTO support_chat (user_id,from_admin,message) VALUES (?,1,?)",
            (user_id, message.strip()))
        await d.commit()
    asyncio.create_task(notify(user_id, f"[Поддержка] {message.strip()[:100]}"))
    return {"ok": True}

@app.get("/support/tickets")
async def support_tickets(uid: int = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403,"Нет доступа")
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            d.row_factory = aiosqlite.Row
            async with d.execute(
                "SELECT user_id, MAX(created_at) as last_time, "
                "(SELECT message FROM support_chat s2 WHERE s2.user_id=s1.user_id ORDER BY created_at DESC LIMIT 1) as last_message "
                "FROM support_chat s1 WHERE from_admin=0 GROUP BY user_id ORDER BY last_time DESC"
            ) as c: rows = await c.fetchall()
        result = []
        for r in rows:
            u = await db.get_user(r["user_id"])
            result.append({
                "user_id": r["user_id"],
                "nickname": nick_of(u),
                "last_message": r["last_message"] or "",
                "last_time": str(r["last_time"]) if r["last_time"] else "",
            })
        return result
    except Exception as e:
        raise HTTPException(500, f"DB error: {e}")

@app.get("/my_products")
async def my_products(uid: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        try: await d.execute("ALTER TABLE products ADD COLUMN subcategory TEXT DEFAULT ''")
        except Exception: pass
        await d.commit()
        d.row_factory = aiosqlite.Row
        async with d.execute(
            "SELECT * FROM products WHERE seller_id=? AND status='active' ORDER BY created_at DESC",
            (uid,)
        ) as c: rows = await c.fetchall()
    return [{"id":p["id"],"title":p["title"],"price":p["price"],
             "category":p["category"],"subcategory":p["subcategory"] if "subcategory" in dict(p) else "",
             "is_premium":bool(p["is_premium"])} for p in rows]

@app.get("/friends")
async def friends_alias(uid: int = Query(...)):
    return await friends_list(uid=uid)

@app.post("/friends/add")
async def add_friend(uid: int = Query(...), friend_id: int = Query(...)):
    if uid == friend_id: raise HTTPException(400,"Нельзя добавить себя")
    async with aiosqlite.connect(DB_PATH) as d:
        try:
            await d.execute("INSERT INTO friends (user_id,friend_id,status) VALUES (?,?,'pending')",(uid,friend_id))
            await d.commit()
        except Exception: pass
    u = await db.get_user(uid)
    asyncio.create_task(notify(friend_id, f"[Заявка] {nick_of(u)} хочет добавить вас в друзья"))
    return {"ok": True}

@app.post("/friends/cancel")
async def cancel_friend(uid: int = Query(...), friend_id: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute(
            "DELETE FROM friends WHERE user_id=? AND friend_id=? AND status='pending'",
            (uid, friend_id)
        )
        await d.commit()
    return {"ok": True}

@app.post("/friends/accept")
async def accept_friend(uid: int = Query(...), friend_id: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute("UPDATE friends SET status='accepted' WHERE user_id=? AND friend_id=?",(friend_id,uid))
        try:
            await d.execute("INSERT INTO friends (user_id,friend_id,status) VALUES (?,?,'accepted')",(uid,friend_id))
        except:
            await d.execute("UPDATE friends SET status='accepted' WHERE user_id=? AND friend_id=?",(uid,friend_id))
        await d.commit()
    u = await db.get_user(uid)
    asyncio.create_task(notify(friend_id, f"[Друзья] {nick_of(u)} принял вашу заявку"))
    return {"ok": True}

@app.post("/friends/remove")
async def remove_friend(uid: int = Query(...), friend_id: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        await d.execute(
            "DELETE FROM friends WHERE (user_id=? AND friend_id=?) OR (user_id=? AND friend_id=?)",
            (uid, friend_id, friend_id, uid)
        )
        await d.commit()
    return {"ok": True}

@app.get("/friends/list")
async def friends_list(uid: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute(
            "SELECT friend_id,status FROM friends WHERE user_id=?",(uid,)
        ) as c: rows = await c.fetchall()
    result = []
    for r in rows:
        u = await db.get_user(r["friend_id"])
        result.append({"friend_id":r["friend_id"],"nickname":nick_of(u),"status":r["status"]})
    return result

@app.get("/friends/requests")
async def friend_requests(uid: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute(
            "SELECT user_id FROM friends WHERE friend_id=? AND status='pending'",(uid,)
        ) as c: rows = await c.fetchall()
    result = []
    for r in rows:
        u = await db.get_user(r["user_id"])
        result.append({"user_id":r["user_id"],"nickname":nick_of(u)})
    return result

@app.get("/friends/status")
async def friend_status(uid: int = Query(...), other_id: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute(
            "SELECT status FROM friends WHERE user_id=? AND friend_id=?",(uid,other_id)
        ) as c: row = await c.fetchone()
    return {"status": row["status"] if row else "none"}

@app.get("/chat/messages")
async def chat_messages(limit: int = Query(default=50)):
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            d.row_factory = aiosqlite.Row
            try:
                await d.execute("CREATE TABLE IF NOT EXISTS global_chat (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                await d.commit()
            except Exception: pass
            async with d.execute(
                "SELECT * FROM global_chat ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as c:
                rows = await c.fetchall()
        return [{"id":r["id"],"user_id":r["user_id"],"nickname":r["nickname"],
                 "message":r["message"],"created_at":str(r["created_at"])} for r in reversed(rows)]
    except Exception as e:
        return []

@app.post("/chat/send")
async def chat_send(uid: int = Query(...), message: str = Query(...)):
    if not message.strip(): raise HTTPException(400,"Пустое сообщение")
    if len(message) > 500: raise HTTPException(400,"Максимум 500 символов")
    if not check_rate_limit(uid):
        raise HTTPException(429,"Слишком много сообщений. Подожди немного")
    u = await db.get_user(uid)
    nickname = nick_of(u)
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            try:
                await d.execute("CREATE TABLE IF NOT EXISTS global_chat (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            except Exception: pass
            await d.execute(
                "INSERT INTO global_chat (user_id, nickname, message) VALUES (?,?,?)",
                (uid, nickname, message.strip())
            )
            await d.commit()
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}

@app.post("/chat/delete")
async def chat_delete(uid: int = Query(...), msg_id: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute("SELECT user_id FROM global_chat WHERE id=?", (msg_id,)) as c:
            row = await c.fetchone()
        if not row: raise HTTPException(404,"Сообщение не найдено")
        if row["user_id"] != uid: raise HTTPException(403,"Нет доступа")
        await d.execute("DELETE FROM global_chat WHERE id=?", (msg_id,))
        await d.commit()
    return {"ok": True}

# ── DIRECT MESSAGES ───────────────────────────────────────
@app.post("/dm/send")
async def dm_send(uid: int = Query(...), to_id: int = Query(...), message: str = Query(...), reply_to_text: str = Query(default="")):
    if not message.strip(): raise HTTPException(400,"Пустое сообщение")
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute(
            "SELECT status FROM friends WHERE user_id=? AND friend_id=?", (uid, to_id)
        ) as c: row = await c.fetchone()
    if not row or row["status"] != "accepted":
        raise HTTPException(403, "Можно писать только друзьям")
    async with aiosqlite.connect(DB_PATH) as d:
        try:
            await d.execute("""CREATE TABLE IF NOT EXISTS dm_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id INTEGER, to_id INTEGER, message TEXT,
                reply_to_text TEXT DEFAULT '',
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        except Exception: pass
        await d.execute(
            "INSERT INTO dm_messages (from_id,to_id,message,reply_to_text) VALUES (?,?,?,?)",
            (uid, to_id, message.strip(), reply_to_text.strip())
        )
        await d.commit()
    me = await db.get_user(uid)
    # Проверяем, замутил ли получатель отправителя
    async with aiosqlite.connect(DB_PATH) as d:
        async with d.execute(
            "SELECT 1 FROM muted_users WHERE user_id=? AND muted_id=?", (to_id, uid)
        ) as c:
            is_muted = await c.fetchone()
    if not is_muted:
        asyncio.create_task(notify(to_id, f"[Сообщение] {nick_of(me)}: {message.strip()[:80]}"))
    return {"ok": True}

@app.post("/dm/mute")
async def dm_mute(uid: int = Query(...), muted_id: int = Query(...), until_ts: int = Query(default=0)):
    async with aiosqlite.connect(DB_PATH) as d:
        if until_ts == -1:
            await d.execute("DELETE FROM muted_users WHERE user_id=? AND muted_id=?", (uid, muted_id))
        else:
            await d.execute(
                "INSERT OR REPLACE INTO muted_users (user_id, muted_id) VALUES (?,?)",
                (uid, muted_id)
            )
        await d.commit()
    return {"ok": True}

@app.get("/dm/messages")
async def dm_messages(uid: int = Query(...), with_id: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        try:
            await d.execute("""CREATE TABLE IF NOT EXISTS dm_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id INTEGER, to_id INTEGER, message TEXT,
                reply_to_text TEXT DEFAULT '',
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            await d.commit()
        except Exception: pass
        await d.execute(
            "UPDATE dm_messages SET is_read=1 WHERE to_id=? AND from_id=?", (uid, with_id)
        )
        await d.commit()
        async with d.execute(
            "SELECT * FROM dm_messages WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?) ORDER BY created_at ASC LIMIT 100",
            (uid, with_id, with_id, uid)
        ) as c: rows = await c.fetchall()
    return [{"id":r["id"],"from_id":r["from_id"],"message":r["message"],
             "reply_to_text":r["reply_to_text"] if "reply_to_text" in dict(r) else "",
             "is_read":bool(r["is_read"]),"created_at":str(r["created_at"])} for r in rows]

@app.get("/dm/unread_count")
async def dm_unread(uid: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        try:
            await d.execute("CREATE TABLE IF NOT EXISTS dm_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, from_id INTEGER, to_id INTEGER, message TEXT, reply_to_text TEXT DEFAULT '', is_read INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            await d.commit()
        except Exception: pass
        d.row_factory = aiosqlite.Row
        async with d.execute(
            "SELECT from_id, COUNT(*) as cnt FROM dm_messages WHERE to_id=? AND is_read=0 GROUP BY from_id", (uid,)
        ) as c: rows = await c.fetchall()
    return {str(r["from_id"]): r["cnt"] for r in rows}

@app.get("/dm/conversations")
async def dm_conversations(uid: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        try:
            await d.execute("""CREATE TABLE IF NOT EXISTS dm_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id INTEGER, to_id INTEGER, message TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            await d.commit()
        except Exception: pass
        # Получаем всех с кем была переписка + последнее сообщение
        async with d.execute("""
            SELECT 
                CASE WHEN from_id=? THEN to_id ELSE from_id END as partner_id,
                message, created_at, is_read, from_id,
                COUNT(CASE WHEN to_id=? AND is_read=0 THEN 1 END) as unread
            FROM dm_messages
            WHERE from_id=? OR to_id=?
            GROUP BY partner_id
            ORDER BY created_at DESC
        """, (uid, uid, uid, uid)) as c:
            rows = await c.fetchall()
    result = []
    for r in rows:
        partner = await db.get_user(r["partner_id"])
        result.append({
            "partner_id": r["partner_id"],
            "nickname": nick_of(partner),
            "last_message": r["message"],
            "created_at": str(r["created_at"]),
            "unread": r["unread"],
            "is_out": r["from_id"] == uid
        })
    return result

@app.post("/dm/delete")
async def dm_delete(uid: int = Query(...), with_id: int = Query(...), both_sides: int = Query(default=0)):
    async with aiosqlite.connect(DB_PATH) as d:
        if both_sides:
            # Удаляем переписку у обоих
            await d.execute(
                "DELETE FROM dm_messages WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)",
                (uid, with_id, with_id, uid)
            )
        else:
            # Удаляем только исходящие сообщения от себя
            await d.execute(
                "DELETE FROM dm_messages WHERE from_id=? AND to_id=?",
                (uid, with_id)
            )
        await d.commit()
    return {"ok": True}
