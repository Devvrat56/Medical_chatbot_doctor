# local_db.py
import sqlite3
from datetime import datetime

DB_PATH = "onco_chatbot.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        session_id TEXT PRIMARY KEY,
        user_type TEXT,
        created_at TEXT,
        last_active TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT,
        role TEXT,
        content TEXT,
        timestamp TEXT
    )
    """)

    conn.commit()
    conn.close()


def ensure_session_exists(session_id, user_type="unknown"):
    conn = get_conn()
    cur = conn.cursor()

    now = datetime.utcnow().isoformat()

    # 🔐 SAFE: creates session if missing
    cur.execute("""
    INSERT OR IGNORE INTO chat_sessions
    (session_id, user_type, created_at, last_active)
    VALUES (?, ?, ?, ?)
    """, (session_id, user_type, now, now))

    conn.commit()
    conn.close()


def update_session_activity(session_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    UPDATE chat_sessions
    SET last_active = ?
    WHERE session_id = ?
    """, (datetime.utcnow().isoformat(), session_id))

    conn.commit()
    conn.close()


def create_session(session_id, user_type):
    ensure_session_exists(session_id, user_type)


def save_message(session_id, role, content):
    # 🛡️ GUARANTEE session row exists
    ensure_session_exists(session_id)

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO chat_messages
    (session_id, role, content, timestamp)
    VALUES (?, ?, ?, ?)
    """, (session_id, role, content, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()

    update_session_activity(session_id)
