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
    clean_text,
    _detect_lecture_type,  # ✅ الاسم الصحيح
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
# المتغيرات العامة
# ═══════════════════════════════════════════════════════════════════════════════

user_states = {}
_Q_SEM = asyncio.Semaphore(2)
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
    "iraq": "🇮🇶 عراقي",
    "egypt": "🇪🇬 مصري",
    "syria": "🇸🇾 شامي",
    "gulf": "🇸🇦 خليجي",
    "msa": "📚 فصحى",
}

LECTURE_TYPE_NAMES = {
    'medicine': '🩺 طبية',
    'math': '📐 رياضيات',
    'physics': '⚡ فيزياء',
    'chemistry': '🧪 كيمياء',
    'history': '📜 تاريخ',
    'biology': '🧬 أحياء',
    'other': '📚 تعليمية'
}


def main_keyboard():
    return ReplyKeyboardMarkup(
        [["📤 رفع محاضرة", "📊 رصيدي"], ["🔗 رابط الإحالة", "❓ مساعدة"]],
        resize_keyboard=True,
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
# أوامر البوت
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

    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 أهلاً *{name}*!\n\n"
        "🎓 أنا *بوت المحاضرات الذكي*\n"
        "أحوّل محاضرتك إلى فيديو تعليمي احترافي!\n\n"
        "📥 أرسل:\n"
        "• ملف PDF 📄\n"
        "• ملف TXT 📃\n"
        "• نص المحاضرة مباشرة ✍️\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة\n\n"
        "⬇️ أرسل المحاضرة الآن!",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ أرسل ملف PDF أو نص المحاضرة\n"
        "2️⃣ اختر لهجة الشرح\n"
        "3️⃣ انتظر المعالجة\n"
        "4️⃣ استلم الفيديو\n\n"
        "/referral - رابط الإحالة\n"
        "/cancel - إلغاء العملية",
        parse_mode="Markdown",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_states.pop(uid, None)
    ev = _cancel_flags.get(uid)
    if ev and not ev.is_set():
        ev.set()
        await update.message.reply_text("⛔ تم إلغاء المعالجة.", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("✅ لا توجد عملية جارية.")


async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return
    await update.message.reply_text(
        f"💳 *رصيدك*\n\n"
        f"🎬 المحاولات: *{user['attempts_left']}*\n"
        f"📊 الفيديوهات: {user['total_videos']}",
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard(user["user_id"]),
    )


async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return
    uid = update.effective_user.id
    stats = get_referral_stats(uid)
    bot = await context.bot.get_me()
    ref_link = f"https://t.me/{bot.username}?start=ref_{uid}"

    await update.message.reply_text(
        f"🔗 *رابط الإحالة*\n\n`{ref_link}`\n\n"
        f"👥 دعوت: *{stats['total_referrals']}*\n"
        f"⭐ نقاط: *{stats['current_points']}*\n\n"
        "كل 10 أشخاص = محاولة مجانية!",
        parse_mode="Markdown",
    )


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
        consumed = await handle_admin_text_search(update, context)
        if consumed:
            return

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
        await msg.reply_text("⏳ جاري المعالجة...")
        return

    lecture_text = None
    filename = "lecture"

    if msg.document:
        fname = msg.document.file_name or ""
        ext = fname.lower().split(".")[-1] if "." in fname else ""
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ أرسل PDF أو TXT فقط.")
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
            await wait.edit_text(f"❌ خطأ: {e}")
            return

    elif msg.text and len(msg.text.strip()) >= 200:
        lecture_text = msg.text.strip()

    else:
        await msg.reply_text("⚠️ أرسل ملف PDF أو نص (200 حرف على الأقل)")
        return

    # تنظيف النص
    lecture_text = clean_text(lecture_text)

    if not lecture_text or len(lecture_text) < 50:
        await msg.reply_text("❌ لم أتمكن من استخراج نص.")
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
    detected = _detect_lecture_type(lecture_text)  # ✅ استخدام الاسم الصحيح
    type_name = LECTURE_TYPE_NAMES.get(detected, '📚 تعليمية')

    await msg.reply_text(
        f"✅ *تم الاستلام!*\n\n"
        f"📝 كلمات: {words:,}\n"
        f"🔍 النوع: {type_name}\n\n"
        "اختر لهجة الشرح:",
        parse_mode="Markdown",
        reply_markup=DIALECT_KEYBOARD,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Callback Handler
# ═══════════════════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id

    if data.startswith("admin_"):
        await handle_admin_callback(update, context)
        return

    await q.answer()

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
            await q.edit_message_text("⛔ تم الإلغاء.")
        return

    if data == "show_referral":
        stats = get_referral_stats(uid)
        bot = await context.bot.get_me()
        ref_link = f"https://t.me/{bot.username}?start=ref_{uid}"
        await q.message.reply_text(
            f"🔗 *رابطك*\n`{ref_link}`\n👥 {stats['total_referrals']} شخص",
            parse_mode="Markdown",
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
            parse_mode="Markdown",
        )

        text = state["text"]
        filename = state.get("filename", "lecture")
        user_states.pop(uid, None)

        task = asyncio.create_task(_process_lecture(uid, text, filename, dialect, prog_msg, context))
        _active_tasks[uid] = task
        return


# ═══════════════════════════════════════════════════════════════════════════════
# معالجة المحاضرة
# ═══════════════════════════════════════════════════════════════════════════════

async def _process_lecture(uid, text, filename, dialect, prog_msg, context):
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
            f"⏳ *معالجة...*\n\n{_pbar(pct)} *{pct}%*\n{label}\n\n⏱️ {_fmt_elapsed(elapsed)}",
            reply_markup=CANCEL_KB,
        )

    try:
        # تحليل
        await upd(10, "🔍 تحليل المحاضرة...")
        lecture_data = await _run_or_cancel(uid, analyze_lecture(text, dialect))

        sections = lecture_data.get("sections", [])
        if not sections:
            raise RuntimeError("لم يتم استخراج أقسام")

        lecture_type = lecture_data.get("lecture_type", "other")
        n_sec = len(sections)
        await upd(30, f"✅ {n_sec} أقسام")

        # صور
        await upd(40, "🖼️ جلب الصور...")
        for s in sections:
            if not s.get("_image_bytes"):
                kw = s.get("keywords", ["مفهوم"])[:3]
                s["_image_bytes"] = await fetch_image_for_keyword(" ".join(kw), s.get("title", ""), lecture_type)
        await upd(55, "✅ الصور جاهزة")

        # صوت
        await upd(60, "🎤 توليد الصوت...")
        voice_res = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
        audio_results = voice_res["results"]
        await upd(75, "✅ الصوت جاهز")

        # فيديو
        await upd(80, "🎬 إنتاج الفيديو...")
        fd, video_path = tempfile.mkstemp(prefix=f"vid_{uid}_", suffix=".mp4", dir=TEMP_DIR)
        os.close(fd)

        total_secs = await create_video_from_sections(
            sections=sections,
            audio_results=audio_results,
            lecture_data=lecture_data,
            output_path=video_path,
            dialect=dialect,
        )
        await upd(95, "✅ الفيديو جاهز")

        # إرسال
        decrement_attempts(uid)
        increment_total_videos(uid)
        update_video_request(req_id, "done", video_path)

        elapsed = time.time() - t_start
        title = lecture_data.get("title", filename)
        vid_min, vid_sec = int(total_secs // 60), int(total_secs % 60)
        remaining = get_user(uid)["attempts_left"]

        caption = f"🎬 *{title}*\n\n📚 أقسام: {n_sec}\n⏱️ {vid_min}:{vid_sec:02d}\n💳 محاولات: {remaining}"

        with open(video_path, "rb") as vf:
            await context.bot.send_video(chat_id=uid, video=vf, caption=caption, parse_mode="Markdown")

        await prog_msg.delete()
        await context.bot.send_message(uid, "✅ *تم بنجاح!* 🎓", parse_mode="Markdown", reply_markup=main_keyboard())

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
# Admin & Main
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    await handle_admin_command(update, context)


async def main():
    init_db()
    logger.info("🤖 Bot starting...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

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
