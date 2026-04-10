# -*- coding: utf-8 -*-
import asyncio
import os
import logging
import tempfile
import time
import re
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    filters,
    ContextTypes,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    OWNER_ID,
    FREE_ATTEMPTS,
    TEMP_DIR,
)
from database import (
    init_db,
    get_user,
    create_user,
    is_banned,
    decrement_attempts,
    add_attempts,
    increment_total_videos,
    save_video_request,
    update_video_request,
    record_referral,
    get_referral_stats,
)
from ai_analyzer import (
    analyze_lecture,
    extract_full_text_from_pdf,
    fetch_image_for_keyword,
)
from voice_generator import generate_sections_audio
from video_creator import create_video_from_sections, estimate_encoding_seconds
from admin_panel import (
    is_owner,
    handle_admin_command,
    handle_admin_callback,
    handle_admin_text_search,
    handle_add_attempts,
    handle_set_attempts,
    handle_ban,
    handle_unban,
    handle_broadcast,
    handle_approve_payment_command,
)
from payment_handler import (
    get_payment_keyboard,
    send_payment_required_message,
    handle_pay_stars,
    handle_pay_mastercard,
    handle_pay_crypto,
    handle_payment_sent,
    handle_pre_checkout,
    handle_successful_payment,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# دالة تنظيف النص من null bytes والأحرف غير المرغوبة
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_text(text: str) -> str:
    """تنظيف النص من جميع الأحرف غير المرغوبة"""
    if not text:
        return ""
    # إزالة null bytes
    text = text.replace('\x00', '').replace('\0', '')
    # إزالة أحرف التحكم
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # استبدال المسافات المتعددة بمسافة واحدة
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# بقية المتغيرات والدوال
# ═══════════════════════════════════════════════════════════════════════════════

user_states: dict[int, dict] = {}
_Q_SEM = asyncio.Semaphore(2)
_active_jobs: dict[int, str] = {}
_active_tasks: dict[int, asyncio.Task] = {}
_cancel_flags: dict[int, asyncio.Event] = {}

CANCEL_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("❌ إلغاء المعالجة", callback_data="cancel_job")
]])

DIALECT_KEYBOARD = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("🇮🇶 عراقي", callback_data="dial_iraq"),
        InlineKeyboardButton("🇪🇬 مصري", callback_data="dial_egypt"),
        InlineKeyboardButton("🇸🇾 شامي", callback_data="dial_syria"),
    ],
    [
        InlineKeyboardButton("🇸🇦 خليجي", callback_data="dial_gulf"),
        InlineKeyboardButton("📚 فصحى", callback_data="dial_msa"),
    ],
])

DIALECT_NAMES = {
    "iraq": "🇮🇶 عراقي",
    "egypt": "🇪🇬 مصري",
    "syria": "🇸🇾 شامي",
    "gulf": "🇸🇦 خليجي",
    "msa": "📚 فصحى",
}


def main_keyboard():
    return ReplyKeyboardMarkup(
        [["📤 رفع محاضرة", "📊 رصيدي"], ["🔗 رابط الإحالة", "❓ مساعدة"]],
        resize_keyboard=True,
    )


def _pbar(pct: int, width: int = 12) -> str:
    filled = int(width * pct / 100)
    return "▓" * filled + "░" * (width - filled)


def _fmt_elapsed(sec: float) -> str:
    if sec < 60:
        return f"{int(sec)} ثانية"
    return f"{int(sec // 60)} دقيقة {int(sec % 60)} ثانية"


async def _safe_edit(msg, text: str, parse_mode: str = "Markdown", reply_markup=None):
    try:
        await msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        pass


async def ensure_user(update: Update) -> dict | None:
    tg = update.effective_user
    user = get_user(tg.id)
    if not user:
        ref_by = user_states.get(tg.id, {}).get("ref_by")
        user = create_user(tg.id, tg.username or "", tg.full_name or "", ref_by)
        if ref_by and ref_by != tg.id:
            res = record_referral(ref_by, tg.id)
            if not res.get("already_referred"):
                try:
                    ref_user = get_user(ref_by)
                    name = ref_user.get("full_name", "صديق") if ref_user else "صديق"
                    await update.effective_message.reply_text(f"✅ انضممت عبر رابط إحالة {name}!")
                except Exception:
                    pass
    if user.get("is_banned"):
        await update.effective_message.reply_text("⛔ أنت محظور من استخدام البوت.")
        return None
    return user


