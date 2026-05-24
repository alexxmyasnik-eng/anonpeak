import aiosqlite
import secrets
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            nickname      TEXT,
            age           INTEGER,
            avatar_id     TEXT,
            balance       REAL DEFAULT 0,
            is_adult      INTEGER DEFAULT 1,
            is_banned     INTEGER DEFAULT 0,
            last_chat_msg TIMESTAMP,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS products (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id    INTEGER,
            category     TEXT,
            title        TEXT,
            description  TEXT,
            price        REAL,
            media_id     TEXT,
            media_type   TEXT,
            status       TEXT DEFAULT 'active',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS orders (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            short_id     TEXT UNIQUE,
            buyer_id     INTEGER,
            seller_id    INTEGER,
            product_id   INTEGER,
            amount       REAL,
            commission   REAL,
            status       TEXT DEFAULT 'pending',
            da_comment   TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id     INTEGER UNIQUE,
            seller_id    INTEGER,
            buyer_id     INTEGER,
            rating       INTEGER,
            text         TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id     INTEGER,
            sender_id    INTEGER,
            receiver_id  INTEGER,
            text         TEXT,
            media_id     TEXT,
            media_type   TEXT,
            is_read      INTEGER DEFAULT 0,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS withdrawals (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            amount       REAL,
            status       TEXT DEFAULT 'pending',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS dm_tokens (
            token        TEXT PRIMARY KEY,
            user_id      INTEGER NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS topups (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            amount       REAL NOT NULL,
            da_comment   TEXT NOT NULL,
            status       TEXT DEFAULT 'pending',
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS used_donation_ids (
            donation_id  INTEGER PRIMARY KEY,
            used_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS support_tickets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL,
            message      TEXT NOT NULL,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS global_chat (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            nickname   TEXT,
            message    TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS support_chat (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            from_admin INTEGER DEFAULT 0,
            message    TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS friends (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            friend_id  INTEGER,
            status     TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, friend_id)
        );

        CREATE TABLE IF NOT EXISTS muted_users (
            user_id  INTEGER,
            muted_id INTEGER,
            PRIMARY KEY(user_id, muted_id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            type        TEXT,
            amount      REAL,
            description TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS frozen_funds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            order_id    INTEGER,
            amount      REAL,
            unfreeze_at TIMESTAMP,
            is_released INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS dm_messages (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id       INTEGER,
            to_id         INTEGER,
            message       TEXT,
            reply_to_text TEXT DEFAULT '',
            is_read       INTEGER DEFAULT 0,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Индексы для производительности
        await db.executescript("""
        CREATE INDEX IF NOT EXISTS idx_products_seller   ON products(seller_id);
        CREATE INDEX IF NOT EXISTS idx_products_category ON products(category, status);
        CREATE INDEX IF NOT EXISTS idx_orders_buyer      ON orders(buyer_id);
        CREATE INDEX IF NOT EXISTS idx_orders_seller     ON orders(seller_id);
        CREATE INDEX IF NOT EXISTS idx_messages_order    ON messages(order_id);
        CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver_id, is_read);
        CREATE INDEX IF NOT EXISTS idx_dm_parties        ON dm_messages(from_id, to_id);
        CREATE INDEX IF NOT EXISTS idx_dm_to_unread      ON dm_messages(to_id, is_read);
        CREATE INDEX IF NOT EXISTS idx_global_chat_time  ON global_chat(created_at);
        CREATE INDEX IF NOT EXISTS idx_friends_user      ON friends(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_friends_friend    ON friends(friend_id, status);
        CREATE INDEX IF NOT EXISTS idx_frozen_user       ON frozen_funds(user_id, is_released);
        CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id, created_at);
        """)

        # Миграции — добавляем колонки если их нет (безопасно при повторном запуске)
        migrations = [
            "ALTER TABLE users    ADD COLUMN gender       TEXT DEFAULT ''",
            "ALTER TABLE users    ADD COLUMN earn_balance REAL DEFAULT 0",
            "ALTER TABLE users    ADD COLUMN avatar_url   TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN subcategory  TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN preview_url  TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN delivery_files TEXT DEFAULT '[]'",
            "ALTER TABLE products ADD COLUMN is_premium   INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN premium_at   TIMESTAMP",
            "ALTER TABLE dm_messages ADD COLUMN reply_to_text TEXT DEFAULT ''",
        ]
        for sql in migrations:
            try:
                await db.execute(sql)
            except Exception:
                pass  # колонка уже существует — это нормально

        await db.commit()


# ─── USERS ───────────────────────────────────────────────

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as c:
            return await c.fetchone()

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

async def update_profile(user_id: int, nickname: str, age: int, avatar_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET nickname=?, age=?, avatar_id=? WHERE user_id=?",
            (nickname, age, avatar_id, user_id)
        )
        await db.commit()

async def get_balance(user_id: int) -> float:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)) as c:
            row = await c.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0

async def change_balance(user_id: int, delta: float) -> bool:
    """
    Изменяет баланс пользователя.
    При отрицательном delta проверяет что средств достаточно.
    Возвращает True если успешно, False если недостаточно средств.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        if delta < 0:
            async with db.execute(
                "SELECT balance FROM users WHERE user_id=?", (user_id,)
            ) as c:
                row = await c.fetchone()
            current = float(row[0]) if row and row[0] is not None else 0.0
            if current + delta < 0:
                return False
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id=?",
            (delta, user_id)
        )
        await db.commit()
        return True

async def update_last_chat(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET last_chat_msg = CURRENT_TIMESTAMP WHERE user_id=?",
            (user_id,)
        )
        await db.commit()

async def get_last_chat_time(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_chat_msg FROM users WHERE user_id=?", (user_id,)
        ) as c:
            row = await c.fetchone()
            return row[0] if row else None


# ─── PRODUCTS ────────────────────────────────────────────

async def add_product(seller_id, category, title, description, price, media_id, media_type):
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT INTO products (seller_id,category,title,description,price,media_id,media_type) "
            "VALUES (?,?,?,?,?,?,?)",
            (seller_id, category, title, description, price, media_id, media_type)
        )
        await db.commit()
        return c.lastrowid

async def get_products_by_category(category: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products WHERE category=? AND status='active' ORDER BY created_at DESC",
            (category,)
        ) as c:
            return await c.fetchall()

async def get_product(product_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE id=?", (product_id,)) as c:
            return await c.fetchone()

async def get_my_products(seller_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products WHERE seller_id=? ORDER BY created_at DESC",
            (seller_id,)
        ) as c:
            return await c.fetchall()

async def delete_product(product_id: int, seller_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE products SET status='deleted' WHERE id=? AND seller_id=?",
            (product_id, seller_id)
        )
        await db.commit()


# ─── ORDERS ──────────────────────────────────────────────

async def _gen_short_id(db) -> str:
    import random, string
    chars = string.ascii_uppercase + string.digits
    for _ in range(20):
        sid = ''.join(random.choices(chars, k=6))
        async with db.execute("SELECT id FROM orders WHERE short_id=?", (sid,)) as c:
            if not await c.fetchone():
                return sid
    return ''.join(random.choices(chars, k=8))

async def create_order(buyer_id, seller_id, product_id, amount, commission, da_comment=""):
    async with aiosqlite.connect(DB_PATH) as db:
        short_id = await _gen_short_id(db)
        c = await db.execute(
            "INSERT INTO orders (short_id,buyer_id,seller_id,product_id,amount,commission,da_comment) "
            "VALUES (?,?,?,?,?,?,?)",
            (short_id, buyer_id, seller_id, product_id, amount, commission, da_comment)
        )
        await db.commit()
        return c.lastrowid

async def get_order(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE id=?", (order_id,)) as c:
            return await c.fetchone()

async def update_order_status(order_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        await db.commit()

async def get_orders_for_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE buyer_id=? OR seller_id=? ORDER BY created_at DESC",
            (user_id, user_id)
        ) as c:
            return await c.fetchall()


# ─── MESSAGES (личка по заказу) ──────────────────────────

async def send_msg(order_id, sender_id, receiver_id, text=None, media_id=None, media_type=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (order_id,sender_id,receiver_id,text,media_id,media_type) "
            "VALUES (?,?,?,?,?,?)",
            (order_id, sender_id, receiver_id, text, media_id, media_type)
        )
        await db.commit()

async def get_order_messages(order_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM messages WHERE order_id=? ORDER BY created_at ASC",
            (order_id,)
        ) as c:
            return await c.fetchall()

async def mark_read(order_id: int, reader_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE messages SET is_read=1 WHERE order_id=? AND receiver_id=? AND is_read=0",
            (order_id, reader_id)
        )
        await db.commit()

async def count_unread(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM messages WHERE receiver_id=? AND is_read=0",
            (user_id,)
        ) as c:
            row = await c.fetchone()
            return row[0] if row else 0

async def get_active_order_between(user_a: int, user_b: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM orders WHERE status NOT IN ('done','cancelled')
               AND ((buyer_id=? AND seller_id=?) OR (buyer_id=? AND seller_id=?))
               ORDER BY created_at DESC LIMIT 1""",
            (user_a, user_b, user_b, user_a)
        ) as c:
            return await c.fetchone()


# ─── REVIEWS ─────────────────────────────────────────────

async def add_review(order_id, seller_id, buyer_id, rating, text):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO reviews (order_id,seller_id,buyer_id,rating,text) "
            "VALUES (?,?,?,?,?)",
            (order_id, seller_id, buyer_id, rating, text)
        )
        await db.commit()

async def get_seller_reviews(seller_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT r.*, u.nickname as buyer_name FROM reviews r "
            "JOIN users u ON r.buyer_id=u.user_id "
            "WHERE r.seller_id=? ORDER BY r.created_at DESC",
            (seller_id,)
        ) as c:
            return await c.fetchall()

async def get_seller_rating(seller_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT AVG(rating), COUNT(*) FROM reviews WHERE seller_id=?",
            (seller_id,)
        ) as c:
            row = await c.fetchone()
            return (round(row[0], 1) if row[0] else 0.0), (row[1] if row[1] else 0)


# ─── WITHDRAWALS ─────────────────────────────────────────

async def create_withdrawal(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT INTO withdrawals (user_id, amount) VALUES (?,?)",
            (user_id, amount)
        )
        await db.commit()
        return c.lastrowid

async def get_pending_withdrawals():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT w.*, u.username, u.nickname FROM withdrawals w "
            "JOIN users u ON w.user_id=u.user_id WHERE w.status='pending'"
        ) as c:
            return await c.fetchall()

async def complete_withdrawal(w_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE withdrawals SET status='done' WHERE id=?", (w_id,))
        await db.commit()


# ─── DM TOKENS ───────────────────────────────────────────

async def get_or_create_dm_token(user_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT token FROM dm_tokens WHERE user_id=?", (user_id,)
        ) as c:
            row = await c.fetchone()
        if row:
            return row["token"]
        token = secrets.token_urlsafe(12)
        await db.execute(
            "INSERT INTO dm_tokens (token, user_id) VALUES (?,?)",
            (token, user_id)
        )
        await db.commit()
        return token

async def get_user_by_dm_token(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id FROM dm_tokens WHERE token=?", (token,)
        ) as c:
            row = await c.fetchone()
        return row["user_id"] if row else None


# ─── TOPUPS ──────────────────────────────────────────────

async def create_topup(user_id: int, amount: float, da_comment: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT INTO topups (user_id, amount, da_comment) VALUES (?,?,?)",
            (user_id, amount, da_comment)
        )
        await db.commit()
        return c.lastrowid

async def get_pending_topups() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM topups WHERE status='pending' ORDER BY created_at ASC"
        ) as c:
            return await c.fetchall()

async def complete_topup(topup_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE topups SET status='done' WHERE id=?", (topup_id,))
        await db.commit()

async def cancel_topup(topup_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE topups SET status='cancelled' WHERE id=?", (topup_id,))
        await db.commit()

async def get_pending_orders_for_payment() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM orders WHERE status='pending_payment' ORDER BY created_at ASC"
        ) as c:
            return await c.fetchall()


# ─── USED DONATION IDS ───────────────────────────────────

async def get_used_donation_ids() -> set:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT donation_id FROM used_donation_ids") as c:
            rows = await c.fetchall()
            return {r[0] for r in rows}

async def mark_donation_used(donation_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO used_donation_ids (donation_id) VALUES (?)",
            (donation_id,)
        )
        await db.commit()

async def is_donation_used(donation_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM used_donation_ids WHERE donation_id=?", (donation_id,)
        ) as c:
            return (await c.fetchone()) is not None


# ─── SUPPORT ─────────────────────────────────────────────

async def create_support_ticket(user_id: int, message: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        c = await db.execute(
            "INSERT INTO support_tickets (user_id, message) VALUES (?,?)",
            (user_id, message)
        )
        await db.commit()
        return c.lastrowid
