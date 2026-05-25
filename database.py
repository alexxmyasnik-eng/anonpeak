import secrets
import random
import string

from db_neon import get_conn


async def init_db():
    pass


# ─── USERS ───────────────────────────────────────────────────────────────────

async def get_user(user_id: int):
    async with get_conn() as d:
        return await d.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)


async def create_user(user_id: int, username: str):
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO users (user_id, username) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            user_id, 
            username
        )


async def get_or_create_user(user_id: int, username: str = ""):
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO users (user_id, username) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            user_id, username
        )
        return await d.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)


async def set_adult(user_id: int):
    async with get_conn() as d:
        await d.execute("UPDATE users SET is_adult=1 WHERE user_id=$1", user_id)


async def update_profile(user_id: int, nickname: str, age: int, avatar_id):
    async with get_conn() as d:
        await d.execute(
            "UPDATE users SET nickname=$1, age=$2, avatar_id=$3 WHERE user_id=$4",
            nickname, age, avatar_id, user_id
        )


async def get_balance(user_id: int) -> float:
    async with get_conn() as d:
        row = await d.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)
        return float(row["balance"]) if row else 0.0


async def change_balance(user_id: int, delta: float):
    async with get_conn() as d:
        await d.execute(
            "UPDATE users SET balance = balance + $1 WHERE user_id=$2",
            delta, 
            user_id
        )


async def update_last_chat(user_id: int):
    async with get_conn() as d:
        await d.execute(
            "UPDATE users SET last_chat_msg = NOW() WHERE user_id=$1", user_id
        )


async def get_last_chat_time(user_id: int):
    async with get_conn() as d:
        row = await d.fetchrow("SELECT last_chat_msg FROM users WHERE user_id=$1", user_id)
        return row["last_chat_msg"] if row else None


# ─── PRODUCTS ────────────────────────────────────────────────────────────────

async def add_product(seller_id, category, title, description, price, media_id, media_type) -> int:
    async with get_conn() as d:
        row = await d.fetchrow(
            """INSERT INTO products (seller_id,category,title,description,price,media_id,media_type)
               VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
            seller_id, category, title, description, price, media_id, media_type
        )
        return row["id"]


async def get_products_by_category(category: str):
    async with get_conn() as d:
        return await d.fetch(
            "SELECT * FROM products WHERE category=$1 AND status='active' ORDER BY created_at DESC",
            category
        )


async def get_product(product_id: int):
    async with get_conn() as d:
        return await d.fetchrow("SELECT * FROM products WHERE id=$1", product_id)


async def get_my_products(seller_id: int):
    async with get_conn() as d:
        return await d.fetch(
            "SELECT * FROM products WHERE seller_id=$1 ORDER BY created_at DESC", seller_id
        )


async def delete_product(product_id: int, seller_id: int):
    async with get_conn() as d:
        await d.execute(
            "UPDATE products SET status='deleted' WHERE id=$1 AND seller_id=$2",
            product_id, seller_id
        )


# ─── ORDERS ──────────────────────────────────────────────────────────────────

async def _gen_short_id(d) -> str:
    chars = string.ascii_uppercase + string.digits
    for _ in range(20):
        sid = ''.join(random.choices(chars, k=6))
        row = await d.fetchrow("SELECT id FROM orders WHERE short_id=$1", sid)
        if not row:
            return sid
    return ''.join(random.choices(chars, k=8))


async def create_order(buyer_id, seller_id, product_id, amount, commission, da_comment="") -> int:
    async with get_conn() as d:
        short_id = await _gen_short_id(d)
        row = await d.fetchrow(
            """INSERT INTO orders (short_id,buyer_id,seller_id,product_id,amount,commission,da_comment)
               VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
            short_id, buyer_id, seller_id, product_id, amount, commission, da_comment
        )
        return row["id"]


async def get_order(order_id: int):
    async with get_conn() as d:
        return await d.fetchrow("SELECT * FROM orders WHERE id=$1", order_id)


async def update_order_status(order_id: int, status: str):
    async with get_conn() as d:
        await d.execute("UPDATE orders SET status=$1 WHERE id=$2", status, order_id)


async def get_orders_for_user(user_id: int):
    async with get_conn() as d:
        return await d.fetch(
            "SELECT * FROM orders WHERE buyer_id=$1 OR seller_id=$1 ORDER BY created_at DESC",
            user_id
        )


async def get_pending_orders_for_payment() -> list:
    async with get_conn() as d:
        return await d.fetch(
            "SELECT * FROM orders WHERE status='pending_payment' ORDER BY created_at ASC"
        )


# ─── MESSAGES ────────────────────────────────────────────────────────────────

async def send_msg(order_id, sender_id, receiver_id, text=None, media_id=None, media_type=None):
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO messages (order_id,sender_id,receiver_id,text,media_id,media_type) VALUES ($1,$2,$3,$4,$5,$6)",
            order_id, sender_id, receiver_id, text, media_id, media_type
        )


async def get_order_messages(order_id: int):
    async with get_conn() as d:
        return await d.fetch(
            "SELECT * FROM messages WHERE order_id=$1 ORDER BY created_at ASC", order_id
        )


async def mark_read(order_id: int, reader_id: int):
    async with get_conn() as d:
        await d.execute(
            "UPDATE messages SET is_read=1 WHERE order_id=$1 AND receiver_id=$2 AND is_read=0",
            order_id, reader_id
        )


