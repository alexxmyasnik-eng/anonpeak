import random, string, math, asyncio, json, hmac, hashlib, urllib.parse, time, base64
from collections import defaultdict
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
from db_neon import get_conn, _get_pool, keepalive_loop
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
import database as db


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
# ── SIMPLE IN-MEMORY CACHE ────────────────────────────────
import time as _time
_cache: dict = {}

def cache_get(key: str, ttl: int = 60):
    """Вернёт данные если не устарели, иначе None."""
    entry = _cache.get(key)
    if entry and (_time.monotonic() - entry["ts"]) < ttl:
        return entry["data"]
    return None

def cache_set(key: str, data):
    _cache[key] = {"data": data, "ts": _time.monotonic()}

def cache_del(key: str):
    _cache.pop(key, None)

def cache_del_prefix(prefix: str):
    for k in list(_cache.keys()):
        if k.startswith(prefix):
            _cache.pop(k, None)


@asynccontextmanager
async def lifespan(app):
    asyncio.create_task(keepalive_loop())
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
_withdraw_ratelimit: dict = {}  # user_id -> timestamp последней заявки


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
        await d.execute("UPDATE products SET subcategory=$1, status='pending' WHERE id=$2", subcategory.strip(), product_id)
        if is_premium:
            await d.execute(
                "UPDATE products SET is_premium=1, premium_at=$1 WHERE id=$2",
                datetime.now(MSK).replace(tzinfo=None), product_id
            )
            cache_del_prefix("products:")
    return {"ok": True, "product_id": product_id, "seller_gets": round(price * (1 - SELL_COMM), 2)}


@app.get("/products/delete")
async def delete_product(uid: int = Query(...), product_id: int = Query(...)):
    async with get_conn() as d:
        row = await d.fetchrow("SELECT seller_id FROM products WHERE id=$1", product_id)
        if not row: raise HTTPException(404, "Товар не найден")
        if row["seller_id"] != uid: raise HTTPException(403, "Нет доступа")
        await d.execute("UPDATE products SET status='deleted' WHERE id=$1", product_id)
    cache_del_prefix("products:")
    return {"ok": True}

@app.get("/products/update")
async def update_product(
    uid: int = Query(...), product_id: int = Query(...),
    title: str = Query(...), description: str = Query(default=""),
    price: float = Query(...)
):
    if not title or len(title) > 100: raise HTTPException(400, "Название от 1 до 100 символов")
    async with get_conn() as d:
        row = await d.fetchrow("SELECT seller_id FROM products WHERE id=$1", product_id)
        if not row: raise HTTPException(404, "Товар не найден")
        if row["seller_id"] != uid: raise HTTPException(403, "Нет доступа")
        await d.execute(
            "UPDATE products SET title=$1, description=$2, price=$3 WHERE id=$4",
            title, description, price, product_id
        )
    cache_del_prefix("products:")
    return {"ok": True}

@app.get("/admin/moderation")
async def admin_moderation(uid: int = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403, "Нет доступа")
    async with get_conn() as d:
        rows = await d.fetch("""
            SELECT p.id, p.title, p.category, p.price, p.created_at,
                   u.nickname as seller_nick, p.seller_id
            FROM products p
            JOIN users u ON u.user_id = p.seller_id
            WHERE p.status='pending'
            ORDER BY p.created_at ASC
        """)
    return [{"id": r["id"], "title": r["title"], "category": r["category"],
             "price": float(r["price"]), "seller_nick": r["seller_nick"] or "Аноним",
             "seller_id": r["seller_id"], "created_at": str(r["created_at"])} for r in rows]

@app.get("/admin/moderation/approve")
async def admin_moderation_approve(uid: int = Query(...), product_id: int = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403, "Нет доступа")
    async with get_conn() as d:
        row = await d.fetchrow("SELECT seller_id FROM products WHERE id=$1 AND status='pending'", product_id)
        if not row: raise HTTPException(404, "Товар не найден")
        await d.execute("UPDATE products SET status='active' WHERE id=$1", product_id)
    cache_del_prefix("products:")
    asyncio.create_task(notify(row["seller_id"], f"✅ Ваш товар #{product_id} прошёл модерацию и теперь виден всем!"))
    return {"ok": True}

