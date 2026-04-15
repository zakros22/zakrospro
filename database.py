import psycopg2
import psycopg2.extras
from psycopg2 import sql
from config import DATABASE_URL, FREE_ATTEMPTS, REFERRAL_POINTS_PER_INVITE, REFERRAL_POINTS_PER_ATTEMPT


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    
    # ══════════════════════════════════════════════════════════════════════════
    # 👥 USERS TABLE
    # ══════════════════════════════════════════════════════════════════════════
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

    for col, definition in [
        ("referral_points", "FLOAT DEFAULT 0"),
        ("referred_by", "BIGINT DEFAULT NULL"),
        ("preferred_dialect", "TEXT DEFAULT 'msa'"),
        ("total_lectures", "INTEGER DEFAULT 0"),
        ("last_active", "TIMESTAMP DEFAULT NOW()"),
    ]:
        try:
            cur.execute(
                sql.SQL("ALTER TABLE users ADD COLUMN IF NOT EXISTS {} {}").format(
                    sql.Identifier(col),
                    sql.SQL(definition),
                )
            )
        except Exception:
            pass
    
    # ══════════════════════════════════════════════════════════════════════════
    # 💰 PAYMENTS TABLE
    # ══════════════════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount DECIMAL(10,2),
            payment_method TEXT,
            status TEXT DEFAULT 'pending',
            reference_id TEXT,
            attempts_granted INTEGER DEFAULT 4,
            proof_message_id BIGINT,
            approved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    # ══════════════════════════════════════════════════════════════════════════
    # 🎬 VIDEO REQUESTS TABLE
    # ══════════════════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_requests (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            input_type TEXT,
            dialect TEXT,
            lecture_type TEXT,
            status TEXT DEFAULT 'processing',
            video_path TEXT,
            pdf_path TEXT,
            error_message TEXT,
            processing_time FLOAT,
            sections_count INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            completed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    for col, definition in [
        ("error_message", "TEXT"),
        ("processing_time", "FLOAT"),
        ("sections_count", "INTEGER"),
        ("completed_at", "TIMESTAMP"),
    ]:
        try:
            cur.execute(
                sql.SQL("ALTER TABLE video_requests ADD COLUMN IF NOT EXISTS {} {}").format(
                    sql.Identifier(col),
                    sql.SQL(definition),
                )
            )
        except Exception:
            pass
    
    # ══════════════════════════════════════════════════════════════════════════
    # 🔗 REFERRALS TABLE
    # ══════════════════════════════════════════════════════════════════════════
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

    # ══════════════════════════════════════════════════════════════════════════
    # 📊 BOT STATS TABLE
    # ══════════════════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bot_stats (
            id SERIAL PRIMARY KEY,
            stat_date DATE DEFAULT CURRENT_DATE,
            total_users INTEGER DEFAULT 0,
            new_users INTEGER DEFAULT 0,
            active_users INTEGER DEFAULT 0,
            total_videos INTEGER DEFAULT 0,
            total_lectures INTEGER DEFAULT 0,
            total_revenue DECIMAL(10,2) DEFAULT 0,
            deepseek_calls INTEGER DEFAULT 0,
            gemini_calls INTEGER DEFAULT 0,
            groq_calls INTEGER DEFAULT 0,
            openrouter_calls INTEGER DEFAULT 0,
            elevenlabs_calls INTEGER DEFAULT 0,
            gtts_calls INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    # ══════════════════════════════════════════════════════════════════════════
    # 📝 NOTES TABLE (للمذكرات)
    # ══════════════════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            content_type TEXT NOT NULL,
            file_id TEXT,
            text_content TEXT,
            original_filename TEXT,
            reminder_at TIMESTAMP,
            reminded BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_reminder ON notes(reminder_at) WHERE reminded = FALSE")

    # ══════════════════════════════════════════════════════════════════════════
    # 🔑 API KEYS USAGE TABLE (لتتبع استخدام المفاتيح)
    # ══════════════════════════════════════════════════════════════════════════
    cur.execute("""
        CREATE TABLE IF NOT EXISTS api_keys_usage (
            id SERIAL PRIMARY KEY,
            service TEXT NOT NULL,
            key_index INTEGER,
            status TEXT DEFAULT 'active',
            calls_count INTEGER DEFAULT 0,
            last_used TIMESTAMP DEFAULT NOW(),
            exhausted_at TIMESTAMP
        )
    """)

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Database initialized successfully")


# ══════════════════════════════════════════════════════════════════════════════
# 👤 USER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_user(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return dict(user) if user else None


def create_user(user_id: int, username: str, full_name: str, referred_by: int | None = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, username, full_name, attempts_left, referred_by)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE
        SET username = EXCLUDED.username,
            full_name = EXCLUDED.full_name,
            last_active = NOW(),
            updated_at = NOW()
        RETURNING *
    """, (user_id, username, full_name, FREE_ATTEMPTS, referred_by))
    user = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return dict(user)


def update_last_active(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_active = NOW() WHERE user_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()


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


def subtract_attempts(user_id: int, count: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET attempts_left = GREATEST(0, attempts_left - %s), updated_at = NOW()
        WHERE user_id = %s
        RETURNING attempts_left
    """, (count, user_id))
    result = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return result['attempts_left'] if result else 0


