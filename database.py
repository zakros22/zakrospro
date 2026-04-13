# database.py
# -*- coding: utf-8 -*-
"""
وحدة إدارة قاعدة بيانات PostgreSQL لبوت المحاضرات الطبية
تحتوي على دوال إنشاء الجداول وإدارة المستخدمين والمدفوعات والإحالات والفيديوهات
"""

import psycopg2
import psycopg2.extras
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Union
from contextlib import contextmanager

from config import config

logger = logging.getLogger(__name__)

# تسجيل محول UUID لـ psycopg2
psycopg2.extras.register_uuid()

@contextmanager
def get_connection():
    """
    مدير سياق للحصول على اتصال بقاعدة البيانات وإغلاقه تلقائياً.
    يستخدم sslmode=require للتوافق مع Heroku Postgres.
    """
    conn = None
    try:
        conn = psycopg2.connect(config.DATABASE_URL, sslmode='require')
        # تمكين الوضع التلقائي للـ commit على كل عملية (الأفضل استخدام المعاملات اليدوية عند الحاجة)
        conn.autocommit = False
        yield conn
    except psycopg2.Error as e:
        logger.error(f"خطأ في الاتصال بقاعدة البيانات: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """
    إنشاء جميع الجداول المطلوبة إذا لم تكن موجودة.
    تستدعى عند بدء تشغيل البوت.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # جدول المستخدمين
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    full_name VARCHAR(510),
                    attempts INTEGER DEFAULT 0,
                    total_videos INTEGER DEFAULT 0,
                    is_banned BOOLEAN DEFAULT FALSE,
                    ban_reason TEXT,
                    referral_points INTEGER DEFAULT 0,
                    referred_by BIGINT,
                    referral_code VARCHAR(50) UNIQUE,
                    subscription_type VARCHAR(50) DEFAULT 'free',
                    subscription_expiry TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_payments DECIMAL(10,2) DEFAULT 0.00,
                    language VARCHAR(10) DEFAULT 'ar',
                    preferred_dialect VARCHAR(50) DEFAULT 'fusha',
                    preferred_specialty VARCHAR(100),
                    education_level VARCHAR(100)
                )
            """)

            # جدول المدفوعات
            cur.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    amount DECIMAL(10,2) NOT NULL,
                    currency VARCHAR(10) DEFAULT 'USD',
                    payment_method VARCHAR(50) NOT NULL,
                    plan_type VARCHAR(50),
                    attempts_added INTEGER DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'pending',
                    receipt_file_id VARCHAR(255),
                    receipt_url TEXT,
                    admin_notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_by BIGINT,
                    transaction_id VARCHAR(255)
                )
            """)

            # جدول طلبات الفيديو
            cur.execute("""
                CREATE TABLE IF NOT EXISTS video_requests (
                    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    original_text TEXT,
                    text_length INTEGER,
                    file_name VARCHAR(255),
                    specialty VARCHAR(100),
                    sub_specialty VARCHAR(100),
                    dialect VARCHAR(50),
                    education_level VARCHAR(100),
                    title VARCHAR(500),
                    sections_count INTEGER,
                    total_duration_seconds INTEGER,
                    status VARCHAR(30) DEFAULT 'processing',
                    video_file_id VARCHAR(255),
                    video_file_path TEXT,
                    error_message TEXT,
                    ai_model_used VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)

            # جدول الإحالات
            cur.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id SERIAL PRIMARY KEY,
                    referrer_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    referred_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    points_awarded INTEGER DEFAULT 0,
                    awarded_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(referrer_id, referred_id)
                )
            """)

            # جدول المحاولات المجانية اليومية (لمنع التجاوز)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS daily_attempts (
                    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    date DATE NOT NULL DEFAULT CURRENT_DATE,
                    attempts_used INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, date)
                )
            """)

            # جدول رسائل البث (لتتبع البث)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS broadcasts (
                    broadcast_id SERIAL PRIMARY KEY,
                    sender_id BIGINT NOT NULL,
                    message_text TEXT,
                    media_file_id VARCHAR(255),
                    recipients_count INTEGER DEFAULT 0,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # إنشاء فهارس لتحسين الأداء
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_video_requests_user_id ON video_requests(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id ON referrals(referrer_id)")

            conn.commit()
            logger.info("✅ تم تهيئة قاعدة البيانات وإنشاء الجداول بنجاح")

# ==================== دوال المستخدمين ====================

def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """جلب بيانات مستخدم من قاعدة البيانات"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