@app.get("/admin/moderation/reject")
async def admin_moderation_reject(uid: int = Query(...), product_id: int = Query(...), reason: str = Query(default="Не соответствует правилам")):
    if uid != ADMIN_ID: raise HTTPException(403, "Нет доступа")
    async with get_conn() as d:
        row = await d.fetchrow("SELECT seller_id, is_premium FROM products WHERE id=$1 AND status='pending'", product_id)
        if not row: raise HTTPException(404, "Товар не найден")
        if row["is_premium"]:
            await db.change_balance(row["seller_id"], PREMIUM_PRICE)
        await d.execute("UPDATE products SET status='deleted' WHERE id=$1", product_id)
    asyncio.create_task(notify(row["seller_id"], f"❌ Ваш товар #{product_id} отклонён модератором. Причина: {reason}"))
    return {"ok": True}

@app.get("/admin/topup")
async def admin_topup(uid: int = Query(...), to_uid: int = Query(...), amount: float = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403, "Нет доступа")
    if amount <= 0: raise HTTPException(400, "Сумма должна быть > 0")
    await db.change_balance(to_uid, amount)
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO transactions (user_id,type,amount,description) VALUES ($1,$2,$3,$4)",
            to_uid, "topup", amount, "Пополнение от администратора"
        )
    asyncio.create_task(notify(to_uid, f"💰 Администратор пополнил ваш баланс на {amount:.0f} ₽"))
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


@app.get("/products/relist")
async def relist_product(
    uid: int = Query(...), product_id: int = Query(...),
    is_premium: bool = Query(default=False)
):
    async with get_conn() as d:
        row = await d.fetchrow("SELECT seller_id, status FROM products WHERE id=$1", product_id)
        if not row: raise HTTPException(404, "Товар не найден")
        if row["status"] not in ("sold", "pending"):
            raise HTTPException(400, f"Нельзя переопубликовать товар со статусом: {row['status']}")
        if row["seller_id"] != uid: raise HTTPException(403, "Нет доступа")
    if is_premium:
        balance = await db.get_balance(uid)
        if balance < PREMIUM_PRICE:
            raise HTTPException(400, f"Недостаточно средств для премиум ({PREMIUM_PRICE} ₽)")
        await db.change_balance(uid, -PREMIUM_PRICE)
    async with get_conn() as d:
        await d.execute("UPDATE products SET status='pending', is_premium=$1 WHERE id=$2", 1 if is_premium else 0, product_id)
    cache_del_prefix("products:")
    return {"ok": True}


    async with get_conn() as d:
        q = """SELECT p.id, p.title, p.description, p.price, p.category,
                      p.subcategory, p.media_id, p.media_type, p.preview_url,
                      p.seller_id, p.is_premium,
                      u.nickname as seller_nick
               FROM products p
               JOIN users u ON u.user_id = p.seller_id
               WHERE p.category=$1 AND p.status='active'"""
        params = [category]
        idx = 2
        if sub and sub.strip():
            q += f" AND REPLACE(TRIM(p.subcategory), '\u00a0', ' ')=${idx}"
            params.append(sub)
            idx += 1
        if seller:
            q += f" AND p.seller_id=${idx}"
            params.append(seller)
        q += " ORDER BY COALESCE(p.is_premium,0) DESC, p.created_at DESC LIMIT 100"
        rows = await d.fetch(q, *params)
        if not rows:
            return []
        seller_ids = list({p["seller_id"] for p in rows})
        ratings = await d.fetch(
            "SELECT seller_id, ROUND(AVG(rating)::numeric,1) as avg FROM reviews WHERE seller_id=ANY($1) GROUP BY seller_id",
            seller_ids
        )
        rating_map = {r["seller_id"]: float(r["avg"]) for r in ratings}

    result = [{
        "id":            p["id"],
        "title":         p["title"],
        "description":   p["description"],
        "price":         round(float(p["price"]), 2),
        "category":      p["category"],
        "subcategory":   p["subcategory"] or "",
        "media_id":      p["media_id"],
        "media_type":    p["media_type"],
        "preview_url":   p["preview_url"] or "",
        "seller_id":     p["seller_id"],
        "seller_nick":   p["seller_nick"] or "Аноним",
        "seller_rating": rating_map.get(p["seller_id"], 0.0),
        "is_premium":    bool(p["is_premium"]),
        "seller_gets":   round(float(p["price"]) * (1 - SELL_COMM), 2)
    } for p in rows]

    if not seller:
        cache_set(cache_key, result)
    return result

