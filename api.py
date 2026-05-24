import random, string, math, asyncio, json, hmac, hashlib, urllib.parse, time, base64
from collections import defaultdict
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
from db_neon import get_conn, _get_pool    
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

import database as db
from db_neon import get_conn

MSK = timezone(timedelta(hours=3))

from config import (
    BOT_TOKEN, ADMIN_ID, DA_LINK,
    MIN_PRICE, MIN_WITHDRAW,
    MEDIA_CHANNEL_ID
)

try:
    from config import SELL_COMM, WITHDRAW_COMM, STAR_RATE, PREMIUM_PRICE
except ImportError:
    SELL_COMM      = 0.10
    WITHDRAW_COMM  = 0.05
    STAR_RATE      = 1.5
    PREMIUM_PRICE  = 99.0

CATEGORIES = {
    "photos":    {"name": "📸 Фото",       "subs": ["В белье","Без белья","Игрушки","Тематика"]},
    "videos":    {"name": "🎬 Видео",       "subs": ["Мастурбация","Проникновение","Анальное","Кастом"]},
    "domination":{"name": "⛓️ Доминация",   "subs": ["Оценка","Задания","Контроль","Унижение"]},
    "slaves":    {"name": "🧎 Рабыня",      "subs": ["Лёгкие приказы","Интим-подчинение"]},
    "audio":     {"name": "🎧 Аудио",       "subs": ["Секстинг","Стоны","Унижение"]},
    "signa":     {"name": "🖊 Сигны",       "subs": ["Обычная","В белье","На голом теле","Видео-сигна"]},
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _get_pool()
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
    return ''.join(random.choices(c, k=4)) + '-' + ''.join(random.choices(c, k=4))


def nick_of(u): return (u["nickname"] if u and u["nickname"] else "Аноним")


async def notify(chat_id, text):
    if not BOT_TOKEN or not chat_id or not HAS_AIOHTTP: return
    try:
        async with aiohttp.ClientSession() as s:
            await asyncio.wait_for(s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                      "reply_markup": {"inline_keyboard": [[{"text": "Открыть", "web_app": {"url": "https://alexxmyasnik-eng.github.io/anonminiapp"}}]]}}
            ), timeout=5)
    except Exception:
        pass


async def upload_media_to_tg(data_url: str) -> str:
    if not data_url.startswith("data:"):
        return data_url
    if not MEDIA_CHANNEL_ID:
        raise HTTPException(500, "MEDIA_CHANNEL_ID не задан")
    header, b64 = data_url.split(",", 1)
    file_bytes = base64.b64decode(b64)
    is_video = "video" in header
    method = "sendVideo" if is_video else "sendPhoto"
    field = "video" if is_video else "photo"
    content_type = "video/mp4" if is_video else "image/jpeg"
    filename = "file.mp4" if is_video else "file.jpg"
    async with aiohttp.ClientSession() as s:
        form = aiohttp.FormData()
        form.add_field("chat_id", str(MEDIA_CHANNEL_ID))
        form.add_field(field, file_bytes, filename=filename, content_type=content_type)
        resp = await s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", data=form)
        result = await resp.json()
    if not result.get("ok"):
        raise HTTPException(500, f"TG upload error: {result.get('description', result)}")
    msg = result["result"]
    if is_video:
        return msg["video"]["file_id"]
    return msg["photo"][-1]["file_id"]


_chat_ratelimit: dict = defaultdict(list)


def check_rate_limit(user_id: int, max_msgs: int = 5, window_sec: int = 10) -> bool:
    now = time.time()
    _chat_ratelimit[user_id] = [t for t in _chat_ratelimit[user_id] if now - t < window_sec]
    if len(_chat_ratelimit[user_id]) >= max_msgs:
        return False
    _chat_ratelimit[user_id].append(now)
    return True


# ── HEALTH ───────────────────────────────────────────────
@app.api_route("/health", methods=["GET", "HEAD"])
async def health(): return {"ok": True}


# ── TG FILE RESOLVER ─────────────────────────────────────
from fastapi.responses import RedirectResponse