# ═══════════════════════════════════════════════════════════════════════════════
# دوال البوت الأساسية
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    uid = update.effective_user.id

    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0][4:])
            if ref_id != uid:
                user_states.setdefault(uid, {})["ref_by"] = ref_id
        except ValueError:
            pass

    user = await ensure_user(update)
    if not user:
        return

    user_states.pop(uid, None)
    name = update.effective_user.first_name

    await update.message.reply_text(
        f"👋 أهلاً *{name}*!\n\n"
        "🎓 أنا *بوت المحاضرات الذكي* - أحوّل محاضرتك إلى فيديو تعليمي احترافي!\n\n"
        "📥 *ما يمكنك إرساله:*\n"
        "• ملف PDF 📄\n"
        "• ملف نصي TXT 📃\n"
        "• نص المحاضرة مباشرة ✍️\n\n"
        "🌍 اختر لهجة الشرح (عراقي، مصري، خليجي...)\n"
        "🎬 استلم فيديو كامل مع شرح وصور وصوت\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية\n\n"
        "⬇️ ابدأ الآن - أرسل المحاضرة!",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ أرسل ملف PDF أو نص المحاضرة\n"
        "2️⃣ اختر لهجة الشرح\n"
        "3️⃣ انتظر - البوت سيحلل المحاضرة ويصنع الفيديو\n"
        "4️⃣ استلم الفيديو التعليمي الكامل\n\n"
        "🔗 */referral* - رابط إحالة لكسب محاولات مجانية\n"
        "/cancel - إلغاء العملية",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_states.pop(uid, None)
    ev = _cancel_flags.get(uid)
    if ev and not ev.is_set():
        ev.set()
        await update.message.reply_text("⛔ تم إلغاء المعالجة.", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("✅ لا توجد عملية جارية.", reply_markup=main_keyboard())


async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return
    await update.message.reply_text(
        f"💳 *رصيدك*\n\n"
        f"🎬 المحاولات المتبقية: *{user['attempts_left']}*\n"
        f"📊 إجمالي الفيديوهات: {user['total_videos']}\n\n"
        "للحصول على محاولات إضافية:",
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard(user["user_id"]),
    )


async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return
    uid = update.effective_user.id
    stats = get_referral_stats(uid)
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"

    await update.message.reply_text(
        f"🔗 *رابط الإحالة الخاص بك*\n\n"
        f"`{ref_link}`\n\n"
        f"👥 أصدقاء دعوتهم: *{stats['total_referrals']}*\n"
        f"⭐ نقاطك: *{stats['current_points']}*\n\n"
        "كل 10 أشخاص = محاولة مجانية!\n"
        "شارك الرابط مع أصدقائك 🎉",
        parse_mode="Markdown",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# استلام المحتوى - مع تنظيف النص
# ═══════════════════════════════════════════════════════════════════════════════

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return

    uid = update.effective_user.id
    msg = update.message

    if is_owner(uid):
        consumed = await handle_admin_text_search(update, context)
        if consumed:
            return

    if msg.text:
        text = msg.text.strip()
        if text == "📤 رفع محاضرة":
            await msg.reply_text("📤 أرسل ملف PDF أو اكتب نص المحاضرة مباشرة:", reply_markup=ReplyKeyboardRemove())
            return
        if text == "📊 رصيدي":
            await my_balance(update, context)
            return
        if text == "🔗 رابط الإحالة":
            await referral_cmd(update, context)
            return
        if text == "❓ مساعدة":
            await help_cmd(update, context)
            return

    if uid in _active_jobs:
        await msg.reply_text("⏳ محاضرتك قيد المعالجة، انتظر قليلاً...")
        return

    lecture_text = None
    filename = "lecture"

    if msg.document:
        fname = msg.document.file_name or ""
        ext = fname.lower().split(".")[-1] if "." in fname else ""
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ أرسل ملف PDF أو TXT فقط.")
            return
        await context.bot.send_chat_action(uid, "upload_document")
        wait = await msg.reply_text(f"📥 *تم استلام الملف!* جاري القراءة...\n📄 `{fname}`", parse_mode="Markdown")
        try:
            file = await msg.document.get_file()
            raw = await file.download_as_bytearray()
            if ext == "pdf":
                lecture_text = await extract_full_text_from_pdf(bytes(raw))
                filename = fname.replace(".pdf", "")
            else:
                lecture_text = raw.decode("utf-8", errors="ignore")
                filename = fname.replace(".txt", "")
            
            # ═══════════════════════════════════════════════════════════════════
            # تنظيف النص فوراً
            # ═══════════════════════════════════════════════════════════════════
            lecture_text = _clean_text(lecture_text)
            
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ خطأ في قراءة الملف: {e}")
            return

    elif msg.text and len(msg.text.strip()) >= 200:
        # ═══════════════════════════════════════════════════════════════════════
        # تنظيف النص فوراً
        # ═══════════════════════════════════════════════════════════════════════
        lecture_text = _clean_text(msg.text.strip())

    elif msg.text and len(msg.text.strip()) < 200:
        await msg.reply_text("⚠️ النص قصير جداً.\n\nأرسل:\n• ملف PDF 📄\n• ملف TXT 📃\n• أو نص المحاضرة مباشرة (200 حرف على الأقل)")
        return

    else:
        await msg.reply_text("⚠️ أرسل ملف PDF أو نص المحاضرة.")
        return

    if not lecture_text or len(lecture_text.strip()) < 50:
        await msg.reply_text("❌ لم أتمكن من استخراج نص من الملف.")
        return

    if user["attempts_left"] <= 0:
        await send_payment_required_message(update, context)
        return

    user_states[uid] = {
        "state": "awaiting_dialect",
        "text": lecture_text,
        "filename": filename,
    }

    words = len(lecture_text.split())
    await msg.reply_text(
        f"✅ *تم استلام المحاضرة!*\n\n📝 عدد الكلمات: {words:,}\n\nاختر لهجة الشرح:",
        parse_mode="Markdown",
        reply_markup=DIALECT_KEYBOARD,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# باقي الدوال (callback_handler, _process_lecture, admin_cmd, main)
# ═══════════════════════════════════════════════════════════════════════════════
# [تظل كما هي بدون تغيير]

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... نفس الكود السابق ...
    pass

async def _process_lecture(uid, text, filename, dialect, prog_msg, context):
    # ... نفس الكود السابق ...
    pass

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    await handle_admin_command(update, context)

async def main():
    # ... نفس الكود السابق ...
    pass

if __name__ == "__main__":
    asyncio.run(main())