@app.get("/search")
async def search_products(q: str = Query(..., min_length=2)):
    cache_key = f"search:{q.lower().strip()}"
    cached = cache_get(cache_key, ttl=120)
    if cached is not None:
        return cached

    async with get_conn() as d:
        rows = await d.fetch("""
            SELECT p.id, p.title, p.description, p.price, p.category,
                   p.subcategory, p.media_id, p.media_type, p.preview_url,
                   p.seller_id, p.is_premium,
                   u.nickname as seller_nick,
                   ROUND(AVG(r.rating)::numeric,1) as seller_rating
            FROM products p
            JOIN users u ON u.user_id = p.seller_id
            LEFT JOIN reviews r ON r.seller_id = p.seller_id
            WHERE p.status='active'
              AND (
                p.title ILIKE $1
                OR p.description ILIKE $1
              )
            GROUP BY p.id, u.nickname
            ORDER BY COALESCE(p.is_premium,0) DESC, p.created_at DESC
            LIMIT 50
        """, f"%{q.strip()}%")

    result = [{
        "id":            p["id"],
        "title":         p["title"],
        "description":   p["description"],
        "price":         round(float(p["price"]), 2),
        "category":      p["category"],
        "subcategory":   p["subcategory"] or "",
        "media_id":      p["media_id"],
        "media_type":    p["media_type"],
        "preview_url":   p["preview_url"] or "",
        "seller_id":     p["seller_id"],
        "seller_nick":   p["seller_nick"] or "Аноним",
        "seller_rating": float(p["seller_rating"]) if p["seller_rating"] else 0.0,
        "is_premium":    bool(p["is_premium"]),
        "seller_gets":   round(float(p["price"]) * (1 - SELL_COMM), 2)
    } for p in rows]

    cache_set(cache_key, result)
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
        "seller_gets": round(p["price"] * (1 - SELL_COMM), 2),
        "status": p["status"]
    }

@app.get("/products/{category}")
async def get_products(category: str, sub: str = Query(default=""), seller: int = Query(default=0)):
    sub = sub.replace('\u00a0', ' ').strip()  # ← добавь эту строку
    if category not in CATEGORIES: raise HTTPException(404, "Не найдено")

    cache_key = f"products:{category}:{sub.strip()}"
    if not seller:
        cached = cache_get(cache_key, ttl=60)
        if cached is not None:
            return cached

    async with get_conn() as d:
        q = """SELECT p.id, p.title, p.description, p.price, p.category,
                      p.subcategory, p.media_id, p.media_type, p.preview_url,
                      p.seller_id, p.is_premium,
                      u.nickname as seller_nick
               FROM products p
               JOIN users u ON u.user_id = p.seller_id
               WHERE p.category=$1 AND p.status='active'"""
        params = [category]
        idx = 2
        if sub and sub.strip():
            q += f" AND LOWER(TRIM(p.subcategory))=LOWER(${idx})"
            params.append(sub.strip())
            idx += 1
        if seller:
            q += f" AND p.seller_id=${idx}"
            params.append(seller)
        q += " ORDER BY COALESCE(p.is_premium,0) DESC, p.created_at DESC LIMIT 100"
        rows = await d.fetch(q, *params)
        if not rows:
            return []
        seller_ids = list({p["seller_id"] for p in rows})
        ratings = await d.fetch(
            "SELECT seller_id, ROUND(AVG(rating)::numeric,1) as avg FROM reviews WHERE seller_id=ANY($1) GROUP BY seller_id",
            seller_ids
        )
        rating_map = {r["seller_id"]: float(r["avg"]) for r in ratings}

    result = [{
        "id":            p["id"],
        "title":         p["title"],
        "description":   p["description"],
        "price":         round(float(p["price"]), 2),
        "category":      p["category"],
        "subcategory":   p["subcategory"] or "",
        "media_id":      p["media_id"],
        "media_type":    p["media_type"],
        "preview_url":   p["preview_url"] or "",
        "seller_id":     p["seller_id"],
        "seller_nick":   p["seller_nick"] or "Аноним",
        "seller_rating": rating_map.get(p["seller_id"], 0.0),
        "is_premium":    bool(p["is_premium"]),
        "seller_gets":   round(float(p["price"]) * (1 - SELL_COMM), 2)
    } for p in rows]

    if not seller:
        cache_set(cache_key, result)
    return result