@app.get("/tg_file")
async def tg_file(file_id: str = Query(...)):
    async with aiohttp.ClientSession() as s:
        resp = await s.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
            params={"file_id": file_id}
        )
        data = await resp.json()
    if not data.get("ok"):
        raise HTTPException(404, "Файл не найден")
    path = data["result"]["file_path"]
    return RedirectResponse(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{path}")


# ── CATEGORIES ───────────────────────────────────────────
@app.get("/categories")
async def get_categories():
    return [{"id": k, "name": v["name"], "subs": v["subs"]} for k, v in CATEGORIES.items()]


# ── PRODUCTS ─────────────────────────────────────────────
@app.get("/products/create")
async def create_product(
    uid: int = Query(...), title: str = Query(...),
    description: str = Query(default=""), price: float = Query(...),
    category: str = Query(...), subcategory: str = Query(default=""),
    is_premium: bool = Query(default=False)
):
    if category not in CATEGORIES: raise HTTPException(400, "Неверная категория")
    if not title or len(title) > 100: raise HTTPException(400, "Название от 1 до 100 символов")
    if price != 0 and price < MIN_PRICE: raise HTTPException(400, f"Минимальная цена {MIN_PRICE} ₽")

    async with get_conn() as d:
        row = await d.fetchrow(
            "SELECT COUNT(*) as cnt FROM products WHERE seller_id=$1 AND status='active'", uid
        )
        if row and row["cnt"] >= 50:
            raise HTTPException(400, "Максимум 50 активных товаров")

    if is_premium:
        balance = await db.get_balance(uid)
        if balance < PREMIUM_PRICE:
            raise HTTPException(400, f"Недостаточно средств для премиум ({PREMIUM_PRICE} ₽).\nБаланс: {balance:.0f} ₽")
        await db.change_balance(uid, -PREMIUM_PRICE)

    product_id = await db.add_product(uid, category, title, description or "", price, None, None)

    async with get_conn() as d:
        await d.execute("UPDATE products SET subcategory=$1 WHERE id=$2", subcategory.strip(), product_id)
        if is_premium:
            await d.execute(
                "UPDATE products SET is_premium=1, premium_at=$1 WHERE id=$2",
                datetime.now(MSK).isoformat(), product_id
            )
    return {"ok": True, "product_id": product_id, "seller_gets": round(price * (1 - SELL_COMM), 2)}


@app.get("/products/delete")
async def delete_product(uid: int = Query(...), product_id: int = Query(...)):
    async with get_conn() as d:
        row = await d.fetchrow("SELECT seller_id FROM products WHERE id=$1", product_id)
        if not row: raise HTTPException(404, "Товар не найден")
        if row["seller_id"] != uid: raise HTTPException(403, "Нет доступа")
        await d.execute("UPDATE products SET status='deleted' WHERE id=$1", product_id)
    return {"ok": True}


@app.post("/products/{product_id}/set_preview")
async def set_product_preview(product_id: int, uid: int = Query(...), request: Request = None):
    data_url = (await request.body()).decode("utf-8", errors="ignore")
    if not data_url.startswith("data:image/"):
        raise HTTPException(400, "Только изображения")
    if len(data_url) > 5_000_000:
        raise HTTPException(400, "Файл слишком большой")
    async with get_conn() as d:
        row = await d.fetchrow("SELECT seller_id FROM products WHERE id=$1", product_id)
        if not row: raise HTTPException(404, "Товар не найден")
        if row["seller_id"] != uid: raise HTTPException(403, "Нет доступа")
    file_id = await upload_media_to_tg(data_url)
    async with get_conn() as d:
        await d.execute("UPDATE products SET preview_url=$1 WHERE id=$2", file_id, product_id)
    return {"ok": True, "file_id": file_id}


@app.post("/products/{product_id}/add_delivery_file")
async def add_delivery_file(product_id: int, uid: int = Query(...), request: Request = None):
    data_url = (await request.body()).decode("utf-8", errors="ignore")
    if not data_url.startswith("data:"):
        raise HTTPException(400, "Только изображения или видео")
    if len(data_url) > 5_000_000:
        raise HTTPException(400, "Файл слишком большой")
    async with get_conn() as d:
        row = await d.fetchrow("SELECT seller_id, delivery_files FROM products WHERE id=$1", product_id)
        if not row: raise HTTPException(404, "Товар не найден")
        if row["seller_id"] != uid: raise HTTPException(403, "Нет доступа")
        try:
            files = json.loads(row["delivery_files"] or "[]")
        except:
            files = []
        if len(files) >= 20: raise HTTPException(400, "Максимум 20 файлов")
    file_id = await upload_media_to_tg(data_url)
    files.append(file_id)
    async with get_conn() as d:
        await d.execute("UPDATE products SET delivery_files=$1 WHERE id=$2", json.dumps(files), product_id)
    return {"ok": True, "file_id": file_id}


@app.get("/products/{product_id}/delivery_files")
async def get_product_delivery_files(product_id: int):
    async with get_conn() as d:
        row = await d.fetchrow("SELECT delivery_files FROM products WHERE id=$1", product_id)
        if not row: raise HTTPException(404, "Товар не найден")
        try:
            files = json.loads(row["delivery_files"] or "[]")
        except:
            files = []
    return {"files": files}


@app.get("/products/{category}")
async def get_products(category: str, sub: str = Query(default=""), seller: int = Query(default=0)):
    if category not in CATEGORIES: raise HTTPException(404, "Не найдено")
    async with get_conn() as d:
        q = "SELECT * FROM products WHERE category=$1 AND status='active'"
        params = [category]
        idx = 2
        if sub and sub.strip():
            q += f" AND TRIM(subcategory)=${idx}"
            params.append(sub.strip())
            idx += 1
        if seller:
            q += f" AND seller_id=${idx}"
            params.append(seller)
        q += " ORDER BY COALESCE(is_premium,0) DESC, created_at DESC"
        rows = await d.fetch(q, *params)
        if not rows:
            return []
        # Один запрос для всех продавцов
        seller_ids = list({p["seller_id"] for p in rows})
        users = await d.fetch("SELECT user_id,nickname FROM users WHERE user_id=ANY($1)", seller_ids)
        user_map = {u["user_id"]: u["nickname"] or "Аноним" for u in users}
        # Один запрос для всех рейтингов
        ratings = await d.fetch(
            "SELECT seller_id, ROUND(AVG(rating)::numeric,1) as avg FROM reviews WHERE seller_id=ANY($1) GROUP BY seller_id",
            seller_ids
        )
        rating_map = {r["seller_id"]: float(r["avg"]) for r in ratings}
    result = []
    for p in rows:
        sid = p["seller_id"]
        result.append({
            "id": p["id"], "title": p["title"], "description": p["description"],
            "price": round(float(p["price"]), 2), "category": p["category"],
            "subcategory": p["subcategory"] or "",
            "media_id": p["media_id"], "media_type": p["media_type"],
            "preview_url": p["preview_url"] or "",
            "seller_id": sid, "seller_nick": user_map.get(sid, "Аноним"),
            "seller_rating": rating_map.get(sid, 0.0),
            "is_premium": bool(p["is_premium"]),
            "seller_gets": round(float(p["price"]) * (1 - SELL_COMM), 2)
        })
    return result


@app.get("/product/{product_id}")
async def get_product(product_id: int):
    p = await db.get_product(product_id)
    if not p: raise HTTPException(404, "Не найдено")
    s = await db.get_user(p["seller_id"])
    avg, cnt = await db.get_seller_rating(p["seller_id"])
    return {
        "id": p["id"], "title": p["title"], "description": p["description"],
        "price": p["price"], "category": p["category"],
        "media_id": p["media_id"], "media_type": p["media_type"],
        "preview_url": p["preview_url"] or "",
        "seller_id": p["seller_id"], "seller_nick": nick_of(s),
        "seller_rating": round(avg, 1), "seller_reviews": cnt,
        "seller_gets": round(p["price"] * (1 - SELL_COMM), 2)
    }


# ── ME ────────────────────────────────────────────────────
@app.get("/me")
async def get_me(uid: int = Query(...)):
    if not await db.get_user(uid): await db.create_user(uid, "")
    u = await db.get_user(uid)
    async with get_conn() as d:
        row = await d.fetchrow(
            "SELECT gender, earn_balance, avatar_url FROM users WHERE user_id=$1", uid
        )
    gender = row["gender"] or "" if row else ""
    earn_bal = float(row["earn_balance"]) if row and row["earn_balance"] else 0.0
    avatar_url = row["avatar_url"] or "" if row else ""
    return {
        "uid": uid, "nickname": u["nickname"] if u else "",
        "age": u["age"] if u else None,
        "balance": float(u["balance"]) if u else 0.0,
        "earn_balance": earn_bal, "avatar_url": avatar_url,
        "avatar_id": u["avatar_id"] if u else None, "gender": gender
    }


@app.get("/me/update")
async def update_me(
    uid: int = Query(...), nickname: str = Query(...),
    age: int = Query(...), gender: str = Query(default="")
):
    if not nickname or len(nickname) > 30: raise HTTPException(400, "Никнейм от 1 до 30 символов")
    if age < 18 or age > 120: raise HTTPException(400, "Минимальный возраст — 18 лет")
    async with get_conn() as d:
        row = await d.fetchrow(
            "SELECT user_id FROM users WHERE nickname=$1 AND user_id!=$2", nickname, uid
        )
        if row: raise HTTPException(400, "Этот никнейм уже занят")
    u = await db.get_user(uid)
    await db.update_profile(uid, nickname, age, u["avatar_id"] if u else None)
    async with get_conn() as d:
        await d.execute("UPDATE users SET gender=$1 WHERE user_id=$2", gender, uid)
    return {"ok": True}


@app.post("/me/set_avatar")
async def set_avatar_post(request: Request, uid: int = Query(...)):
    body = await request.body()
    avatar_data = body.decode('utf-8')[:15000000]
    async with get_conn() as d:
        await d.execute("UPDATE users SET avatar_url=$1 WHERE user_id=$2", avatar_data, uid)
    return {"ok": True}


@app.get("/me/set_avatar")
async def set_avatar(uid: int = Query(...), avatar_url: str = Query(default="")):
    async with get_conn() as d:
        await d.execute("UPDATE users SET avatar_url=$1 WHERE user_id=$2", avatar_url, uid)
    return {"ok": True}


@app.get("/user/{user_id}")
async def get_user_profile(user_id: int):
    u = await db.get_user(user_id)
    if not u: raise HTTPException(404, "Не найден")
    avg, cnt = await db.get_seller_rating(user_id)
    async with get_conn() as d:
        row = await d.fetchrow("SELECT gender, avatar_url FROM users WHERE user_id=$1", user_id)
    gender = row["gender"] or "" if row else ""
    avatar_url = row["avatar_url"] or "" if row else ""
    return {
        "uid": user_id, "nickname": u["nickname"] or "Аноним",
        "age": u["age"], "gender": gender, "avatar_url": avatar_url,
        "rating": round(avg, 1), "reviews": cnt,
    }


# ── ORDERS ────────────────────────────────────────────────
@app.get("/orders")
async def get_orders(uid: int = Query(...)):
    async with get_conn() as d:
        orders = await d.fetch(
            "SELECT * FROM orders WHERE buyer_id=$1 OR seller_id=$1 ORDER BY created_at DESC", uid
        )
        if not orders:
            return []
        partner_ids = list({o["seller_id"] if o["buyer_id"]==uid else o["buyer_id"] for o in orders})
        product_ids = list({o["product_id"] for o in orders})
        users = await d.fetch("SELECT user_id,nickname FROM users WHERE user_id=ANY($1)", partner_ids)
        user_map = {u["user_id"]: u["nickname"] or "Аноним" for u in users}
        products = await d.fetch("SELECT id,title FROM products WHERE id=ANY($1)", product_ids)
        prod_map = {p["id"]: p["title"] for p in products}
        unreads = await d.fetch(
            "SELECT order_id, COUNT(*) as cnt FROM messages WHERE order_id=ANY($1) AND receiver_id=$2 AND is_read=0 GROUP BY order_id",
            [o["id"] for o in orders], uid
        )
        unread_map = {r["order_id"]: r["cnt"] for r in unreads}
    result = []
    for o in orders:
        pid = o["seller_id"] if o["buyer_id"]==uid else o["buyer_id"]
        result.append({
            "id": o["id"], "short_id": o["short_id"] or f"#{o['id']}",
            "product_title": prod_map.get(o["product_id"], "Удалён"),
            "amount": o["amount"], "status": o["status"],
            "buyer_id": o["buyer_id"], "seller_id": o["seller_id"],
            "partner_nick": user_map.get(pid, "Аноним"),
            "role": "buyer" if o["buyer_id"]==uid else "seller",
            "commission": o["commission"],
            "unread": unread_map.get(o["id"], 0),
            "product_id": o["product_id"]
        })
    return result

@app.get("/orders/{order_id}/messages")
async def get_messages(order_id: int, uid: int = Query(...)):
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"], order["seller_id"]):
        raise HTTPException(403, "Нет доступа")
    await db.mark_read(order_id, uid)
    msgs = await db.get_order_messages(order_id)
    return [{"id": m["id"], "sender_id": m["sender_id"], "text": m["text"],
             "media_type": m["media_type"], "created_at": str(m["created_at"])} for m in msgs]


@app.get("/send_msg")
async def send_msg(order_id: int = Query(...), uid: int = Query(...), text: str = Query(...)):
    if not text.strip(): raise HTTPException(400, "Пустое сообщение")
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"], order["seller_id"]):
        raise HTTPException(403, "Нет доступа")
    partner_id = order["seller_id"] if order["buyer_id"] == uid else order["buyer_id"]
    await db.send_msg(order_id, uid, partner_id, text=text.strip())
    me = await db.get_user(uid)
    short = order["short_id"] or f"#{order_id}"
    asyncio.create_task(notify(partner_id,
        f"💬 Сообщение от <b>{nick_of(me)}</b>\nЗаказ {short}: {text.strip()[:80]}"))
    return {"ok": True}


@app.get("/buy")
async def buy(product_id: int = Query(...), uid: int = Query(...)):
    p = await db.get_product(product_id)
    if not p or p["status"] != "active": raise HTTPException(400, "Товар недоступен")
    if p["seller_id"] == uid: raise HTTPException(400, "Нельзя купить свой товар")
    balance = await db.get_balance(uid)
    if balance < p["price"]:
        return {"ok": False, "reason": "insufficient", "balance": balance, "price": p["price"]}
    commission = round(p["price"] * SELL_COMM, 2)
    await db.change_balance(uid, -p["price"])
    order_id = await db.create_order(uid, p["seller_id"], product_id, p["price"], commission, "")
    await db.update_order_status(order_id, "paid")
    order = await db.get_order(order_id)
    short = order["short_id"] or f"#{order_id}"
    seller_gets = round(p["price"] - commission, 2)
    buyer = await db.get_user(uid)
    asyncio.create_task(notify(p["seller_id"],
        f"💰 <b>Новый заказ!</b>\nПокупатель: {nick_of(buyer)}\nТовар: {p['title']}\nВы получите: {seller_gets} ₽\nЗаказ: {short}"))
    return {"ok": True, "short_id": short}


@app.get("/confirm_order")
async def confirm_order(order_id: int = Query(...), uid: int = Query(...)):
    order = await db.get_order(order_id)
    if not order or order["buyer_id"] != uid: raise HTTPException(403, "Нет доступа")
    if order["status"] not in ("paid", "seller_confirmed"): raise HTTPException(400, "Нельзя закрыть")
    seller_gets = round(order["amount"] - order["commission"], 2)
    unfreeze_at = (datetime.now(MSK) + timedelta(days=2)).isoformat()
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO frozen_funds (user_id,order_id,amount,unfreeze_at) VALUES ($1,$2,$3,$4)",
            order["seller_id"], order_id, seller_gets, unfreeze_at
        )
    await db.update_order_status(order_id, "done")
    asyncio.create_task(notify(order["seller_id"],
        f"💰 Продажа завершена!\n{seller_gets} ₽ заморожены на 2 дня и поступят на баланс {unfreeze_at[:10]}"))
    return {"ok": True}


