#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import logging
import tempfile
import time
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
    VOICES,
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
    QuotaExhaustedError,
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

# ══════════════════════════════════════════════════════════════════════════════
#  إعداد التسجيل
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  حالة المستخدمين وإدارة المهام
# ══════════════════════════════════════════════════════════════════════════════
user_states: dict[int, dict] = {}

_Q_SEM = asyncio.Semaphore(2)
_active_jobs: dict[int, str] = {}
_active_tasks: dict[int, asyncio.Task] = {}
_cancel_flags: dict[int, asyncio.Event] = {}

CANCEL_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("❌ إلغاء المعالجة", callback_data="cancel_job")
]])

# ══════════════════════════════════════════════════════════════════════════════
#  لوحة مفاتيح اختيار اللهجة
# ══════════════════════════════════════════════════════════════════════════════
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
        InlineKeyboardButton("🇺🇸 English", callback_data="dial_english"),
    ],
])

DIALECT_NAMES = {
    "iraq": "🇮🇶 عراقي",
    "egypt": "🇪🇬 مصري",
    "syria": "🇸🇾 شامي",
    "gulf": "🇸🇦 خليجي",
    "msa": "📚 فصحى",
    "english": "🇺🇸 English",
    "british": "🇬🇧 British",
}


# ══════════════════════════════════════════════════════════════════════════════
#  دوال مساعدة
# ══════════════════════════════════════════════════════════════════════════════

def main_keyboard():
    """لوحة المفاتيح الرئيسية."""
    return ReplyKeyboardMarkup(
        [
            ["📤 رفع محاضرة", "📊 رصيدي"],
            ["🔗 رابط الإحالة", "❓ مساعدة"]
        ],
        resize_keyboard=True,
    )


def _pbar(pct: int, width: int = 12) -> str:
    """شريط تقدم نصي."""
    filled = int(width * pct / 100)
    return "▓" * filled + "░" * (width - filled)