def create_or_update_user(user_id: int, username: str = None, first_name: str = None,
                          last_name: str = None, referred_by: int = None) -> Dict[str, Any]:
    """
    إنشاء مستخدم جديد أو تحديث بياناته عند الدخول.
    إذا كان المستخدم جديداً وتم توفير referred_by، يتم تسجيل الإحالة.
    """
    full_name = f"{first_name or ''} {last_name or ''}".strip()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # التحقق من وجود المستخدم
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            existing = cur.fetchone()

            if existing:
                # تحديث البيانات
                cur.execute("""
                    UPDATE users SET
                        username = COALESCE(%s, username),
                        first_name = COALESCE(%s, first_name),
                        last_name = COALESCE(%s, last_name),
                        full_name = COALESCE(%s, full_name),
                        last_active = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                    RETURNING *
                """, (username, first_name, last_name, full_name, user_id))
                updated = cur.fetchone()
                conn.commit()
                logger.debug(f"تم تحديث بيانات المستخدم {user_id}")
                return dict(updated)

            # مستخدم جديد
            referral_code = f"REF{user_id}{uuid.uuid4().hex[:4].upper()}"
            attempts = config.FREE_ATTEMPTS

            cur.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, full_name,
                                 attempts, referral_code, referred_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (user_id, username, first_name, last_name, full_name, attempts, referral_code, referred_by))
            new_user = cur.fetchone()
            conn.commit()

            # إذا كان هناك إحالة، سجلها
            if referred_by:
                record_referral(referred_by, user_id)

            logger.info(f"✅ تم إنشاء مستخدم جديد: {user_id} مع {attempts} محاولات مجانية")
            return dict(new_user)

def update_last_active(user_id: int):
    """تحديث وقت آخر نشاط للمستخدم"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = %s", (user_id,))
            conn.commit()

def is_banned(user_id: int) -> Tuple[bool, Optional[str]]:
    """التحقق مما إذا كان المستخدم محظوراً، وإرجاع سبب الحظر"""
    user = get_user(user_id)
    if user and user.get('is_banned'):
        return True, user.get('ban_reason')
    return False, None

def ban_user(user_id: int, reason: str = None, banned_by: int = None) -> bool:
    """حظر مستخدم"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users SET is_banned = TRUE, ban_reason = %s
                WHERE user_id = %s
            """, (reason, user_id))
            affected = cur.rowcount
            conn.commit()
            if affected:
                logger.warning(f"تم حظر المستخدم {user_id}. السبب: {reason}")
            return affected > 0

def unban_user(user_id: int) -> bool:
    """رفع الحظر عن مستخدم"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users SET is_banned = FALSE, ban_reason = NULL
                WHERE user_id = %s
            """, (user_id,))
            affected = cur.rowcount
            conn.commit()
            return affected > 0

def decrement_attempts(user_id: int, amount: int = 1) -> bool:
    """خصم محاولة (أو أكثر) من رصيد المستخدم"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users SET attempts = attempts - %s
                WHERE user_id = %s AND attempts >= %s
                RETURNING attempts
            """, (amount, user_id, amount))
            result = cur.fetchone()
            if result:
                # تسجيل الاستخدام اليومي
                cur.execute("""
                    INSERT INTO daily_attempts (user_id, date, attempts_used)
                    VALUES (%s, CURRENT_DATE, %s)
                    ON CONFLICT (user_id, date) DO UPDATE SET attempts_used = daily_attempts.attempts_used + %s
                """, (user_id, amount, amount))
                conn.commit()
                logger.debug(f"تم خصم {amount} محاولة من المستخدم {user_id}. الرصيد المتبقي: {result[0]}")
                return True
            conn.rollback()
            return False

def add_attempts(user_id: int, amount: int, reason: str = None) -> int:
    """
    إضافة محاولات لرصيد المستخدم.
    ترجع الرصيد الجديد.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users SET attempts = attempts + %s
                WHERE user_id = %s
                RETURNING attempts
            """, (amount, user_id))
            result = cur.fetchone()
            conn.commit()
            new_balance = result[0] if result else 0
            logger.info(f"تمت إضافة {amount} محاولة للمستخدم {user_id}. السبب: {reason}. الرصيد الجديد: {new_balance}")
            return new_balance

def increment_total_videos(user_id: int) -> None:
    """زيادة عداد الفيديوهات المنتجة للمستخدم"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET total_videos = total_videos + 1 WHERE user_id = %s", (user_id,))
            conn.commit()