@app.get("/topup/create")
async def topup_create(amount: int = Query(...), uid: int = Query(...)):
    if amount < 10: raise HTTPException(400, "Минимум 10 ₽")
    code = gen_code()
    topup_id = await db.create_topup(uid, amount, code)
    return {"topup_id": topup_id, "code": code, "da_link": DA_LINK, "amount": amount}


@app.get("/withdraw")
async def withdraw(uid: int = Query(...), amount: float = Query(...), username: str = Query(...)):
    if amount < MIN_WITHDRAW: raise HTTPException(400, f"Минимум {MIN_WITHDRAW} ₽")
    if not username or not username.startswith("@"): raise HTTPException(400, "Укажи @username")
    balance = await db.get_balance(uid)
    if balance < amount: raise HTTPException(400, f"Недостаточно средств. Баланс: {balance:.0f} ₽")
    after = round(amount * (1 - WITHDRAW_COMM), 2)
    stars = math.ceil(after / STAR_RATE)
    await db.change_balance(uid, -amount)
    w_id = await db.create_withdrawal(uid, amount)
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO transactions (user_id,type,amount,description) VALUES ($1,$2,$3,$4)",
            uid, "withdraw", -amount, f"Вывод ⭐{stars} · комиссия {round(amount * WITHDRAW_COMM, 2)} ₽"
        )
    u = await db.get_user(uid)
    asyncio.create_task(notify(ADMIN_ID,
        f"💸 <b>Вывод #{w_id}</b>\n👤 {nick_of(u)} (ID:{uid})\n"
        f"💰 {amount:.0f} ₽ → {after:.0f} ₽ → ⭐{stars}\n📱 {username}"))
    return {"ok": True, "w_id": w_id, "after_commission": after, "stars": stars}