# ── ME ────────────────────────────────────────────────────
@app.get("/me")
async def get_me(uid: int = Query(...)):
    u = await db.get_or_create_user(uid)
    return {
        "uid": uid,
        "nickname": u["nickname"] or "",
        "age": u["age"],
        "balance": float(u["balance"] or 0),
        "earn_balance": float(u["earn_balance"] or 0),
        "avatar_url": u["avatar_url"] or "",
        "avatar_id": u["avatar_id"],
        "gender": u["gender"] or ""
    }


@app.get("/me/update")
async def update_me(
    uid: int = Query(...), nickname: str = Query(...),
    age: int = Query(...), gender: str = Query(default="")
):
    if not nickname or len(nickname) > 30: raise HTTPException(400, "Никнейм от 1 до 30 символов")
    if age < 10 or age > 120: raise HTTPException(400, "Минимальный возраст — 10 лет")
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
    # Если прислали file_id (короткая строка) — сохраняем напрямую
    text = body.decode('utf-8').strip()
    if len(text) < 200:  # file_id всегда короткий
        async with get_conn() as d:
            await d.execute("UPDATE users SET avatar_url=$1 WHERE user_id=$2", text, uid)
        return {"ok": True, "mode": "file_id"}
    # Старый путь: base64 — конвертируем через бота
    import base64, io
    try:
        header, b64data = text.split(",", 1)
        img_bytes = base64.b64decode(b64data)
    except Exception:
        raise HTTPException(400, "Неверный формат")
    # Отправляем фото в Telegram-канал через бота, получаем file_id
    from config import MEDIA_CHANNEL_ID, BOT_TOKEN
    import aiohttp as _aio
    async with _aio.ClientSession() as session:
        data = _aio.FormData()
        data.add_field("chat_id", str(MEDIA_CHANNEL_ID))
        data.add_field("photo", io.BytesIO(img_bytes), filename="ava.jpg", content_type="image/jpeg")
        async with session.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data=data) as resp:
            result = await resp.json()
    if not result.get("ok"):
        raise HTTPException(500, "Ошибка загрузки фото")
    # Берём наибольший размер фото
    file_id = result["result"]["photo"][-1]["file_id"]
    async with get_conn() as d:
        await d.execute("UPDATE users SET avatar_url=$1 WHERE user_id=$2", file_id, uid)
    return {"ok": True, "mode": "file_id", "file_id": file_id}


@app.get("/me/set_avatar")
async def set_avatar(uid: int = Query(...), avatar_url: str = Query(default="")):
    # Оставляем для совместимости (URL или file_id)
    async with get_conn() as d:
        await d.execute("UPDATE users SET avatar_url=$1 WHERE user_id=$2", avatar_url, uid)
    return {"ok": True}

@app.get("/user/{user_id}")
async def get_user_profile(user_id: int):
    async with get_conn() as d:
        row = await d.fetchrow("""
            SELECT u.*, 
                   ROUND(AVG(r.rating)::numeric, 1) as avg_rating,
                   COUNT(r.id) as review_cnt
            FROM users u
            LEFT JOIN reviews r ON r.seller_id = u.user_id
            WHERE u.user_id = $1
            GROUP BY u.user_id
        """, user_id)
    if not row:
        raise HTTPException(404, "Не найден")
    return {
        "uid": user_id,
        "nickname": row["nickname"] or "Аноним",
        "age": row["age"],
        "gender": row["gender"] or "",
        "avatar_url": row["avatar_url"] or "",
        "rating": float(row["avg_rating"] or 0),
        "reviews": row["review_cnt"] or 0,
    }


