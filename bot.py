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


# ═══════════════════════════════════════════════════════════════════════════════
# استلام المحتوى
# ═══════════════════════════════════════════════════════════════════════════════

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return

    uid = update.effective_user.id
    msg = update.message

    if is_owner(uid):
        if await handle_admin_text_search(update, context):
            return

    if msg.text:
        text = msg.text.strip()
        if text == "📤 رفع محاضرة":
            await msg.reply_text("📤 أرسل ملف PDF أو اكتب نص المحاضرة:", reply_markup=ReplyKeyboardRemove())
            return
        if text == "📊 رصيدي":
            await msg.reply_text(f"💳 رصيدك: {user['attempts_left']} محاولات")
            return
        if text == "🔗 رابط الإحالة":
            stats = get_referral_stats(uid)
            bot = await context.bot.get_me()
            ref_link = f"https://t.me/{bot.username}?start=ref_{uid}"
            await msg.reply_text(f"🔗 رابطك:\n{ref_link}\n👥 المدعوين: {stats['total_referrals']}")
            return
        if text == "❓ مساعدة":
            await msg.reply_text("📖 أرسل PDF أو نص طويل (200 حرف على الأقل)")
            return

    if uid in _active_jobs:
        await msg.reply_text("⏳ لديك محاضرة قيد المعالجة...")
        return

    lecture_text = None
    filename = "lecture"

    if msg.document:
        fname = msg.document.file_name or ""
        ext = fname.split(".")[-1].lower() if "." in fname else ""
        
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ PDF أو TXT فقط")
            return

        wait = await msg.reply_text("📥 جاري قراءة الملف...")
        
        try:
            file = await msg.document.get_file()
            raw = await file.download_as_bytearray()
            
            if ext == "pdf":
                lecture_text = await extract_full_text_from_pdf(bytes(raw))
                filename = fname.replace(".pdf", "")
            else:
                lecture_text = raw.decode("utf-8", errors="ignore")
                filename = fname.replace(".txt", "")
            
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ خطأ: {str(e)[:100]}")
            return

    elif msg.text and len(msg.text.strip()) >= 200:
        lecture_text = msg.text.strip()

    else:
        await msg.reply_text("⚠️ أرسل PDF أو نص (200 حرف على الأقل)")
        return

    lecture_text = clean_text(lecture_text)
    
    if not lecture_text or len(lecture_text) < 50:
        await msg.reply_text("❌ نص غير كاف")
        return

    if user["attempts_left"] <= 0:
        await send_payment_required_message(update, context)
        return

    # حفظ النص في الحالة
    user_states[uid] = {
        "state": "awaiting_type",
        "text": lecture_text,
        "filename": filename
    }

    words = len(lecture_text.split())
    detected = _detect_type(lecture_text)
    detected_name = LECTURE_TYPES.get(detected, '📖 أخرى')

    await msg.reply_text(
        f"✅ *تم استلام المحاضرة!*\n\n"
        f"📝 عدد الكلمات: {words:,}\n"
        f"🔍 النوع المقترح: {detected_name}\n\n"
        f"👆 *اختر نوع المحاضرة:*",
        parse_mode="Markdown",
        reply_markup=get_type_keyboard()
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Callback Handler - معالجة جميع الاختيارات
# ═══════════════════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id

    if data.startswith("admin_"):
        await handle_admin_callback(update, context)
        return

    await q.answer()

    # Payment callbacks
    if data in ("pay_stars", "pay_mastercard", "pay_crypto"):
        if data == "pay_stars":
            await handle_pay_stars(update, context)
        elif data == "pay_mastercard":
            await handle_pay_mastercard(update, context)
        else:
            await handle_pay_crypto(update, context)
        return

    if data.startswith("sent_"):
        await handle_payment_sent(update, context)
        return

    if data == "cancel_job":
        ev = _cancel_flags.get(uid)
        if ev and not ev.is_set():
            ev.set()
            await q.edit_message_text("⛔ تم الإلغاء")
        return

    # ═══════════════════════════════════════════════════════════════════════════
    # اختيار نوع المحاضرة
    # ═══════════════════════════════════════════════════════════════════════════
    if data.startswith("type_"):
        main_type = data[5:]
        state = user_states.get(uid, {})
        
        if state.get("state") != "awaiting_type":
            await q.edit_message_text("⚠️ انتهت الجلسة، أرسل المحاضرة مرة أخرى")
            return
        
        state["main_type"] = main_type
        state["state"] = "awaiting_subtype"
        user_states[uid] = state
        
        type_name = LECTURE_TYPES.get(main_type, main_type)
        
        # إذا كان النوع له تخصصات فرعية
        if main_type in SUB_TYPES:
            await q.edit_message_text(
                f"📚 النوع: *{type_name}*\n\n"
                f"👆 اختر التخصص الفرعي:",
                parse_mode="Markdown",
                reply_markup=get_subtype_keyboard(main_type)
            )
        else:
            # لا يوجد تخصصات فرعية، ننتقل للمرحلة الدراسية
            state["subtype"] = "none"
            state["state"] = "awaiting_level"
            user_states[uid] = state
            
            await q.edit_message_text(
                f"📚 النوع: *{type_name}*\n\n"
                f"👆 اختر المرحلة الدراسية:",
                parse_mode="Markdown",
                reply_markup=get_level_keyboard()
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # اختيار التخصص الفرعي
    # ═══════════════════════════════════════════════════════════════════════════
    elif data.startswith("subtype_"):
        parts = data.split("_")
        main_type = parts[1]
        subtype = "_".join(parts[2:]) if len(parts) > 2 else "none"
        
        state = user_states.get(uid, {})
        if state.get("state") != "awaiting_subtype":
            await q.edit_message_text("⚠️ انتهت الجلسة")
            return
        
        state["subtype"] = subtype
        state["state"] = "awaiting_level"
        user_states[uid] = state
        
        type_name = LECTURE_TYPES.get(main_type, main_type)
        sub_name = "بدون تخصص"
        if main_type in SUB_TYPES and subtype in SUB_TYPES[main_type]:
            sub_name = SUB_TYPES[main_type][subtype]
        
        await q.edit_message_text(
            f"📚 النوع: *{type_name}*\n"
            f"🔬 التخصص: *{sub_name}*\n\n"
            f"👆 اختر المرحلة الدراسية:",
            parse_mode="Markdown",
            reply_markup=get_level_keyboard()
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # اختيار المرحلة الدراسية
    # ═══════════════════════════════════════════════════════════════════════════
    elif data.startswith("level_"):
        level = data[6:]
        state = user_states.get(uid, {})
        
        if state.get("state") != "awaiting_level":
            await q.edit_message_text("⚠️ انتهت الجلسة")
            return
        
        state["level"] = level
        state["state"] = "awaiting_dialect"
        user_states[uid] = state
        
        level_name = EDUCATION_LEVELS.get(level, level)
        
        await q.edit_message_text(
            f"✅ *تم تحديد جميع الإعدادات!*\n\n"
            f"📚 النوع: {LECTURE_TYPES.get(state.get('main_type', 'other'), 'أخرى')}\n"
            f"🏫 المرحلة: {level_name}\n\n"
            f"🌍 اختر لهجة الشرح:",
            parse_mode="Markdown",
            reply_markup=DIALECT_KEYBOARD
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # اختيار اللهجة وبدء المعالجة
    # ═══════════════════════════════════════════════════════════════════════════
    elif data.startswith("dial_"):
        dialect = data[5:]
        state = user_states.get(uid, {})
        
        if state.get("state") != "awaiting_dialect":
            await q.edit_message_text("⚠️ انتهت الجلسة")
            return

        user = get_user(uid)
        if not user or user["attempts_left"] <= 0:
            await q.edit_message_text("❌ لا محاولات")
            return

        # تجهيز معلومات المعلم
        main_type = state.get("main_type", "other")
        teacher_info = TEACHER_CHARACTERS.get(main_type, TEACHER_CHARACTERS["other"])
        teacher_name = teacher_info["name"]
        teacher_outfit = teacher_info["outfit"]
        
        # تعديل اسم المعلم حسب المرحلة
        level = state.get("level", "university")
        if level == "elementary":
            teacher_name = "معلم " + teacher_name
        elif level == "middle":
            teacher_name = "أستاذ " + teacher_name
        
        dial_name = DIALECT_NAMES.get(dialect, dialect)
        
        prog_msg = await q.edit_message_text(
            f"🎬 *بدأت المعالجة!*\n"
            f"👨‍🏫 المعلم: {teacher_name}\n"
            f"🌍 اللهجة: {dial_name}\n\n"
            f"{_pbar(0)} 0%\n"
            f"🔍 جاري التحليل...",
            parse_mode="Markdown"
        )

        text = state["text"]
        filename = state.get("filename", "lecture")
        
        # حفظ معلومات إضافية للفيديو
        lecture_meta = {
            "main_type": main_type,
            "subtype": state.get("subtype", "none"),
            "level": level,
            "teacher_name": teacher_name,
            "teacher_outfit": teacher_outfit,
        }
        
        user_states.pop(uid, None)

        task = asyncio.create_task(
            _process_lecture(uid, text, filename, dialect, lecture_meta, prog_msg, context)
        )
        _active_tasks[uid] = task
        return

    # ═══════════════════════════════════════════════════════════════════════════
    # عرض الإحالة
    # ═══════════════════════════════════════════════════════════════════════════
    elif data == "show_referral":
        stats = get_referral_stats(uid)
        bot = await context.bot.get_me()
        ref_link = f"https://t.me/{bot.username}?start=ref_{uid}"
        await q.message.reply_text(
            f"🔗 *رابط الإحالة*\n`{ref_link}`\n👥 {stats['total_referrals']} شخص",
            parse_mode="Markdown"
        )
        return


# ═══════════════════════════════════════════════════════════════════════════════
# دالة المعالجة الرئيسية
# ═══════════════════════════════════════════════════════════════════════════════

async def _process_lecture(uid, text, filename, dialect, lecture_meta, prog_msg, context):
    _active_jobs[uid] = "processing"
    cancel_ev = asyncio.Event()
    _cancel_flags[uid] = cancel_ev
    
    req_id = save_video_request(
        uid, "text", dialect,
        lecture_meta["main_type"],
        lecture_meta["subtype"],
        lecture_meta["level"],
        lecture_meta["teacher_name"],
        lecture_meta["teacher_outfit"]
    )
    
    t_start = time.time()
    video_path = None
    pdf_path = None

    async def upd(pct, label):
        elapsed = time.time() - t_start
        await _safe_edit(
            prog_msg,
            f"⏳ *جاري المعالجة...*\n\n{_pbar(pct)} *{pct}%*\n{label}\n\n⏱️ {_fmt_elapsed(elapsed)}",
            reply_markup=CANCEL_KB
        )

    try:
        # ───────────────────────────────────────────────────────────────────────────
        # المرحلة 1: التحليل
        # ───────────────────────────────────────────────────────────────────────────
        await upd(5, "🔍 جاري قراءة النص وتنظيفه...")
        await asyncio.sleep(0.5)
        
        await upd(8, "📊 تحليل نوع المحاضرة وتحديد التخصص...")
        await asyncio.sleep(0.5)
        
        await upd(12, "🔑 استخراج الكلمات المفتاحية من النص...")
        await asyncio.sleep(0.5)
        
        await upd(15, "🧠 جاري الاتصال بالذكاء الاصطناعي لتحليل المحاضرة...")
        
        lecture_data = await _run_or_cancel(uid, analyze_lecture(text, dialect))
        
        # إضافة معلومات المعلم إلى بيانات المحاضرة
        lecture_data["teacher_name"] = lecture_meta["teacher_name"]
        lecture_data["teacher_outfit"] = lecture_meta["teacher_outfit"]
        lecture_data["main_type"] = lecture_meta["main_type"]
        lecture_data["education_level"] = lecture_meta["level"]

        sections = lecture_data.get("sections", [])
        if not sections:
            raise RuntimeError("لم يتم استخراج أقسام")
        
        n_sec = len(sections)
        is_eng = lecture_data.get("is_english", False)
        
        await upd(25, "✅ تم تحليل المحاضرة بنجاح!")
        await asyncio.sleep(0.5)
        await upd(28, f"📚 تم تقسيم المحاضرة إلى {n_sec} أقسام تعليمية")
        await asyncio.sleep(0.5)
        await upd(30, f"📝 العنوان: {lecture_data.get('title', 'المحاضرة')[:40]}...")

        # ───────────────────────────────────────────────────────────────────────────
        # المرحلة 2: جلب الصور
        # ───────────────────────────────────────────────────────────────────────────
        await upd(33, "🖼️ جاري تجهيز الصور التوضيحية...")
        await asyncio.sleep(0.5)
        
        total_images = len(sections)
        for i, s in enumerate(sections):
            if not s.get("_image_bytes"):
                kw = s.get("keywords", ["مفهوم"])[:4]
                section_title = s.get("title", f"القسم {i+1}")
                
                # تحديث المستخدم بحالة جلب الصورة
                pct = 35 + int((i / total_images) * 20)
                await upd(pct, f"🖼️ جاري جلب الصورة للقسم {i+1}/{total_images}: {section_title[:30]}...")
                
                s["_image_bytes"] = await fetch_image_for_keyword(
                    " ".join(kw), 
                    section_title, 
                    lecture_data.get("lecture_type", "other"),
                    is_eng
                )
                
                if s["_image_bytes"]:
                    await upd(pct, f"✅ تم جلب الصورة للقسم {i+1}/{total_images}")
                else:
                    await upd(pct, f"⚠️ استخدام صورة احتياطية للقسم {i+1}/{total_images}")
                
                await asyncio.sleep(0.3)
        
        await upd(55, "✅ تم جلب جميع الصور التوضيحية بنجاح!")
        await asyncio.sleep(0.5)

        # ───────────────────────────────────────────────────────────────────────────
        # المرحلة 3: توليد الصوت
        # ───────────────────────────────────────────────────────────────────────────
        await upd(58, "🎤 جاري الاتصال بخدمة تحويل النص إلى صوت...")
        await asyncio.sleep(0.5)
        
        await upd(62, "🎙️ جاري توليد الصوت للقسم الأول...")
        await asyncio.sleep(0.5)
        
        voice_res = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
        audio_results = voice_res["results"]
        
        # حساب المدة الإجمالية
        total_duration = sum(r.get("duration", 0) for r in audio_results if r.get("ok"))
        total_min = int(total_duration // 60)
        total_sec = int(total_duration % 60)
        
        await upd(72, "✅ تم توليد الصوت لجميع الأقسام!")
        await asyncio.sleep(0.5)
        await upd(75, f"⏱️ المدة الإجمالية للصوت: {total_min}:{total_sec:02d}")

        # ───────────────────────────────────────────────────────────────────────────
        # المرحلة 4: إنتاج الفيديو
        # ───────────────────────────────────────────────────────────────────────────
        await upd(78, "🎬 جاري إنتاج الفيديو...")
        await asyncio.sleep(0.5)
        
        await upd(82, "🎨 إنشاء شرائح المقدمة والعنوان...")
        await asyncio.sleep(0.5)
        
        await upd(86, "📝 بناء شرائح الأقسام وإضافة الصور...")
        await asyncio.sleep(0.5)
        
        await upd(90, "🎬 جاري تشفير الفيديو (قد يستغرق دقيقة)...")
        
        fd, video_path = tempfile.mkstemp(prefix=f"vid_{uid}_", suffix=".mp4", dir=TEMP_DIR)
        os.close(fd)

        total_secs = await create_video_from_sections(
            sections=sections,
            audio_results=audio_results,
            lecture_data=lecture_data,
            output_path=video_path,
            dialect=dialect
        )
        
        vid_min = int(total_secs // 60)
        vid_sec = int(total_secs % 60)
        
        await upd(95, f"✅ اكتمل الفيديو! المدة: {vid_min}:{vid_sec:02d}")

        # ───────────────────────────────────────────────────────────────────────────
        # المرحلة 5: إرسال الفيديو
        # ───────────────────────────────────────────────────────────────────────────
        await upd(97, "📤 جاري إرسال الفيديو...")
        
        decrement_attempts(uid)
        increment_total_videos(uid)
        update_video_request(req_id, "done", video_path, pdf_path)

        title = lecture_data.get("title", filename)
        remaining = get_user(uid)["attempts_left"]

        caption = f"🎬 *{title}*\n\n📚 الأقسام: {n_sec}\n⏱️ المدة: {vid_min}:{vid_sec:02d}\n💳 المحاولات: {remaining}"

        with open(video_path, "rb") as vf:
            await context.bot.send_video(
                chat_id=uid, video=vf, caption=caption,
                parse_mode="Markdown", supports_streaming=True
            )

        await upd(100, "✅ تم الإرسال بنجاح!")
        await asyncio.sleep(0.5)
        
        await prog_msg.delete()
        await context.bot.send_message(
            uid, 
            "✅ *تم بنجاح!* 🎓\n\n"
            f"📹 الفيديو جاهز للمشاهدة\n"
            f"📚 عدد الأقسام: {n_sec}\n"
            f"⏱️ المدة: {vid_min}:{vid_sec:02d}\n"
            f"💳 المحاولات المتبقية: {remaining}",
            parse_mode="Markdown", 
            reply_markup=main_keyboard()
        )

    except asyncio.CancelledError:
        update_video_request(req_id, "cancelled")
        await context.bot.send_message(uid, "⛔ تم إلغاء المعالجة", reply_markup=main_keyboard())

    except Exception as e:
        update_video_request(req_id, "failed")
        logger.error(f"Error: {e}")
        await _safe_edit(prog_msg, f"❌ خطأ: {str(e)[:200]}")
        await context.bot.send_message(uid, "❌ حدث خطأ، حاول مرة أخرى", reply_markup=main_keyboard())

    finally:
        _active_jobs.pop(uid, None)
        _active_tasks.pop(uid, None)
        _cancel_flags.pop(uid, None)
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except:
                pass
        if pdf_path and os.path.exists(pdf_path):
            try:
                os.remove(pdf_path)
            except:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
# ═══════════════════════════════════════════════════════════════════════════════
# أوامر البوت الأساسية
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    uid = update.effective_user.id

    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0][4:])
            if ref_id != uid:
                user_states.setdefault(uid, {})["ref_by"] = ref_id
        except:
            pass

    user = await ensure_user(update)
    if not user:
        return

    await update.message.reply_text(
        f"👋 أهلاً *{update.effective_user.first_name}*!\n\n"
        f"🎓 أنا *بوت المحاضرات الذكي*\n"
        f"📥 أرسل لي ملف PDF أو نص المحاضرة\n"
        f"🎬 سأحوله إلى فيديو تعليمي احترافي\n"
        f"👨‍🏫 مع شخصية كرتونية تناسب تخصصك!\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ أرسل ملف PDF أو نص المحاضرة\n"
        "2️⃣ اختر نوع المحاضرة\n"
        "3️⃣ اختر التخصص الفرعي\n"
        "4️⃣ اختر المرحلة الدراسية\n"
        "5️⃣ اختر لهجة الشرح\n"
        "6️⃣ انتظر الفيديو!\n\n"
        "/cancel - إلغاء المعالجة",
        parse_mode="Markdown"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    ev = _cancel_flags.get(uid)
    if ev and not ev.is_set():
        ev.set()
        await update.message.reply_text("⛔ تم إلغاء المعالجة.", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("✅ لا توجد عملية جارية.", reply_markup=main_keyboard())


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    await handle_admin_command(update, context)


# ═══════════════════════════════════════════════════════════════════════════════
# تشغيل البوت
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    init_db()
    logger.info("🤖 Bot starting...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("admin", admin_cmd))

    app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, 
        receive_content
    ))

    logger.info("✅ Ready")

    webhook_url = os.getenv("WEBHOOK_URL", "")
    
    if webhook_url and webhook_url.strip():
        webhook_url = webhook_url.rstrip("/")
        await app.bot.set_webhook(url=f"{webhook_url}/telegram", drop_pending_updates=True)
        logger.info(f"✅ Webhook mode: {webhook_url}")
        
        # استمرار التشغيل بدون polling
        await asyncio.Event().wait()
    else:
        logger.info("🔄 Polling mode...")
        await app.updater.start_polling(drop_pending_updates=True)
        await asyncio.Event().wait()
        await app.updater.stop()


if __name__ == "__main__":
    asyncio.run(main())