def get_user_attempts(user_id: int) -> int:
    """إرجاع رصيد المحاولات الحالي للمستخدم"""
    user = get_user(user_id)
    return user['attempts'] if user else 0

def check_and_update_subscription_status(user_id: int) -> str:
    """
    التحقق من حالة اشتراك المستخدم وتحديثها إذا انتهت.
    ترجع نوع الاشتراك الحالي.
    """
    user = get_user(user_id)
    if not user:
        return 'free'
    sub_type = user.get('subscription_type', 'free')
    expiry = user.get('subscription_expiry')
    if sub_type != 'free' and expiry and expiry < datetime.now():
        # انتهى الاشتراك
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users SET subscription_type = 'free', subscription_expiry = NULL
                    WHERE user_id = %s
                """, (user_id,))
                conn.commit()
        logger.info(f"انتهى اشتراك المستخدم {user_id}. تم إعادته إلى الخطة المجانية")
        return 'free'
    return sub_type

# ==================== دوال المدفوعات ====================

def create_payment(user_id: int, amount: float, payment_method: str, plan_type: str = None,
                   currency: str = "USD", receipt_file_id: str = None) -> uuid.UUID:
    """إنشاء سجل دفع جديد وإرجاع معرف الدفع"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO payments (user_id, amount, currency, payment_method, plan_type, receipt_file_id, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending')
                RETURNING payment_id
            """, (user_id, amount, currency, payment_method, plan_type, receipt_file_id))
            payment_id = cur.fetchone()[0]
            conn.commit()
            logger.info(f"تم إنشاء طلب دفع {payment_id} للمستخدم {user_id} بقيمة {amount} {currency}")
            return payment_id

def update_payment_status(payment_id: uuid.UUID, status: str, processed_by: int = None,
                          admin_notes: str = None, transaction_id: str = None) -> bool:
    """تحديث حالة الدفع"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE payments SET
                    status = %s,
                    processed_by = COALESCE(%s, processed_by),
                    admin_notes = COALESCE(%s, admin_notes),
                    transaction_id = COALESCE(%s, transaction_id),
                    updated_at = CURRENT_TIMESTAMP
                WHERE payment_id = %s
            """, (status, processed_by, admin_notes, transaction_id, payment_id))
            affected = cur.rowcount
            conn.commit()
            return affected > 0

def approve_payment(payment_id: uuid.UUID, processed_by: int) -> Tuple[bool, int, str]:
    """
    الموافقة على الدفع: تحديث حالة الدفع وإضافة المحاولات للمستخدم.
    ترجع (نجاح, user_id, plan_type)
    """
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # جلب تفاصيل الدفع
            cur.execute("SELECT * FROM payments WHERE payment_id = %s", (payment_id,))
            payment = cur.fetchone()
            if not payment:
                return False, 0, ""
            if payment['status'] != 'pending':
                return False, payment['user_id'], payment['plan_type']

            user_id = payment['user_id']
            plan_type = payment['plan_type']
            amount = payment['amount']
            attempts_to_add = config.ATTEMPTS_PER_PLAN.get(plan_type, 0)

            # تحديث حالة الدفع
            cur.execute("""
                UPDATE payments SET status = 'approved', processed_by = %s, updated_at = CURRENT_TIMESTAMP
                WHERE payment_id = %s
            """, (processed_by, payment_id))

            # إضافة المحاولات وتحديث الاشتراك
            if attempts_to_add > 0:
                cur.execute("UPDATE users SET attempts = attempts + %s WHERE user_id = %s", (attempts_to_add, user_id))

            # حساب تاريخ انتهاء الاشتراك
            if plan_type in ['1_month', '3_months', '12_months', 'unlimited']:
                if plan_type == '1_month':
                    expiry = datetime.now() + timedelta(days=30)
                elif plan_type == '3_months':
                    expiry = datetime.now() + timedelta(days=90)
                elif plan_type == '12_months':
                    expiry = datetime.now() + timedelta(days=365)
                elif plan_type == 'unlimited':
                    expiry = datetime.now() + timedelta(days=365 * 10)  # 10 سنوات
                else:
                    expiry = None

                if expiry:
                    cur.execute("""
                        UPDATE users SET
                            subscription_type = %s,
                            subscription_expiry = %s,
                            total_payments = total_payments + %s
                        WHERE user_id = %s
                    """, (plan_type, expiry, amount, user_id))
                else:
                    cur.execute("""
                        UPDATE users SET
                            subscription_type = %s,
                            total_payments = total_payments + %s
                        WHERE user_id = %s
                    """, (plan_type, amount, user_id))

            conn.commit()
            logger.info(f"✅ تمت الموافقة على الدفع {payment_id}. أضيفت {attempts_to_add} محاولة للمستخدم {user_id}")
            return True, user_id, plan_type

def get_pending_payments() -> List[Dict[str, Any]]:
    """جلب جميع طلبات الدفع المعلقة"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT p.*, u.username, u.first_name, u.last_name, u.full_name
                FROM payments p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.status = 'pending'
                ORDER BY p.created_at DESC
            """)
            return [dict(row) for row in cur.fetchall()]

def get_payment_by_id(payment_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    """جلب تفاصيل دفعة محددة"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM payments WHERE payment_id = %s", (payment_id,))
            row = cur.fetchone()
            return dict(row) if row else None

