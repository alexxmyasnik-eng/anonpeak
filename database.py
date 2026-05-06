import aiosqlite
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                nickname    TEXT,
                age         INTEGER,
                avatar_id   TEXT,
                balance     INTEGER DEFAULT 0,
                is_adult    INTEGER DEFAULT 0,
                is_banned   INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id   INTEGER,
                category    TEXT,
                title       TEXT,
                description TEXT,
                price       INTEGER,
                media_id    TEXT,
                media_type  TEXT,
                status      TEXT DEFAULT 'active',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (seller_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_id     INTEGER,
                seller_id    INTEGER,
                product_id   INTEGER,
                amount       INTEGER,
                commission   INTEGER,
                status       TEXT DEFAULT 'pending',
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (buyer_id)   REFERENCES users(user_id),
                FOREIGN KEY (seller_id)  REFERENCES users(user_id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                amount     INTEGER,
                status     TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

# ─── USERS ───────────────────────────────────────────────

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            return await cur.fetchone()

async def create_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
            (user_id, username)
        )
        await db.commit()

async def set_adult(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_adult=1 WHERE user_id=?", (user_id,))
        await db.commit()

async def update_profile(user_id: int, nickname: str, age: int, avatar_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET nickname=?, age=?, avatar_id=? WHERE user_id=?",
            (nickname, age, avatar_id, user_id)
        )
        await db.commit()

async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def change_balance(user_id: int, delta: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id=?",
            (delta, user_id)
        )
        await db.commit()

# ─── PRODUCTS ────────────────────────────────────────────

async def add_product(seller_id, category, title, description, price, media_id, media_type):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO products (seller_id,category,title,description,price,media_id,media_type)
               VALUES (?,?,?,?,?,?,?)""",
            (seller_id, category, title, description, price, media_id, media_type)
        )
        await db.commit()

async def get_products_by_category(category: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products WHERE category=? AND status='active' ORDER BY created_at DESC",
            (category,)
        ) as cur:
            return await cur.fetchall()

async def get_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE id=?", (product_id,)) as cur:
            return await cur.fetchone()

async def get_my_products(seller_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products WHERE seller_id=? ORDER BY created_at DESC",
            (seller_id,)
        ) as cur:
            return await cur.fetchall()

async def delete_product(product_id: int, seller_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE products SET status='deleted' WHERE id=? AND seller_id=?",
            (product_id, seller_id)
        )
        await db.commit()

# ─── ORDERS ──────────────────────────────────────────────

async def create_order(buyer_id, seller_id, product_id, amount, commission):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO orders (buyer_id,seller_id,product_id,amount,commission)
               VALUES (?,?,?,?,?)""",
            (buyer_id, seller_id, product_id, amount, commission)
        )
        await db.commit()
        return cur.lastrowid

async def get_order(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id=?", (order_id,)) as cur:
            return await cur.fetchone()

async def confirm_order(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status='confirmed' WHERE id=?", (order_id,)
        )
        await db.commit()

async def get_pending_orders_for_seller(seller_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE seller_id=? AND status='pending'",
            (seller_id,)
        ) as cur:
            return await cur.fetchall()

# ─── WITHDRAWALS ─────────────────────────────────────────

async def create_withdrawal(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO withdrawals (user_id, amount) VALUES (?,?)",
            (user_id, amount)
        )
        await db.commit()
        return cur.lastrowid

async def get_pending_withdrawals():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT w.*, u.username, u.nickname FROM withdrawals w "
            "JOIN users u ON w.user_id=u.user_id WHERE w.status='pending'"
        ) as cur:
            return await cur.fetchall()

async def complete_withdrawal(withdrawal_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE withdrawals SET status='done' WHERE id=?", (withdrawal_id,)
        )
        await db.commit()