def set_attempts(user_id: int, count: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users SET attempts_left = %s, updated_at = NOW()
        WHERE user_id = %s
    """, (count, user_id))
    conn.commit()
    cur.close()
    conn.close()


def increment_total_videos(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users SET total_videos = total_videos + 1, total_lectures = total_lectures + 1, updated_at = NOW()
        WHERE user_id = %s
    """, (user_id,))
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


# ══════════════════════════════════════════════════════════════════════════════
# 💰 PAYMENT FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

PAID_ATTEMPTS_CONST = 4


def create_payment(user_id: int, method: str, amount: float, reference: str = None) -> int:
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
        UPDATE payments SET status = 'approved', attempts_granted = 4, approved_at = NOW()
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


def mark_payment_approved_without_adding(payment_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE payments SET status = 'approved', attempts_granted = %s, approved_at = NOW()
        WHERE id = %s
    """, (PAID_ATTEMPTS_CONST, payment_id))
    conn.commit()
    cur.close()
    conn.close()


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


# ══════════════════════════════════════════════════════════════════════════════
# 🔗 REFERRAL FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

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
        ON CONFLICT (referred_id) DO NOTHING
    """, (referrer_id, referred_id, REFERRAL_POINTS_PER_INVITE))

    cur.execute("""
        UPDATE users
        SET referral_points = referral_points + %s, updated_at = NOW()
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
                referral_points = %s,
                updated_at = NOW()
            WHERE user_id = %s
        """, (attempts_granted, round(new_points, 2), referrer_id))

    conn.commit()
    cur.close()
    conn.close()
    return {
        'already_referred': False,
        'new_points': round(new_points, 2),
        'attempts_granted': attempts_granted,
        'total_points_added': REFERRAL_POINTS_PER_INVITE,
    }


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
        'next_attempt_at': int(total_referrals + ((REFERRAL_POINTS_PER_ATTEMPT - points) / REFERRAL_POINTS_PER_INVITE)) + 1,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🎬 VIDEO REQUEST FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def save_video_request(user_id: int, input_type: str, dialect: str, lecture_type: str = None) -> int:
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


def update_video_request(req_id: int, status: str, video_path: str = None, 
                         pdf_path: str = None, error_message: str = None,
                         processing_time: float = None, sections_count: int = None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE video_requests 
        SET status = %s, video_path = %s, pdf_path = %s, 
            error_message = %s, processing_time = %s, sections_count = %s,
            completed_at = CASE WHEN %s IN ('done', 'failed', 'cancelled') THEN NOW() ELSE completed_at END
        WHERE id = %s
    """, (status, video_path, pdf_path, error_message, processing_time, sections_count, status, req_id))
    conn.commit()
    cur.close()
    conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# 📊 STATS FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def get_all_users(limit: int = 50, offset: int = 0):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, username, full_name, attempts_left, total_videos, 
               total_lectures, is_banned, referral_points, created_at, last_active
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

    cur.execute("SELECT COALESCE(SUM(total_videos), 0) as total FROM users")
    total_videos = cur.fetchone()['total'] or 0

    cur.execute("SELECT COALESCE(SUM(amount), 0) as total FROM payments WHERE status = 'approved'")
    total_revenue = cur.fetchone()['total'] or 0

    cur.execute("SELECT COUNT(*) as total FROM payments WHERE status = 'pending'")
    pending_payments = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) as total FROM users WHERE is_banned = true")
    banned_users = cur.fetchone()['total']

    cur.execute("SELECT COUNT(*) as total FROM users WHERE last_active > NOW() - INTERVAL '24 hours'")
    active_users = cur.fetchone()['total']

    cur.close()
    conn.close()

    return {
        'total_users': total_users,
        'new_today': new_today,
        'total_videos': total_videos,
        'total_revenue': float(total_revenue),
        'pending_payments': pending_payments,
        'banned_users': banned_users,
        'active_users': active_users,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 📝 NOTES FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def save_note(user_id: int, name: str, content_type: str,
              file_id: str = None, text_content: str = None,
              original_filename: str = None, reminder_at=None) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO notes (user_id, name, content_type, file_id, text_content, original_filename, reminder_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (user_id, name, content_type, file_id, text_content, original_filename, reminder_at))
    note_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    return note_id


def get_user_notes(user_id: int) -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, content_type, reminder_at, reminded, created_at
        FROM notes WHERE user_id = %s ORDER BY created_at DESC
    """, (user_id,))
    notes = [dict(n) for n in cur.fetchall()]
    cur.close()
    conn.close()
    return notes


def get_note(note_id: int, user_id: int) -> dict | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM notes WHERE id = %s AND user_id = %s", (note_id, user_id))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def delete_note(note_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id = %s AND user_id = %s RETURNING id", (note_id, user_id))
    deleted = cur.fetchone() is not None
    conn.commit()
    cur.close()
    conn.close()
    return deleted


def set_note_reminder(note_id: int, user_id: int, reminder_at) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE notes SET reminder_at = %s, reminded = FALSE
        WHERE id = %s AND user_id = %s RETURNING id
    """, (reminder_at, note_id, user_id))
    updated = cur.fetchone() is not None
    conn.commit()
    cur.close()
    conn.close()
    return updated


def get_due_reminders() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM notes
        WHERE reminder_at IS NOT NULL AND reminder_at <= NOW() AND reminded = FALSE
    """)
    notes = [dict(n) for n in cur.fetchall()]
    cur.close()
    conn.close()
    return notes


def mark_reminded(note_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notes SET reminded = TRUE WHERE id = %s", (note_id,))
    conn.commit()
    cur.close()
    conn.close()
