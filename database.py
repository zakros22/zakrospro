# -*- coding: utf-8 -*-
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from config import DATABASE_URL, FREE_ATTEMPTS, REFERRAL_POINTS_PER_INVITE, REFERRAL_POINTS_PER_ATTEMPT

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    
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
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount DECIMAL(10,2),
            payment_method TEXT,
            status TEXT DEFAULT 'pending',
            reference_id TEXT,
            attempts_granted INTEGER DEFAULT 4,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_requests (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            input_type TEXT,
            dialect TEXT,
            lecture_type TEXT,
            status TEXT DEFAULT 'processing',
            video_path TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL UNIQUE,
            points_awarded FLOAT DEFAULT 0.1,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id)
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("[DB] Database initialized")

def get_user(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return dict(user) if user else None

def create_user(user_id: int, username: str, full_name: str, referred_by: int = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, username, full_name, attempts_left, referred_by)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET username = EXCLUDED.username,
            full_name = EXCLUDED.full_name,
            updated_at = NOW()
        RETURNING *
    """, (user_id, username, full_name, FREE_ATTEMPTS, referred_by))
    user = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return dict(user)

def decrement_attempts(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users SET attempts_left = attempts_left - 1, updated_at = NOW()
        WHERE user_id = %s AND attempts_left > 0
        RETURNING attempts_left
    """, (user_id,))
    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return result['attempts_left'] if result else 0

def add_attempts(user_id: int, count: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users SET attempts_left = attempts_left + %s, updated_at = NOW()
        WHERE user_id = %s
        RETURNING attempts_left
    """, (count, user_id))
    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return result['attempts_left'] if result else 0

def increment_total_videos(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET total_videos = total_videos + 1 WHERE user_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def ban_user(user_id: int, banned: bool = True):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_banned = %s WHERE user_id = %s", (banned, user_id))
    conn.commit()
    cur.close()
    conn.close()

def is_banned(user_id: int) -> bool:
    user = get_user(user_id)
    return user.get('is_banned', False) if user else False

def create_payment(user_id: int, method: str, amount: float, reference: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO payments (user_id, payment_method, amount, reference_id, status)
        VALUES (%s, %s, %s, %s, 'pending')
        RETURNING id
    """, (user_id, method, amount, reference))
    payment_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    return payment_id

def approve_payment(payment_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE payments SET status = 'approved', attempts_granted = 4
        WHERE id = %s AND status = 'pending'
        RETURNING user_id
    """, (payment_id,))
    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if result:
        add_attempts(result['user_id'], 4)
    return result

def record_referral(referrer_id: int, referred_id: int) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM referrals WHERE referred_id = %s", (referred_id,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return {'already_referred': True, 'new_points': 0, 'attempts_granted': 0}
    
    cur.execute("""
        INSERT INTO referrals (referrer_id, referred_id, points_awarded)
        VALUES (%s, %s, %s)
    """, (referrer_id, referred_id, REFERRAL_POINTS_PER_INVITE))
    
    cur.execute("""
        UPDATE users SET referral_points = referral_points + %s
        WHERE user_id = %s
        RETURNING referral_points
    """, (REFERRAL_POINTS_PER_INVITE, referrer_id))
    row = cur.fetchone()
    new_points = row['referral_points'] if row else 0
    
    attempts_granted = 0
    while new_points >= REFERRAL_POINTS_PER_ATTEMPT:
        new_points -= REFERRAL_POINTS_PER_ATTEMPT
        attempts_granted += 1
    
    if attempts_granted > 0:
        cur.execute("""
            UPDATE users SET attempts_left = attempts_left + %s, referral_points = %s
            WHERE user_id = %s
        """, (attempts_granted, round(new_points, 2), referrer_id))
    
    conn.commit()
    cur.close()
    conn.close()
    return {'already_referred': False, 'new_points': round(new_points, 2), 'attempts_granted': attempts_granted}

def get_referral_stats(user_id: int) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT referral_points FROM users WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    points = row['referral_points'] if row else 0
    
    cur.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = %s", (user_id,))
    total_referrals = cur.fetchone()['cnt']
    
    cur.close()
    conn.close()
    return {
        'total_referrals': total_referrals,
        'current_points': round(points, 2),
        'points_needed': round(REFERRAL_POINTS_PER_ATTEMPT - points, 2) if points < REFERRAL_POINTS_PER_ATTEMPT else 0,
    }

def get_all_users(limit: int = 50, offset: int = 0):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, full_name, attempts_left, total_videos, is_banned, created_at
        FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s
    """, (limit, offset))
    users = [dict(u) for u in cur.fetchall()]
    cur.close()
    conn.close()
    return users

def get_stats():
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) as total FROM users")
    total_users = cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(*) as total FROM users WHERE DATE(created_at) = CURRENT_DATE")
    new_today = cur.fetchone()['total']
    
    cur.execute("SELECT SUM(total_videos) as total FROM users")
    total_videos = cur.fetchone()['total'] or 0
    
    cur.execute("SELECT SUM(amount) as total FROM payments WHERE status = 'approved'")
    total_revenue = cur.fetchone()['total'] or 0
    
    cur.execute("SELECT COUNT(*) as total FROM payments WHERE status = 'pending'")
    pending_payments = cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(*) as total FROM users WHERE is_banned = true")
    banned_users = cur.fetchone()['total']
    
    cur.close()
    conn.close()
    
    return {
        'total_users': total_users,
        'new_today': new_today,
        'total_videos': total_videos,
        'total_revenue': float(total_revenue),
        'pending_payments': pending_payments,
        'banned_users': banned_users
    }

def get_pending_payments():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*, u.username, u.full_name
        FROM payments p JOIN users u ON p.user_id = u.user_id
        WHERE p.status = 'pending'
        ORDER BY p.created_at DESC
        LIMIT 20
    """)
    payments = [dict(p) for p in cur.fetchall()]
    cur.close()
    conn.close()
    return payments

def save_video_request(user_id: int, input_type: str, dialect: str, lecture_type: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO video_requests (user_id, input_type, dialect, lecture_type, status)
        VALUES (%s, %s, %s, %s, 'processing')
        RETURNING id
    """, (user_id, input_type, dialect, lecture_type))
    req_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    return req_id

def update_video_request(req_id: int, status: str, video_path: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE video_requests SET status = %s, video_path = %s WHERE id = %s", (status, video_path, req_id))
    conn.commit()
    cur.close()
    conn.close()
