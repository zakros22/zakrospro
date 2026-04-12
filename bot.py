# -*- coding: utf-8 -*-
import asyncio
import os
import logging
import tempfile
import time
import re
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, PreCheckoutQueryHandler,
    filters, ContextTypes
)

from config import (
    TELEGRAM_BOT_TOKEN, OWNER_ID, FREE_ATTEMPTS, TEMP_DIR
)
from database import (
    init_db, get_user, create_user, is_banned,
    decrement_attempts, add_attempts, increment_total_videos,
    save_video_request, update_video_request,
    record_referral, get_referral_stats
)
from ai_analyzer import (
    analyze_lecture, extract_full_text_from_pdf,
    fetch_image_for_keyword, clean_text, _detect_type
)
from voice_generator import generate_sections_audio
from video_creator import create_video_from_sections, estimate_encoding_seconds
from pdf_generator import create_pdf_summary
from admin_panel import (
    is_owner, handle_admin_command, handle_admin_callback,
    handle_admin_text_search, handle_add_attempts, handle_set_attempts,
    handle_ban, handle_unban, handle_broadcast, handle_approve_payment_command
)
from payment_handler import (
    get_payment_keyboard, send_payment_required_message,
    handle_pay_stars, handle_pay_mastercard, handle_pay_crypto,
    handle_payment_sent, handle_pre_checkout, handle_successful_payment
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# أنواع المحاضرات الرئيسية
# ═══════════════════════════════════════════════════════════════════════════════

LECTURE_TYPES = {
    "medicine": "🩺 طب",
    "engineering": "⚙️ هندسة",
    "math": "📐 رياضيات",
    "physics": "⚡ فيزياء",
    "chemistry": "🧪 كيمياء",
    "biology": "🧬 أحياء",
    "history": "📜 تاريخ",
    "literature": "📚 أدب",
    "philosophy": "🤔 فلسفة",
    "law": "⚖️ قانون",
    "economics": "📊 اقتصاد",
    "islamic": "🕌 علوم إسلامية",
    "computer": "💻 حاسوب",
    "psychology": "🧠 علم نفس",
    "other": "📖 أخرى"
}

# التخصصات الفرعية
SUB_TYPES = {
    "medicine": {
        "anatomy": "🦴 تشريح",
        "physiology": "❤️ فسيولوجي",
        "pathology": "🔬 مرضي",
        "pharmacology": "💊 أدوية",
        "surgery": "🔪 جراحة",
    },
    "engineering": {
        "civil": "🏗️ مدنية",
        "mechanical": "🔧 ميكانيكية",
        "electrical": "⚡ كهربائية",
        "aerospace": "🚀 فضائية",
        "chemical": "🧪 كيميائية",
        "computer": "💻 حاسوب",
    },
    "islamic": {
        "aqeedah": "📿 عقيدة",
        "fiqh": "📜 فقه",
        "seerah": "🕋 سيرة",
        "tafseer": "📖 تفسير",
        "hadith": "📚 حديث",
    },
    "math": {
        "algebra": "🧮 جبر",
        "geometry": "📐 هندسة",
        "calculus": "📈 تفاضل وتكامل",
        "statistics": "📊 إحصاء",
    },
    "physics": {
        "mechanics": "⚙️ ميكانيكا",
        "electricity": "⚡ كهرباء",
        "optics": "🔆 بصريات",
        "nuclear": "☢️ نووية",
        "quantum": "🔬 كموم",
    },
    "chemistry": {
        "organic": "🌿 عضوية",
        "inorganic": "🧪 غير عضوية",
        "physical": "⚗️ فيزيائية",
        "analytical": "🔬 تحليلية",
    },
    "biology": {
        "botany": "🌱 نبات",
        "zoology": "🐾 حيوان",
        "microbiology": "🦠 أحياء دقيقة",
        "genetics": "🧬 وراثة",
    },
    "history": {
        "ancient": "🏛️ قديم",
        "medieval": "🏰 وسيط",
        "modern": "🏭 حديث",
        "islamic": "🕌 إسلامي",
    },
}

# المراحل الدراسية
EDUCATION_LEVELS = {
    "elementary": "🏫 ابتدائي",
    "middle": "📚 متوسط",
    "high": "📝 إعدادي/ثانوي",
    "university": "🎓 جامعي",
    "postgrad": "🔬 دراسات عليا",
}

# شخصيات المعلمين حسب النوع (تؤثر على الملابس)
TEACHER_CHARACTERS = {
    "medicine": {"name": "دكتور حكيم", "outfit": "doctor"},
    "engineering": {"name": "مهندس ماهر", "outfit": "engineer"},
    "math": {"name": "أستاذ أرقام", "outfit": "teacher"},
    "physics": {"name": "فيزيائي", "outfit": "scientist"},
    "chemistry": {"name": "كيميائي", "outfit": "scientist"},
    "biology": {"name": "عالم أحياء", "outfit": "scientist"},
    "history": {"name": "مؤرخ", "outfit": "historian"},
    "literature": {"name": "أديب", "outfit": "writer"},
    "philosophy": {"name": "فيلسوف", "outfit": "thinker"},
    "law": {"name": "قانوني", "outfit": "lawyer"},
    "economics": {"name": "خبير اقتصادي", "outfit": "business"},
    "islamic": {"name": "شيخ", "outfit": "sheikh"},
    "computer": {"name": "مبرمج", "outfit": "developer"},
    "psychology": {"name": "عالم نفس", "outfit": "psychologist"},
    "other": {"name": "معلم", "outfit": "teacher"},
}

# ═══════════════════════════════════════════════════════════════════════════════
# المتغيرات العامة
# ═══════════════════════════════════════════════════════════════════════════════

user_states = {}
_active_jobs = {}
_active_tasks = {}
_cancel_flags = {}

CANCEL_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("❌ إلغاء المعالجة", callback_data="cancel_job")
]])