# ── ORDERS ────────────────────────────────────────────────
@app.get("/orders")
async def get_orders(uid: int = Query(...)):
    async with get_conn() as d:
        orders = await d.fetch("""
            SELECT o.id, o.short_id, o.product_id, o.buyer_id, o.seller_id,
                   o.amount, o.status, o.commission, o.created_at,
                   p.title as product_title,
                   u.nickname as partner_nick,
                   COALESCE(unr.cnt, 0) as unread
            FROM orders o
            LEFT JOIN products p ON p.id = o.product_id
            LEFT JOIN users u ON u.user_id =
                CASE WHEN o.buyer_id=$1 THEN o.seller_id ELSE o.buyer_id END
            LEFT JOIN (
                SELECT order_id, COUNT(*) as cnt
                FROM messages
                WHERE receiver_id=$1 AND is_read=0
                GROUP BY order_id
            ) unr ON unr.order_id = o.id
            WHERE o.buyer_id=$1 OR o.seller_id=$1
            ORDER BY o.created_at DESC
            LIMIT 50
        """, uid)
    return [{
        "id":            o["id"],
        "short_id":      o["short_id"] or f"#{o['id']}",
        "product_title": o["product_title"] or "Удалён",
        "amount":        o["amount"],
        "status":        o["status"],
        "buyer_id":      o["buyer_id"],
        "seller_id":     o["seller_id"],
        "partner_nick":  o["partner_nick"] or "Аноним",
        "role":          "buyer" if o["buyer_id"] == uid else "seller",
        "commission":    o["commission"],
        "unread":        o["unread"],
        "product_id":    o["product_id"]
    } for o in orders]

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
    # Помечаем товар как проданный
    async with get_conn() as d:
        await d.execute("UPDATE products SET status='sold' WHERE id=$1", product_id)
    cache_del_prefix("products:")
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
    unfreeze_at = datetime.now(MSK) + timedelta(days=2)
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO frozen_funds (user_id,order_id,amount,unfreeze_at) VALUES ($1,$2,$3,$4)",
            order["seller_id"], order_id, seller_gets, unfreeze_at
        )
    await db.update_order_status(order_id, "done")
    asyncio.create_task(notify(order["seller_id"],
        f"💰 Продажа завершена!\n{seller_gets} ₽ заморожены на 2 дня и поступят на баланс {unfreeze_at.strftime('%Y-%m-%d')}"))
    return {"ok": True}


@app.get("/topup/create")
async def topup_create(amount: int = Query(...), uid: int = Query(...)):
    if amount < 10: raise HTTPException(400, "Минимум 10 ₽")
    code = gen_code()
    topup_id = await db.create_topup(uid, amount, code)
    return {"topup_id": topup_id, "code": code, "da_link": DA_LINK, "amount": amount}


@app.get("/withdraw")
async def withdraw(uid: int = Query(...), amount: float = Query(...), username: str = Query(...)):
    now_ts = time.time()
    last = _withdraw_ratelimit.get(uid, 0)
    if now_ts - last < 3600:
        wait_min = int((3600 - (now_ts - last)) // 60) + 1
        raise HTTPException(429, f"Следующую заявку можно подать через {wait_min} мин.")
    if amount < MIN_WITHDRAW: raise HTTPException(400, f"Минимум {MIN_WITHDRAW} ₽")
    if not username or not username.startswith("@"): raise HTTPException(400, "Укажи @username")
    balance = await db.get_balance(uid)
    if balance < amount: raise HTTPException(400, f"Недостаточно средств. Баланс: {balance:.0f} ₽")
    after = round(amount * (1 - WITHDRAW_COMM), 2)
    stars = math.ceil(after / STAR_RATE)
    await db.change_balance(uid, -amount)
    w_id = await db.create_withdrawal(uid, amount)
    _withdraw_ratelimit[uid] = now_ts
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO transactions (user_id,type,amount,description) VALUES ($1,$2,$3,$4)",
            uid, "withdraw", -amount, f"Вывод {stars} ⭐"
        )
    u = await db.get_user(uid)
    asyncio.create_task(notify(ADMIN_ID,
        f"💸 <b>Вывод #{w_id}</b>\n👤 {nick_of(u)} (ID:{uid})\n"
        f"💰 {amount:.0f} ₽ → {after:.0f} ₽ → ⭐{stars}\n📱 {username}"))
    return {"ok": True, "w_id": w_id, "after_commission": after, "stars": stars}