# ── TRANSACTIONS ──────────────────────────────────────────
@app.get("/transactions")
async def get_transactions(uid: int = Query(...)):
    now = datetime.now(MSK)
    async with get_conn() as d:
        due = await d.fetch(
            "SELECT * FROM frozen_funds WHERE user_id=$1 AND is_released=0 AND unfreeze_at<=$2",
            uid, now
        )
        for f in due:
            await db.change_balance(uid, float(f["amount"]))
            await d.execute("UPDATE frozen_funds SET is_released=1 WHERE id=$1", f["id"])
            await d.execute(
                "INSERT INTO transactions (user_id,type,amount,description) VALUES ($1,$2,$3,$4)",
                uid, "sale", float(f["amount"]), "Продажа разморожена (заказ #" + str(f["order_id"]) + ")"
            )
        frozen = await d.fetch(
            "SELECT * FROM frozen_funds WHERE user_id=$1 AND is_released=0 ORDER BY unfreeze_at ASC", uid
        )
        txs = await d.fetch(
            "SELECT * FROM transactions WHERE user_id=$1 ORDER BY created_at DESC LIMIT 50", uid
        )
    frozen_list = [{"id": f["id"], "amount": f["amount"], "order_id": f["order_id"],
                    "unfreeze_at": str(f["unfreeze_at"]),
                    "description": "❄️ Заморожено до " + str(f["unfreeze_at"])[:10]}
                   for f in frozen]
    tx_list = [{"id": t["id"], "type": t["type"], "amount": t["amount"],
                "description": t["description"], "created_at": str(t["created_at"])} for t in txs]
    return {"transactions": tx_list, "frozen": frozen_list}


