import asyncio
import os
import logging
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from config import TELEGRAM_BOT_TOKEN, TEMP_DIR, VOICES, OWNER_ID, FREE_ATTEMPTS
from database import init_db, get_user, create_user, decrement_attempts, increment_total_videos, save_video_request, update_video_request
from ai_analyzer import analyze_lecture, extract_text_from_pdf, fetch_image_for_keyword
from voice_generator import generate_audio_for_section
from video_creator import create_video

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

_thread_pool = ThreadPoolExecutor(max_workers=4)
_active_tasks: dict[int, asyncio.Task] = {}
user_states: dict[int, dict] = {}

DIALECTS = InlineKeyboardMarkup([
    [InlineKeyboardButton("🇮🇶 عراقي", callback_data="dial_iraq"),
     InlineKeyboardButton("🇪🇬 مصري", callback_data="dial_egypt")],
    [InlineKeyboardButton("🇸🇾 شامي", callback_data="dial_syria"),
     InlineKeyboardButton("🇸🇦 خليجي", callback_data="dial_gulf")],
    [InlineKeyboardButton("📚 فصحى", callback_data="dial_msa")],
    [InlineKeyboardButton("🇺🇸 English", callback_data="dial_english"),
     InlineKeyboardButton("🇬🇧 British", callback_data="dial_british")],
])

DIALECT_NAMES = {k: v["name"] for k, v in VOICES.items()}

