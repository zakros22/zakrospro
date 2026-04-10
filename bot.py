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
    _detect_type,
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

user_states: dict[int, dict] = {}
_Q_SEM = asyncio.Semaphore(2)           # يمنع تشغيل أكثر من عمليتين في نفس الوقت
_active_jobs: dict[int, str] = {}       # uid -> status
_active_tasks: dict[int, asyncio.Task] = {}  # uid -> Task
_cancel_flags: dict[int, asyncio.Event] = {}  # uid -> Event للإلغاء

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


# ═══════════════════════════════════════════════════════════════════════════════
# الحل الجذري لمشكلة التوقف - دالة _run_or_cancel
# ═══════════════════════════════════════════════════════════════════════════════

async def _run_or_cancel(uid: int, coro):
    """
    تشغيل كوروتين مع إمكانية الإلغاء من قبل المستخدم.
    هذا يحل مشكلة توقف البوت لأن العملية تعمل في الخلفية.
    """
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


# ═══════════════════════════════════════════════════════════════════════════════
# دوال مساعدة
# ═══════════════════════════════════════════════════════════════════════════════

async def ensure_user(update: Update) -> dict | None:
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
        except ValueError:
            pass

    user = await ensure_user(update)
    if not user:
        return

    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 أهلاً *{name}*!\n\n"
        "🎓 أنا *بوت المحاضرات الذكي*\n"
        "أحوّل محاضرتك إلى فيديو تعليمي احترافي بأسلوب Osmosis!\n\n"
        "📥 أرسل:\n"
        "• ملف PDF 📄\n"
        "• ملف TXT 📃\n"
        "• نص المحاضرة مباشرة ✍️\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية\n\n"
        "⬇️ أرسل المحاضرة الآن!",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ أرسل ملف PDF أو نص المحاضرة\n"
        "2️⃣ اختر لهجة الشرح\n"
        "3️⃣ انتظر - البوت سيحلل ويصنع الفيديو\n"
        "4️⃣ استلم الفيديو التعليمي\n\n"
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

    # Admin special replies
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

    # منع تشغيل أكثر من عملية للمستخدم نفسه
    if uid in _active_jobs:
        await msg.reply_text("⏳ لديك محاضرة قيد المعالجة، انتظر حتى تنتهي...")
        return

    lecture_text = None
    filename = "lecture"

    # استلام الملف
    if msg.document:
        fname = msg.document.file_name or ""
        ext = fname.lower().split(".")[-1] if "." in fname else ""
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ أرسل ملف PDF أو TXT فقط.")
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
            await wait.edit_text(f"❌ خطأ في قراءة الملف: {e}")
            return

    elif msg.text and len(msg.text.strip()) >= 200:
        lecture_text = msg.text.strip()

    else:
        await msg.reply_text("⚠️ أرسل ملف PDF أو نص (200 حرف على الأقل)")
        return

    # تنظيف النص
    lecture_text = clean_text(lecture_text)

    if not lecture_text or len(lecture_text) < 50:
        await msg.reply_text("❌ لم أتمكن من استخراج نص كافٍ من الملف.")
        return

    if user["attempts_left"] <= 0:
        await send_payment_required_message(update, context)
        return

    # حفظ الحالة
    user_states[uid] = {
        "state": "awaiting_dialect",
        "text": lecture_text,
        "filename": filename,
    }

    words = len(lecture_text.split())
    detected = _detect_type(lecture_text)
    type_name = LECTURE_TYPE_NAMES.get(detected, '📚 تعليمية')

    await msg.reply_text(
        f"✅ *تم استلام المحاضرة!*\n\n"
        f"📝 عدد الكلمات: {words:,}\n"
        f"🔍 نوع المحتوى: {type_name}\n\n"
        "اختر لهجة الشرح:",
        parse_mode="Markdown",
        reply_markup=DIALECT_KEYBOARD,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Callback Handler - بدء المعالجة في الخلفية (حل مشكلة التوقف)
# ═══════════════════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id

    # Admin callbacks
    if data.startswith("admin_"):
        await handle_admin_callback(update, context)
        return

    await q.answer()

    # Payment callbacks
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

    # Cancel job
    if data == "cancel_job":
        ev = _cancel_flags.get(uid)
        if ev and not ev.is_set():
            ev.set()
            try:
                await q.edit_message_text("⛔ تم إلغاء المعالجة.")
            except Exception:
                pass
            await context.bot.send_message(uid, "⛔ تم الإلغاء.", reply_markup=main_keyboard())
        return

    # Show referral
    if data == "show_referral":
        stats = get_referral_stats(uid)
        bot = await context.bot.get_me()
        ref_link = f"https://t.me/{bot.username}?start=ref_{uid}"
        await q.message.reply_text(
            f"🔗 *رابطك*\n`{ref_link}`\n👥 {stats['total_referrals']} شخص",
            parse_mode="Markdown",
        )
        return

    # Dialect selection - THIS IS THE CRITICAL PART FOR BACKGROUND PROCESSING
    if data.startswith("dial_"):
        dialect = data[5:]
        state = user_states.get(uid, {})
        
        if state.get("state") != "awaiting_dialect":
            await q.edit_message_text("⚠️ أرسل المحاضرة أولاً.")
            return

        user = get_user(uid)
        if not user:
            await q.edit_message_text("⚠️ خطأ، أعد المحاولة.")
            return
        if user["attempts_left"] <= 0:
            await q.edit_message_text("❌ لا تملك محاولات كافية.")
            return

        dial_name = DIALECT_NAMES.get(dialect, dialect)
        
        # رسالة مؤقتة
        prog_msg = await q.edit_message_text(
            f"🎬 *بدأت المعالجة!*\n"
            f"🌍 اللهجة: {dial_name}\n\n"
            f"{_pbar(0)} 0%\n"
            f"🔍 جاري التحليل...",
            parse_mode="Markdown",
        )

        text = state["text"]
        filename = state.get("filename", "lecture")
        user_states.pop(uid, None)

        # ═══════════════════════════════════════════════════════════════════════
        # الحل الجذري: بدء المعالجة في الخلفية وعدم انتظارها
        # هذا يمنع Heroku من قتل العملية بسبب timeout
        # ═══════════════════════════════════════════════════════════════════════
        task = asyncio.create_task(
            _process_lecture(uid, text, filename, dialect, prog_msg, context)
        )
        _active_tasks[uid] = task
        return


# ═══════════════════════════════════════════════════════════════════════════════
# دالة المعالجة الرئيسية (تعمل في الخلفية)
# ═══════════════════════════════════════════════════════════════════════════════

async def _process_lecture(
    uid: int,
    text: str,
    filename: str,
    dialect: str,
    prog_msg,
    context: ContextTypes.DEFAULT_TYPE,
):
    _active_jobs[uid] = "processing"
    cancel_ev = asyncio.Event()
    _cancel_flags[uid] = cancel_ev
    req_id = save_video_request(uid, "text", dialect)
    t_start = time.time()
    video_path = None

    async def upd(pct: int, label: str):
        elapsed = time.time() - t_start
        await _safe_edit(
            prog_msg,
            f"⏳ *جاري المعالجة...*\n\n"
            f"{_pbar(pct)} *{pct}%*\n"
            f"{label}\n\n"
            f"⏱️ الوقت: {_fmt_elapsed(elapsed)}",
            reply_markup=CANCEL_KB,
        )

    async with _Q_SEM:
        try:
            # 1. تحليل المحاضرة
            await upd(10, "🔍 جاري تحليل المحاضرة وتحديد نوعها...")
            lecture_data = await _run_or_cancel(uid, analyze_lecture(text, dialect))

            sections = lecture_data.get("sections", [])
            if not sections:
                raise RuntimeError("لم يتم استخراج أي أقسام من المحاضرة")
            
            lecture_type = lecture_data.get("lecture_type", "other")
            n_sec = len(sections)
            await upd(30, f"✅ تم التحليل - {n_sec} أقسام")

            # 2. جلب الصور
            await upd(40, "🖼️ جاري جلب الصور التوضيحية...")
            for s in sections:
                if not s.get("_image_bytes"):
                    kw = s.get("keywords", ["مفهوم"])[:3]
                    s["_image_bytes"] = await fetch_image_for_keyword(
                        " ".join(kw), s.get("title", ""), lecture_type
                    )
            await upd(55, "✅ الصور جاهزة")

            # 3. توليد الصوت
            await upd(60, "🎤 جاري توليد الصوت الاحترافي...")
            voice_res = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
            audio_results = voice_res["results"]
            await upd(75, "✅ الصوت جاهز")

            # 4. إنتاج الفيديو
            await upd(80, "🎬 جاري إنتاج الفيديو بأسلوب Osmosis...")
            fd, video_path = tempfile.mkstemp(
                prefix=f"vid_{uid}_", suffix=".mp4", dir=TEMP_DIR
            )
            os.close(fd)

            total_secs = await create_video_from_sections(
                sections=sections,
                audio_results=audio_results,
                lecture_data=lecture_data,
                output_path=video_path,
                dialect=dialect,
            )
            await upd(95, "✅ الفيديو جاهز")

            # 5. خصم المحاولة وإرسال الفيديو
            decrement_attempts(uid)
            increment_total_videos(uid)
            update_video_request(req_id, "done", video_path)

            elapsed = time.time() - t_start
            title = lecture_data.get("title", filename)
            vid_min, vid_sec = int(total_secs // 60), int(total_secs % 60)
            remaining = get_user(uid)["attempts_left"]

            caption = (
                f"🎬 *{title}*\n\n"
                f"📚 الأقسام: {n_sec}\n"
                f"⏱️ المدة: {vid_min}:{vid_sec:02d}\n"
                f"💳 المحاولات المتبقية: {remaining}"
            )

            with open(video_path, "rb") as vf:
                await context.bot.send_video(
                    chat_id=uid,
                    video=vf,
                    caption=caption,
                    parse_mode="Markdown",
                    supports_streaming=True,
                )

            await prog_msg.delete()
            await context.bot.send_message(
                uid,
                "✅ *تم بنجاح!* 🎓\n\n"
                "الفيديو جاهز للمشاهدة. شارك المعرفة مع أصدقائك!",
                parse_mode="Markdown",
                reply_markup=main_keyboard(),
            )

        except asyncio.CancelledError:
            update_video_request(req_id, "cancelled")
            try:
                await prog_msg.edit_text("⛔ تم إلغاء المعالجة.")
            except Exception:
                pass
            await context.bot.send_message(uid, "⛔ تم الإلغاء.", reply_markup=main_keyboard())

        except Exception as e:
            update_video_request(req_id, "failed")
            logger.error(f"Video generation failed for user {uid}: {e}", exc_info=True)
            await _safe_edit(
                prog_msg,
                f"❌ *حدث خطأ*\n\n`{str(e)[:200]}`\n\nلم يتم خصم محاولتك، حاول مرة أخرى.",
            )
            await context.bot.send_message(
                uid,
                "❌ يمكنك المحاولة مجدداً.",
                reply_markup=main_keyboard(),
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


# ═══════════════════════════════════════════════════════════════════════════════
# Admin & Main
# ═══════════════════════════════════════════════════════════════════════════════

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    await handle_admin_command(update, context)


async def main():
    init_db()
    logger.info("🤖 Lecture video bot starting...")

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
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.Document.ALL) & ~filters.COMMAND,
            receive_content,
        )
    )

    logger.info("✅ Bot ready")

    webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")

    async with app:
        await app.start()

        if webhook_url:
            full_url = f"{webhook_url}/telegram"
            await app.bot.set_webhook(
                url=full_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "pre_checkout_query", "successful_payment"],
            )
            logger.info(f"✅ Webhook mode active → {full_url}")

            try:
                import web_server as _ws
                _ws.set_bot_app(app)
            except Exception as _e:
                logger.warning(f"Could not register webhook handler: {_e}")

            await asyncio.Event().wait()

        else:
            logger.info("🔄 Polling mode active (development)")
            await app.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "pre_checkout_query", "successful_payment"],
            )
            await asyncio.Event().wait()
            await app.updater.stop()

        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
