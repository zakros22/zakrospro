import psycopg2
import psycopg2.extras
from config import DATABASE_URL, FREE_ATTEMPTS, REFERRAL_POINTS_PER_INVITE, REFERRAL_POINTS_PER_ATTEMPT

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    
    # جدول المستخدمين
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            attempts_left INTEGER DEFAULT 3,
            total_videos INTEGER DEFAULT 0,
            is_banned BOOLEAN DEFAULT FALSE,
            referral_points FLOAT DEFAULT 0,
            referred_by BIGINT DEFAULT NULL,
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
            pdf_path TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # جدول الإحصاءات
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_stats (
            id SERIAL PRIMARY KEY,
            stat_date DATE DEFAULT CURRENT_DATE,
            total_users INTEGER DEFAULT 0,
            new_users INTEGER DEFAULT 0,
            total_videos INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Database initialized")

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
            full_name = EXCLUDED.full_name
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
        UPDATE users SET attempts_left = attempts_left - 1
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
        UPDATE users SET attempts_left = attempts_left + %s
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

def is_banned(user_id: int) -> bool:
    user = get_user(user_id)
    return user.get('is_banned', False) if user else False

def ban_user(user_id: int, banned: bool = True):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_banned = %s WHERE user_id = %s", (banned, user_id))
    conn.commit()
    cur.close()
    conn.close()

def save_video_request(user_id: int, input_type: str, dialect: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO video_requests (user_id, input_type, dialect, status)
        VALUES (%s, %s, %s, 'processing')
        RETURNING id
    """, (user_id, input_type, dialect))
    req_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    return req_id

def update_video_request(req_id: int, status: str, video_path: str = None, pdf_path: str = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE video_requests SET status = %s, video_path = %s, pdf_path = %s
        WHERE id = %s
    """, (status, video_path, pdf_path, req_id))
    conn.commit()
    cur.close()
    conn.close()

def record_referral(referrer_id: int, referred_id: int) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id FROM referrals WHERE referred_id = %s", (referred_id,))
    if cur.fetchone():
        cur.close(); conn.close()
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
            UPDATE users
            SET attempts_left = attempts_left + %s,
                referral_points = %s
            WHERE user_id = %s
        """, (attempts_granted, new_points, referrer_id))
    
    conn.commit()
    cur.close()
    conn.close()
    return {
        'already_referred': False,
        'new_points': new_points,
        'attempts_granted': attempts_granted
    }

def get_referral_stats(user_id: int) -> dict:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT referral_points FROM users WHERE user_id = %s", (user_id,))
    row = cur.fetchone()
    points = row['referral_points'] if row else 0
    
    cur.execute("SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = %s", (user_id,))
    total = cur.fetchone()['cnt']
    cur.close(); conn.close()
    
    return {
        'total_referrals': total,
        'current_points': round(points, 2),
        'points_needed': round(1.0 - points, 2) if points < 1.0 else 0
    }

def get_stats():
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) as total FROM users")
    total_users = cur.fetchone()['total']
    
    cur.execute("SELECT COUNT(*) as total FROM users WHERE DATE(created_at) = CURRENT_DATE")
    new_today = cur.fetchone()['total']
    
    cur.execute("SELECT SUM(total_videos) as total FROM users")
    total_videos = cur.fetchone()['total'] or 0
    
    cur.execute("SELECT COUNT(*) as total FROM users WHERE is_banned = true")
    banned = cur.fetchone()['total']
    
    cur.close(); conn.close()
    
    return {
        'total_users': total_users,
        'new_today': new_today,
        'total_videos': total_videos,
        'banned_users': banned
    }

def get_all_users(limit: int = 50):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, full_name, attempts_left, total_videos, is_banned, created_at
        FROM users ORDER BY created_at DESC LIMIT %s
    """, (limit,))
    users = [dict(u) for u in cur.fetchall()]
    cur.close(); conn.close()
    return users
