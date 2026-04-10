# -*- coding: utf-8 -*-
import asyncio
import os
import logging
import tempfile
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, OWNER_ID, FREE_ATTEMPTS, TEMP_DIR
from database import *
from ai_analyzer import analyze_lecture, extract_full_text_from_pdf, fetch_image_for_keyword, clean_text, _detect_type
from voice_generator import generate_sections_audio
from video_creator import create_video_from_sections

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# متغيرات عامة
# ═══════════════════════════════════════════════════════════════════════════════

user_states = {}
_active_jobs = {}
_active_tasks = {}
_cancel_flags = {}

CANCEL_KB = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء المعالجة", callback_data="cancel_job")]])

DIALECT_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("🇮🇶 عراقي", callback_data="dial_iraq"), InlineKeyboardButton("🇪🇬 مصري", callback_data="dial_egypt")],
    [InlineKeyboardButton("🇸🇾 شامي", callback_data="dial_syria"), InlineKeyboardButton("🇸🇦 خليجي", callback_data="dial_gulf")],
    [InlineKeyboardButton("📚 فصحى", callback_data="dial_msa")]
])

DIALECT_NAMES = {
    "iraq": "🇮🇶 عراقي", "egypt": "🇪🇬 مصري",
    "syria": "🇸🇾 شامي", "gulf": "🇸🇦 خليجي", "msa": "📚 فصحى"
}

