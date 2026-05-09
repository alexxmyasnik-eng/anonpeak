import random
import string
import math
import aiosqlite
import aiohttp
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

import database as db

# Берём всё из config безопасно
try:
    from config import BOT_TOKEN, ADMIN_ID, DA_LINK, DB_PATH
except ImportError:
    BOT_TOKEN = ""
    ADMIN_ID = 0
    DA_LINK = "https://donationalerts.com"
    DB_PATH = "bot.db"

SELL_COMM    = 0.16
WITHDRAW_COMM = 0.05
STAR_RATE    = 1.4
PREMIUM_PRICE = 9
MIN_PRICE    = 15
MIN_WITHDRAW = 100

CATEGORIES = {
    "signa":  "🖊 Сигна",
    "mugs":   "☕ Кружки",
    "photos": "📸 Фото",
    "videos": "🎬 Видео",
}


async def migrate():
    """Добавляем колонки если их нет — без ошибок."""
    async with aiosqlite.connect(DB_PATH) as d:
        for sql in [
            "ALTER TABLE users ADD COLUMN gender TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN is_premium INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN premium_at TIMESTAMP",
        ]:
            try:
                await d.execute(sql)
            except Exception:
                pass
        await d.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await migrate()
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── HELPERS ───────────────────────────────────────────────

def gen_code() -> str:
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    a = ''.join(random.choices(chars, k=4))
    b = ''.join(random.choices(chars, k=4))
    return f"{a}-{b}"


async def notify(chat_id: int, text: str, btn_text: str = "Открыть приложение"):
    """Отправляет уведомление в Telegram. Не падает при ошибке."""
    if not BOT_TOKEN or not chat_id:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await asyncio.wait_for(
                s.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": {
                            "inline_keyboard": [[{
                                "text": btn_text,
                                "web_app": {"url": "https://alexxmyasnik-eng.github.io/anonminiapp"}
                            }]]
                        }
                    }
                ),
                timeout=5
            )
    except Exception:
        pass


async def get_uid(
    uid: Optional[str] = Query(default=None),
    x_tg_user_id: str = Header(default="")
) -> int:
    # Принимаем uid из query параметра (?uid=123) или из заголовка
    raw = uid or x_tg_user_id or ""
    if not raw or not raw.isdigit():
        raise HTTPException(401, "Unauthorized")
    user_id = int(raw)
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(user_id, "")
    return user_id


def nick_of(user) -> str:
    if user and user["nickname"]:
        return user["nickname"]
    return "Аноним"


# ── PUBLIC ────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/categories")
async def get_categories():
    return [{"id": k, "name": v} for k, v in CATEGORIES.items()]


@app.get("/products/{category}")
async def get_products(category: str):
    if category not in CATEGORIES:
        raise HTTPException(404, "Категория не найдена")
    async with aiosqlite.connect(DB_PATH) as d:
        d.row_factory = aiosqlite.Row
        async with d.execute(
            "SELECT * FROM products WHERE category=? AND status='active' "
            "ORDER BY COALESCE(is_premium,0) DESC, created_at DESC",
            (category,)
        ) as c:
            rows = await c.fetchall()
    result = []
    for p in rows:
        seller = await db.get_user(p["seller_id"])
        avg, _ = await db.get_seller_rating(p["seller_id"])
        is_prem = bool(p["is_premium"]) if "is_premium" in p.keys() else False
        result.append({
            "id": p["id"], "title": p["title"],
            "description": p["description"], "price": p["price"],
            "category": p["category"],
            "media_id": p["media_id"], "media_type": p["media_type"],
            "seller_id": p["seller_id"],
            "seller_nick": nick_of(seller),
            "seller_rating": round(avg, 1),
            "is_premium": is_prem,
            "seller_gets": round(p["price"] * (1 - SELL_COMM), 2),
        })
    return result


@app.get("/product/{product_id}")
async def get_product(product_id: int):
    p = await db.get_product(product_id)
    if not p:
        raise HTTPException(404, "Товар не найден")
    seller = await db.get_user(p["seller_id"])
    avg, cnt = await db.get_seller_rating(p["seller_id"])
    return {
        "id": p["id"], "title": p["title"],
        "description": p["description"], "price": p["price"],
        "category": p["category"],
        "media_id": p["media_id"], "media_type": p["media_type"],
        "seller_id": p["seller_id"],
        "seller_nick": nick_of(seller),
        "seller_rating": round(avg, 1),
        "seller_reviews": cnt,
        "seller_gets": round(p["price"] * (1 - SELL_COMM), 2),
    }


# ── AUTH REQUIRED ─────────────────────────────────────────

