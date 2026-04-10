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

user_states: dict[int, dict] = {}
_Q_SEM = asyncio.Semaphore(2)
_active_jobs: dict[int, str] = {}
_active_tasks: dict[int, asyncio.Task] = {}
_cancel_flags: dict[int, asyncio.Event] = {}

CANCEL_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("❌ إلغاء المعالجة", callback_data="cancel_job")
]])

LECTURE_TYPE_NAMES = {
    'medicine': '🩺 محاضرة طبية',
    'math': '📐 محاضرة رياضيات',
    'physics': '⚡ محاضرة فيزياء',
    'chemistry': '🧪 محاضرة كيمياء',
    'history': '📜 محاضرة تاريخية',
    'biology': '🧬 محاضرة أحياء',
    'computer': '💻 محاضرة حاسوب',
    'other': '📚 محاضرة تعليمية'
}

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
        "🎓 أنا *بوت المحاضرات الذكي* - أحوّل محاضرتك إلى فيديو تعليمي احترافي بأسلول Osmosis!\n\n"
        "📥 *ما يمكنك إرساله:*\n"
        "• ملف PDF 📄\n"
        "• ملف نصي TXT 📃\n"
        "• نص المحاضرة مباشرة ✍️\n\n"
        "🌍 اختر لهجة الشرح (عراقي، مصري، خليجي...)\n"
        "🎬 استلم فيديو كامل مع:\n"
        "• سبورة بيضاء بأسلوب Osmosis\n"
        "• نصوص وكلمات مفتاحية واضحة\n"
        "• صور توضيحية بسيطة\n"
        "• صوت بشري طبيعي\n\n"
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
        "4️⃣ استلم الفيديو التعليمي بأسلوب Osmosis\n\n"
        "🎨 *مميزات الفيديو:*\n"
        "• سبورة بيضاء احترافية\n"
        "• نصوص وكلمات مفتاحية واضحة\n"
        "• صور توضيحية بسيطة\n"
        "• شرح صوتي باللهجة المختارة\n\n"
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
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ خطأ في قراءة الملف: {e}")
            return

    elif msg.text and len(msg.text.strip()) >= 200:
        lecture_text = msg.text.strip()

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


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id

    if data.startswith("admin_"):
        await handle_admin_callback(update, context)
        return

    await q.answer()

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

    if data == "cancel_job":
        ev = _cancel_flags.get(uid)
        if ev and not ev.is_set():
            ev.set()
            try:
                await q.edit_message_text("⛔ تم إلغاء المعالجة.\n\nأرسل محاضرة جديدة متى شئت.")
            except Exception:
                pass
            await context.bot.send_message(uid, "⛔ تم الإلغاء.", reply_markup=main_keyboard())
        return

    if data == "show_referral":
        stats = get_referral_stats(uid)
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
        await q.message.reply_text(
            f"🔗 *رابط الإحالة الخاص بك*\n\n`{ref_link}`\n\n"
            f"👥 أصدقاء دعوتهم: *{stats['total_referrals']}*\n"
            f"⭐ نقاطك: *{stats['current_points']}*\n\n"
            f"📌 *كيف يعمل؟*\n• شارك رابطك مع أصدقائك\n• لكل 10 أصدقاء يسجلون = محاولة مجانية لك 🎉",
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
        if not user:
            await q.edit_message_text("⚠️ خطأ، أعد المحاولة.")
            return
        if user["attempts_left"] <= 0:
            await q.edit_message_text("❌ لا تملك محاولات كافية.")
            return

        dial_name = DIALECT_NAMES.get(dialect, dialect)
        prog_msg = await q.edit_message_text(
            f"🎬 *بدأت المعالجة!*\n🌍 اللهجة: {dial_name}\n\n{_pbar(0)} 0%\n🔍 جاري بدء التحليل...",
            parse_mode="Markdown",
        )

        text = state["text"]
        filename = state.get("filename", "lecture")
        user_states.pop(uid, None)

        task = asyncio.create_task(_process_lecture(uid, text, filename, dialect, prog_msg, context))
        _active_tasks[uid] = task
        return


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

    def _check_cancelled():
        if cancel_ev.is_set():
            raise asyncio.CancelledError("User cancelled")

    async def upd(pct: int, label: str):
        elapsed = time.time() - t_start
        await _safe_edit(
            prog_msg,
            f"⏳ *جاري المعالجة...*\n\n{_pbar(pct)} *{pct}%*\n{label}\n\n⏱️ الوقت: {_fmt_elapsed(elapsed)}",
            reply_markup=CANCEL_KB,
        )

    async with _Q_SEM:
        try:
            _check_cancelled()

            # ─────────────────────────────────────────────────────────────────
            # المرحلة 1: تحليل المحاضرة
            # ─────────────────────────────────────────────────────────────────
            await upd(5, "🔍 جاري قراءة المحاضرة وتحليل المحتوى...")
            lecture_data = await analyze_lecture(text, dialect)

            sections = lecture_data.get("sections", [])
            if not sections:
                raise RuntimeError("لم يتم استخراج أي أقسام من المحاضرة")
            
            lecture_type = lecture_data.get("lecture_type", "other")
            n_sec = len(sections)
            
            await upd(25, f"✅ تم تحليل المحاضرة إلى {n_sec} أقسام")

            # ─────────────────────────────────────────────────────────────────
            # المرحلة 2: جلب الصور
            # ─────────────────────────────────────────────────────────────────
            _check_cancelled()
            await upd(30, "🖼️ جاري جلب الصور التوضيحية...")

            _img_sem = asyncio.Semaphore(6)
            total_images = sum(len(s.get("keywords", [])) for s in sections)
            images_done = [0]

            async def _fetch_section_images(section: dict):
                async with _img_sem:
                    keywords = section.get("keywords", [])[:4]
                    images = []
                    for kw in keywords:
                        try:
                            img_bytes = await fetch_image_for_keyword(
                                keyword=kw,
                                section_title=section.get("title", ""),
                                lecture_type=lecture_type,
                                image_search_en=kw
                            )
                            images.append(img_bytes)
                        except Exception as e:
                            print(f"Failed to fetch image for {kw}: {e}")
                            images.append(None)
                        images_done[0] += 1
                        
                        pct = 30 + int((images_done[0] / max(total_images, 1)) * 15)
                        await upd(pct, f"🖼️ جاري جلب الصور... ({images_done[0]}/{total_images})")
                    
                    section["_keyword_images"] = images
                    section["_image_bytes"] = images[0] if images else None

            await asyncio.gather(*[_fetch_section_images(s) for s in sections])
            await upd(45, f"✅ تم جلب {total_images} صورة توضيحية")

            # ─────────────────────────────────────────────────────────────────
            # المرحلة 3: توليد الصوت
            # ─────────────────────────────────────────────────────────────────
            _check_cancelled()
            await upd(50, "🎤 جاري توليد الصوت...")
            
            voice_res = await generate_sections_audio(sections, dialect)
            audio_results = voice_res["results"]
            
            await upd(70, f"✅ تم توليد الصوت لـ {len(audio_results)} أقسام")

            # ─────────────────────────────────────────────────────────────────
            # المرحلة 4: إنتاج الفيديو
            # ─────────────────────────────────────────────────────────────────
            _check_cancelled()
            await upd(75, "🎬 جاري إنتاج الفيديو...")

            fd, video_path = tempfile.mkstemp(prefix=f"lecture_{uid}_", suffix=".mp4", dir=TEMP_DIR)
            os.close(fd)

            async def _video_progress(elapsed_enc: float, est_enc: float):
                pct = int(75 + (elapsed_enc / max(est_enc, 1)) * 20)
                await upd(min(pct, 95), "🎬 جاري تشفير الفيديو...")

            total_video_secs = await create_video_from_sections(
                sections=sections,
                audio_results=audio_results,
                lecture_data=lecture_data,
                output_path=video_path,
                dialect=dialect,
                progress_cb=_video_progress,
            )

            await upd(99, "✅ اكتمل الفيديو، جاري الإرسال...")

            # ─────────────────────────────────────────────────────────────────
            # إرسال الفيديو
            # ─────────────────────────────────────────────────────────────────
            decrement_attempts(uid)
            increment_total_videos(uid)
            update_video_request(req_id, "done", video_path)

            elapsed_total = time.time() - t_start
            title = lecture_data.get("title", filename)
            vid_min = int(total_video_secs // 60)
            vid_sec = int(total_video_secs % 60)
            dial_name = DIALECT_NAMES.get(dialect, dialect)
            used_user = get_user(uid)
            remaining = used_user["attempts_left"] if used_user else 0

            caption = (
                f"🎬 *{title}*\n\n"
                f"🌍 اللهجة: {dial_name}\n"
                f"📚 الأقسام: {n_sec}\n"
                f"⏱️ مدة الفيديو: {vid_min}:{vid_sec:02d}\n"
                f"🕐 وقت المعالجة: {_fmt_elapsed(elapsed_total)}\n\n"
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
                "✅ *اكتمل الفيديو!*\n\n"
                "📹 تم إنتاج فيديو تعليمي احترافي بأسلوب Osmosis:\n"
                "• سبورة بيضاء نظيفة\n"
                "• نصوص وكلمات مفتاحية واضحة\n"
                "• صور توضيحية بسيطة\n"
                "• شرح صوتي باللهجة المختارة\n\n"
                "شارك المعرفة مع أصدقائك 🎓",
                parse_mode="Markdown",
                reply_markup=main_keyboard(),
            )

        except asyncio.CancelledError:
            update_video_request(req_id, "cancelled")
            try:
                await prog_msg.edit_text("⛔ تم إلغاء المعالجة.\n\nأرسل محاضرة جديدة متى شئت.")
            except Exception:
                pass
            await context.bot.send_message(uid, "⛔ تم الإلغاء.", reply_markup=main_keyboard())

        except Exception as e:
            update_video_request(req_id, "failed")
            error_msg = str(e)[:200]
            logger.error(f"Video generation failed for user {uid}: {e}", exc_info=True)
            await _safe_edit(
                prog_msg,
                f"❌ *حدث خطأ أثناء المعالجة*\n\n`{error_msg}`\n\nلم يتم خصم محاولتك، حاول مرة أخرى.",
            )
            await context.bot.send_message(uid, "يمكنك المحاولة مجدداً أو التواصل مع الدعم.", reply_markup=main_keyboard())

        finally:
            _active_jobs.pop(uid, None)
            _active_tasks.pop(uid, None)
            _cancel_flags.pop(uid, None)
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                except Exception:
                    pass


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
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, receive_content))

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
