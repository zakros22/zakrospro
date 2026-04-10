# -*- coding: utf-8 -*-
import asyncio, os, logging, tempfile, time, re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from config import TELEGRAM_BOT_TOKEN, OWNER_ID, FREE_ATTEMPTS, TEMP_DIR
from database import *
from ai_analyzer import analyze_lecture, extract_full_text_from_pdf, fetch_image_for_keyword, clean_text, _detect_type
from voice_generator import generate_sections_audio
from video_creator import create_video_from_sections, estimate_encoding_seconds

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

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
DIALECT_NAMES = {"iraq":"🇮🇶 عراقي","egypt":"🇪🇬 مصري","syria":"🇸🇾 شامي","gulf":"🇸🇦 خليجي","msa":"📚 فصحى"}
LECTURE_TYPE_NAMES = {'medicine':'🩺 طبية','math':'📐 رياضيات','physics':'⚡ فيزياء','chemistry':'🧪 كيمياء','history':'📜 تاريخ','biology':'🧬 أحياء','other':'📚 تعليمية'}

def main_keyboard(): return ReplyKeyboardMarkup([["📤 رفع محاضرة", "📊 رصيدي"], ["🔗 رابط الإحالة", "❓ مساعدة"]], resize_keyboard=True)
def _pbar(pct, w=12): return "▓"*int(w*pct/100) + "░"*(w-int(w*pct/100))
def _fmt_elapsed(sec): return f"{int(sec)} ثانية" if sec<60 else f"{int(sec//60)} دقيقة {int(sec%60)} ثانية"
async def _safe_edit(msg, txt, parse_mode="Markdown", reply_markup=None):
    try: await msg.edit_text(txt, parse_mode=parse_mode, reply_markup=reply_markup)
    except: pass

async def ensure_user(update):
    tg = update.effective_user; user = get_user(tg.id)
    if not user: user = create_user(tg.id, tg.username or "", tg.full_name or "")
    if user.get("is_banned"): await update.effective_message.reply_text("⛔ محظور"); return None
    return user

async def start(update, context):
    user = await ensure_user(update)
    if not user: return
    await update.message.reply_text(f"👋 أهلاً *{update.effective_user.first_name}*!\n\n🎓 بوت المحاضرات الذكي\n📥 أرسل PDF أو نص\n🎁 *{user['attempts_left']}* محاولة", parse_mode="Markdown", reply_markup=main_keyboard())

async def receive_content(update, context):
    user = await ensure_user(update)
    if not user: return
    uid, msg = update.effective_user.id, update.message
    if msg.text:
        if msg.text == "📤 رفع محاضرة": await msg.reply_text("📤 أرسل PDF أو نص:", reply_markup=ReplyKeyboardRemove()); return
        if msg.text == "📊 رصيدي": await msg.reply_text(f"💳 {user['attempts_left']} محاولات"); return
    if uid in _active_jobs: await msg.reply_text("⏳ جاري المعالجة..."); return

    text = None
    if msg.document:
        fname, ext = msg.document.file_name or "", (msg.document.file_name or "").split(".")[-1].lower()
        if ext not in ("pdf","txt"): await msg.reply_text("⚠️ PDF أو TXT فقط"); return
        wait = await msg.reply_text("📥 قراءة الملف...")
        try:
            file = await msg.document.get_file(); raw = await file.download_as_bytearray()
            if ext == "pdf": text = await asyncio.wait_for(extract_full_text_from_pdf(bytes(raw)), timeout=90.0)
            else: text = raw.decode("utf-8", errors="ignore")
            await wait.delete()
        except asyncio.TimeoutError: await wait.edit_text("❌ الملف كبير جداً"); return
        except Exception as e: await wait.edit_text(f"❌ خطأ: {e}"); return
    elif msg.text and len(msg.text) >= 200: text = msg.text
    else: await msg.reply_text("⚠️ أرسل PDF أو نص (200 حرف)"); return

    text = clean_text(text)
    if not text or len(text) < 50: await msg.reply_text("❌ نص غير كاف"); return
    if user["attempts_left"] <= 0: await msg.reply_text("❌ لا محاولات"); return

    user_states[uid] = {"state": "awaiting_dialect", "text": text}
    words = len(text.split()); detected = _detect_type(text); type_name = LECTURE_TYPE_NAMES.get(detected, '📚 تعليمية')
    await msg.reply_text(f"✅ *تم الاستلام!*\n\n📝 كلمات: {words:,}\n🔍 النوع: {type_name}\n\nاختر لهجة الشرح:", parse_mode="Markdown", reply_markup=DIALECT_KEYBOARD)

