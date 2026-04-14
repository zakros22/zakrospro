#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
قاعدة البيانات - تدعم PostgreSQL و SQLite
"""

import os
import sqlite3
import logging
from config import FREE_ATTEMPTS, PAID_ATTEMPTS, REFERRAL_POINTS_PER_INVITE, REFERRAL_POINTS_PER_ATTEMPT

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  اختيار نوع قاعدة البيانات
# ══════════════════════════════════════════════════════════════════════════════
DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL and DATABASE_URL.startswith("postgresql"):
    import psycopg2
    import psycopg2.extras
    
    def get_connection():
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    
    USING_POSTGRES = True
    PLACEHOLDER = "%s"
    logger.info("🗄️ استخدام PostgreSQL")
else:
    USING_POSTGRES = False
    PLACEHOLDER = "?"
    DB_PATH = os.path.join("/tmp/telegram_bot", "bot.db")
    os.makedirs("/tmp/telegram_bot", exist_ok=True)
    
    def get_connection():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    
    logger.info("🗄️ استخدام SQLite")


# ══════════════════════════════════════════════════════════════════════════════
#  تهيئة قاعدة البيانات
# ══════════════════════════════════════════════════════════════════════════════
def init_db():
    """إنشاء الجداول إذا لم تكن موجودة."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        # جدول المستخدمين
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                attempts_left INTEGER DEFAULT 1,
                total_videos INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT FALSE,
                referral_points FLOAT DEFAULT 0,
                referred_by BIGINT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # جدول المدفوعات
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                amount DECIMAL(10,2),
                payment_method TEXT,
                status TEXT DEFAULT 'pending',
                reference_id TEXT,
                attempts_granted INTEGER DEFAULT 7,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # جدول الإحالات
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT NOT NULL,
                referred_id BIGINT NOT NULL UNIQUE,
                points_awarded FLOAT DEFAULT 0.1,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # جدول طلبات الفيديو
        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                input_type TEXT,
                dialect TEXT,
                status TEXT DEFAULT 'processing',
                video_path TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
    else:
        # جدول المستخدمين
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                attempts_left INTEGER DEFAULT 1,
                total_videos INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                referral_points REAL DEFAULT 0,
                referred_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # جدول المدفوعات
        cur.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL,
                payment_method TEXT,
                status TEXT DEFAULT 'pending',
                reference_id TEXT,
                attempts_granted INTEGER DEFAULT 7,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # جدول الإحالات
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                points_awarded REAL DEFAULT 0.1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # جدول طلبات الفيديو
        cur.execute("""
            CREATE TABLE IF NOT EXISTS video_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                input_type TEXT,
                dialect TEXT,
                status TEXT DEFAULT 'processing',
                video_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    conn.commit()
    cur.close()
    conn.close()
    logger.info("✅ تم تهيئة قاعدة البيانات")


# ══════════════════════════════════════════════════════════════════════════════
#  دوال المستخدمين
# ══════════════════════════════════════════════════════════════════════════════
def get_user(user_id: int):
    """جلب بيانات المستخدم."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM users WHERE user_id = {PLACEHOLDER}", (user_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    
    if row:
        if USING_POSTGRES:
            return dict(row)
        else:
            return {
                "user_id": row[0], "username": row[1], "full_name": row[2],
                "attempts_left": row[3], "total_videos": row[4], "is_banned": bool(row[5]),
                "referral_points": row[6], "referred_by": row[7], "created_at": row[8]
            }
    return None


def create_user(user_id: int, username: str = "", full_name: str = "", referred_by: int = None):
    """إنشاء مستخدم جديد."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("""
            INSERT INTO users (user_id, username, full_name, attempts_left, referred_by)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                updated_at = NOW()
            RETURNING *
        """, (user_id, username, full_name, FREE_ATTEMPTS, referred_by))
    else:
        cur.execute("""
            INSERT OR REPLACE INTO users (user_id, username, full_name, attempts_left, referred_by, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (user_id, username, full_name, FREE_ATTEMPTS, referred_by))
        cur.execute(f"SELECT * FROM users WHERE user_id = {PLACEHOLDER}", (user_id,))
    
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    if USING_POSTGRES:
        return dict(row)
    else:
        return {
            "user_id": row[0], "username": row[1], "full_name": row[2],
            "attempts_left": row[3], "total_videos": row[4], "is_banned": bool(row[5]),
            "referral_points": row[6], "referred_by": row[7]
        }


def decrement_attempts(user_id: int) -> int:
    """خصم محاولة وإضافة فيديو."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("""
            UPDATE users SET attempts_left = attempts_left - 1, 
            total_videos = total_videos + 1, updated_at = NOW()
            WHERE user_id = %s AND attempts_left > 0
            RETURNING attempts_left
        """, (user_id,))
    else:
        cur.execute("""
            UPDATE users SET attempts_left = attempts_left - 1,
            total_videos = total_videos + 1, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ? AND attempts_left > 0
        """, (user_id,))
        cur.execute(f"SELECT attempts_left FROM users WHERE user_id = {PLACEHOLDER}", (user_id,))
    
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    if row:
        return row[0] if not USING_POSTGRES else row['attempts_left']
    return 0


def add_attempts(user_id: int, count: int) -> int:
    """إضافة محاولات."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("""
            UPDATE users SET attempts_left = attempts_left + %s, updated_at = NOW()
            WHERE user_id = %s
            RETURNING attempts_left
        """, (count, user_id))
    else:
        cur.execute("""
            UPDATE users SET attempts_left = attempts_left + ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (count, user_id))
        cur.execute(f"SELECT attempts_left FROM users WHERE user_id = {PLACEHOLDER}", (user_id,))
    
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    if row:
        return row[0] if not USING_POSTGRES else row['attempts_left']
    return 0


def subtract_attempts(user_id: int, count: int) -> int:
    """خصم محاولات."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("""
            UPDATE users SET attempts_left = GREATEST(0, attempts_left - %s), updated_at = NOW()
            WHERE user_id = %s
            RETURNING attempts_left
        """, (count, user_id))
    else:
        cur.execute("""
            UPDATE users SET attempts_left = MAX(0, attempts_left - ?), updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (count, user_id))
        cur.execute(f"SELECT attempts_left FROM users WHERE user_id = {PLACEHOLDER}", (user_id,))
    
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    if row:
        return row[0] if not USING_POSTGRES else row['attempts_left']
    return 0


