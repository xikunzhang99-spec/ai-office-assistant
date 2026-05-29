import sqlite3
import os
from config.settings import DATABASE_PATH


def get_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def execute(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params or ())
        conn.commit()
        return cur
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_one(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params or ())
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def fetch_all(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params or ())
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def insert(sql, params=None):
    conn = get_connection()
    try:
        cur = conn.execute(sql, params or ())
        conn.commit()
        return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
