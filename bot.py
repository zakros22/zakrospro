# -*- coding: utf-8 -*-
import asyncio
import os
import logging
import tempfile
import time
import re
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from config import TELEGRAM_BOT_TOKEN, OWNER_ID, FREE_ATTEMPTS, TEMP_DIR
from database import init_db, get_user, create_user, is_banned, decrement_attempts, increment_total_videos, save_video_request, update_video_request

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

user_states = {}
_active_jobs = {}
_active_tasks = {}
_cancel_flags = {}

CANCEL_KB = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="cancel_job")]])

def main_keyboard():
    return ReplyKeyboardMarkup([["📤 رفع محاضرة", "📊 رصيدي"], ["❓ مساعدة"]], resize_keyboard=True)

def clean_text(text):
    if not text: return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def extract_keywords(text, max_words=20):
    stop = {'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه', 'كان', 'مع', 'ما', 'لا', 'عن', 'إذا', 'لم', 'لن', 'قد', 'ثم', 'أو', 'the', 'a', 'an', 'is', 'are', 'of', 'to', 'in', 'and', 'or'}
    words = re.findall(r'[\u0600-\u06FF]{4,}|[a-zA-Z]{4,}', text)
    freq = {}
    for w in words:
        wl = w.lower()
        if wl not in stop: freq[w] = freq.get(w, 0) + 1
    return [w[0] for w in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_words]]

def split_text(text, parts=4):
    words = text.split()
    chunk = max(1, len(words) // parts)
    return [' '.join(words[i:i+chunk]) for i in range(0, len(words), chunk)][:parts]

async def ensure_user(update):
    tg = update.effective_user
    user = get_user(tg.id)
    if not user: user = create_user(tg.id, tg.username or "", tg.full_name or "")
    if user.get("is_banned"): await update.effective_message.reply_text("⛔ محظور"); return None
    return user

async def start(update, context):
    user = await ensure_user(update)
    if not user: return
    await update.message.reply_text(f"👋 أهلاً!\n🎓 بوت المحاضرات\n📥 أرسل PDF أو نص\n🎁 {user['attempts_left']} محاولات", reply_markup=main_keyboard())

async def receive_content(update, context):
    user = await ensure_user(update)
    if not user: return
    uid = update.effective_user.id
    msg = update.message
    
    if msg.text:
        if msg.text == "📤 رفع محاضرة":
            await msg.reply_text("📤 أرسل PDF أو نص:", reply_markup=ReplyKeyboardRemove())
            return
        if msg.text == "📊 رصيدي":
            await msg.reply_text(f"💳 {user['attempts_left']} محاولات")
            return
        if msg.text == "❓ مساعدة":
            await msg.reply_text("📖 أرسل PDF أو نص طويل")
            return

    if uid in _active_jobs:
        await msg.reply_text("⏳ جاري المعالجة...")
        return

    text = None
    if msg.document:
        fname = msg.document.file_name or ""
        ext = fname.split(".")[-1].lower() if "." in fname else ""
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ PDF أو TXT فقط")
            return
        wait = await msg.reply_text("📥 قراءة...")
        try:
            file = await msg.document.get_file()
            raw = await file.download_as_bytearray()
            if ext == "pdf":
                import PyPDF2, io
                r = PyPDF2.PdfReader(io.BytesIO(raw))
                text = "\n".join([p.extract_text() or "" for p in r.pages])
            else:
                text = raw.decode("utf-8", errors="ignore")
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ {e}")
            return
    elif msg.text and len(msg.text) >= 200:
        text = msg.text

    if not text or len(clean_text(text)) < 50:
        await msg.reply_text("❌ نص غير كاف")
        return

    text = clean_text(text)
    if user["attempts_left"] <= 0:
        await msg.reply_text("❌ لا محاولات")
        return

    prog_msg = await msg.reply_text("🎬 بدء...", reply_markup=CANCEL_KB)
    task = asyncio.create_task(_process(uid, text, prog_msg, context))
    _active_tasks[uid] = task

async def _process(uid, text, prog_msg, context):
    _active_jobs[uid] = "processing"
    cancel_ev = asyncio.Event()
    _cancel_flags[uid] = cancel_ev
    req_id = save_video_request(uid, "text", "msa")
    
    async def upd(msg): await prog_msg.edit_text(msg, reply_markup=CANCEL_KB)
    
    try:
        await upd("🔍 تحليل...")
        keywords = extract_keywords(text, 16)
        title = keywords[0] if keywords else "محاضرة"
        parts = split_text(text, 4)
        
        await upd("🎤 صوت...")
        from gtts import gTTS
        audio_paths = []
        for i, p in enumerate(parts):
            if not p: continue
            buf = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            gTTS(text=p, lang="ar", slow=False).write_to_fp(buf)
            buf.close()
            audio_paths.append(buf.name)
        
        await upd("🎬 فيديو...")
        from video_creator_simple import create_simple_video
        video_path = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
        await create_simple_video(title, parts, keywords, audio_paths, video_path)
        
        await upd("📤 إرسال...")
        decrement_attempts(uid)
        increment_total_videos(uid)
        update_video_request(req_id, "done")
        
        with open(video_path, "rb") as f:
            await context.bot.send_video(uid, f, caption=f"🎬 {title}")
        await prog_msg.delete()
        await context.bot.send_message(uid, "✅ تم!", reply_markup=main_keyboard())
        
    except asyncio.CancelledError:
        await context.bot.send_message(uid, "⛔ إلغاء")
    except Exception as e:
        await prog_msg.edit_text(f"❌ {str(e)[:100]}")
    finally:
        _active_jobs.pop(uid, None)
        _active_tasks.pop(uid, None)
        import os as os_clean
        for p in audio_paths if 'audio_paths' in dir() else []:
            try: os_clean.remove(p)
            except: pass
        if 'video_path' in dir() and os.path.exists(video_path):
            try: os_clean.remove(video_path)
            except: pass

async def callback_handler(update, context):
    q = update.callback_query
    if q.data == "cancel_job":
        ev = _cancel_flags.get(q.from_user.id)
        if ev: ev.set()
        await q.edit_message_text("⛔ إلغاء")
    await q.answer()

async def main():
    init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, receive_content))
    
    async with app:
        await app.start()
        if os.getenv("WEBHOOK_URL"):
            await app.bot.set_webhook(url=f"{os.getenv('WEBHOOK_URL')}/telegram")
        else:
            await app.updater.start_polling()
        await asyncio.Event().wait()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
