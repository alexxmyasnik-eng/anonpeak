"""
FastAPI бэкенд для Telegram Mini App.
Запускается параллельно с ботом на Railway.
"""
import json, time
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import database as db
from config import BOT_TOKEN, BOT_COMMISSION, DA_LINK, ADMIN_ID

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CATEGORIES = {
    "signa":  "🖊 Сигна",
    "mugs":   "☕ Кружки",
    "photos": "📸 Фото",
    "videos": "🎬 Видео",
}


# ─── АВТОРИЗАЦИЯ ЧЕРЕЗ TELEGRAM INITDATA ─────────────────

def verify_init_data(init_data: str) -> dict:
    """Проверяет подпись Telegram WebApp initData."""
    if not init_data:
        raise HTTPException(status_code=401, detail="No initData")
    try:
        parsed = dict(x.split("=", 1) for x in init_data.split("&") if "=" in x)
        user_str = parsed.get("user", "{}")
        # URL-decode user string
        from urllib.parse import unquote
        user_str = unquote(user_str)
        user = json.loads(user_str)
        if not user.get("id"):
            raise HTTPException(status_code=401, detail="No user id")
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Bad initData: {e}")


async def get_tg_user(x_init_data: str = Header(default="")) -> dict:
    if not x_init_data:
        raise HTTPException(status_code=401, detail="No initData — открой через Telegram бота")
    tg = verify_init_data(x_init_data)
    uid = tg.get("id")
    if not uid:
        raise HTTPException(status_code=401, detail="No user id")
    user = await db.get_user(uid)
    if not user:
        await db.create_user(uid, tg.get("username", ""))
        user = await db.get_user(uid)
    return {"tg": tg, "db": user, "uid": uid}


def _product_dict(p) -> dict:
    return {
        "id": p["id"], "title": p["title"], "description": p["description"],
        "price": p["price"], "category": p["category"],
        "media_id": p["media_id"], "media_type": p["media_type"],
        "seller_id": p["seller_id"],
    }


def _order_dict(o) -> dict:
    return {
        "id": o["id"], "short_id": o["short_id"] or f"#{o['id']}",
        "product_id": o["product_id"], "amount": o["amount"],
        "status": o["status"], "buyer_id": o["buyer_id"], "seller_id": o["seller_id"],
    }


# ─── ЭНДПОИНТЫ ───────────────────────────────────────────

@app.get("/me")
async def get_me(ctx: dict = Depends(get_tg_user)):
    u = ctx["db"]
    return {
        "uid": ctx["uid"],
        "nickname": u["nickname"] if u else None,
        "age": u["age"] if u else None,
        "balance": float(u["balance"]) if u else 0.0,
        "avatar_id": u["avatar_id"] if u else None,
    }

@app.get("/categories")
async def get_categories():
    return [{"id": k, "name": v} for k, v in CATEGORIES.items()]

@app.get("/products/{category}")
async def get_products(category: str):
    if category not in CATEGORIES:
        raise HTTPException(404, "Category not found")
    products = await db.get_products_by_category(category)
    result = []
    for p in products:
        seller = await db.get_user(p["seller_id"])
        d = _product_dict(p)
        d["seller_nick"] = seller["nickname"] if seller else "?"
        d["seller_rating"] = (await db.get_seller_rating(p["seller_id"]))[0]
        result.append(d)
    return result

@app.get("/product/{product_id}")
async def get_product(product_id: int):
    p = await db.get_product(product_id)
    if not p:
        raise HTTPException(404, "Not found")
    seller = await db.get_user(p["seller_id"])
    avg, cnt = await db.get_seller_rating(p["seller_id"])
    d = _product_dict(p)
    d["seller_nick"] = seller["nickname"] if seller else "?"
    d["seller_rating"] = avg
    d["seller_reviews"] = cnt
    return d

class BuyRequest(BaseModel):
    product_id: int