# ==================== دوال الإحالات ====================

def record_referral(referrer_id: int, referred_id: int, points: int = None) -> bool:
    """
    تسجيل إحالة جديدة ومنح النقاط للمُحيل.
    تمنع تسجيل الإحالة الذاتية أو المكررة.
    """
    if referrer_id == referred_id:
        logger.warning(f"محاولة إحالة ذاتية: {referrer_id}")
        return False

    if points is None:
        points = config.REFERRAL_POINTS_PER_REFERRAL

    with get_connection() as conn:
        with conn.cursor() as cur:
            # التحقق من عدم وجود إحالة سابقة
            cur.execute("SELECT id FROM referrals WHERE referrer_id = %s AND referred_id = %s",
                       (referrer_id, referred_id))
            if cur.fetchone():
                logger.warning(f"الإحالة موجودة مسبقاً: {referrer_id} -> {referred_id}")
                return False

            # إضافة سجل الإحالة
            cur.execute("""
                INSERT INTO referrals (referrer_id, referred_id, points_awarded, awarded_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            """, (referrer_id, referred_id, points))

            # إضافة النقاط للمُحيل
            cur.execute("""
                UPDATE users SET referral_points = referral_points + %s
                WHERE user_id = %s
            """, (points, referrer_id))

            # التحقق مما إذا كان المُحيل قد وصل للحد المطلوب للحصول على محاولة مجانية
            cur.execute("SELECT referral_points FROM users WHERE user_id = %s", (referrer_id,))
            result = cur.fetchone()
            if result:
                current_points = result[0]
                # منح محاولة مجانية عند الوصول للمضاعفات (كل 10 نقاط)
                # ولكن هنا نتحقق فقط من الوصول للحد الأساسي
                if current_points >= config.REFERRAL_POINTS_REQUIRED:
                    # نخصم النقاط المطلوبة ونضيف محاولة
                    cur.execute("""
                        UPDATE users SET
                            referral_points = referral_points - %s,
                            attempts = attempts + 1
                        WHERE user_id = %s
                    """, (config.REFERRAL_POINTS_REQUIRED, referrer_id))
                    logger.info(f"🎉 المستخدم {referrer_id} حصل على محاولة مجانية من نقاط الإحالة!")

            conn.commit()
            logger.info(f"✅ تم تسجيل إحالة: {referrer_id} أحال {referred_id} وحصل على {points} نقاط")
            return True

