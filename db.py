"""
Слой хранения данных для бота-магнита МенялоФФ (обмен USDT↔RUB).
"""
import sqlite3
import json
import time
from contextlib import contextmanager

DB_PATH = "bot.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                source TEXT DEFAULT 'organic',
                direction TEXT,          -- buy / sell
                stage TEXT DEFAULT 'новый',
                first_seen INTEGER,
                stopped INTEGER DEFAULT 0,
                current_step TEXT DEFAULT 'entry',
                reminded INTEGER DEFAULT 0,
                history TEXT DEFAULT '[]'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS emergencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                etype TEXT,
                text TEXT,
                source TEXT,
                direction TEXT,
                created_at INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exchange_clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                created_at INTEGER
            )
        """)


def get_or_create_user(telegram_id, username, first_name, source="organic"):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, source, first_seen) VALUES (?,?,?,?,?)",
            (telegram_id, username, first_name, source, int(time.time())),
        )
        row = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        return dict(row)


def update_user(telegram_id, **fields):
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [telegram_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE users SET {keys} WHERE telegram_id=?", values)


def log_history(telegram_id, entry: str):
    with get_conn() as conn:
        row = conn.execute("SELECT history FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        hist = json.loads(row["history"]) if row and row["history"] else []
        hist.append({"t": int(time.time()), "e": entry})
        conn.execute("UPDATE users SET history=? WHERE telegram_id=?", (json.dumps(hist, ensure_ascii=False), telegram_id))


def mark_stopped(telegram_id):
    update_user(telegram_id, stopped=1)


def log_exchange_click(telegram_id):
    with get_conn() as conn:
        conn.execute("INSERT INTO exchange_clicks (telegram_id, created_at) VALUES (?,?)", (telegram_id, int(time.time())))


def log_emergency(telegram_id, etype, text, source, direction):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO emergencies (telegram_id, etype, text, source, direction, created_at) VALUES (?,?,?,?,?,?)",
            (telegram_id, etype, text, source, direction, int(time.time())),
        )


def breakage_ratio():
    with get_conn() as conn:
        emergencies = conn.execute("SELECT COUNT(*) c FROM emergencies").fetchone()["c"]
        clicks = conn.execute("SELECT COUNT(*) c FROM exchange_clicks").fetchone()["c"]
    if clicks == 0:
        return None
    return emergencies / clicks