@app.post("/buy")
async def buy_product(req: BuyRequest, ctx: dict = Depends(get_tg_user)):
    uid = ctx["uid"]
    p = await db.get_product(req.product_id)
    if not p or p["status"] != "active":
        raise HTTPException(400, "Product unavailable")
    if p["seller_id"] == uid:
        raise HTTPException(400, "Cannot buy own product")

    price = p["price"]
    commission = round(price * BOT_COMMISSION, 2)
    balance = await db.get_balance(uid)

    if balance < price:
        return {"ok": False, "reason": "insufficient", "balance": balance, "price": price}

    await db.change_balance(uid, -price)
    order_id = await db.create_order(uid, p["seller_id"], req.product_id, price, commission, "")
    await db.update_order_status(order_id, "paid")
    order = await db.get_order(order_id)
    return {"ok": True, "order": _order_dict(order)}

@app.get("/orders")
async def get_orders(ctx: dict = Depends(get_tg_user)):
    uid = ctx["uid"]
    orders = await db.get_orders_for_user(uid)
    result = []
    for o in orders:
        partner_id = o["seller_id"] if o["buyer_id"] == uid else o["buyer_id"]
        partner = await db.get_user(partner_id)
        p = await db.get_product(o["product_id"])
        d = _order_dict(o)
        d["partner_nick"] = partner["nickname"] if partner else "?"
        d["product_title"] = p["title"] if p else "?"
        d["role"] = "buyer" if o["buyer_id"] == uid else "seller"
        result.append(d)
    return result

@app.get("/orders/{order_id}/messages")
async def get_messages(order_id: int, ctx: dict = Depends(get_tg_user)):
    uid = ctx["uid"]
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"], order["seller_id"]):
        raise HTTPException(403, "No access")
    await db.mark_read(order_id, uid)
    msgs = await db.get_order_messages(order_id)
    return [{"id": m["id"], "sender_id": m["sender_id"], "text": m["text"],
             "media_id": m["media_id"], "media_type": m["media_type"],
             "is_read": m["is_read"], "created_at": str(m["created_at"])} for m in msgs]

class SendMsgRequest(BaseModel):
    text: str

@app.post("/orders/{order_id}/messages")
async def send_message(order_id: int, req: SendMsgRequest, ctx: dict = Depends(get_tg_user)):
    uid = ctx["uid"]
    order = await db.get_order(order_id)
    if not order or uid not in (order["buyer_id"], order["seller_id"]):
        raise HTTPException(403, "No access")
    partner_id = order["seller_id"] if order["buyer_id"] == uid else order["buyer_id"]
    await db.send_msg(order_id, uid, partner_id, text=req.text)
    return {"ok": True}

class ConfirmOrderRequest(BaseModel):
    order_id: int

@app.post("/confirm_order")
async def confirm_order(req: ConfirmOrderRequest, ctx: dict = Depends(get_tg_user)):
    uid = ctx["uid"]
    order = await db.get_order(req.order_id)
    if not order or order["buyer_id"] != uid:
        raise HTTPException(403, "No access")
    if order["status"] not in ("paid", "seller_confirmed"):
        raise HTTPException(400, "Wrong status")
    seller_gets = round(order["amount"] - order["commission"], 2)
    await db.change_balance(order["seller_id"], seller_gets)
    await db.update_order_status(req.order_id, "done")
    return {"ok": True, "seller_gets": seller_gets}

@app.get("/topup/init/{amount}")
async def topup_init(amount: int, ctx: dict = Depends(get_tg_user)):
    uid = ctx["uid"]
    if amount < 10:
        raise HTTPException(400, "Min 10")
    da_comment = f"Топап {uid} {amount}"
    topup_id = await db.create_topup(uid, amount, da_comment)
    return {"topup_id": topup_id, "da_comment": da_comment, "da_link": DA_LINK, "amount": amount}

@app.get("/health")
async def health():
    return {"ok": True}