def set_attempts(user_id: int, count: int):
    """تعيين عدد المحاولات."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("UPDATE users SET attempts_left = %s, updated_at = NOW() WHERE user_id = %s", (count, user_id))
    else:
        cur.execute("UPDATE users SET attempts_left = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", (count, user_id))
    
    conn.commit()
    cur.close()
    conn.close()


def increment_total_videos(user_id: int):
    """زيادة عداد الفيديوهات."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("UPDATE users SET total_videos = total_videos + 1 WHERE user_id = %s", (user_id,))
    else:
        cur.execute("UPDATE users SET total_videos = total_videos + 1 WHERE user_id = ?", (user_id,))
    
    conn.commit()
    cur.close()
    conn.close()


def ban_user(user_id: int, banned: bool = True):
    """حظر أو رفع الحظر عن مستخدم."""
    conn = get_connection()
    cur = conn.cursor()
    ban_val = banned if USING_POSTGRES else (1 if banned else 0)
    cur.execute(f"UPDATE users SET is_banned = {PLACEHOLDER} WHERE user_id = {PLACEHOLDER}", (ban_val, user_id))
    conn.commit()
    cur.close()
    conn.close()


def is_banned(user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم محظوراً."""
    user = get_user(user_id)
    return user.get('is_banned', False) if user else False


def get_all_users(limit: int = 50, offset: int = 0):
    """جلب قائمة المستخدمين."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s", (limit, offset))
    else:
        cur.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    users = []
    for row in rows:
        if USING_POSTGRES:
            users.append(dict(row))
        else:
            users.append({
                "user_id": row[0], "username": row[1], "full_name": row[2],
                "attempts_left": row[3], "total_videos": row[4], "is_banned": bool(row[5]),
                "referral_points": row[6], "created_at": row[8]
            })
    return users


