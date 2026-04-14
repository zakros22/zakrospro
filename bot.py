#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
البوت الرئيسي - جميع المنطق هنا
"""

import asyncio
import os
import logging
import tempfile
import time
import re
import json
import io
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, filters, ContextTypes
)

from config import (
    TELEGRAM_BOT_TOKEN, OWNER_ID, FREE_ATTEMPTS, TEMP_DIR, WATERMARK_TEXT
)
from database import (
    get_user, create_user, decrement_attempts, add_attempts,
    ban_user, get_stats, get_all_users, record_referral, get_referral_stats,
    save_video_request, update_video_request
)
from ai_analyzer import analyze_lecture, extract_full_text_from_pdf, QuotaExhaustedError
from image_generator import create_educational_card, create_summary_card
from voice_generator import generate_sections_audio
from video_creator import create_video_from_sections, estimate_encoding_seconds
from admin_panel import (
    is_owner, handle_admin_command, handle_admin_callback, handle_admin_text_search,
    handle_add_attempts, handle_set_attempts, handle_ban, handle_unban, handle_broadcast
)
from payment_handler import (
    get_payment_keyboard, send_payment_required_message,
    handle_pay_stars, handle_pay_mastercard, handle_pay_crypto,
    handle_payment_sent, handle_pre_checkout, handle_successful_payment
)

# ══════════════════════════════════════════════════════════════════════════════
#  إعداد التسجيل
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  حالة المستخدمين
# ══════════════════════════════════════════════════════════════════════════════
user_states = {}
active_jobs = {}
active_tasks = {}
cancel_flags = {}

_Q_SEM = asyncio.Semaphore(2)

# ══════════════════════════════════════════════════════════════════════════════
#  لوحات المفاتيح
# ══════════════════════════════════════════════════════════════════════════════
def main_keyboard():
    return ReplyKeyboardMarkup(
        [["📤 رفع محاضرة", "📊 رصيدي"], ["🔗 رابط الإحالة", "❓ مساعدة"]],
        resize_keyboard=True
    )

DIALECT_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🇮🇶 عراقي", callback_data="dial_iraq"),
     InlineKeyboardButton("🇪🇬 مصري", callback_data="dial_egypt")],
    [InlineKeyboardButton("🇸🇾 شامي", callback_data="dial_syria"),
     InlineKeyboardButton("🇸🇦 خليجي", callback_data="dial_gulf")],
    [InlineKeyboardButton("📚 فصحى", callback_data="dial_msa"),
     InlineKeyboardButton("🇺🇸 English", callback_data="dial_english")],
])

CANCEL_KB = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء المعالجة", callback_data="cancel_job")]])

DIALECT_NAMES = {
    "iraq": "🇮🇶 عراقي", "egypt": "🇪🇬 مصري", "syria": "🇸🇾 شامي",
    "gulf": "🇸🇦 خليجي", "msa": "📚 فصحى", "english": "🇺🇸 English"
}

# ══════════════════════════════════════════════════════════════════════════════
#  دوال مساعدة
# ══════════════════════════════════════════════════════════════════════════════
def pbar(pct: int, width: int = 12) -> str:
    filled = int(width * pct / 100)
    return "▓" * filled + "░" * (width - filled)

def fmt_time(sec: float) -> str:
    if sec < 60:
        return f"{int(sec)} ثانية"
    m, s = divmod(int(sec), 60)
    return f"{m} دقيقة و {s} ثانية"

async def safe_edit(msg, text, markup=None):
    try:
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    except:
        pass

async def ensure_user(update: Update):
    tg = update.effective_user
    user = get_user(tg.id)
    if not user:
        ref_by = user_states.get(tg.id, {}).get("ref_by")
        user = create_user(tg.id, tg.username or "", tg.full_name or "", ref_by)
        if ref_by and ref_by != tg.id:
            record_referral(ref_by, tg.id)
    if user and user.get("is_banned"):
        await update.effective_message.reply_text("⛔ أنت محظور من استخدام البوت.")
        return None
    return user

async def _run_or_cancel(uid: int, coro):
    ev = cancel_flags.get(uid)
    if ev and ev.is_set():
        raise asyncio.CancelledError()
    
    task = asyncio.ensure_future(coro)
    if ev:
        cancel_task = asyncio.ensure_future(ev.wait())
        done, pending = await asyncio.wait([task, cancel_task], return_when=asyncio.FIRST_COMPLETED)
        for p in pending:
            p.cancel()
        if cancel_task in done:
            task.cancel()
            raise asyncio.CancelledError()
    return await task

# ══════════════════════════════════════════════════════════════════════════════
#  أوامر البوت
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args
    
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
    
    name = update.effective_user.first_name or "صديقي"
    await update.message.reply_text(
        f"👋 *أهلاً {name}!*\n\n"
        f"🎓 أنا *بوت المحاضرات الذكي*\n"
        f"أحوّل محاضرتك إلى فيديو تعليمي احترافي!\n\n"
        f"📤 أرسل ملف PDF أو TXT أو نص المحاضرة\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ أرسل ملف PDF أو نص المحاضرة\n"
        "2️⃣ اختر لهجة الشرح\n"
        "3️⃣ انتظر حتى اكتمال الفيديو\n"
        "4️⃣ استلم الفيديو التعليمي\n\n"
        "/start - بدء\n/cancel - إلغاء\n/referral - رابط الإحالة",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_states.pop(uid, None)
    
    if uid in cancel_flags:
        cancel_flags[uid].set()
        await update.message.reply_text("⛔ تم إلغاء المعالجة", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("✅ لا توجد عملية جارية", reply_markup=main_keyboard())

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return
    await update.message.reply_text(
        f"💳 *رصيدك*\n\n🎬 المحاولات: *{user['attempts_left']}*\n📊 الفيديوهات: *{user['total_videos']}*",
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard(user['user_id'])
    )

async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return
    
    uid = update.effective_user.id
    stats = get_referral_stats(uid)
    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
    
    progress = (stats['current_points'] / 1.0) * 100
    await update.message.reply_text(
        f"🔗 *رابط الإحالة*\n\n`{ref_link}`\n\n"
        f"👥 الأصدقاء: *{stats['total_referrals']}*\n"
        f"⭐ النقاط: *{stats['current_points']:.1f}*\n"
        f"{pbar(int(progress))} {progress:.0f}%",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

# ══════════════════════════════════════════════════════════════════════════════
#  استقبال المحتوى
# ══════════════════════════════════════════════════════════════════════════════
async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    
    # أزرار القائمة
    if msg.text:
        text = msg.text.strip()
        if text == "📤 رفع محاضرة":
            await msg.reply_text("📤 أرسل ملف PDF أو TXT أو نص المحاضرة:", reply_markup=ReplyKeyboardRemove())
            return
        if text == "📊 رصيدي":
            await balance_cmd(update, context)
            return
        if text == "🔗 رابط الإحالة":
            await referral_cmd(update, context)
            return
        if text == "❓ مساعدة":
            await help_cmd(update, context)
            return
    
    # أدمن
    if is_owner(uid):
        if await handle_admin_text_search(update, context):
            return
    
    user = await ensure_user(update)
    if not user:
        return
    
    if uid in active_jobs:
        await msg.reply_text("⏳ محاضرتك قيد المعالجة...")
        return
    
    if user['attempts_left'] <= 0:
        await send_payment_required_message(update, context)
        return
    
    # استخراج النص
    text = None
    filename = "محاضرة"
    
    if msg.document:
        doc = msg.document
        fname = doc.file_name or ""
        ext = fname.lower().split(".")[-1] if "." in fname else ""
        
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ PDF أو TXT فقط")
            return
        
        wait = await msg.reply_text("📥 جاري قراءة الملف...")
        try:
            file = await doc.get_file()
            raw = await file.download_as_bytearray()
            if ext == "pdf":
                text = await extract_full_text_from_pdf(bytes(raw))
                filename = fname.replace(".pdf", "").replace(".PDF", "")
            else:
                text = raw.decode("utf-8", errors="ignore")
                filename = fname.replace(".txt", "").replace(".TXT", "")
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ خطأ: {e}")
            return
    
    elif msg.text:
        if len(msg.text.strip()) < 100:
            await msg.reply_text("⚠️ النص قصير جداً (أقل من 100 حرف)")
            return
        text = msg.text.strip()
        filename = text[:30].replace("\n", " ")
    else:
        return
    
    if not text or len(text.strip()) < 50:
        await msg.reply_text("❌ لم أستطع قراءة النص")
        return
    
    user_states[uid] = {"text": text, "filename": filename}
    
    await msg.reply_text(
        f"✅ *تم الاستلام!*\n📝 {len(text.split()):,} كلمة\n\nاختر لهجة الشرح:",
        parse_mode="Markdown",
        reply_markup=DIALECT_KB
    )

# ══════════════════════════════════════════════════════════════════════════════
#  معالج الأزرار
# ══════════════════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    
    if data.startswith("admin_"):
        await handle_admin_callback(update, context)
        return
    
    await q.answer()
    
    # دفع
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
    if data == "show_referral":
        await referral_cmd(update, context)
        return
    
    # إلغاء
    if data == "cancel_job":
        if uid in cancel_flags:
            cancel_flags[uid].set()
        await q.edit_message_text("⛔ تم الإلغاء")
        return
    
    # اختيار اللهجة
    if data.startswith("dial_"):
        dialect = data[5:]
        state = user_states.pop(uid, {})
        text = state.get("text")
        filename = state.get("filename", "محاضرة")
        
        if not text:
            await q.edit_message_text("⚠️ انتهت الجلسة")
            return
        
        user = get_user(uid)
        if user['attempts_left'] <= 0:
            await q.edit_message_text("❌ لا تملك محاولات")
            return
        
        dial_name = DIALECT_NAMES.get(dialect, dialect)
        prog_msg = await q.edit_message_text(
            f"🎬 *بدأت المعالجة*\n{pbar(0)} 0%\n🔍 تحليل...",
            parse_mode="Markdown",
            reply_markup=CANCEL_KB
        )
        
        cancel_flags[uid] = asyncio.Event()
        active_jobs[uid] = True
        
        task = asyncio.create_task(
            process_lecture(uid, text, filename, dialect, prog_msg, context)
        )
        active_tasks[uid] = task

# ══════════════════════════════════════════════════════════════════════════════
#  معالجة المحاضرة
# ══════════════════════════════════════════════════════════════════════════════
async def process_lecture(uid, text, filename, dialect, prog_msg, context):
    t0 = time.time()
    req_id = save_video_request(uid, "text", dialect)
    video_path = None
    is_arabic = dialect not in ("english", "british")
    
    async def upd(pct, label):
        if cancel_flags.get(uid, asyncio.Event()).is_set():
            raise asyncio.CancelledError()
        e = time.time() - t0
        await safe_edit(prog_msg, f"🎬 *المعالجة*\n{pbar(pct)} {pct}%\n{label}\n⏱️ {fmt_time(e)}", CANCEL_KB)
    
    async with _Q_SEM:
        try:
            # 1. تحليل
            await upd(10, "🔍 تحليل المحتوى...")
            data = await _run_or_cancel(uid, analyze_lecture(text, dialect))
            sections = data.get("sections", [])
            subject = data.get("lecture_type", "other")
            
            if not sections:
                raise Exception("لم يتم استخراج أقسام")
            
            await upd(25, f"✅ {len(sections)} أقسام")
            
            # 2. صور
            for i, sec in enumerate(sections):
                await upd(30 + i*8, f"🎨 تصميم الكرت {i+1}...")
                if cancel_flags.get(uid, asyncio.Event()).is_set():
                    raise asyncio.CancelledError()
                
                img_path = create_educational_card(
                    sec.get("title", f"القسم {i+1}"),
                    sec.get("keywords", []),
                    subject, i+1, len(sections), is_arabic
                )
                sec["_image_path"] = img_path
            
            # 3. صوت
            await upd(60, "🎤 توليد الصوت...")
            voice_res = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
            audio_results = voice_res["results"]
            
            # 4. فيديو
            await upd(75, "🎬 إنتاج الفيديو...")
            
            fd, video_path = tempfile.mkstemp(suffix=".mp4", dir=TEMP_DIR)
            os.close(fd)
            
            total_secs = await create_video_from_sections(
                sections, audio_results, data, video_path, dialect,
                progress_cb=lambda e, est: upd(80 + int(e/est*15), "🎥 تشفير...")
            )
            
            # 5. إرسال
            await upd(98, "📤 إرسال...")
            
            decrement_attempts(uid)
            update_video_request(req_id, "done", video_path)
            
            user = get_user(uid)
            vid_min, vid_sec = divmod(int(total_secs), 60)
            caption = f"🎬 *{data.get('title', filename)}*\n📚 {len(sections)} أقسام\n⏱️ {vid_min}:{vid_sec:02d}\n💳 متبقي: {user['attempts_left']}"
            
            with open(video_path, "rb") as vf:
                await context.bot.send_video(uid, vf, caption=caption, parse_mode="Markdown")
            
            await prog_msg.delete()
            await context.bot.send_message(uid, "✅ *تم بنجاح!* 🎉", parse_mode="Markdown", reply_markup=main_keyboard())
            
        except asyncio.CancelledError:
            update_video_request(req_id, "cancelled")
            await safe_edit(prog_msg, "⛔ تم الإلغاء")
        except Exception as e:
            update_video_request(req_id, "failed")
            logger.error(f"Error: {e}")
            await safe_edit(prog_msg, f"❌ خطأ: {str(e)[:200]}")
        finally:
            active_jobs.pop(uid, None)
            active_tasks.pop(uid, None)
            cancel_flags.pop(uid, None)
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                except:
                    pass

# ══════════════════════════════════════════════════════════════════════════════
#  أمر الأدمن
# ══════════════════════════════════════════════════════════════════════════════
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    await handle_admin_command(update, context)

# ══════════════════════════════════════════════════════════════════════════════
#  دالة run_bot (المطلوبة من main.py)
# ══════════════════════════════════════════════════════════════════════════════
async def run_bot(shutdown_event: asyncio.Event, set_bot_app_cb=None):
    """تشغيل البوت - تستدعى من main.py"""
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("referral", referral_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("add", handle_add_attempts))
    app.add_handler(CommandHandler("set", handle_set_attempts))
    app.add_handler(CommandHandler("ban", handle_ban))
    app.add_handler(CommandHandler("unban", handle_unban))
    app.add_handler(CommandHandler("broadcast", handle_broadcast))
    
    app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, receive_content))
    
    # وضع التشغيل
    webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
    
    async with app:
        await app.start()
        
        if webhook_url:
            full_url = f"{webhook_url}/telegram"
            await app.bot.delete_webhook(drop_pending_updates=True)
            await app.bot.set_webhook(url=full_url, drop_pending_updates=True)
            logger.info(f"✅ Webhook: {full_url}")
            
            if set_bot_app_cb:
                set_bot_app_cb(app)
            
            await shutdown_event.wait()
            await app.bot.delete_webhook(drop_pending_updates=True)
        else:
            logger.info("🔄 Polling mode")
            await app.updater.start_polling(drop_pending_updates=True)
            await shutdown_event.wait()
            await app.updater.stop()
        
        await app.stop()
