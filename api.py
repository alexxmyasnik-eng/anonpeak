import random, string, math, aiosqlite, asyncio, json
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import database as db

try:
    from config import BOT_TOKEN, ADMIN_ID, DA_LINK, DB_PATH
except ImportError:
    BOT_TOKEN = ""; ADMIN_ID = 0; DA_LINK = "https://donationalerts.com"; DB_PATH = "bot.db"

SELL_COMM     = 0.16
WITHDRAW_COMM = 0.05
STAR_RATE     = 1.4
PREMIUM_PRICE = 9
MIN_PRICE     = 15
MIN_WITHDRAW  = 100

CATEGORIES = {
    "signa":"🖊 Сигна","mugs":"☕ Кружки",
    "photos":"📸 Фото","videos":"🎬 Видео",
}

async def migrate():
    async with aiosqlite.connect(DB_PATH) as d:
        for sql in [
            "ALTER TABLE users ADD COLUMN gender TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN is_premium INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN premium_at TIMESTAMP",
        ]:
            try: await d.execute(sql)
            except: pass
        await d.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await migrate()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"], allow_credentials=False,
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

async def require_uid(uid: Optional[str] = Query(default=None)) -> int:
    if not uid or not uid.isdigit():
        raise HTTPException(401, "Unauthorized")
    user_id = int(uid)
    if not await db.get_user(user_id):
        await db.create_user(user_id, "")
    return user_id

# ── HEALTH ───────────────────────────────────────────────
@app.get("/health")
async def health(): return {"ok": True}

# ── CATEGORIES ───────────────────────────────────────────
@app.get("/categories")
async def get_categories():
    return [{"id":k,"name":v} for k,v in CATEGORIES.items()]

# ── PRODUCTS ─────────────────────────────────────────────
@app.get("/products/create")
async def create_product(
    uid: int = Query(...), title: str = Query(...),
    description: str = Query(default=""), price: float = Query(...),
    category: str = Query(...), is_premium: bool = Query(default=False)
):
    if category not in CATEGORIES: raise HTTPException(400,"Неверная категория")
    if not title or len(title)>100: raise HTTPException(400,"Название от 1 до 100 символов")
    if price<MIN_PRICE: raise HTTPException(400,f"Минимальная цена {MIN_PRICE} ₽")
    if is_premium:
        balance = await db.get_balance(uid)
        if balance<PREMIUM_PRICE:
            raise HTTPException(400,f"Недостаточно средств для премиум ({PREMIUM_PRICE} ₽). Баланс: {balance:.0f} ₽")
        await db.change_balance(uid,-PREMIUM_PRICE)
    product_id = await db.add_product(uid,category,title,description or "",price,None,None)
    if is_premium:
        try:
            async with aiosqlite.connect(DB_PATH) as d:
                await d.execute("UPDATE products SET is_premium=1, premium_at=? WHERE id=?",
                    (datetime.now().isoformat(),product_id))
                await d.commit()
        except: pass
    return {"ok":True,"product_id":product_id,"seller_gets":round(price*(1-SELL_COMM),2)}

@app.get("/products/{category}")
async def get_products(category: str):
    if category not in CATEGORIES: raise HTTPException(404,"Не найдено")
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute(
            "SELECT * FROM products WHERE category=? AND status='active' "
            "ORDER BY COALESCE(is_premium,0) DESC, created_at DESC",(category,)
        ) as c: rows = await c.fetchall()
    result = []
    for p in rows:
        s = await db.get_user(p["seller_id"])
        avg,_ = await db.get_seller_rating(p["seller_id"])
        cols = [d[0] for d in p.description] if hasattr(p,'description') else list(dict(p).keys())
        is_prem = bool(p["is_premium"]) if "is_premium" in cols else False
        result.append({"id":p["id"],"title":p["title"],"description":p["description"],
            "price":p["price"],"category":p["category"],"media_id":p["media_id"],
            "media_type":p["media_type"],"seller_id":p["seller_id"],
            "seller_nick":nick_of(s),"seller_rating":round(avg,1),"is_premium":is_prem,
            "seller_gets":round(p["price"]*(1-SELL_COMM),2)})
    return result

@app.get("/product/{product_id}")
async def get_product(product_id: int):
    p = await db.get_product(product_id)
    if not p: raise HTTPException(404,"Не найдено")
    s = await db.get_user(p["seller_id"])
    avg,cnt = await db.get_seller_rating(p["seller_id"])
    return {"id":p["id"],"title":p["title"],"description":p["description"],
        "price":p["price"],"category":p["category"],"media_id":p["media_id"],
        "media_type":p["media_type"],"seller_id":p["seller_id"],
        "seller_nick":nick_of(s),"seller_rating":round(avg,1),"seller_reviews":cnt,
        "seller_gets":round(p["price"]*(1-SELL_COMM),2)}

# ── ME ────────────────────────────────────────────────────
@app.get("/me")
async def get_me(uid: int = Query(...)):
    if not await db.get_user(uid): await db.create_user(uid,"")
    u = await db.get_user(uid)
    gender = ""
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            async with d.execute("SELECT gender FROM users WHERE user_id=?",(uid,)) as c:
                row = await c.fetchone()
                if row and row[0]: gender = row[0]
    except: pass
    return {"uid":uid,"nickname":u["nickname"] if u else "",
            "age":u["age"] if u else None,"balance":float(u["balance"]) if u else 0.0,
            "avatar_id":u["avatar_id"] if u else None,"gender":gender}