LECTURE_TYPE_NAMES = {
    'medicine': '🩺 طبية', 'math': '📐 رياضيات', 'physics': '⚡ فيزياء',
    'chemistry': '🧪 كيمياء', 'history': '📜 تاريخ', 'biology': '🧬 أحياء',
    'other': '📚 تعليمية'
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
    """تشغيل مهمة مع إمكانية الإلغاء"""
    ev = _cancel_flags.get(uid)
    if ev is None or ev.is_set():
        raise asyncio.CancelledError()
    
    coro_task = asyncio.ensure_future(coro)
    cancel_task = asyncio.ensure_future(ev.wait())
    
    try:
        done, pending = await asyncio.wait([coro_task, cancel_task], return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()
        if cancel_task in done:
            raise asyncio.CancelledError()
        return coro_task.result()
    except asyncio.CancelledError:
        coro_task.cancel()
        raise


async def ensure_user(update: Update):
    """التأكد من وجود المستخدم في القاعدة"""
    tg = update.effective_user
    user = get_user(tg.id)
    if not user:
        user = create_user(tg.id, tg.username or "", tg.full_name or "")
    if user.get("is_banned"):
        await update.effective_message.reply_text("⛔ أنت محظور من استخدام البوت.")
        return None
    return user


# ═══════════════════════════════════════════════════════════════════════════════
# أوامر البوت
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start"""
    user = await ensure_user(update)
    if not user:
        return
    
    await update.message.reply_text(
        f"👋 أهلاً *{update.effective_user.first_name}*!\n\n"
        f"🎓 أنا *بوت المحاضرات الذكي*\n"
        f"📥 أرسل لي ملف PDF أو نص المحاضرة\n"
        f"🎬 سأحوله إلى فيديو تعليمي احترافي\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /help"""
    await update.message.reply_text(
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ أرسل ملف PDF أو نص المحاضرة\n"
        "2️⃣ اختر لهجة الشرح\n"
        "3️⃣ انتظر حتى تكتمل المعالجة\n"
        "4️⃣ استلم الفيديو التعليمي\n\n"
        "/referral - رابط الإحالة\n"
        "/cancel - إلغاء المعالجة",
        parse_mode="Markdown"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /cancel"""
    uid = update.effective_user.id
    ev = _cancel_flags.get(uid)
    if ev and not ev.is_set():
        ev.set()
        await update.message.reply_text("⛔ تم إلغاء المعالجة.", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("✅ لا توجد عملية جارية.")


async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الرصيد"""
    user = await ensure_user(update)
    if not user:
        return
    await update.message.reply_text(
        f"💳 *رصيدك*\n\n🎬 المحاولات المتبقية: *{user['attempts_left']}*\n📊 إجمالي الفيديوهات: {user['total_videos']}",
        parse_mode="Markdown"
    )


async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /referral"""
    user = await ensure_user(update)
    if not user:
        return
    
    uid = update.effective_user.id
    stats = get_referral_stats(uid)
    bot = await context.bot.get_me()
    ref_link = f"https://t.me/{bot.username}?start=ref_{uid}"
    
    await update.message.reply_text(
        f"🔗 *رابط الإحالة الخاص بك*\n\n`{ref_link}`\n\n"
        f"👥 عدد المدعوين: *{stats['total_referrals']}*\n"
        f"⭐ النقاط الحالية: *{stats['current_points']}*\n\n"
        "كل 10 أشخاص = محاولة مجانية!",
        parse_mode="Markdown"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# استلام المحتوى
# ═══════════════════════════════════════════════════════════════════════════════

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استلام المحاضرة من المستخدم"""
    user = await ensure_user(update)
    if not user:
        return
    
    uid = update.effective_user.id
    msg = update.message
    
    if msg.text:
        text = msg.text.strip()
        if text == "📤 رفع محاضرة":
            await msg.reply_text("📤 أرسل ملف PDF أو اكتب نص المحاضرة:", reply_markup=ReplyKeyboardRemove())
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
        await msg.reply_text("⏳ لديك محاضرة قيد المعالجة، انتظر حتى تنتهي...")
        return
    
    lecture_text = None
    
    if msg.document:
        fname = msg.document.file_name or ""
        ext = fname.split(".")[-1].lower() if "." in fname else ""
        
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ أرسل ملف PDF أو TXT فقط.")
            return
        
        wait = await msg.reply_text("📥 جاري قراءة الملف...")
        
        try:
            file = await msg.document.get_file()
            raw = await file.download_as_bytearray()
            
            if ext == "pdf":
                lecture_text = await extract_full_text_from_pdf(bytes(raw))
            else:
                lecture_text = raw.decode("utf-8", errors="ignore")
            
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ خطأ في قراءة الملف: {str(e)[:100]}")
            return
    
    elif msg.text and len(msg.text.strip()) >= 200:
        lecture_text = msg.text.strip()
    
    else:
        await msg.reply_text("⚠️ أرسل ملف PDF أو نص (200 حرف على الأقل)")
        return
    
    lecture_text = clean_text(lecture_text)
    
    if not lecture_text or len(lecture_text) < 50:
        await msg.reply_text("❌ لم أتمكن من استخراج نص كافٍ من الملف.")
        return
    
    if user["attempts_left"] <= 0:
        await msg.reply_text("❌ لا تملك محاولات كافية.")
        return
    
    user_states[uid] = {"state": "awaiting_dialect", "text": lecture_text}
    
    words = len(lecture_text.split())
    detected = _detect_type(lecture_text)
    type_name = LECTURE_TYPE_NAMES.get(detected, '📚 تعليمية')
    
    await msg.reply_text(
        f"✅ *تم استلام المحاضرة!*\n\n"
        f"📝 عدد الكلمات: {words:,}\n"
        f"🔍 نوع المحتوى: {type_name}\n\n"
        "اختر لهجة الشرح:",
        parse_mode="Markdown",
        reply_markup=DIALECT_KEYBOARD
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Callback Handler
# ═══════════════════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أزرار لوحة المفاتيح"""
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    
    await q.answer()
    
    if data == "cancel_job":
        ev = _cancel_flags.get(uid)
        if ev and not ev.is_set():
            ev.set()
            await q.edit_message_text("⛔ تم إلغاء المعالجة.")
        return
    
    if data == "show_referral":
        stats = get_referral_stats(uid)
        bot = await context.bot.get_me()
        ref_link = f"https://t.me/{bot.username}?start=ref_{uid}"
        await q.message.reply_text(
            f"🔗 *رابطك*\n`{ref_link}`\n👥 {stats['total_referrals']} شخص",
            parse_mode="Markdown"
        )
        return
    
    if data.startswith("dial_"):
        dialect = data[5:]
        state = user_states.get(uid, {})
        
        if state.get("state") != "awaiting_dialect":
            await q.edit_message_text("⚠️ أرسل المحاضرة أولاً.")
            return
        
        user = get_user(uid)
        if not user or user["attempts_left"] <= 0:
            await q.edit_message_text("❌ لا تملك محاولات.")
            return
        
        dial_name = DIALECT_NAMES.get(dialect, dialect)
        prog_msg = await q.edit_message_text(
            f"🎬 *بدأت المعالجة*\n🌍 {dial_name}\n\n{_pbar(0)} 0%\n🔍 جاري التحليل...",
            parse_mode="Markdown"
        )
        
        text = state["text"]
        user_states.pop(uid, None)
        
        task = asyncio.create_task(_process_lecture(uid, text, dialect, prog_msg, context))
        _active_tasks[uid] = task
        return


# ═══════════════════════════════════════════════════════════════════════════════
# معالجة المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

async def _process_lecture(uid, text, dialect, prog_msg, context):
    """المعالجة الكاملة للمحاضرة"""
    _active_jobs[uid] = "processing"
    cancel_ev = asyncio.Event()
    _cancel_flags[uid] = cancel_ev
    req_id = save_video_request(uid, "text", dialect)
    t_start = time.time()
    video_path = None
    
    async def upd(pct, label):
        elapsed = time.time() - t_start
        await _safe_edit(
            prog_msg,
            f"⏳ *جاري المعالجة...*\n\n{_pbar(pct)} *{pct}%*\n{label}\n\n⏱️ {_fmt_elapsed(elapsed)}",
            reply_markup=CANCEL_KB
        )
    
    try:
        await upd(10, "🔍 تحليل المحاضرة...")
        lecture_data = await _run_or_cancel(uid, analyze_lecture(text, dialect))
        
        sections = lecture_data.get("sections", [])
        if not sections:
            raise RuntimeError("لم يتم استخراج أقسام")
        
        lecture_type = lecture_data.get("lecture_type", "other")
        await upd(30, f"✅ {len(sections)} أقسام")
        
        await upd(40, "🖼️ جلب الصور...")
        for s in sections:
            if not s.get("_image_bytes"):
                kw = s.get("keywords", ["مفهوم"])[:3]
                s["_image_bytes"] = await fetch_image_for_keyword(" ".join(kw), s.get("title", ""), lecture_type)
        await upd(55, "✅ الصور جاهزة")
        
        await upd(60, "🎤 توليد الصوت...")
        voice_res = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
        audio_results = voice_res["results"]
        await upd(75, "✅ الصوت جاهز")
        
        await upd(80, "🎬 إنتاج الفيديو...")
        fd, video_path = tempfile.mkstemp(prefix=f"vid_{uid}_", suffix=".mp4", dir=TEMP_DIR)
        os.close(fd)
        
        total_secs = await create_video_from_sections(
            sections=sections,
            audio_results=audio_results,
            lecture_data=lecture_data,
            output_path=video_path,
            dialect=dialect
        )
        await upd(95, "✅ الفيديو جاهز")
        
        decrement_attempts(uid)
        increment_total_videos(uid)
        update_video_request(req_id, "done", video_path)
        
        title = lecture_data.get("title", "محاضرة")
        vid_min = int(total_secs // 60)
        vid_sec = int(total_secs % 60)
        remaining = get_user(uid)["attempts_left"]
        
        caption = f"🎬 *{title}*\n\n📚 أقسام: {len(sections)}\n⏱️ {vid_min}:{vid_sec:02d}\n💳 محاولات: {remaining}"
        
        with open(video_path, "rb") as vf:
            await context.bot.send_video(
                chat_id=uid, video=vf, caption=caption,
                parse_mode="Markdown", supports_streaming=True
            )
        
        await prog_msg.delete()
        await context.bot.send_message(
            uid, "✅ *تم بنجاح!* 🎓",
            parse_mode="Markdown", reply_markup=main_keyboard()
        )
    
    except asyncio.CancelledError:
        update_video_request(req_id, "cancelled")
        await context.bot.send_message(uid, "⛔ تم الإلغاء.", reply_markup=main_keyboard())
    
    except Exception as e:
        update_video_request(req_id, "failed")
        logger.error(f"Error: {e}")
        await _safe_edit(prog_msg, f"❌ خطأ: {str(e)[:200]}")
        await context.bot.send_message(uid, "❌ حاول مرة أخرى.", reply_markup=main_keyboard())
    
    finally:
        _active_jobs.pop(uid, None)
        _active_tasks.pop(uid, None)
        _cancel_flags.pop(uid, None)
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except:
                pass


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
    app.add_handler(CommandHandler("referral", referral_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, receive_content))
    
    logger.info("✅ Ready")
    
    webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
    
    async with app:
        await app.start()
        
        if webhook_url:
            await app.bot.set_webhook(url=f"{webhook_url}/telegram", drop_pending_updates=True)
            logger.info(f"✅ Webhook: {webhook_url}")
            await asyncio.Event().wait()
        else:
            logger.info("🔄 Polling...")
            await app.updater.start_polling(drop_pending_updates=True)
            await asyncio.Event().wait()
            await app.updater.stop()
        
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