# ──────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    if not user:
        user = create_user(uid, update.effective_user.username or "", update.effective_user.full_name or "")
    
    await update.message.reply_text(
        f"🎓 *بوت المحاضرات الذكي*\n\n"
        f"أرسل:\n• ملف PDF 📄\n• ملف TXT 📃\n• نص مباشر ✍️\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    
    user = get_user(uid)
    if not user:
        user = create_user(uid, update.effective_user.username or "", update.effective_user.full_name or "")
    
    if user['attempts_left'] <= 0:
        await msg.reply_text("❌ لا تملك محاولات كافية")
        return
    
    # نص مباشر
    if msg.text and len(msg.text) >= 100:
        text = msg.text
        user_states[uid] = {"text": text, "filename": "lecture"}
        await msg.reply_text(f"✅ تم استلام النص ({len(text.split())} كلمة)\nاختر اللهجة:", reply_markup=DIALECTS)
        return
    
    # ملف
    if msg.document:
        doc = msg.document
        fname = doc.file_name or "file"
        ext = fname.split('.')[-1].lower() if '.' in fname else ''
        
        if ext not in ('pdf', 'txt'):
            await msg.reply_text("❌ أرسل PDF أو TXT فقط")
            return
        
        status = await msg.reply_text("📥 جاري التحميل...")
        
        # تحميل في الخلفية
        asyncio.create_task(_process_document(update, context, status, doc, fname, ext, uid))
        return
    
    await msg.reply_text("أرسل ملف PDF/TXT أو نص (100 حرف على الأقل)")

async def _process_document(update, context, status, doc, fname, ext, uid):
    try:
        file = await context.bot.get_file(doc.file_id)
        raw = await file.download_as_bytearray()
        
        await status.edit_text("🔍 جاري استخراج النص...")
        
        loop = asyncio.get_event_loop()
        if ext == 'pdf':
            text = await loop.run_in_executor(_thread_pool, extract_text_from_pdf_sync, bytes(raw))
        else:
            text = raw.decode('utf-8', errors='ignore')
        
        if not text or len(text.strip()) < 50:
            await status.edit_text("❌ لم يتم استخراج نص كافٍ")
            return
        
        user_states[uid] = {"text": text, "filename": fname.replace(f".{ext}", "")}
        await status.edit_text(f"✅ تم استخراج {len(text.split())} كلمة\nاختر اللهجة:", reply_markup=DIALECTS)
    except Exception as e:
        await status.edit_text(f"❌ خطأ: {str(e)[:100]}")

def extract_text_from_pdf_sync(data):
    import PyPDF2, io
    reader = PyPDF2.PdfReader(io.BytesIO(data))
    texts = []
    for page in reader.pages[:50]:
        try:
            t = page.extract_text()
            if t: texts.append(t)
        except: pass
    return "\n".join(texts)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    
    if data.startswith("dial_"):
        dialect = data[5:]
        state = user_states.get(uid, {})
        
        if not state.get("text"):
            await q.edit_message_text("❌ أرسل المحاضرة أولاً")
            return
        
        await q.edit_message_text(f"🎬 بدء المعالجة...\nاللهجة: {DIALECT_NAMES.get(dialect, dialect)}")
        
        task = asyncio.create_task(_process_lecture(uid, state["text"], state["filename"], dialect, q.message, context))
        _active_tasks[uid] = task
        user_states.pop(uid, None)
    
    await q.answer()

async def _process_lecture(uid, text, filename, dialect, status_msg, context):
    req_id = save_video_request(uid, "text", dialect)
    start = time.time()
    
    try:
        await status_msg.edit_text("🔍 تحليل المحاضرة...")
        data = await analyze_lecture(text, dialect)
        sections = data.get("sections", [])
        
        if not sections:
            raise Exception("لم يتم استخراج أقسام")
        
        await status_msg.edit_text(f"✅ تم التحليل - {len(sections)} أقسام\n🎨 جلب الصور...")
        
        # جلب الصور
        for i, sec in enumerate(sections):
            keywords = sec.get("keywords", [])[:4]
            images = []
            for kw in keywords:
                img = await fetch_image_for_keyword(kw, sec.get("title", ""), data.get("lecture_type", "other"), kw)
                images.append(img)
            sec["_images"] = images
            sec["_main_image"] = images[0] if images else None
            await status_msg.edit_text(f"🎨 جلب الصور... ({i+1}/{len(sections)})")
        
        await status_msg.edit_text("🎤 توليد الصوت...")
        
        # توليد الصوت
        audio_results = []
        for i, sec in enumerate(sections):
            narration = sec.get("narration", sec.get("content", ""))
            audio_data = await generate_audio_for_section(narration, dialect)
            audio_results.append(audio_data)
            await status_msg.edit_text(f"🎤 توليد الصوت... ({i+1}/{len(sections)})")
        
        await status_msg.edit_text("🎬 إنتاج الفيديو...")
        
        # إنشاء الفيديو
        fd, video_path = tempfile.mkstemp(suffix=".mp4", dir=TEMP_DIR)
        os.close(fd)
        
        total_secs = await create_video(sections, audio_results, data, video_path, dialect)
        
        # إرسال الفيديو
        decrement_attempts(uid)
        increment_total_videos(uid)
        update_video_request(req_id, "done", video_path)
        
        mins, secs = int(total_secs // 60), int(total_secs % 60)
        caption = f"🎬 *{data.get('title', filename)}*\n📚 {len(sections)} أقسام\n⏱️ {mins}:{secs:02d}"
        
        with open(video_path, "rb") as f:
            await context.bot.send_video(uid, f, caption=caption, parse_mode="Markdown")
        
        await status_msg.delete()
        await context.bot.send_message(uid, "✅ تم بنجاح!")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text(f"❌ خطأ: {str(e)[:200]}")
        update_video_request(req_id, "failed")
    finally:
        _active_tasks.pop(uid, None)

async def run_bot():
    init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.Document.ALL, handle_message))
    
    await app.initialize()
    await app.start()
    
    # Webhook أو Polling
    app_url = os.getenv("HEROKU_APP_NAME", "")
    if app_url:
        await app.bot.set_webhook(f"https://{app_url}.herokuapp.com/telegram")
        logger.info(f"Webhook: https://{app_url}.herokuapp.com/telegram")
    else:
        await app.updater.start_polling()
        logger.info("Polling...")
    
    await asyncio.Event().wait()