@app.get("/me")
async def get_me(uid: int = Depends(get_uid)):
    u = await db.get_user(uid)
    gender = ""
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            async with d.execute(
                "SELECT gender FROM users WHERE user_id=?", (uid,)
            ) as c:
                row = await c.fetchone()
                if row and row[0]:
                    gender = row[0]
    except Exception:
        pass
    return {
        "uid": uid,
        "nickname": u["nickname"] if u else "",
        "age": u["age"] if u else None,
        "balance": float(u["balance"]) if u else 0.0,
        "avatar_id": u["avatar_id"] if u else None,
        "gender": gender,
    }


class UpdateProfileReq(BaseModel):
    nickname: str
    age: int
    gender: Optional[str] = ""


@app.post("/me/update")
async def update_me(req: UpdateProfileReq, uid: int = Depends(get_uid)):
    if not req.nickname or len(req.nickname) > 30:
        raise HTTPException(400, "Никнейм от 1 до 30 символов")
    if req.age < 1 or req.age > 120:
        raise HTTPException(400, "Укажи реальный возраст")
    u = await db.get_user(uid)
    await db.update_profile(uid, req.nickname, req.age, u["avatar_id"] if u else None)
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            await d.execute(
                "UPDATE users SET gender=? WHERE user_id=?",
                (req.gender or "", uid)
            )
            await d.commit()
    except Exception:
        pass
    return {"ok": True}


@app.get("/orders")
async def get_orders(uid: int = Depends(get_uid)):
    orders = await db.get_orders_for_user(uid)
    result = []
    for o in orders:
        partner_id = o["seller_id"] if o["buyer_id"] == uid else o["buyer_id"]
        partner = await db.get_user(partner_id)
        p = await db.get_product(o["product_id"])
        unread = 0
        try:
            async with aiosqlite.connect(DB_PATH) as d:
                async with d.execute(
                    "SELECT COUNT(*) FROM messages "
                    "WHERE order_id=? AND receiver_id=? AND is_read=0",
                    (o["id"], uid)
                ) as c:
                    row = await c.fetchone()
                    unread = row[0] if row else 0
        except Exception:
            pass
        result.append({
            "id": o["id"],
            "short_id": o["short_id"] or f"#{o['id']}",
            "product_title": p["title"] if p else "Товар удалён",
            "amount": o["amount"], "status": o["status"],
            "buyer_id": o["buyer_id"], "seller_id": o["seller_id"],
            "partner_nick": nick_of(partner),
            "role": "buyer" if o["buyer_id"] == uid else "seller",
            "commission": o["commission"],
            "unread": unread,
        })
    return result


@app.get("/orders/{order_id}/messages")
async def get_messages(order_id: int, uid: int = Depends(get_uid)):
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"], order["seller_id"]):
        raise HTTPException(403, "Нет доступа")
    await db.mark_read(order_id, uid)
    msgs = await db.get_order_messages(order_id)
    return [
        {
            "id": m["id"], "sender_id": m["sender_id"],
            "text": m["text"], "media_type": m["media_type"],
            "created_at": str(m["created_at"])
        }
        for m in msgs
    ]


class SendMsgReq(BaseModel):
    text: str


@app.post("/orders/{order_id}/messages")
async def send_message(order_id: int, req: SendMsgReq, uid: int = Depends(get_uid)):
    if not req.text or not req.text.strip():
        raise HTTPException(400, "Пустое сообщение")
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"], order["seller_id"]):
        raise HTTPException(403, "Нет доступа")
    partner_id = order["seller_id"] if order["buyer_id"] == uid else order["buyer_id"]
    await db.send_msg(order_id, uid, partner_id, text=req.text.strip())
    me = await db.get_user(uid)
    short = order["short_id"] or f"#{order_id}"
    asyncio.create_task(notify(
        partner_id,
        f"💬 Новое сообщение от <b>{nick_of(me)}</b>\n"
        f"Заказ {short}: {req.text.strip()[:80]}",
        "Открыть чат"
    ))
    return {"ok": True}


class BuyReq(BaseModel):
    product_id: int


@app.post("/buy")
async def buy_product(req: BuyReq, uid: int = Depends(get_uid)):
    p = await db.get_product(req.product_id)
    if not p or p["status"] != "active":
        raise HTTPException(400, "Товар недоступен")
    if p["seller_id"] == uid:
        raise HTTPException(400, "Нельзя купить свой товар")
    balance = await db.get_balance(uid)
    if balance < p["price"]:
        return {"ok": False, "reason": "insufficient",
                "balance": balance, "price": p["price"]}
    commission = round(p["price"] * SELL_COMM, 2)
    await db.change_balance(uid, -p["price"])
    order_id = await db.create_order(
        uid, p["seller_id"], req.product_id, p["price"], commission, ""
    )
    await db.update_order_status(order_id, "paid")
    order = await db.get_order(order_id)
    short = order["short_id"] or f"#{order_id}"
    seller_gets = round(p["price"] - commission, 2)
    buyer = await db.get_user(uid)
    asyncio.create_task(notify(
        p["seller_id"],
        f"💰 <b>Новый заказ!</b>\n"
        f"Покупатель: {nick_of(buyer)}\n"
        f"Товар: {p['title']}\n"
        f"Вы получите: {seller_gets} ₽\n"
        f"Заказ: {short}",
        "Открыть заказ"
    ))
    return {"ok": True, "short_id": short}