# ── SUPPORT ───────────────────────────────────────────────
@app.get("/support")
async def support(uid: int = Query(...), message: str = Query(...)):
    if not message.strip(): raise HTTPException(400, "Пустое сообщение")
    ticket_id = await db.create_support_ticket(uid, message.strip())
    u = await db.get_user(uid)
    asyncio.create_task(notify(ADMIN_ID,
        f"[SUPPORT #{ticket_id}] {nick_of(u)} (ID:{uid}) - {message.strip()}"))
    return {"ok": True, "ticket_id": ticket_id}


@app.get("/support/messages")
async def support_messages(uid: int = Query(...)):
    async with get_conn() as d:
        rows = await d.fetch(
            "SELECT * FROM support_chat WHERE user_id=$1 ORDER BY created_at ASC LIMIT 100", uid
        )
    return [{"id": r["id"], "from_admin": bool(r["from_admin"]),
             "message": r["message"], "created_at": str(r["created_at"])} for r in rows]


@app.get("/support/send")
async def support_send(uid: int = Query(...), message: str = Query(...)):
    if not message.strip(): raise HTTPException(400, "Пустое")
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO support_chat (user_id,from_admin,message) VALUES ($1,0,$2)",
            uid, message.strip()
        )
    u = await db.get_user(uid)
    asyncio.create_task(notify(ADMIN_ID,
        f"[SUPPORT] {nick_of(u)} (ID:{uid}): {message.strip()[:100]}"))
    return {"ok": True}