def get_stats():
    """جلب إحصائيات عامة."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) as total FROM users")
    total_users = cur.fetchone()[0] if not USING_POSTGRES else cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(*) as total FROM users WHERE DATE(created_at) = DATE('now')")
    new_today = cur.fetchone()[0] if not USING_POSTGRES else cur.fetchone()['total']
    
    cur.execute("SELECT COALESCE(SUM(total_videos), 0) as total FROM users")
    total_videos = cur.fetchone()[0] if not USING_POSTGRES else cur.fetchone()['total']
    
    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE status = 'approved'")
    total_revenue = cur.fetchone()[0] if not USING_POSTGRES else cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(*) as total FROM payments WHERE status = 'pending'")
    pending_payments = cur.fetchone()[0] if not USING_POSTGRES else cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(*) as total FROM users WHERE is_banned = true")
    banned_users = cur.fetchone()[0] if not USING_POSTGRES else cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    return {
        'total_users': total_users,
        'new_today': new_today,
        'total_videos': int(total_videos or 0),
        'total_revenue': float(total_revenue or 0),
        'pending_payments': pending_payments,
        'banned_users': banned_users
    }


# ══════════════════════════════════════════════════════════════════════════════
#  دوال المدفوعات
# ══════════════════════════════════════════════════════════════════════════════
def create_payment(user_id: int, method: str, amount: float, reference: str = None) -> int:
    """إنشاء طلب دفع جديد."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("""
            INSERT INTO payments (user_id, payment_method, amount, reference_id, status)
            VALUES (%s, %s, %s, %s, 'pending')
            RETURNING id
        """, (user_id, method, amount, reference))
        pid = cur.fetchone()['id']
    else:
        cur.execute("""
            INSERT INTO payments (user_id, payment_method, amount, reference_id, status)
            VALUES (?, ?, ?, ?, 'pending')
        """, (user_id, method, amount, reference))
        pid = cur.lastrowid
    
    conn.commit()
    cur.close()
    conn.close()
    return pid


def approve_payment(payment_id: int):
    """الموافقة على دفع وإضافة المحاولات."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("""
            UPDATE payments SET status = 'approved', attempts_granted = %s
            WHERE id = %s AND status = 'pending'
            RETURNING user_id
        """, (PAID_ATTEMPTS, payment_id))
    else:
        cur.execute("""
            UPDATE payments SET status = 'approved', attempts_granted = ?
            WHERE id = ? AND status = 'pending'
        """, (PAID_ATTEMPTS, payment_id))
        cur.execute(f"SELECT user_id FROM payments WHERE id = {PLACEHOLDER}", (payment_id,))
    
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    if row:
        user_id = row[0] if not USING_POSTGRES else row['user_id']
        add_attempts(user_id, PAID_ATTEMPTS)
        return {"user_id": user_id}
    return None


def mark_payment_approved_without_adding(payment_id: int):
    """تحديث حالة الدفع إلى approved بدون إضافة محاولات."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("UPDATE payments SET status = 'approved', attempts_granted = %s WHERE id = %s", (PAID_ATTEMPTS, payment_id))
    else:
        cur.execute("UPDATE payments SET status = 'approved', attempts_granted = ? WHERE id = ?", (PAID_ATTEMPTS, payment_id))
    
    conn.commit()
    cur.close()
    conn.close()