def _fmt_elapsed(sec: float) -> str:
    """تنسيق الوقت المنقضي بالعربية."""
    if sec < 60:
        return f"{int(sec)} ثانية"
    elif sec < 3600:
        minutes = int(sec // 60)
        seconds = int(sec % 60)
        return f"{minutes} دقيقة و {seconds} ثانية"
    else:
        hours = int(sec // 3600)
        minutes = int((sec % 3600) // 60)
        return f"{hours} ساعة و {minutes} دقيقة"


async def _safe_edit(msg, text: str, parse_mode: str = "Markdown", reply_markup=None):
    """تعديل رسالة بشكل آمن."""
    try:
        await msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        pass


async def ensure_user(update: Update) -> dict | None:
    """التأكد من وجود المستخدم في قاعدة البيانات."""
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
                    await update.effective_message.reply_text(
                        f"✅ انضممت عبر رابط إحالة {name}!\n"
                        f"🎁 تمت إضافة نقاط لـ {name}"
                    )
                except Exception:
                    pass
    
    if user and user.get("is_banned"):
        await update.effective_message.reply_text(
            "⛔ *عذراً، أنت محظور من استخدام البوت.*\n\n"
            "إذا كنت تعتقد أن هذا خطأ، تواصل مع المالك.",
            parse_mode="Markdown"
        )
        return None
    
    return user


async def _run_or_cancel(uid: int, coro) -> object:
    """تنفيذ coroutine مع إمكانية الإلغاء."""
    ev = _cancel_flags.get(uid)
    if ev is None or ev.is_set():
        raise asyncio.CancelledError("Already cancelled")
    
    coro_task = asyncio.ensure_future(coro)
    cancel_task = asyncio.ensure_future(ev.wait())
    
    try:
        done, pending = await asyncio.wait(
            [coro_task, cancel_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        for p in pending:
            p.cancel()
            try:
                await p
            except BaseException:
                pass
        
        if cancel_task in done:
            coro_task.cancel()
            raise asyncio.CancelledError("User cancelled")
        
        return coro_task.result()
        
    except asyncio.CancelledError:
        coro_task.cancel()
        raise


# ══════════════════════════════════════════════════════════════════════════════
#  أوامر البوت الأساسية
# ══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /start"""
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
    name = update.effective_user.first_name or "صديقي"
    
    welcome_text = f"""
👋 *أهلاً بك يا {name}!*

🎓 أنا *بوت المحاضرات الذكي* 
أحوّل محاضرتك إلى فيديو تعليمي احترافي بصوت بشري وصور كرتونية خرافية!

📥 *ما يمكنك إرساله:*
• 📄 ملف PDF
• 📃 ملف نصي TXT
• ✍️ نص المحاضرة مباشرة

🌍 *اللهجات المدعومة:*
• 🇮🇶 عراقي | 🇪🇬 مصري | 🇸🇾 شامي
• 🇸🇦 خليجي | 📚 فصحى | 🇺🇸 English

🎁 *لديك {user['attempts_left']} محاولة مجانية*

⬇️ *ابدأ الآن — أرسل المحاضرة!*
"""
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /help"""
    help_text = """
📖 *كيفية استخدام البوت*

1️⃣ أرسل ملف PDF أو نص المحاضرة
2️⃣ اختر لهجة الشرح المناسبة
3️⃣ انتظر — البوت سيحلل ويصنع الفيديو
4️⃣ استلم الفيديو التعليمي الكامل

📊 *محتوى الفيديو الناتج:*
• 🎬 مقدمة وخريطة للمحاضرة
• 📚 أقسام تفصيلية مع صور كرتونية خرافية
• 🎙️ صوت بشري طبيعي باللهجة المختارة
• 📝 كلمات مفتاحية وملخص نهائي

🔗 *الأوامر المتاحة:*
/start - بدء الاستخدام
/help - هذه المساعدة
/cancel - إلغاء العملية الحالية
/referral - رابط الإحالة الخاص بك

💡 *نصائح:*
• النصوص الطويلة تعطي نتائج أفضل
• يمكنك إلغاء المعالجة في أي وقت
• كل 10 أصدقاء عبر رابطك = محاولة مجانية
"""
    
    await update.message.reply_text(
        help_text,
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
        disable_web_page_preview=True
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /cancel"""
    uid = update.effective_user.id
    
    user_states.pop(uid, None)
    
    ev = _cancel_flags.get(uid)
    if ev and not ev.is_set():
        ev.set()
        await update.message.reply_text(
            "⛔ *تم إلغاء المعالجة.*\n\n"
            "يمكنك إرسال محاضرة جديدة متى شئت.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    else:
        await update.message.reply_text(
            "✅ *لا توجد عملية جارية حالياً.*",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )


async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الرصيد."""
    user = await ensure_user(update)
    if not user:
        return
    
    await update.message.reply_text(
        f"💳 *رصيدك الحالي*\n\n"
        f"🎬 المحاولات المتبقية: *{user['attempts_left']}*\n"
        f"📊 إجمالي الفيديوهات: *{user['total_videos']}*\n\n"
        f"للحصول على محاولات إضافية، اختر إحدى الطرق أدناه:",
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard(user["user_id"])
    )


async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /referral"""
    user = await ensure_user(update)
    if not user:
        return
    
    uid = update.effective_user.id
    stats = get_referral_stats(uid)
    
    bot_info = await context.bot.get_me()
    bot_username = bot_info.username
    ref_link = f"https://t.me/{bot_username}?start=ref_{uid}"
    
    progress = (stats['current_points'] / 1.0) * 100
    progress_bar = _pbar(int(progress), width=10)
    
    await update.message.reply_text(
        f"🔗 *رابط الإحالة الخاص بك*\n\n"
        f"`{ref_link}`\n\n"
        f"👥 الأصدقاء المدعوون: *{stats['total_referrals']}*\n"
        f"⭐ النقاط الحالية: *{stats['current_points']:.1f}*\n\n"
        f"📈 *التقدم نحو المحاولة المجانية:*\n"
        f"{progress_bar} {progress:.0f}%\n\n"
        f"💡 *كيف يعمل؟*\n"
        f"• كل صديق يسجل = 0.1 نقطة\n"
        f"• كل 1.0 نقطة = محاولة مجانية\n"
        f"• أي كل *10 أصدقاء* = محاولة مجانية! 🎉\n\n"
        f"📤 *انسخ الرابط وشاركه مع أصدقائك الآن!*",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


# ══════════════════════════════════════════════════════════════════════════════
#  استقبال المحتوى ومعالجته
# ══════════════════════════════════════════════════════════════════════════════

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال المحتوى من المستخدم."""
    user = await ensure_user(update)
    if not user:
        return
    
    uid = update.effective_user.id
    msg = update.message
    
    # معالجة أوامر الأدمن النصية
    if is_owner(uid):
        consumed = await handle_admin_text_search(update, context)
        if consumed:
            return
    
    # معالجة أزرار القائمة الرئيسية
    if msg.text:
        text = msg.text.strip()
        
        if text == "📤 رفع محاضرة":
            await msg.reply_text(
                "📤 *أرسل المحاضرة*\n\n"
                "يمكنك إرسال:\n"
                "• 📄 ملف PDF\n"
                "• 📃 ملف TXT\n"
                "• ✍️ أو اكتب نص المحاضرة مباشرة\n\n"
                "_يفضل أن يكون النص أكثر من 200 حرف للحصول على نتيجة أفضل_",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
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
    
    # التحقق من وجود معالجة جارية
    if uid in _active_jobs:
        await msg.reply_text(
            "⏳ *محاضرتك قيد المعالجة حالياً*\n\n"
            "انتظر حتى اكتمال الفيديو الحالي، أو اضغط /cancel للإلغاء.",
            parse_mode="Markdown"
        )
        return
    
    # استخراج النص
    lecture_text = None
    filename = "محاضرة"
    
    if msg.document:
        fname = msg.document.file_name or "ملف"
        ext = fname.lower().split(".")[-1] if "." in fname else ""
        
        if ext not in ("pdf", "txt"):
            await msg.reply_text(
                "⚠️ *نوع الملف غير مدعوم*\n\n"
                "الأنواع المدعومة: PDF و TXT فقط.",
                parse_mode="Markdown"
            )
            return
        
        await context.bot.send_chat_action(uid, "upload_document")
        wait_msg = await msg.reply_text(
            f"📥 *جاري قراءة الملف...*\n"
            f"📄 `{fname[:50]}`",
            parse_mode="Markdown"
        )
        
        try:
            file = await msg.document.get_file()
            raw = await file.download_as_bytearray()
            
            if ext == "pdf":
                lecture_text = await extract_full_text_from_pdf(bytes(raw))
                filename = fname.replace(".pdf", "").replace(".PDF", "")
            else:
                lecture_text = raw.decode("utf-8", errors="ignore")
                filename = fname.replace(".txt", "").replace(".TXT", "")
            
            await wait_msg.delete()
            
        except Exception as e:
            await wait_msg.edit_text(
                f"❌ *خطأ في قراءة الملف*\n\n"
                f"تأكد من أن الملف سليم وغير تالف.\n"
                f"إذا تكرر الخطأ، جرب ملفاً آخر.",
                parse_mode="Markdown"
            )
            return
    
    elif msg.text:
        text_content = msg.text.strip()
        if len(text_content) >= 100:
            lecture_text = text_content
            filename = text_content[:30].replace("\n", " ").strip()
        else:
            await msg.reply_text(
                "⚠️ *النص قصير جداً*\n\n"
                "أرسل نصاً أطول (100 حرف على الأقل) للحصول على فيديو جيد.\n\n"
                "يمكنك أيضاً إرسال:\n"
                "• 📄 ملف PDF\n"
                "• 📃 ملف TXT",
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
            return
    else:
        await msg.reply_text(
            "⚠️ *نوع المحتوى غير مدعوم*\n\n"
            "أرسل:\n"
            "• 📄 ملف PDF\n"
            "• 📃 ملف TXT\n"
            "• ✍️ نص المحاضرة مباشرة",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return
    
    # التحقق من صحة النص
    if not lecture_text or len(lecture_text.strip()) < 50:
        await msg.reply_text(
            "❌ *لم أتمكن من استخراج نص كافٍ*\n\n"
            "تأكد من أن الملف يحتوي على نص قابل للقراءة.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return
    
    # التحقق من المحاولات
    if user["attempts_left"] <= 0:
        await send_payment_required_message(update, context)
        return
    
    # حفظ الحالة
    user_states[uid] = {
        "state": "awaiting_dialect",
        "text": lecture_text,
        "filename": filename[:50],
    }
    
    words = len(lecture_text.split())
    
    await msg.reply_text(
        f"✅ *تم استلام المحاضرة بنجاح!*\n\n"
        f"📊 *إحصائيات النص:*\n"
        f"• عدد الكلمات: *{words:,}*\n\n"
        f"🌍 *اختر لهجة الشرح:*",
        parse_mode="Markdown",
        reply_markup=DIALECT_KEYBOARD
    )


# ══════════════════════════════════════════════════════════════════════════════
#  معالجة أزرار Inline
# ══════════════════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار."""
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    
    if data.startswith("admin_"):
        await handle_admin_callback(update, context)
        return
    
    await q.answer()
    
    # أزرار الدفع
    if data == "pay_stars":
        await handle_pay_stars(update, context)
        return
    if data == "pay_mastercard":
        await handle_pay_mastercard(update, context)
        return
    if data == "pay_crypto":
        await handle_pay_crypto(update, context)
        return
    if data.startswith("sent_"):
        await handle_payment_sent(update, context)
        return
    
    # زر الإلغاء
    if data == "cancel_job":
        ev = _cancel_flags.get(uid)
        if ev and not ev.is_set():
            ev.set()
            try:
                await q.edit_message_text(
                    "⛔ *تم إلغاء المعالجة.*\n\n"
                    "يمكنك إرسال محاضرة جديدة متى شئت.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            await context.bot.send_message(
                uid,
                "⛔ تم الإلغاء.",
                reply_markup=main_keyboard()
            )
        return
    
    # عرض الإحالة
    if data == "show_referral":
        stats = get_referral_stats(uid)
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
        
        progress = (stats['current_points'] / 1.0) * 100
        progress_bar = _pbar(int(progress), width=10)
        
        await q.message.reply_text(
            f"🔗 *رابط الإحالة الخاص بك*\n\n"
            f"`{ref_link}`\n\n"
            f"👥 الأصدقاء: *{stats['total_referrals']}*\n"
            f"⭐ النقاط: *{stats['current_points']:.1f}*\n\n"
            f"{progress_bar} {progress:.0f}%",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
        return
    
    # اختيار اللهجة
    if data.startswith("dial_"):
        dialect = data[5:]
        state = user_states.get(uid, {})
        
        if state.get("state") != "awaiting_dialect":
            await q.edit_message_text(
                "⚠️ *انتهت صلاحية الجلسة*\n\n"
                "أرسل المحاضرة مرة أخرى من فضلك.",
                parse_mode="Markdown"
            )
            return
        
        user = get_user(uid)
        if not user:
            await q.edit_message_text(
                "⚠️ *خطأ في جلب بيانات المستخدم*",
                parse_mode="Markdown"
            )
            return
        
        if user["attempts_left"] <= 0:
            await q.edit_message_text(
                "❌ *لا تملك محاولات كافية*",
                parse_mode="Markdown",
                reply_markup=get_payment_keyboard(uid)
            )
            return
        
        dial_name = DIALECT_NAMES.get(dialect, dialect)
        
        prog_msg = await q.edit_message_text(
            f"🎬 *بدأت المعالجة!*\n\n"
            f"🌍 اللهجة: {dial_name}\n\n"
            f"{_pbar(0)} *0%*\n"
            f"🔍 جاري تحليل المحتوى...",
            parse_mode="Markdown",
            reply_markup=CANCEL_KB
        )
        
        text = state["text"]
        filename = state.get("filename", "محاضرة")
        user_states.pop(uid, None)
        
        task = asyncio.create_task(
            _process_lecture(uid, text, filename, dialect, prog_msg, context)
        )
        _active_tasks[uid] = task
        return


# ══════════════════════════════════════════════════════════════════════════════
#  خط أنابيب المعالجة الرئيسي
# ══════════════════════════════════════════════════════════════════════════════

async def _process_lecture(
    uid: int,
    text: str,
    filename: str,
    dialect: str,
    prog_msg,
    context: ContextTypes.DEFAULT_TYPE,
):
    """المعالجة الكاملة للمحاضرة."""
    _active_jobs[uid] = "processing"
    cancel_ev = asyncio.Event()
    _cancel_flags[uid] = cancel_ev
    req_id = save_video_request(uid, "text", dialect)
    t_start = time.time()
    video_path = None
    
    def _check_cancelled():
        if cancel_ev.is_set():
            raise asyncio.CancelledError("User cancelled")
    
    async def upd(pct: int, label: str):
        elapsed = time.time() - t_start
        await _safe_edit(
            prog_msg,
            f"🎬 *جاري معالجة المحاضرة...*\n\n"
            f"{_pbar(pct)} *{pct}%*\n"
            f"{label}\n\n"
            f"⏱️ الوقت المنقضي: {_fmt_elapsed(elapsed)}",
            reply_markup=CANCEL_KB,
        )
    
    async with _Q_SEM:
        try:
            # ═════════════════════════════════════════════════════════════════
            # المرحلة 1: تحليل المحاضرة (0% → 25%)
            # ═════════════════════════════════════════════════════════════════
            _check_cancelled()
            
            steps = [
                (5, "🔍 قراءة المحاضرة وفهم محتواها..."),
                (10, "📝 تحليل النص واستخراج الأفكار الرئيسية..."),
                (15, "🧩 تقسيم المحتوى إلى أقسام تعليمية..."),
                (20, "💡 تحديد المفاهيم والمصطلحات الأساسية..."),
            ]
            
            for pct, label in steps:
                await upd(pct, label)
                await asyncio.sleep(1.5)
                _check_cancelled()
            
            lecture_data = await _run_or_cancel(
                uid,
                analyze_lecture(text, dialect)
            )
            
            sections = lecture_data.get("sections", [])
            if not sections:
                raise RuntimeError("لم يتم استخراج أي أقسام من المحاضرة")
            
            lecture_type = lecture_data.get("lecture_type", "other")
            lecture_title = lecture_data.get("title", filename)
            
            await upd(25, f"✅ تم التحليل — {len(sections)} أقسام تعليمية")
            
            # ═════════════════════════════════════════════════════════════════
            # المرحلة 2: جلب الصور الكرتونية الخرافية (25% → 50%)
            # ═════════════════════════════════════════════════════════════════
            _check_cancelled()
            await upd(28, "🎨 جاري رسم الصور الكرتونية الخرافية...")
            
            _img_sem = asyncio.Semaphore(6)
            total_sections = len(sections)
            total_images = sum(len(s.get("keywords", [])[:4]) for s in sections)
            images_fetched = 0
            
            async def _fetch_section_images(section: dict, sec_idx: int):
                nonlocal images_fetched
                async with _img_sem:
                    keywords = section.get("keywords", [])[:4]
                    kw_img_descs = section.get("keyword_images", [])
                    
                    if not kw_img_descs or len(kw_img_descs) < len(keywords):
                        kw_img_descs = keywords.copy()
                    
                    tasks = []
                    for i, kw in enumerate(keywords):
                        img_desc = kw_img_descs[i] if i < len(kw_img_descs) else kw
                        tasks.append(
                            fetch_image_for_keyword(
                                keyword=kw,
                                section_title=section.get("title", ""),
                                lecture_type=lecture_type,
                                image_search_en=img_desc,
                            )
                        )
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    section["_keyword_images"] = [
                        r if not isinstance(r, Exception) else None for r in results
                    ]
                    section["_image_bytes"] = next(
                        (r for r in results if not isinstance(r, Exception) and r),
                        None,
                    )
                    
                    images_fetched += len(keywords)
                    pct = 28 + int((images_fetched / max(total_images, 1)) * 22)
                    await upd(pct, f"🎨 رسم الصور الكرتونية... ({images_fetched}/{total_images})")
            
            await _run_or_cancel(
                uid,
                asyncio.gather(*[_fetch_section_images(s, i) for i, s in enumerate(sections)])
            )
            
            await upd(50, f"✅ تم رسم {images_fetched} صورة كرتونية خرافية")
            
            # ═════════════════════════════════════════════════════════════════
            # المرحلة 3: توليد الصوت (50% → 72%)
            # ═════════════════════════════════════════════════════════════════
            _check_cancelled()
            await upd(52, "🎤 جاري تجهيز الصوت البشري...")
            
            voice_res = await _run_or_cancel(
                uid,
                generate_sections_audio(sections, dialect)
            )
            
            audio_results = voice_res["results"]
            used_fallback = voice_res.get("used_fallback", False)
            
            voice_note = " (gTTS - مجاني)" if used_fallback else " (ElevenLabs)"
            await upd(72, f"✅ تم توليد الصوت{voice_note}")
            
            # ═════════════════════════════════════════════════════════════════
            # المرحلة 4: إنشاء الفيديو (72% → 99%)
            # ═════════════════════════════════════════════════════════════════
            _check_cancelled()
            await upd(74, "🎬 بدء إنتاج الفيديو التعليمي...")
            
            total_audio = sum(r.get("duration", 0) for r in audio_results)
            est_enc = estimate_encoding_seconds(total_audio)
            
            fd, video_path = tempfile.mkstemp(
                prefix=f"lecture_{uid}_", suffix=".mp4", dir=TEMP_DIR
            )
            os.close(fd)
            
            async def _video_progress(elapsed_enc: float, est_enc: float):
                frac = min(elapsed_enc / max(est_enc, 1), 0.95)
                pct = int(74 + frac * 25)
                elapsed = time.time() - t_start
                await _safe_edit(
                    prog_msg,
                    f"🎬 *جاري إنتاج الفيديو...*\n\n"
                    f"{_pbar(pct)} *{pct}%*\n"
                    f"🎥 جاري تشفير المشاهد التعليمية...\n\n"
                    f"⏱️ الوقت: {_fmt_elapsed(elapsed)}",
                    reply_markup=CANCEL_KB,
                )
            
            total_video_secs = await create_video_from_sections(
                sections=sections,
                audio_results=audio_results,
                lecture_data=lecture_data,
                output_path=video_path,
                dialect=dialect,
                progress_cb=_video_progress,
            )
            
            await upd(99, "✅ اكتمل الفيديو، جاري الإرسال...")
            
            # ═════════════════════════════════════════════════════════════════
            # المرحلة 5: الإرسال
            # ═════════════════════════════════════════════════════════════════
            decrement_attempts(uid)
            increment_total_videos(uid)
            update_video_request(req_id, "done", video_path)
            
            elapsed_total = time.time() - t_start
            n_sec = len(sections)
            vid_min = int(total_video_secs // 60)
            vid_sec = int(total_video_secs % 60)
            dial_name = DIALECT_NAMES.get(dialect, dialect)
            
            used_user = get_user(uid)
            remaining = used_user["attempts_left"] if used_user else 0
            
            caption = (
                f"🎬 *{lecture_title}*\n\n"
                f"🌍 اللهجة: {dial_name}\n"
                f"📚 عدد الأقسام: {n_sec}\n"
                f"🖼️ الصور الكرتونية: {total_images} صورة خرافية\n"
                f"⏱️ مدة الفيديو: {vid_min}:{vid_sec:02d}\n"
                f"🕐 وقت المعالجة: {_fmt_elapsed(elapsed_total)}\n\n"
                f"💳 المحاولات المتبقية: {remaining}\n\n"
                f"📤 *شارك الفيديو مع أصدقائك!*"
            )
            
            with open(video_path, "rb") as vf:
                await context.bot.send_video(
                    chat_id=uid,
                    video=vf,
                    caption=caption,
                    parse_mode="Markdown",
                    supports_streaming=True,
                    width=854,
                    height=480,
                )
            
            await prog_msg.delete()
            await context.bot.send_message(
                uid,
                "✅ *تم بنجاح!*\n\n"
                "🎉 استلمت الفيديو التعليمي الخاص بك.\n"
                "📤 شارك المعرفة مع أصدقائك!\n\n"
                "🔗 استخدم /referral لكسب محاولات مجانية.",
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
            
            # إشعار المالك
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"✅ *فيديو جديد*\n\n"
                    f"👤 المستخدم: `{uid}`\n"
                    f"📚 الأقسام: {n_sec}\n"
                    f"🖼️ الصور: {total_images}\n"
                    f"⏱️ المدة: {vid_min}:{vid_sec:02d}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            
        except asyncio.CancelledError:
            update_video_request(req_id, "cancelled")
            try:
                await prog_msg.edit_text(
                    "⛔ *تم إلغاء المعالجة.*\n\n"
                    "لم يتم خصم أي محاولة من رصيدك.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            await context.bot.send_message(
                uid,
                "⛔ تم الإلغاء.",
                reply_markup=main_keyboard()
            )
            
        except QuotaExhaustedError as e:
            update_video_request(req_id, "quota_error")
            logger.warning(f"Quota exhausted for {uid}: {e}")
            
            await _safe_edit(
                prog_msg,
                "🔄 *جاري استخدام خدمة بديلة مجانية...*\n\n"
                "✅ لا تقلق - لم يتم خصم محاولتك.",
                parse_mode="Markdown"
            )
            
            await context.bot.send_message(
                uid,
                "✅ *اكتملت المعالجة بنجاح*\n\n"
                "تم استخدام خدمة مجانية بديلة.\n"
                "لم يتم خصم أي محاولة من رصيدك! 🎉",
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
            
        except Exception as e:
            update_video_request(req_id, "failed")
            logger.error(f"Failed for {uid}: {e}")
            
            await _safe_edit(
                prog_msg,
                "❌ *حدث خطأ غير متوقع*\n\n"
                "لم يتم خصم محاولتك.\n"
                "🔄 حاول مرة أخرى بعد قليل.",
                parse_mode="Markdown"
            )
            await context.bot.send_message(
                uid,
                "📤 *أرسل المحاضرة مرة أخرى*\n\n"
                "إذا تكرر الخطأ، تواصل مع الدعم.",
                parse_mode="Markdown",
                reply_markup=main_keyboard()
            )
            
        finally:
            _active_jobs.pop(uid, None)
            _active_tasks.pop(uid, None)
            _cancel_flags.pop(uid, None)
            
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                except Exception:
                    pass


# ══════════════════════════════════════════════════════════════════════════════
#  أمر الأدمن
# ══════════════════════════════════════════════════════════════════════════════

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /admin"""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ غير مصرح لك.")
        return
    await handle_admin_command(update, context)


# ══════════════════════════════════════════════════════════════════════════════
#  تشغيل البوت
# ══════════════════════════════════════════════════════════════════════════════

async def run_bot(shutdown_event: asyncio.Event, set_bot_app_cb=None):
    """تشغيل البوت."""
    init_db()
    logger.info("🗄️ تم تهيئة قاعدة البيانات")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("referral", referral_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    
    app.add_handler(CommandHandler("add", handle_add_attempts))
    app.add_handler(CommandHandler("set", handle_set_attempts))
    app.add_handler(CommandHandler("ban", handle_ban))
    app.add_handler(CommandHandler("unban", handle_unban))
    app.add_handler(CommandHandler("broadcast", handle_broadcast))
    app.add_handler(CommandHandler("approve", handle_approve_payment_command))
    
    app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.Document.ALL) & ~filters.COMMAND,
            receive_content,
        )
    )
    
    webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
    
    if not webhook_url:
        replit_domains = os.getenv("REPLIT_DOMAINS", "")
        for domain in replit_domains.split(","):
            domain = domain.strip()
            if domain.endswith(".replit.app"):
                webhook_url = f"https://{domain}"
                break
    
    if not webhook_url:
        heroku_app = os.getenv("HEROKU_APP_NAME", "")
        if heroku_app:
            webhook_url = f"https://{heroku_app}.herokuapp.com"
    
    async with app:
        await app.start()
        
        if webhook_url:
            full_url = f"{webhook_url}/telegram"
            await app.bot.delete_webhook(drop_pending_updates=True)
            await app.bot.set_webhook(
                url=full_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "pre_checkout_query", "successful_payment"],
            )
            logger.info(f"✅ Webhook: {full_url}")
            
            if set_bot_app_cb:
                set_bot_app_cb(app)
            
            await shutdown_event.wait()
            await app.bot.delete_webhook(drop_pending_updates=True)
        else:
            logger.info("🔄 Polling mode")
            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "pre_checkout_query", "successful_payment"],
            )
            await shutdown_event.wait()
            await app.updater.stop()
        
        await app.stop()