@app.get("/withdraw/cancel")
async def withdraw_cancel(uid: int = Query(...), w_id: int = Query(...)):
    # Проверяем что заявка принадлежит этому пользователю
    async with get_conn() as d:
        row = await d.fetchrow(
            "SELECT user_id, status FROM withdrawals WHERE id=$1", w_id
        )
    if not row:
        raise HTTPException(404, "Заявка не найдена")
    if row["user_id"] != uid:
        raise HTTPException(403, "Нет доступа")
    if row["status"] != "pending":
        raise HTTPException(400, "Нельзя отменить — заявка уже обработана")
    result = await db.cancel_withdrawal(w_id)
    if not result:
        raise HTTPException(400, "Не удалось отменить заявку")
    u = await db.get_user(uid)
    asyncio.create_task(notify(ADMIN_ID,
        f"❌ <b>Вывод #{w_id} отменён</b> пользователем\n👤 {nick_of(u)} (ID:{uid})\n💰 {result['amount']:.0f} ₽ возвращено"))
    return {"ok": True, "refunded": result["amount"]}

@app.get("/withdraw/cooldown")
async def withdraw_cooldown(uid: int = Query(...)):
    now_ts = time.time()
    last = _withdraw_ratelimit.get(uid, 0)
    remaining = 3600 - (now_ts - last)
    if remaining > 0:
        wait_min = int(remaining // 60) + 1
        return {"wait_min": wait_min}
    return {"wait_min": 0}

@app.get("/admin/withdrawals")
async def admin_withdrawals(uid: int = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403, "Нет доступа")
    async with get_conn() as d:
        rows = await d.fetch(
            """SELECT w.id, w.user_id, w.amount, w.created_at,
                      u.nickname
               FROM withdrawals w
               JOIN users u ON u.user_id = w.user_id
               WHERE w.status='pending'
               ORDER BY w.created_at ASC""")
    return [{"id": r["id"], "user_id": r["user_id"], "amount": float(r["amount"]),
             "nickname": r["nickname"] or "Аноним", "created_at": str(r["created_at"])}
            for r in rows]

@app.get("/admin/withdraw/approve")
async def admin_withdraw_approve(uid: int = Query(...), w_id: int = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403, "Нет доступа")
    async with get_conn() as d:
        row = await d.fetchrow("SELECT user_id, amount FROM withdrawals WHERE id=$1 AND status='pending'", w_id)
        if not row: raise HTTPException(404, "Заявка не найдена или уже обработана")
        await d.execute("UPDATE withdrawals SET status='done' WHERE id=$1", w_id)
    u = await db.get_user(row["user_id"])
    asyncio.create_task(notify(row["user_id"], f"✅ Вывод #{w_id} одобрен! {float(row['amount']):.0f} ₽ отправлены."))
    return {"ok": True}

@app.get("/admin/withdraw/reject")
async def admin_withdraw_reject(uid: int = Query(...), w_id: int = Query(...)):
    if uid != ADMIN_ID: raise HTTPException(403, "Нет доступа")
    async with get_conn() as d:
        row = await d.fetchrow("SELECT user_id, amount FROM withdrawals WHERE id=$1 AND status='pending'", w_id)
        if not row: raise HTTPException(404, "Заявка не найдена или уже обработана")
        await db.change_balance(row["user_id"], float(row["amount"]))
        await d.execute("UPDATE withdrawals SET status='cancelled' WHERE id=$1", w_id)
        await d.execute("DELETE FROM transactions WHERE user_id=$1 AND type='withdraw' AND ABS(amount)=$2 AND created_at > NOW() - INTERVAL '2 hours'",
                        row["user_id"], float(row["amount"]))
    u = await db.get_user(row["user_id"])
    asyncio.create_task(notify(row["user_id"], f"❌ Вывод #{w_id} отклонён. {float(row['amount']):.0f} ₽ возвращены на баланс."))
    return {"ok": True}


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
        pending_wds = await d.fetch(
            "SELECT id, amount, created_at FROM withdrawals WHERE user_id=$1 AND status='pending' ORDER BY created_at DESC",
            uid
        )
    frozen_list = [{"id": f["id"], "amount": f["amount"], "order_id": f["order_id"],
                    "unfreeze_at": str(f["unfreeze_at"]),
                    "description": "❄️ Заморожено до " + str(f["unfreeze_at"])[:10]}
                   for f in frozen]
    tx_list = [{"id": t["id"], "type": t["type"], "amount": t["amount"],
                "description": t["description"], "created_at": str(t["created_at"])} for t in txs]
    return {
        "transactions": tx_list,
        "frozen": frozen_list,
        "pending_withdrawals": [
            {"id": w["id"], "amount": float(w["amount"]), "created_at": str(w["created_at"])}
            for w in pending_wds
        ]
    }


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
            "SELECT * FROM products WHERE seller_id=$1 AND status IN ('active','sold','pending') ORDER BY created_at DESC", uid
        )
    return [{"id": p["id"], "title": p["title"], "price": p["price"],
         "category": p["category"], "subcategory": p["subcategory"] or "",
         "preview_url": p["preview_url"] or "",
         "is_premium": bool(p["is_premium"]),
         "status": p["status"]} for p in rows]


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
        rows = await d.fetch("""
            SELECT f.friend_id, u.nickname, u.avatar_url, f.status
            FROM friends f
            JOIN users u ON u.user_id = f.friend_id
            WHERE f.user_id=$1 AND f.status='accepted'
        """, uid)
    return [{
        "friend_id":  r["friend_id"],
        "nickname":   r["nickname"] or "Аноним",
        "avatar_url": r["avatar_url"] or "",
        "status":     r["status"]
    } for r in rows]