def get_referral_stats(user_id: int) -> Dict[str, Any]:
    """جلب إحصائيات الإحالة لمستخدم"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT COUNT(*) as total_referrals, COALESCE(SUM(points_awarded), 0) as total_points
                FROM referrals WHERE referrer_id = %s
            """, (user_id,))
            stats = dict(cur.fetchone())
            cur.execute("SELECT referral_points FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
            stats['current_points'] = user['referral_points'] if user else 0
            stats['points_needed_for_reward'] = max(0, config.REFERRAL_POINTS_REQUIRED - stats['current_points'])
            return stats

def get_referral_code(user_id: int) -> Optional[str]:
    """إرجاع كود الإحالة الخاص بالمستخدم"""
    user = get_user(user_id)
    return user.get('referral_code') if user else None

def get_user_by_referral_code(code: str) -> Optional[Dict[str, Any]]:
    """البحث عن مستخدم بواسطة كود الإحالة"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE referral_code = %s", (code,))
            row = cur.fetchone()
            return dict(row) if row else None

# ==================== دوال طلبات الفيديو ====================

def save_video_request(user_id: int, text: str = None, file_name: str = None,
                       specialty: str = None, sub_specialty: str = None,
                       dialect: str = None, education_level: str = None) -> uuid.UUID:
    """حفظ طلب فيديو جديد وإرجاع معرف الطلب"""
    text_length = len(text) if text else 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO video_requests
                (user_id, original_text, text_length, file_name, specialty, sub_specialty, dialect, education_level, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'processing')
                RETURNING request_id
            """, (user_id, text, text_length, file_name, specialty, sub_specialty, dialect, education_level))
            request_id = cur.fetchone()[0]
            conn.commit()
            return request_id

def update_video_request(request_id: uuid.UUID, status: str = None, title: str = None,
                         sections_count: int = None, total_duration: int = None,
                         video_file_id: str = None, video_file_path: str = None,
                         error_message: str = None, ai_model_used: str = None) -> None:
    """تحديث حالة طلب الفيديو عند اكتماله أو فشله"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            fields = []
            values = []
            if status is not None:
                fields.append("status = %s")
                values.append(status)
            if title is not None:
                fields.append("title = %s")
                values.append(title)
            if sections_count is not None:
                fields.append("sections_count = %s")
                values.append(sections_count)
            if total_duration is not None:
                fields.append("total_duration_seconds = %s")
                values.append(total_duration)
            if video_file_id is not None:
                fields.append("video_file_id = %s")
                values.append(video_file_id)
            if video_file_path is not None:
                fields.append("video_file_path = %s")
                values.append(video_file_path)
            if error_message is not None:
                fields.append("error_message = %s")
                values.append(error_message)
            if ai_model_used is not None:
                fields.append("ai_model_used = %s")
                values.append(ai_model_used)

            if status == 'completed' or status == 'failed':
                fields.append("completed_at = CURRENT_TIMESTAMP")
            else:
                fields.append("completed_at = NULL")

            if not fields:
                return

            query = f"UPDATE video_requests SET {', '.join(fields)} WHERE request_id = %s"
            values.append(request_id)
            cur.execute(query, values)
            conn.commit()

# ==================== دوال الإدارة والإحصائيات ====================

def get_stats() -> Dict[str, Any]:
    """جلب إحصائيات عامة عن البوت"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            stats = {}
            cur.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users WHERE created_at::date = CURRENT_DATE")
            stats['new_users_today'] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM users WHERE is_banned = TRUE")
            stats['banned_users'] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM video_requests WHERE status = 'completed'")
            stats['total_videos'] = cur.fetchone()[0]
            cur.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'approved'")
            stats['total_revenue'] = float(cur.fetchone()[0] or 0)
            cur.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
            stats['pending_payments'] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM referrals")
            stats['total_referrals'] = cur.fetchone()[0]
            return stats

