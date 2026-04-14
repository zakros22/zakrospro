#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import os
from config import TEMP_DIR, FREE_ATTEMPTS

DB_PATH = os.path.join(TEMP_DIR, "bot.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # جدول المستخدمين
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            attempts INTEGER DEFAULT 1,
            videos INTEGER DEFAULT 0,
            banned INTEGER DEFAULT 0,
            referral_points REAL DEFAULT 0,
            referred_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # جدول المدفوعات
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            method TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # جدول الإحالات
    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER UNIQUE,
            points REAL DEFAULT 0.1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "user_id": row[0], "username": row[1], "full_name": row[2],
            "attempts_left": row[3], "total_videos": row[4], "is_banned": row[5],
            "referral_points": row[6], "referred_by": row[7]
        }
    return None

def create_user(user_id: int, username: str = "", full_name: str = "", referred_by: int = None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO users (user_id, username, full_name, attempts, referred_by)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, full_name, FREE_ATTEMPTS, referred_by))
    conn.commit()
    conn.close()
    return get_user(user_id)

def decrement_attempts(user_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET attempts = attempts - 1, videos = videos + 1 WHERE user_id = ? AND attempts > 0", (user_id,))
    conn.commit()
    c.execute("SELECT attempts FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def add_attempts(user_id: int, count: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET attempts = attempts + ? WHERE user_id = ?", (count, user_id))
    conn.commit()
    conn.close()

def ban_user(user_id: int, banned: bool = True):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET banned = ? WHERE user_id = ?", (1 if banned else 0, user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, username, full_name, attempts, videos, banned FROM users ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [{"user_id": r[0], "username": r[1], "full_name": r[2], "attempts_left": r[3], "total_videos": r[4], "is_banned": r[5]} for r in rows]

def get_stats():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE banned = 1")
    banned = c.fetchone()[0]
    c.execute("SELECT SUM(videos) FROM users")
    videos = c.fetchone()[0] or 0
    conn.close()
    return {"total_users": total, "banned_users": banned, "total_videos": videos}

def record_referral(referrer_id: int, referred_id: int):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)", (referrer_id, referred_id))
        c.execute("UPDATE users SET referral_points = referral_points + 0.1 WHERE user_id = ?", (referrer_id,))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_referral_stats(user_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    count = c.fetchone()[0]
    c.execute("SELECT referral_points FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    points = row[0] if row else 0
    conn.close()
    return {"total_referrals": count, "current_points": points}

# تهيئة قاعدة البيانات
init_db()
