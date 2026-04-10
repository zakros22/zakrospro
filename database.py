# -*- coding: utf-8 -*-
import psycopg2
import psycopg2.extras
from config import DATABASE_URL, FREE_ATTEMPTS, REFERRAL_POINTS_PER_INVITE, REFERRAL_POINTS_PER_ATTEMPT

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY, username TEXT, full_name TEXT,
            attempts_left INTEGER DEFAULT 1, total_videos INTEGER DEFAULT 0,
            is_banned BOOLEAN DEFAULT FALSE, referral_points FLOAT DEFAULT 0,
            referred_by BIGINT DEFAULT NULL, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, amount DECIMAL(10,2),
            payment_method TEXT, status TEXT DEFAULT 'pending', reference_id TEXT,
            attempts_granted INTEGER DEFAULT 4, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_requests (
            id SERIAL PRIMARY KEY, user_id BIGINT NOT NULL, input_type TEXT,
            dialect TEXT, lecture_type TEXT, status TEXT DEFAULT 'processing',
            video_path TEXT, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY, referrer_id BIGINT NOT NULL, referred_id BIGINT NOT NULL UNIQUE,
            points_awarded FLOAT DEFAULT 0.1, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def get_user(uid): 
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = %s", (uid,))
        return dict(cur.fetchone() or {})

def create_user(uid, username, full_name, ref=None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, full_name, attempts_left, referred_by)
            VALUES (%s, %s, %s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username
            RETURNING *
        """, (uid, username, full_name, FREE_ATTEMPTS, ref))
        conn.commit()
        return dict(cur.fetchone())

def decrement_attempts(uid):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET attempts_left = attempts_left - 1 WHERE user_id = %s AND attempts_left > 0 RETURNING attempts_left", (uid,))
        conn.commit()
        return (cur.fetchone() or {}).get('attempts_left', 0)

def add_attempts(uid, count):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET attempts_left = attempts_left + %s WHERE user_id = %s RETURNING attempts_left", (count, uid))
        conn.commit()
        return (cur.fetchone() or {}).get('attempts_left', 0)

def increment_total_videos(uid):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET total_videos = total_videos + 1 WHERE user_id = %s", (uid,))
        conn.commit()

def save_video_request(uid, itype, dialect, ltype=None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO video_requests (user_id, input_type, dialect, lecture_type) VALUES (%s,%s,%s,%s) RETURNING id", (uid, itype, dialect, ltype))
        conn.commit()
        return cur.fetchone()['id']

def update_video_request(rid, status, path=None):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE video_requests SET status=%s, video_path=%s WHERE id=%s", (status, path, rid))
        conn.commit()

def record_referral(ref_id, refd_id):
    with get_connection() as conn:
        cur = conn.cursor()
        if cur.execute("SELECT 1 FROM referrals WHERE referred_id=%s", (refd_id,)): return
        cur.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (%s,%s)", (ref_id, refd_id))
        cur.execute("UPDATE users SET referral_points = referral_points + %s WHERE user_id=%s RETURNING referral_points", (REFERRAL_POINTS_PER_INVITE, ref_id))
        pts = (cur.fetchone() or {}).get('referral_points', 0)
        while pts >= REFERRAL_POINTS_PER_ATTEMPT:
            pts -= REFERRAL_POINTS_PER_ATTEMPT
            add_attempts(ref_id, 1)
        cur.execute("UPDATE users SET referral_points=%s WHERE user_id=%s", (pts, ref_id))
        conn.commit()

def get_referral_stats(uid):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT referral_points FROM users WHERE user_id=%s", (uid,))
        pts = (cur.fetchone() or {}).get('referral_points', 0)
        cur.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id=%s", (uid,))
        total = cur.fetchone()['cnt']
        return {'total_referrals': total, 'current_points': pts}