def get_all_users_paginated(page: int = 1, per_page: int = 10, search: str = None) -> Tuple[List[Dict], int]:
    """جلب قائمة المستخدمين مع التصفح والبحث"""
    offset = (page - 1) * per_page
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            if search:
                search_term = f"%{search}%"
                cur.execute("""
                    SELECT COUNT(*) FROM users
                    WHERE user_id::text LIKE %s OR username ILIKE %s OR first_name ILIKE %s OR full_name ILIKE %s
                """, (search_term, search_term, search_term, search_term))
                total = cur.fetchone()[0]
                cur.execute("""
                    SELECT * FROM users
                    WHERE user_id::text LIKE %s OR username ILIKE %s OR first_name ILIKE %s OR full_name ILIKE %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (search_term, search_term, search_term, search_term, per_page, offset))
            else:
                cur.execute("SELECT COUNT(*) FROM users")
                total = cur.fetchone()[0]
                cur.execute("""
                    SELECT * FROM users
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, (per_page, offset))
            users = [dict(row) for row in cur.fetchall()]
            return users, total

def get_video_requests_by_user(user_id: int, limit: int = 10) -> List[Dict]:
    """جلب آخر طلبات الفيديو لمستخدم"""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT * FROM video_requests WHERE user_id = %s
                ORDER BY created_at DESC LIMIT %s
            """, (user_id, limit))
            return [dict(row) for row in cur.fetchall()]

def delete_old_temp_files(days: int = 1):
    """تنظيف سجلات الملفات المؤقتة القديمة (يمكن استخدامها مع cron)"""
    # هذه الدالة لا تحذف الملفات الفعلية بل تنظف قاعدة البيانات فقط
    cutoff = datetime.now() - timedelta(days=days)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM video_requests
                WHERE status = 'completed' AND created_at < %s AND video_file_path IS NOT NULL
            """, (cutoff,))
            deleted = cur.rowcount
            conn.commit()
            logger.info(f"تم حذف {deleted} سجل فيديو قديم من قاعدة البيانات")
            return deleted

# ==================== دوال البث ====================

def save_broadcast(sender_id: int, message_text: str, media_file_id: str = None) -> int:
    """حفظ سجل رسالة بث"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO broadcasts (sender_id, message_text, media_file_id)
                VALUES (%s, %s, %s)
                RETURNING broadcast_id
            """, (sender_id, message_text, media_file_id))
            bid = cur.fetchone()[0]
            conn.commit()
            return bid

def update_broadcast_recipients(broadcast_id: int, count: int):
    """تحديث عدد مستلمي البث"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE broadcasts SET recipients_count = %s WHERE broadcast_id = %s",
                       (count, broadcast_id))
            conn.commit()

# ==================== دوال مساعدة ====================

def get_daily_attempts_used(user_id: int, date: datetime = None) -> int:
    """معرفة عدد المحاولات المستخدمة اليوم"""
    if date is None:
        date = datetime.now().date()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT attempts_used FROM daily_attempts WHERE user_id = %s AND date = %s",
                       (user_id, date))
            row = cur.fetchone()
            return row[0] if row else 0

# تشغيل تهيئة قاعدة البيانات عند استيراد الملف
if __name__ == "__main__":
    init_db()
    print("تم تهيئة قاعدة البيانات بنجاح!")
