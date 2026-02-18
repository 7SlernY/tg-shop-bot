import sqlite3
import os

DB_PATH = "/opt/render/project/src/data/shop.db"

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            username TEXT,
            product TEXT NOT NULL,
            address TEXT NOT NULL,
            amount INTEGER NOT NULL,
            payment_url TEXT,
            status TEXT DEFAULT 'created',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_order(user_id: str, username: str, product: str, address: str, amount: int, payment_url: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO orders (user_id, username, product, address, amount, payment_url)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, username, product, address, amount, payment_url))
    conn.commit()
    conn.close()

def get_user_orders(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT product, status, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"product": row[0], "status": row[1], "created_at": row[2]} for row in rows]
