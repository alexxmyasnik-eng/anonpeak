import json, aiosqlite
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import database as db
from config import BOT_COMMISSION, DA_LINK, ADMIN_ID, BOT_TOKEN, DB_PATH, MIN_PRICE

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CATEGORIES = {
    "signa":  "🖊 Сигна",
    "mugs":   "☕ Кружки",
    "photos": "📸 Фото",
    "videos": "🎬 Видео",
}

# ── AUTH ─────────────────────────────────────────────────

async def get_uid(x_tg_user_id: str = Header(default="")) -> int:
    if not x_tg_user_id or not x_tg_user_id.isdigit():
        raise HTTPException(401, "Unauthorized")
    uid = int(x_tg_user_id)
    user = await db.get_user(uid)
    if not user:
        await db.create_user(uid, "")
    return uid

# ── PUBLIC ───────────────────────────────────────────────

@app.get("/health")
async def health(): return {"ok": True}

@app.get("/categories")
async def get_categories():
    return [{"id": k, "name": v} for k, v in CATEGORIES.items()]

@app.get("/products/{category}")
async def get_products(category: str):
    if category not in CATEGORIES:
        raise HTTPException(404, "Not found")
    products = await db.get_products_by_category(category)
    result = []
    for p in products:
        seller = await db.get_user(p["seller_id"])
        avg, _ = await db.get_seller_rating(p["seller_id"])
        result.append({
            "id": p["id"], "title": p["title"],
            "description": p["description"], "price": p["price"],
            "category": p["category"], "media_id": p["media_id"],
            "media_type": p["media_type"], "seller_id": p["seller_id"],
            "seller_nick": seller["nickname"] if seller and seller["nickname"] else "Аноним",
            "seller_rating": round(avg, 1),
        })
    return result

@app.get("/product/{product_id}")
async def get_product(product_id: int):
    p = await db.get_product(product_id)
    if not p: raise HTTPException(404, "Not found")
    seller = await db.get_user(p["seller_id"])
    avg, cnt = await db.get_seller_rating(p["seller_id"])
    return {
        "id": p["id"], "title": p["title"],
        "description": p["description"], "price": p["price"],
        "category": p["category"], "media_id": p["media_id"],
        "media_type": p["media_type"], "seller_id": p["seller_id"],
        "seller_nick": seller["nickname"] if seller and seller["nickname"] else "Аноним",
        "seller_rating": round(avg, 1), "seller_reviews": cnt,
    }

# ── AUTH REQUIRED ─────────────────────────────────────────

@app.get("/me")
async def get_me(uid: int = Depends(get_uid)):
    u = await db.get_user(uid)
    gender = ""
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            async with d.execute("SELECT gender FROM users WHERE user_id=?", (uid,)) as c:
                row = await c.fetchone()
                if row and row[0]: gender = row[0]
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

class UpdateProfileRequest(BaseModel):
    nickname: str
    age: int
    gender: Optional[str] = ""

@app.post("/me/update")
async def update_me(req: UpdateProfileRequest, uid: int = Depends(get_uid)):
    if not req.nickname or len(req.nickname) > 30:
        raise HTTPException(400, "Никнейм от 1 до 30 символов")
    if req.age < 1 or req.age > 120:
        raise HTTPException(400, "Укажи реальный возраст")
    u = await db.get_user(uid)
    await db.update_profile(uid, req.nickname, req.age, u["avatar_id"] if u else None)
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            # Добавляем колонку если нет
            try:
                await d.execute("ALTER TABLE users ADD COLUMN gender TEXT DEFAULT ''")
            except Exception:
                pass
            await d.execute("UPDATE users SET gender=? WHERE user_id=?", (req.gender or "", uid))
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
        result.append({
            "id": o["id"],
            "short_id": o["short_id"] or f"#{o['id']}",
            "product_title": p["title"] if p else "Товар удалён",
            "amount": o["amount"], "status": o["status"],
            "buyer_id": o["buyer_id"], "seller_id": o["seller_id"],
            "partner_nick": partner["nickname"] if partner and partner["nickname"] else "Аноним",
            "role": "buyer" if o["buyer_id"] == uid else "seller",
            "commission": o["commission"],
        })
    return result

@app.get("/orders/{order_id}/messages")
async def get_messages(order_id: int, uid: int = Depends(get_uid)):
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"], order["seller_id"]):
        raise HTTPException(403, "Нет доступа")
    await db.mark_read(order_id, uid)
    msgs = await db.get_order_messages(order_id)
    return [{"id": m["id"], "sender_id": m["sender_id"], "text": m["text"],
             "media_type": m["media_type"], "created_at": str(m["created_at"])} for m in msgs]