@app.get("/friends/requests")
async def friend_requests(uid: int = Query(...)):
    async with get_conn() as d:
        rows = await d.fetch("""
            SELECT f.user_id, u.nickname, u.avatar_url
            FROM friends f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.friend_id=$1 AND f.status='pending'
        """, uid)
    return [{"user_id": r["user_id"], "nickname": r["nickname"] or "Аноним", "avatar_url": r["avatar_url"] or ""} for r in rows]


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



@app.get("/notifications")
async def notifications(uid: int = Query(...)):
    async with get_conn() as d:
        # Непрочитанные сообщения в заказах
        orders_row = await d.fetchrow("""
            SELECT COUNT(*) as cnt
            FROM messages m
            JOIN orders o ON o.id = m.order_id
            WHERE m.receiver_id=$1
              AND m.is_read=0
              AND (o.buyer_id=$1 OR o.seller_id=$1)
        """, uid)

        # Непрочитанные DM
        dm_row = await d.fetchrow("""
            SELECT COUNT(*) as cnt
            FROM dm_messages
            WHERE to_id=$1 AND is_read=0
        """, uid)

        # Заявки в друзья
        fr_row = await d.fetchrow("""
            SELECT COUNT(*) as cnt
            FROM friends
            WHERE friend_id=$1 AND status='pending'
        """, uid)

    return {
        "orders_unread":   int(orders_row["cnt"]) if orders_row else 0,
        "dm_unread":       int(dm_row["cnt"])     if dm_row     else 0,
        "friend_requests": int(fr_row["cnt"])     if fr_row     else 0
    }

@app.get("/dm/conversations")
async def dm_conversations(uid: int = Query(...)):
    async with get_conn() as d:
        rows = await d.fetch("""
            SELECT DISTINCT ON (partner_id)
                CASE WHEN m.from_id=$1 THEN m.to_id ELSE m.from_id END as partner_id,
                m.message,
                m.created_at,
                m.is_read,
                m.from_id,
                u.nickname,
                u.avatar_url,
                (
                    SELECT COUNT(*) FROM dm_messages x
                    WHERE x.to_id=$1 AND x.from_id=
                        CASE WHEN m.from_id=$1 THEN m.to_id ELSE m.from_id END
                    AND x.is_read=0
                ) as unread_cnt
            FROM dm_messages m
            JOIN users u ON u.user_id =
                CASE WHEN m.from_id=$1 THEN m.to_id ELSE m.from_id END
            WHERE m.from_id=$1 OR m.to_id=$1
            ORDER BY partner_id, m.created_at DESC
        """, uid)
    return [{
        "partner_id": r["partner_id"],
        "nickname":   r["nickname"] or "Аноним",
        "avatar_url": r["avatar_url"] or "",
        "last_message": r["message"],
        "created_at": str(r["created_at"]),
        "unread": r["unread_cnt"],
        "is_out": r["from_id"] == uid
    } for r in rows]


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
