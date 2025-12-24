# local_db.py
import sqlite3
from datetime import datetime

DB_PATH = "onco_chatbot.db"


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Chat sessions table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        session_id TEXT PRIMARY KEY,
        user_type TEXT,
        created_at TEXT,
        last_active TEXT
    )
    """)

    # Chat messages table
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


def create_session(session_id, user_type):
    now = datetime.utcnow().isoformat()
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO chat_sessions
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


def save_message(session_id, role, content):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO chat_messages
    (session_id, role, content, timestamp)
    VALUES (?, ?, ?, ?)
    """, (session_id, role, content, datetime.utcnow().isoformat()))

    # Update session timestamp
    update_session_activity(session_id)

    conn.commit()
    conn.close()