@app.get("/support/reply")
async def support_reply(uid: int = Query(...), user_id: int = Query(...), message: str = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403, "Нет доступа")
    if not message.strip(): raise HTTPException(400, "Пустое")
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO support_chat (user_id,from_admin,message) VALUES ($1,1,$2)",
            user_id, message.strip()
        )
    asyncio.create_task(notify(user_id, f"[Поддержка] {message.strip()[:100]}"))
    return {"ok": True}


@app.get("/support/tickets")
async def support_tickets(uid: int = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403, "Нет доступа")
    async with get_conn() as d:
        rows = await d.fetch(
            """SELECT user_id, MAX(created_at) as last_time,
               (SELECT message FROM support_chat s2 WHERE s2.user_id=s1.user_id ORDER BY created_at DESC LIMIT 1) as last_message
               FROM support_chat s1 WHERE from_admin=0 GROUP BY user_id ORDER BY last_time DESC"""
        )
    result = []
    for r in rows:
        u = await db.get_user(r["user_id"])
        result.append({
            "user_id": r["user_id"], "nickname": nick_of(u),
            "last_message": r["last_message"] or "",
            "last_time": str(r["last_time"]) if r["last_time"] else "",
        })
    return result


# ── MY PRODUCTS ───────────────────────────────────────────
@app.get("/my_products")
async def my_products(uid: int = Query(...)):
    async with get_conn() as d:
        rows = await d.fetch(
            "SELECT * FROM products WHERE seller_id=$1 AND status='active' ORDER BY created_at DESC", uid
        )
    return [{"id": p["id"], "title": p["title"], "price": p["price"],
         "category": p["category"], "subcategory": p["subcategory"] or "",
         "preview_url": p["preview_url"] or "",
         "is_premium": bool(p["is_premium"])} for p in rows]


# ── FRIENDS ───────────────────────────────────────────────
@app.get("/friends")
async def friends_alias(uid: int = Query(...)):
    return await friends_list(uid=uid)