async def callback_handler(update, context):
    q = update.callback_query; data = q.data; uid = q.from_user.id
    await q.answer()
    if data == "cancel_job":
        ev = _cancel_flags.get(uid)
        if ev and not ev.is_set(): ev.set(); await q.edit_message_text("⛔ تم الإلغاء.")
        return
    if data.startswith("dial_"):
        dialect = data[5:]
        state = user_states.get(uid, {})
        if state.get("state") != "awaiting_dialect": await q.edit_message_text("⚠️ أرسل المحاضرة أولاً."); return
        user = get_user(uid)
        if not user or user["attempts_left"] <= 0: await q.edit_message_text("❌ لا محاولات"); return
        dial_name = DIALECT_NAMES.get(dialect, dialect)
        prog_msg = await q.edit_message_text(f"🎬 *بدأت المعالجة*\n🌍 {dial_name}\n\n{_pbar(0)} 0%\n🔍 جاري التحليل...", parse_mode="Markdown")
        text = state["text"]; user_states.pop(uid, None)
        task = asyncio.create_task(_process_lecture(uid, text, dialect, prog_msg, context))
        _active_tasks[uid] = task; return

async def _run_or_cancel(uid, coro):
    ev = _cancel_flags.get(uid)
    if ev is None or ev.is_set(): raise asyncio.CancelledError()
    coro_task = asyncio.ensure_future(coro); cancel_task = asyncio.ensure_future(ev.wait())
    try:
        done, pending = await asyncio.wait([coro_task, cancel_task], return_when=asyncio.FIRST_COMPLETED)
        for p in pending: p.cancel()
        if cancel_task in done: raise asyncio.CancelledError()
        return coro_task.result()
    except asyncio.CancelledError:
        coro_task.cancel(); raise

async def _process_lecture(uid, text, dialect, prog_msg, context):
    _active_jobs[uid] = "processing"; cancel_ev = asyncio.Event(); _cancel_flags[uid] = cancel_ev
    req_id = save_video_request(uid, "text", dialect); t_start = time.time(); video_path = None
    async def upd(pct, label):
        elapsed = time.time() - t_start
        await _safe_edit(prog_msg, f"⏳ *معالجة...*\n\n{_pbar(pct)} *{pct}%*\n{label}\n\n⏱️ {_fmt_elapsed(elapsed)}", reply_markup=CANCEL_KB)
    try:
        await upd(5, "🔍 تحليل المحاضرة وتحديد نوعها...")
        lecture_data = await _run_or_cancel(uid, analyze_lecture(text, dialect))
        sections = lecture_data.get("sections", [])
        if not sections: raise RuntimeError("لا أقسام")
        n_sec, ltype = len(sections), lecture_data.get("lecture_type", "other")
        await upd(30, f"✅ {n_sec} أقسام")
        await upd(40, "🖼️ جلب الصور التوضيحية...")
        for s in sections:
            if not s.get("_image_bytes"):
                kw = s.get("keywords", ["مفهوم"])[:3]
                s["_image_bytes"] = await fetch_image_for_keyword(" ".join(kw), s.get("title", ""), ltype)
        await upd(55, "✅ الصور جاهزة")
        await upd(60, "🎤 توليد الصوت الاحترافي...")
        voice_res = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
        audio_results = voice_res["results"]
        await upd(75, "✅ الصوت جاهز")
        await upd(80, "🎬 إنتاج الفيديو بأسلوب Osmosis...")
        fd, video_path = tempfile.mkstemp(prefix=f"vid_{uid}_", suffix=".mp4", dir=TEMP_DIR); os.close(fd)
        total_secs = await create_video_from_sections(sections, audio_results, lecture_data, video_path, dialect)
        await upd(95, "✅ الفيديو جاهز")
        decrement_attempts(uid); increment_total_videos(uid); update_video_request(req_id, "done", video_path)
        elapsed = time.time() - t_start; title = lecture_data.get("title", "محاضرة")
        vid_min, vid_sec = int(total_secs//60), int(total_secs%60); remaining = get_user(uid)["attempts_left"]
        caption = f"🎬 *{title}*\n\n📚 أقسام: {n_sec}\n⏱️ {vid_min}:{vid_sec:02d}\n💳 محاولات: {remaining}"
        with open(video_path, "rb") as vf: await context.bot.send_video(chat_id=uid, video=vf, caption=caption, parse_mode="Markdown")
        await prog_msg.delete(); await context.bot.send_message(uid, "✅ *تم بنجاح!* 🎓", parse_mode="Markdown", reply_markup=main_keyboard())
    except asyncio.CancelledError:
        update_video_request(req_id, "cancelled"); await context.bot.send_message(uid, "⛔ تم الإلغاء.", reply_markup=main_keyboard())
    except Exception as e:
        update_video_request(req_id, "failed"); logger.error(f"Error: {e}")
        await _safe_edit(prog_msg, f"❌ خطأ: {str(e)[:200]}"); await context.bot.send_message(uid, "❌ حاول مرة أخرى.", reply_markup=main_keyboard())
    finally:
        _active_jobs.pop(uid, None); _active_tasks.pop(uid, None); _cancel_flags.pop(uid, None)
        if video_path and os.path.exists(video_path):
            try: os.remove(video_path)
            except: pass

async def main():
    init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, receive_content))
    async with app:
        await app.start()
        if os.getenv("WEBHOOK_URL"): await app.bot.set_webhook(url=f"{os.getenv('WEBHOOK_URL')}/telegram")
        else: await app.updater.start_polling()
        await asyncio.Event().wait()
        await app.stop()

if __name__ == "__main__": asyncio.run(main())