def get_pending_payments():
    """جلب المدفوعات المعلقة."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("""
            SELECT p.*, u.username, u.full_name
            FROM payments p JOIN users u ON p.user_id = u.user_id
            WHERE p.status = 'pending'
            ORDER BY p.created_at DESC
            LIMIT 20
        """)
    else:
        cur.execute("""
            SELECT p.*, u.username, u.full_name
            FROM payments p JOIN users u ON p.user_id = u.user_id
            WHERE p.status = 'pending'
            ORDER BY p.created_at DESC
            LIMIT 20
        """)
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    payments = []
    for row in rows:
        if USING_POSTGRES:
            payments.append(dict(row))
        else:
            payments.append({
                "id": row[0], "user_id": row[1], "amount": row[2], "payment_method": row[3],
                "status": row[4], "reference_id": row[5], "attempts_granted": row[6],
                "created_at": row[7], "username": row[8], "full_name": row[9]
            })
    return payments


# ══════════════════════════════════════════════════════════════════════════════
#  دوال الإحالات
# ══════════════════════════════════════════════════════════════════════════════
def record_referral(referrer_id: int, referred_id: int) -> dict:
    """تسجيل إحالة جديدة."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(f"SELECT id FROM referrals WHERE referred_id = {PLACEHOLDER}", (referred_id,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return {'already_referred': True, 'new_points': 0, 'attempts_granted': 0}
    
    if USING_POSTGRES:
        cur.execute("""
            INSERT INTO referrals (referrer_id, referred_id, points_awarded)
            VALUES (%s, %s, %s)
        """, (referrer_id, referred_id, REFERRAL_POINTS_PER_INVITE))
        
        cur.execute("""
            UPDATE users SET referral_points = referral_points + %s, updated_at = NOW()
            WHERE user_id = %s
            RETURNING referral_points
        """, (REFERRAL_POINTS_PER_INVITE, referrer_id))
        row = cur.fetchone()
        new_points = row['referral_points'] if row else 0
    else:
        cur.execute("""
            INSERT INTO referrals (referrer_id, referred_id, points_awarded)
            VALUES (?, ?, ?)
        """, (referrer_id, referred_id, REFERRAL_POINTS_PER_INVITE))
        
        cur.execute("""
            UPDATE users SET referral_points = referral_points + ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (REFERRAL_POINTS_PER_INVITE, referrer_id))
        cur.execute(f"SELECT referral_points FROM users WHERE user_id = {PLACEHOLDER}", (referrer_id,))
        row = cur.fetchone()
        new_points = row[0] if row else 0
    
    attempts_granted = 0
    while new_points >= REFERRAL_POINTS_PER_ATTEMPT:
        new_points -= REFERRAL_POINTS_PER_ATTEMPT
        attempts_granted += 1
    
    if attempts_granted > 0:
        if USING_POSTGRES:
            cur.execute("""
                UPDATE users SET attempts_left = attempts_left + %s, referral_points = %s
                WHERE user_id = %s
            """, (attempts_granted, new_points, referrer_id))
        else:
            cur.execute("""
                UPDATE users SET attempts_left = attempts_left + ?, referral_points = ?
                WHERE user_id = ?
            """, (attempts_granted, new_points, referrer_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {
        'already_referred': False,
        'new_points': new_points,
        'attempts_granted': attempts_granted,
        'total_points_added': REFERRAL_POINTS_PER_INVITE
    }


def get_referral_stats(user_id: int) -> dict:
    """جلب إحصائيات الإحالة لمستخدم."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(f"SELECT COUNT(*) FROM referrals WHERE referrer_id = {PLACEHOLDER}", (user_id,))
    total = cur.fetchone()[0]
    
    cur.execute(f"SELECT referral_points FROM users WHERE user_id = {PLACEHOLDER}", (user_id,))
    row = cur.fetchone()
    points = row[0] if row else 0
    
    cur.close()
    conn.close()
    
    return {
        'total_referrals': total,
        'current_points': round(points, 2),
        'points_needed': round(REFERRAL_POINTS_PER_ATTEMPT - points, 2) if points < REFERRAL_POINTS_PER_ATTEMPT else 0
    }


# ══════════════════════════════════════════════════════════════════════════════
#  دوال طلبات الفيديو
# ══════════════════════════════════════════════════════════════════════════════
def save_video_request(user_id: int, input_type: str, dialect: str) -> int:
    """حفظ طلب فيديو جديد."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("""
            INSERT INTO video_requests (user_id, input_type, dialect, status)
            VALUES (%s, %s, %s, 'processing')
            RETURNING id
        """, (user_id, input_type, dialect))
        req_id = cur.fetchone()['id']
    else:
        cur.execute("""
            INSERT INTO video_requests (user_id, input_type, dialect, status)
            VALUES (?, ?, ?, 'processing')
        """, (user_id, input_type, dialect))
        req_id = cur.lastrowid
    
    conn.commit()
    cur.close()
    conn.close()
    return req_id


def update_video_request(req_id: int, status: str, video_path: str = None):
    """تحديث حالة طلب فيديو."""
    conn = get_connection()
    cur = conn.cursor()
    
    if USING_POSTGRES:
        cur.execute("UPDATE video_requests SET status = %s, video_path = %s WHERE id = %s", (status, video_path, req_id))
    else:
        cur.execute("UPDATE video_requests SET status = ?, video_path = ? WHERE id = ?", (status, video_path, req_id))
    
    conn.commit()
    cur.close()
    conn.close()


# تهيئة قاعدة البيانات
init_db()