async def count_unread(user_id: int) -> int:
    async with get_conn() as d:
        row = await d.fetchrow(
            "SELECT COUNT(*) as cnt FROM messages WHERE receiver_id=$1 AND is_read=0", user_id
        )
        return row["cnt"] if row else 0


async def get_active_order_between(user_a: int, user_b: int):
    async with get_conn() as d:
        return await d.fetchrow(
            """SELECT * FROM orders WHERE status NOT IN ('done','cancelled')
               AND ((buyer_id=$1 AND seller_id=$2) OR (buyer_id=$2 AND seller_id=$1))
               ORDER BY created_at DESC LIMIT 1""",
            user_a, user_b
        )


# ─── REVIEWS ─────────────────────────────────────────────────────────────────

async def add_review(order_id, seller_id, buyer_id, rating, text):
    async with get_conn() as d:
        await d.execute(
            """INSERT INTO reviews (order_id,seller_id,buyer_id,rating,text)
               VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (order_id) DO UPDATE SET rating=$4, text=$5""",
            order_id, seller_id, buyer_id, rating, text
        )


async def get_seller_reviews(seller_id: int):
    async with get_conn() as d:
        return await d.fetch(
            """SELECT r.*, u.nickname as buyer_name FROM reviews r
               JOIN users u ON r.buyer_id=u.user_id
               WHERE r.seller_id=$1 ORDER BY r.created_at DESC""",
            seller_id
        )


async def get_seller_rating(seller_id: int):
    async with get_conn() as d:
        row = await d.fetchrow(
            "SELECT AVG(rating) as avg, COUNT(*) as cnt FROM reviews WHERE seller_id=$1",
            seller_id
        )
        avg = round(float(row["avg"]), 1) if row and row["avg"] else 0
        cnt = row["cnt"] if row else 0
        return avg, cnt


# ─── WITHDRAWALS ─────────────────────────────────────────────────────────────

async def create_withdrawal(user_id: int, amount: float) -> int:
    async with get_conn() as d:
        row = await d.fetchrow(
            "INSERT INTO withdrawals (user_id, amount) VALUES ($1, $2) RETURNING id",
            user_id, amount
        )
        return row["id"]


async def get_pending_withdrawals():
    async with get_conn() as d:
        return await d.fetch(
            """SELECT w.*, u.username, u.nickname FROM withdrawals w
               JOIN users u ON w.user_id=u.user_id WHERE w.status='pending'"""
        )


async def complete_withdrawal(w_id: int):
    async with get_conn() as d:
        await d.execute("UPDATE withdrawals SET status='done' WHERE id=$1", w_id)


# ─── DM TOKENS ───────────────────────────────────────────────────────────────

async def get_or_create_dm_token(user_id: int) -> str:
    async with get_conn() as d:
        row = await d.fetchrow("SELECT token FROM dm_tokens WHERE user_id=$1", user_id)
        if row:
            return row["token"]
        token = secrets.token_urlsafe(12)
        await d.execute(
            "INSERT INTO dm_tokens (token, user_id) VALUES ($1, $2)", token, user_id
        )
        return token


async def get_user_by_dm_token(token: str):
    async with get_conn() as d:
        row = await d.fetchrow("SELECT user_id FROM dm_tokens WHERE token=$1", token)
        return row["user_id"] if row else None


# ─── TOPUPS ──────────────────────────────────────────────────────────────────

async def create_topup(user_id: int, amount: float, da_comment: str) -> int:
    async with get_conn() as d:
        row = await d.fetchrow(
            "INSERT INTO topups (user_id, amount, da_comment) VALUES ($1, $2, $3) RETURNING id",
            user_id, amount, da_comment
        )
        return row["id"]


async def get_pending_topups() -> list:
    async with get_conn() as d:
        return await d.fetch(
            "SELECT * FROM topups WHERE status='pending' ORDER BY created_at ASC"
        )


async def complete_topup(topup_id: int):
    async with get_conn() as d:
        await d.execute("UPDATE topups SET status='done' WHERE id=$1", topup_id)


async def cancel_topup(topup_id: int):
    async with get_conn() as d:
        await d.execute("UPDATE topups SET status='cancelled' WHERE id=$1", topup_id)


# ─── USED DONATION IDS ───────────────────────────────────────────────────────

async def get_used_donation_ids() -> set:
    async with get_conn() as d:
        rows = await d.fetch("SELECT donation_id FROM used_donation_ids")
        return {r["donation_id"] for r in rows}


async def mark_donation_used(donation_id: int):
    async with get_conn() as d:
        await d.execute(
            "INSERT INTO used_donation_ids (donation_id) VALUES ($1) ON CONFLICT DO NOTHING",
            donation_id
        )


async def is_donation_used(donation_id: int) -> bool:
    async with get_conn() as d:
        row = await d.fetchrow(
            "SELECT 1 FROM used_donation_ids WHERE donation_id=$1", donation_id
        )
        return row is not None


# ─── SUPPORT ─────────────────────────────────────────────────────────────────

async def create_support_ticket(user_id: int, message: str) -> int:
    async with get_conn() as d:
        row = await d.fetchrow(
            "INSERT INTO support_tickets (user_id, message) VALUES ($1, $2) RETURNING id",
            user_id, message
        )
        return row["id"]