DIALECT_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🇮🇶 عراقي", callback_data="dial_iraq"),
        InlineKeyboardButton("🇪🇬 مصري", callback_data="dial_egypt"),
    ],
    [
        InlineKeyboardButton("🇸🇾 شامي", callback_data="dial_syria"),
        InlineKeyboardButton("🇸🇦 خليجي", callback_data="dial_gulf"),
    ],
    [
        InlineKeyboardButton("📚 فصحى", callback_data="dial_msa"),
    ],
])

DIALECT_NAMES = {
    "iraq": "🇮🇶 عراقي", "egypt": "🇪🇬 مصري",
    "syria": "🇸🇾 شامي", "gulf": "🇸🇦 خليجي", "msa": "📚 فصحى"
}


def main_keyboard():
    return ReplyKeyboardMarkup(
        [["📤 رفع محاضرة", "📊 رصيدي"], ["🔗 رابط الإحالة", "❓ مساعدة"]],
        resize_keyboard=True
    )


def _pbar(pct, width=12):
    filled = int(width * pct / 100)
    return "▓" * filled + "░" * (width - filled)


def _fmt_elapsed(sec):
    if sec < 60:
        return f"{int(sec)} ثانية"
    return f"{int(sec // 60)} دقيقة {int(sec % 60)} ثانية"


async def _safe_edit(msg, text, parse_mode="Markdown", reply_markup=None):
    try:
        await msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except:
        pass


async def _run_or_cancel(uid, coro):
    ev = _cancel_flags.get(uid)
    if ev is None or ev.is_set():
        raise asyncio.CancelledError()

    coro_task = asyncio.ensure_future(coro)
    cancel_task = asyncio.ensure_future(ev.wait())
    
    try:
        done, pending = await asyncio.wait(
            [coro_task, cancel_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        for p in pending:
            p.cancel()
        if cancel_task in done:
            raise asyncio.CancelledError()
        return coro_task.result()
    except asyncio.CancelledError:
        coro_task.cancel()
        raise


async def ensure_user(update: Update):
    tg = update.effective_user
    user = get_user(tg.id)
    if not user:
        ref_by = user_states.get(tg.id, {}).get("ref_by")
        user = create_user(tg.id, tg.username or "", tg.full_name or "", ref_by)
        if ref_by and ref_by != tg.id:
            record_referral(ref_by, tg.id)
    if user.get("is_banned"):
        await update.effective_message.reply_text("⛔ أنت محظور من استخدام البوت.")
        return None
    return user


# ═══════════════════════════════════════════════════════════════════════════════
# لوحات اختيار نوع المحاضرة والتخصص
# ═══════════════════════════════════════════════════════════════════════════════

def get_type_keyboard():
    """لوحة اختيار نوع المحاضرة الرئيسي"""
    keyboard = []
    row = []
    for i, (key, name) in enumerate(LECTURE_TYPES.items()):
        row.append(InlineKeyboardButton(name, callback_data=f"type_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


def get_subtype_keyboard(main_type: str):
    """لوحة اختيار التخصص الفرعي"""
    subs = SUB_TYPES.get(main_type, {})
    keyboard = []
    row = []
    for key, name in subs.items():
        row.append(InlineKeyboardButton(name, callback_data=f"subtype_{main_type}_{key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    # إضافة زر "بدون تخصص"
    keyboard.append([InlineKeyboardButton("⏭️ تخطي (بدون تخصص)", callback_data=f"subtype_{main_type}_none")])
    return InlineKeyboardMarkup(keyboard)


def get_level_keyboard():
    """لوحة اختيار المرحلة الدراسية"""
    keyboard = []
    for key, name in EDUCATION_LEVELS.items():
        keyboard.append([InlineKeyboardButton(name, callback_data=f"level_{key}")])
    return InlineKeyboardMarkup(keyboard)