@app.get("/friends/add")
async def add_friend(uid: int = Query(...), friend_id: int = Query(...)):
    if uid == friend_id: raise HTTPException(400, "Нельзя добавить себя")
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO friends (user_id,friend_id,status) VALUES ($1,$2,'pending') ON CONFLICT DO NOTHING",
            uid, friend_id
        )
    u = await db.get_user(uid)
    asyncio.create_task(notify(friend_id, f"[Заявка] {nick_of(u)} хочет добавить вас в друзья"))
    return {"ok": True}


@app.get("/friends/cancel")
async def cancel_friend(uid: int = Query(...), friend_id: int = Query(...)):
    async with get_conn() as d:
        await d.execute(
            "DELETE FROM friends WHERE user_id=$1 AND friend_id=$2 AND status='pending'",
            uid, friend_id
        )
    return {"ok": True}


@app.get("/friends/accept")
async def accept_friend(uid: int = Query(...), friend_id: int = Query(...)):
    async with get_conn() as d:
        await d.execute(
            "UPDATE friends SET status='accepted' WHERE user_id=$1 AND friend_id=$2",
            friend_id, uid
        )
        await d.execute(
            """INSERT INTO friends (user_id,friend_id,status) VALUES ($1,$2,'accepted')
               ON CONFLICT (user_id,friend_id) DO UPDATE SET status='accepted'""",
            uid, friend_id
        )
    u = await db.get_user(uid)
    asyncio.create_task(notify(friend_id, f"[Друзья] {nick_of(u)} принял вашу заявку"))
    return {"ok": True}


@app.get("/friends/remove")
async def remove_friend(uid: int = Query(...), friend_id: int = Query(...)):
    async with get_conn() as d:
        await d.execute(
            "DELETE FROM friends WHERE (user_id=$1 AND friend_id=$2) OR (user_id=$2 AND friend_id=$1)",
            uid, friend_id
        )
    return {"ok": True}


@app.get("/friends/list")
async def friends_list(uid: int = Query(...)):
    async with get_conn() as d:
        rows = await d.fetch("SELECT friend_id,status FROM friends WHERE user_id=$1", uid)
        if not rows:
            return []
        friend_ids = [r["friend_id"] for r in rows]
        users = await d.fetch("SELECT user_id,nickname FROM users WHERE user_id=ANY($1)", friend_ids)
        user_map = {u["user_id"]: u["nickname"] or "Аноним" for u in users}
    return [{"friend_id": r["friend_id"], "nickname": user_map.get(r["friend_id"], "Аноним"), "status": r["status"]} for r in rows]


@app.get("/friends/requests")
async def friend_requests(uid: int = Query(...)):
    async with get_conn() as d:
        rows = await d.fetch(
            "SELECT user_id FROM friends WHERE friend_id=$1 AND status='pending'", uid
        )
    result = []
    for r in rows:
        u = await db.get_user(r["user_id"])
        result.append({"user_id": r["user_id"], "nickname": nick_of(u)})
    return result


@app.get("/friends/status")
async def friend_status(uid: int = Query(...), other_id: int = Query(...)):
    async with get_conn() as d:
        row = await d.fetchrow(
            "SELECT status FROM friends WHERE user_id=$1 AND friend_id=$2", uid, other_id
        )
    return {"status": row["status"] if row else "none"}


# ── GLOBAL CHAT ───────────────────────────────────────────
@app.get("/chat/messages")
async def chat_messages(limit: int = Query(default=50)):
    async with get_conn() as d:
        rows = await d.fetch(
            "SELECT * FROM global_chat ORDER BY created_at DESC LIMIT $1", limit
        )
    return [{"id": r["id"], "user_id": r["user_id"], "nickname": r["nickname"],
             "message": r["message"], "created_at": str(r["created_at"])}
            for r in reversed(rows)]


@app.get("/chat/send")
async def chat_send(uid: int = Query(...), message: str = Query(...)):
    if not message.strip(): raise HTTPException(400, "Пустое сообщение")
    if len(message) > 500: raise HTTPException(400, "Максимум 500 символов")
    if not check_rate_limit(uid):
        raise HTTPException(429, "Слишком много сообщений. Подожди немного")
    u = await db.get_user(uid)
    nickname = nick_of(u)
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO global_chat (user_id, nickname, message) VALUES ($1,$2,$3)",
            uid, nickname, message.strip()
        )
    return {"ok": True}


@app.get("/chat/delete")
async def chat_delete(uid: int = Query(...), msg_id: int = Query(...)):
    async with get_conn() as d:
        row = await d.fetchrow("SELECT user_id FROM global_chat WHERE id=$1", msg_id)
        if not row: raise HTTPException(404, "Сообщение не найдено")
        if row["user_id"] != uid: raise HTTPException(403, "Нет доступа")
        await d.execute("DELETE FROM global_chat WHERE id=$1", msg_id)
    return {"ok": True}


