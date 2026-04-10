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
            referred_by BIGINT, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY, user_id BIGINT, amount DECIMAL,
            payment_method TEXT, status TEXT DEFAULT 'pending',
            reference_id TEXT, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_requests (
            id SERIAL PRIMARY KEY, user_id BIGINT, input_type TEXT,
            dialect TEXT, lecture_type TEXT, status TEXT DEFAULT 'processing',
            video_path TEXT, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY, referrer_id BIGINT, referred_id BIGINT UNIQUE,
            points_awarded FLOAT DEFAULT 0.1, created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def get_user(uid):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = %s", (uid,))
    u = cur.fetchone()
    cur.close()
    conn.close()
    return dict(u) if u else None

def create_user(uid, username, full_name, ref=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, username, full_name, attempts_left, referred_by)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username
        RETURNING *
    """, (uid, username, full_name, FREE_ATTEMPTS, ref))
    conn.commit()
    u = cur.fetchone()
    cur.close()
    conn.close()
    return dict(u)

def decrement_attempts(uid):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET attempts_left=attempts_left-1 WHERE user_id=%s AND attempts_left>0 RETURNING attempts_left", (uid,))
    conn.commit()
    r = cur.fetchone()
    cur.close()
    conn.close()
    return r['attempts_left'] if r else 0

def add_attempts(uid, count):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET attempts_left=attempts_left+%s WHERE user_id=%s RETURNING attempts_left", (count, uid))
    conn.commit()
    r = cur.fetchone()
    cur.close()
    conn.close()
    return r['attempts_left'] if r else 0

def increment_total_videos(uid):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET total_videos=total_videos+1 WHERE user_id=%s", (uid,))
    conn.commit()
    cur.close()
    conn.close()

def save_video_request(uid, itype, dialect, ltype=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO video_requests (user_id, input_type, dialect, lecture_type) VALUES (%s,%s,%s,%s) RETURNING id", (uid, itype, dialect, ltype))
    conn.commit()
    rid = cur.fetchone()['id']
    cur.close()
    conn.close()
    return rid

def update_video_request(rid, status, path=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE video_requests SET status=%s, video_path=%s WHERE id=%s", (status, path, rid))
    conn.commit()
    cur.close()
    conn.close()

def is_banned(uid):
    u = get_user(uid)
    return u.get('is_banned', False) if u else False

def record_referral(ref_id, refd_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM referrals WHERE referred_id=%s", (refd_id,))
    if cur.fetchone():
        cur.close()
        conn.close()
        return
    cur.execute("INSERT INTO referrals (referrer_id, referred_id) VALUES (%s,%s)", (ref_id, refd_id))
    cur.execute("UPDATE users SET referral_points=referral_points+%s WHERE user_id=%s RETURNING referral_points", (REFERRAL_POINTS_PER_INVITE, ref_id))
    pts = cur.fetchone()['referral_points']
    while pts >= REFERRAL_POINTS_PER_ATTEMPT:
        pts -= REFERRAL_POINTS_PER_ATTEMPT
        add_attempts(ref_id, 1)
    cur.execute("UPDATE users SET referral_points=%s WHERE user_id=%s", (pts, ref_id))
    conn.commit()
    cur.close()
    conn.close()

def get_referral_stats(uid):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT referral_points FROM users WHERE user_id=%s", (uid,))
    pts = cur.fetchone()['referral_points'] if cur.rowcount else 0
    cur.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id=%s", (uid,))
    total = cur.fetchone()['cnt']
    cur.close()
    conn.close()
    return {'total_referrals': total, 'current_points': pts}