class ConfirmReq(BaseModel):
    order_id: int


@app.post("/confirm_order")
async def confirm_order(req: ConfirmReq, uid: int = Depends(get_uid)):
    order = await db.get_order(req.order_id)
    if not order or order["buyer_id"] != uid:
        raise HTTPException(403, "Нет доступа")
    if order["status"] not in ("paid", "seller_confirmed"):
        raise HTTPException(400, "Нельзя закрыть этот заказ")
    seller_gets = round(order["amount"] - order["commission"], 2)
    await db.change_balance(order["seller_id"], seller_gets)
    await db.update_order_status(req.order_id, "done")
    return {"ok": True}


class TopupReq(BaseModel):
    amount: int


@app.post("/topup/create")
async def topup_create(req: TopupReq, uid: int = Depends(get_uid)):
    if req.amount < 10:
        raise HTTPException(400, "Минимум 10 ₽")
    code = gen_code()
    topup_id = await db.create_topup(uid, req.amount, code)
    return {"topup_id": topup_id, "code": code, "da_link": DA_LINK, "amount": req.amount}


class CreateProductReq(BaseModel):
    title: str
    description: Optional[str] = ""
    price: float
    category: str
    is_premium: bool = False


@app.post("/products/create")
async def create_product(req: CreateProductReq, uid: int = Depends(get_uid)):
    if req.category not in CATEGORIES:
        raise HTTPException(400, "Неверная категория")
    if not req.title or len(req.title) > 100:
        raise HTTPException(400, "Название от 1 до 100 символов")
    if req.price < MIN_PRICE:
        raise HTTPException(400, f"Минимальная цена {MIN_PRICE} ₽")
    if req.is_premium:
        balance = await db.get_balance(uid)
        if balance < PREMIUM_PRICE:
            raise HTTPException(
                400,
                f"Недостаточно средств для премиум ({PREMIUM_PRICE} ₽). "
                f"Баланс: {balance:.0f} ₽"
            )
        await db.change_balance(uid, -PREMIUM_PRICE)
    product_id = await db.add_product(
        uid, req.category, req.title,
        req.description or "", req.price, None, None
    )
    if req.is_premium:
        try:
            from datetime import datetime
            async with aiosqlite.connect(DB_PATH) as d:
                await d.execute(
                    "UPDATE products SET is_premium=1, premium_at=? WHERE id=?",
                    (datetime.now().isoformat(), product_id)
                )
                await d.commit()
        except Exception:
            pass
    seller_gets = round(req.price * (1 - SELL_COMM), 2)
    return {"ok": True, "product_id": product_id, "seller_gets": seller_gets}


class WithdrawReq(BaseModel):
    amount: float
    username: str


@app.post("/withdraw")
async def withdraw(req: WithdrawReq, uid: int = Depends(get_uid)):
    if req.amount < MIN_WITHDRAW:
        raise HTTPException(400, f"Минимум {MIN_WITHDRAW} ₽")
    if not req.username or not req.username.startswith("@") or len(req.username) < 2:
        raise HTTPException(400, "Укажи @username")
    balance = await db.get_balance(uid)
    if balance < req.amount:
        raise HTTPException(400, f"Недостаточно средств. Баланс: {balance:.0f} ₽")
    after = round(req.amount * (1 - WITHDRAW_COMM), 2)
    stars = math.ceil(after / STAR_RATE)
    await db.change_balance(uid, -req.amount)
    w_id = await db.create_withdrawal(uid, req.amount)
    u = await db.get_user(uid)
    asyncio.create_task(notify(
        ADMIN_ID,
        f"💸 <b>Вывод #{w_id}</b>\n"
        f"👤 {nick_of(u)} (ID:{uid})\n"
        f"💰 {req.amount:.0f} ₽ → {after:.0f} ₽ → ⭐{stars} звёзд\n"
        f"📱 Username: {req.username}",
        "OK"
    ))
    return {"ok": True, "w_id": w_id, "after_commission": after, "stars": stars}


class SupportReq(BaseModel):
    message: str


@app.post("/support")
async def support(req: SupportReq, uid: int = Depends(get_uid)):
    if not req.message or not req.message.strip():
        raise HTTPException(400, "Пустое сообщение")
    ticket_id = await db.create_support_ticket(uid, req.message.strip())
    u = await db.get_user(uid)
    asyncio.create_task(notify(
        ADMIN_ID,
        f"🆘 <b>Поддержка #{ticket_id}</b>\n"
        f"👤 {nick_of(u)} (ID:{uid})\n\n"
        f"{req.message.strip()}",
        "OK"
    ))
    return {"ok": True, "ticket_id": ticket_id}