class SendMsgRequest(BaseModel):
    text: str

@app.post("/orders/{order_id}/messages")
async def send_message(order_id: int, req: SendMsgRequest, uid: int = Depends(get_uid)):
    if not req.text or not req.text.strip():
        raise HTTPException(400, "Пустое сообщение")
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"], order["seller_id"]):
        raise HTTPException(403, "Нет доступа")
    partner_id = order["seller_id"] if order["buyer_id"] == uid else order["buyer_id"]
    await db.send_msg(order_id, uid, partner_id, text=req.text.strip())
    return {"ok": True}

class BuyRequest(BaseModel):
    product_id: int

@app.post("/buy")
async def buy_product(req: BuyRequest, uid: int = Depends(get_uid)):
    p = await db.get_product(req.product_id)
    if not p or p["status"] != "active":
        raise HTTPException(400, "Товар недоступен")
    if p["seller_id"] == uid:
        raise HTTPException(400, "Нельзя купить свой товар")
    balance = await db.get_balance(uid)
    if balance < p["price"]:
        return {"ok": False, "reason": "insufficient", "balance": balance, "price": p["price"]}
    commission = round(p["price"] * BOT_COMMISSION, 2)
    await db.change_balance(uid, -p["price"])
    order_id = await db.create_order(uid, p["seller_id"], req.product_id, p["price"], commission, "")
    await db.update_order_status(order_id, "paid")
    order = await db.get_order(order_id)
    return {"ok": True, "short_id": order["short_id"] or f"#{order_id}"}

class ConfirmOrderRequest(BaseModel):
    order_id: int

@app.post("/confirm_order")
async def confirm_order(req: ConfirmOrderRequest, uid: int = Depends(get_uid)):
    order = await db.get_order(req.order_id)
    if not order or order["buyer_id"] != uid:
        raise HTTPException(403, "Нет доступа")
    if order["status"] not in ("paid", "seller_confirmed"):
        raise HTTPException(400, "Нельзя закрыть этот заказ")
    seller_gets = round(order["amount"] - order["commission"], 2)
    await db.change_balance(order["seller_id"], seller_gets)
    await db.update_order_status(req.order_id, "done")
    return {"ok": True}

class TopupRequest(BaseModel):
    amount: int

@app.post("/topup/create")
async def topup_create(req: TopupRequest, uid: int = Depends(get_uid)):
    if req.amount < 10:
        raise HTTPException(400, "Минимум 10 ₽")
    # Генерируем красивый код
    import random, string
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    code = ''.join(random.choices(chars, k=4)) + '-' + ''.join(random.choices(chars, k=4))
    da_comment = code
    topup_id = await db.create_topup(uid, req.amount, da_comment)
    return {
        "topup_id": topup_id,
        "code": code,
        "da_link": DA_LINK,
        "amount": req.amount
    }

class CreateProductRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    price: float
    category: str

@app.post("/products/create")
async def create_product(req: CreateProductRequest, uid: int = Depends(get_uid)):
    if req.category not in CATEGORIES:
        raise HTTPException(400, "Неверная категория")
    if not req.title or len(req.title) > 100:
        raise HTTPException(400, "Название от 1 до 100 символов")
    if req.price < MIN_PRICE:
        raise HTTPException(400, f"Минимальная цена {MIN_PRICE} ₽")
    # Правильное имя функции в database.py — add_product
    product_id = await db.add_product(
        uid, req.category, req.title,
        req.description or "", req.price, None, None
    )
    return {"ok": True, "product_id": product_id}

class SupportRequest(BaseModel):
    message: str

@app.post("/support")
async def support(req: SupportRequest, uid: int = Depends(get_uid)):
    if not req.message or not req.message.strip():
        raise HTTPException(400, "Пустое сообщение")
    ticket_id = await db.create_support_ticket(uid, req.message.strip())
    try:
        import aiohttp
        u = await db.get_user(uid)
        nick = u["nickname"] if u and u["nickname"] else f"ID:{uid}"
        async with aiohttp.ClientSession() as s:
            await s.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": ADMIN_ID,
                    "text": f"🆘 <b>Поддержка #{ticket_id}</b>\n👤 {nick} (ID:{uid})\n\n{req.message.strip()}",
                    "parse_mode": "HTML"
                }
            )
    except Exception:
        pass
    return {"ok": True, "ticket_id": ticket_id}