# ── DIRECT MESSAGES ───────────────────────────────────────
@app.get("/dm/send")
async def dm_send(uid: int = Query(...), to_id: int = Query(...),
                  message: str = Query(...), reply_to_text: str = Query(default="")):
    if not message.strip(): raise HTTPException(400, "Пустое сообщение")
    async with get_conn() as d:
        row = await d.fetchrow(
            "SELECT status FROM friends WHERE user_id=$1 AND friend_id=$2", uid, to_id
        )
        if not row or row["status"] != "accepted":
            raise HTTPException(403, "Можно писать только друзьям")
        await d.execute(
            "INSERT INTO dm_messages (from_id,to_id,message,reply_to_text) VALUES ($1,$2,$3,$4)",
            uid, to_id, message.strip(), reply_to_text.strip()
        )
        is_muted = await d.fetchrow(
            "SELECT 1 FROM muted_users WHERE user_id=$1 AND muted_id=$2", to_id, uid
        )
    me = await db.get_user(uid)
    if not is_muted:
        asyncio.create_task(notify(to_id, f"[Сообщение] {nick_of(me)}: {message.strip()[:80]}"))
    return {"ok": True}


@app.get("/dm/mute")
async def dm_mute(uid: int = Query(...), muted_id: int = Query(...), until_ts: int = Query(default=0)):
    async with get_conn() as d:
        if until_ts == -1:
            await d.execute("DELETE FROM muted_users WHERE user_id=$1 AND muted_id=$2", uid, muted_id)
        else:
            await d.execute(
                "INSERT INTO muted_users (user_id,muted_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                uid, muted_id
            )
    return {"ok": True}


@app.get("/dm/messages")
async def dm_messages(uid: int = Query(...), with_id: int = Query(...)):
    async with get_conn() as d:
        await d.execute(
            "UPDATE dm_messages SET is_read=1 WHERE to_id=$1 AND from_id=$2", uid, with_id
        )
        rows = await d.fetch(
            """SELECT * FROM dm_messages
               WHERE (from_id=$1 AND to_id=$2) OR (from_id=$2 AND to_id=$1)
               ORDER BY created_at ASC LIMIT 100""",
            uid, with_id
        )
    return [{"id": r["id"], "from_id": r["from_id"], "message": r["message"],
             "reply_to_text": r["reply_to_text"] or "",
             "is_read": bool(r["is_read"]), "created_at": str(r["created_at"])} for r in rows]


@app.get("/dm/unread_count")
async def dm_unread(uid: int = Query(...)):
    async with get_conn() as d:
        rows = await d.fetch(
            "SELECT from_id, COUNT(*) as cnt FROM dm_messages WHERE to_id=$1 AND is_read=0 GROUP BY from_id",
            uid
        )
    return {str(r["from_id"]): r["cnt"] for r in rows}


@app.get("/dm/conversations")
async def dm_conversations(uid: int = Query(...)):
    async with get_conn() as d:
        rows = await d.fetch(
            """SELECT DISTINCT ON (partner_id)
                CASE WHEN from_id=$1 THEN to_id ELSE from_id END as partner_id,
                message, created_at, is_read, from_id
               FROM dm_messages
               WHERE from_id=$1 OR to_id=$1
               ORDER BY partner_id, created_at DESC""",
            uid
        )
    result = []
    for r in rows:
        partner = await db.get_user(r["partner_id"])
        async with get_conn() as d:
            urow = await d.fetchrow(
                "SELECT COUNT(*) as cnt FROM dm_messages WHERE to_id=$1 AND from_id=$2 AND is_read=0",
                uid, r["partner_id"]
            )
        result.append({
            "partner_id": r["partner_id"], "nickname": nick_of(partner),
            "last_message": r["message"], "created_at": str(r["created_at"]),
            "unread": urow["cnt"] if urow else 0,
            "is_out": r["from_id"] == uid
        })
    return result


@app.get("/dm/delete")
async def dm_delete(uid: int = Query(...), with_id: int = Query(...), both_sides: int = Query(default=0)):
    async with get_conn() as d:
        if both_sides:
            await d.execute(
                "DELETE FROM dm_messages WHERE (from_id=$1 AND to_id=$2) OR (from_id=$2 AND to_id=$1)",
                uid, with_id
            )
        else:
            await d.execute(
                "DELETE FROM dm_messages WHERE from_id=$1 AND to_id=$2", uid, with_id
            )
    return {"ok": True}