@app.get("/me/update")
async def update_me(
    uid: int = Query(...), nickname: str = Query(...),
    age: int = Query(...), gender: str = Query(default="")
):
    if not nickname or len(nickname)>30: raise HTTPException(400,"Никнейм от 1 до 30 символов")
    if age<1 or age>120: raise HTTPException(400,"Укажи реальный возраст")
    u = await db.get_user(uid)
    await db.update_profile(uid,nickname,age,u["avatar_id"] if u else None)
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            await d.execute("UPDATE users SET gender=? WHERE user_id=?",(gender,uid))
            await d.commit()
    except: pass
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
        except: pass
        result.append({"id":o["id"],"short_id":o["short_id"] or f"#{o['id']}",
            "product_title":p["title"] if p else "Удалён","amount":o["amount"],
            "status":o["status"],"buyer_id":o["buyer_id"],"seller_id":o["seller_id"],
            "partner_nick":nick_of(partner),"role":"buyer" if o["buyer_id"]==uid else "seller",
            "commission":o["commission"],"unread":unread})
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

@app.get("/send_msg")
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

@app.get("/buy")
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

@app.get("/confirm_order")
async def confirm_order(order_id: int = Query(...), uid: int = Query(...)):
    order = await db.get_order(order_id)
    if not order or order["buyer_id"]!=uid: raise HTTPException(403,"Нет доступа")
    if order["status"] not in ("paid","seller_confirmed"): raise HTTPException(400,"Нельзя закрыть")
    seller_gets = round(order["amount"]-order["commission"],2)
    await db.change_balance(order["seller_id"],seller_gets)
    await db.update_order_status(order_id,"done")
    return {"ok":True}

@app.get("/topup/create")
async def topup_create(amount: int = Query(...), uid: int = Query(...)):
    if amount<10: raise HTTPException(400,"Минимум 10 ₽")
    code = gen_code()
    topup_id = await db.create_topup(uid,amount,code)
    return {"topup_id":topup_id,"code":code,"da_link":DA_LINK,"amount":amount}

@app.get("/withdraw")
async def withdraw(
    uid: int = Query(...), amount: float = Query(...), username: str = Query(...)
):
    if amount<MIN_WITHDRAW: raise HTTPException(400,f"Минимум {MIN_WITHDRAW} ₽")
    if not username or not username.startswith("@"): raise HTTPException(400,"Укажи @username")
    balance = await db.get_balance(uid)
    if balance<amount: raise HTTPException(400,f"Недостаточно средств. Баланс: {balance:.0f} ₽")
    after = round(amount*(1-WITHDRAW_COMM),2)
    stars = math.ceil(after/STAR_RATE)
    await db.change_balance(uid,-amount)
    w_id = await db.create_withdrawal(uid,amount)
    u = await db.get_user(uid)
    asyncio.create_task(notify(ADMIN_ID,
        f"💸 <b>Вывод #{w_id}</b>\n👤 {nick_of(u)} (ID:{uid})\n"
        f"💰 {amount:.0f} ₽ → {after:.0f} ₽ → ⭐{stars}\n📱 {username}"))
    return {"ok":True,"w_id":w_id,"after_commission":after,"stars":stars}

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

@app.get("/chat/messages")
async def chat_messages(limit: int = Query(default=50)):
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            d.row_factory = aiosqlite.Row
            try:
                await d.execute("CREATE TABLE IF NOT EXISTS global_chat (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                await d.commit()
            except: pass
            async with d.execute(
                "SELECT * FROM global_chat ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as c:
                rows = await c.fetchall()
        return [{"id":r["id"],"user_id":r["user_id"],"nickname":r["nickname"],
                 "message":r["message"],"created_at":str(r["created_at"])} for r in reversed(rows)]
    except Exception as e:
        return []

@app.get("/chat/send")
async def chat_send(uid: int = Query(...), message: str = Query(...)):
    if not message.strip(): raise HTTPException(400,"Пустое сообщение")
    if len(message) > 500: raise HTTPException(400,"Максимум 500 символов")
    u = await db.get_user(uid)
    nickname = nick_of(u)
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            try:
                await d.execute("CREATE TABLE IF NOT EXISTS global_chat (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, nickname TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            except: pass
            await d.execute(
                "INSERT INTO global_chat (user_id, nickname, message) VALUES (?,?,?)",
                (uid, nickname, message.strip())
            )
            await d.commit()
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}

@app.get("/chat/delete")
async def chat_delete(uid: int = Query(...), msg_id: int = Query(...)):
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute("SELECT user_id FROM global_chat WHERE id=?", (msg_id,)) as c:
            row = await c.fetchone()
        if not row: raise HTTPException(404,"Сообщение не найдено")
        # Удалять может только автор
        if row["user_id"] != uid: raise HTTPException(403,"Нет доступа")
        await d.execute("DELETE FROM global_chat WHERE id=?", (msg_id,))
        await d.commit()
    return {"ok": True}
