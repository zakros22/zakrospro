import asyncio
import os
import logging
import tempfile
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

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
    get_stats,
    get_all_users,
    save_video_request,
    update_video_request,
    record_referral,
    get_referral_stats,
)
from ai_analyzer import (
    analyze_lecture,
    extract_full_text_from_pdf,
    extract_full_text_from_pdf_path,
    fetch_image_for_keyword,
    QuotaExhaustedError,
)
from voice_generator import generate_sections_audio, keys_status
from video_creator import create_video_from_sections, estimate_encoding_seconds
from pdf_generator import create_pdf_summary
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

# ═════════════════════════════════════════════════════════════════════════════
# 🧵 Thread Pool للعمليات الثقيلة
# ═════════════════════════════════════════════════════════════════════════════
_thread_pool = ThreadPoolExecutor(max_workers=4)

# ═════════════════════════════════════════════════════════════════════════════
# 📊 State Machine
# ═════════════════════════════════════════════════════════════════════════════
user_states: dict[int, dict] = {}

# ═════════════════════════════════════════════════════════════════════════════
# 🔄 Queue System - معالجة متوازية
# ═════════════════════════════════════════════════════════════════════════════
_Q_SEM = asyncio.Semaphore(3)
_active_jobs: dict[int, str] = {}
_active_tasks: dict[int, asyncio.Task] = {}
_cancel_flags: dict[int, asyncio.Event] = {}

CANCEL_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("❌ إلغاء المعالجة", callback_data="cancel_job")
]])


async def _run_or_cancel(uid: int, coro) -> object:
    """تنفيذ مهمة مع إمكانية الإلغاء"""
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


# ═════════════════════════════════════════════════════════════════════════════
# 🌍 لهجات
# ═════════════════════════════════════════════════════════════════════════════
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
    [
        InlineKeyboardButton("🇺🇸 English", callback_data="dial_english"),
        InlineKeyboardButton("🇬🇧 British", callback_data="dial_british"),
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


# ═════════════════════════════════════════════════════════════════════════════
# ⌨️ لوحة المفاتيح
# ═════════════════════════════════════════════════════════════════════════════
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


# ═════════════════════════════════════════════════════════════════════════════
# 👤 إدارة المستخدم
# ═════════════════════════════════════════════════════════════════════════════
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


# ═════════════════════════════════════════════════════════════════════════════
# 🚀 /start
# ═════════════════════════════════════════════════════════════════════════════
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
        "🎓 أنا *بوت المحاضرات الذكي* — أحوّل محاضرتك إلى فيديو تعليمي احترافي!\n\n"
        "📥 *ما يمكنك إرساله:*\n"
        "• ملف PDF 📄 (حتى 50MB)\n"
        "• ملف نصي TXT 📃\n"
        "• نص المحاضرة مباشرة ✍️\n\n"
        "🌍 اختر لهجة الشرح\n"
        "🎬 استلم فيديو كامل + PDF ملخص\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية\n\n"
        "⬇️ ابدأ الآن — أرسل المحاضرة!",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


# ═════════════════════════════════════════════════════════════════════════════
# ❓ /help
# ═════════════════════════════════════════════════════════════════════════════
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ أرسل ملف PDF أو TXT أو نص\n"
        "2️⃣ اختر لهجة الشرح\n"
        "3️⃣ انتظر المعالجة\n"
        "4️⃣ استلم الفيديو + PDF الملخص\n\n"
        "/cancel — إلغاء العملية",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


# ═════════════════════════════════════════════════════════════════════════════
# ⛔ /cancel
# ═════════════════════════════════════════════════════════════════════════════
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_states.pop(uid, None)
    ev = _cancel_flags.get(uid)
    if ev and not ev.is_set():
        ev.set()
        await update.message.reply_text("⛔ تم إلغاء المعالجة.", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("✅ لا توجد عملية جارية.", reply_markup=main_keyboard())


# ═════════════════════════════════════════════════════════════════════════════
# 💳 رصيدي
# ═════════════════════════════════════════════════════════════════════════════
async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return
    await update.message.reply_text(
        f"💳 *رصيدك*\n\n"
        f"🎬 المحاولات المتبقية: *{user['attempts_left']}*\n"
        f"📊 إجمالي الفيديوهات: {user['total_videos']}",
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard(user["user_id"]),
    )


# ═════════════════════════════════════════════════════════════════════════════
# 🔗 /referral
# ═════════════════════════════════════════════════════════════════════════════
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
        f"🔗 *رابط الإحالة*\n\n"
        f"`{ref_link}`\n\n"
        f"👥 المدعوين: *{stats['total_referrals']}*\n"
        f"⭐ النقاط: *{stats['current_points']}*",
        parse_mode="Markdown",
    )


# ═════════════════════════════════════════════════════════════════════════════
# 📥 استقبال المحتوى
# ═════════════════════════════════════════════════════════════════════════════
async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return

    uid = update.effective_user.id
    msg = update.message

    # Admin
    if is_owner(uid):
        consumed = await handle_admin_text_search(update, context)
        if consumed:
            return

    # أزرار القائمة
    if msg.text:
        text = msg.text.strip()
        if text == "📤 رفع محاضرة":
            await msg.reply_text("📤 أرسل ملف PDF أو TXT أو نص مباشر:", reply_markup=ReplyKeyboardRemove())
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

    # هل يوجد معالجة جارية؟
    if uid in _active_jobs:
        await msg.reply_text("⏳ محاضرتك قيد المعالجة...")
        return

    # التحقق من المحاولات
    if user["attempts_left"] <= 0:
        await send_payment_required_message(update, context)
        return

    # نص مباشر
    if msg.text and len(msg.text.strip()) >= 200:
        lecture_text = msg.text.strip()
        words = len(lecture_text.split())
        user_states[uid] = {"state": "awaiting_dialect", "text": lecture_text, "filename": "lecture"}
        await msg.reply_text(f"✅ *تم استلام النص!* ({words:,} كلمة)\n\nاختر اللهجة:", parse_mode="Markdown", reply_markup=DIALECT_KEYBOARD)
        return

    # ملف
    if msg.document:
        doc = msg.document
        fname = doc.file_name or "file"
        file_size = doc.file_size or 0
        ext = fname.lower().split(".")[-1] if "." in fname else ""

        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ أرسل PDF أو TXT فقط.")
            return

        if file_size > 50 * 1024 * 1024:
            await msg.reply_text("⚠️ حجم الملف كبير (حد أقصى 50MB)")
            return

        # رد فوري
        status = await msg.reply_text(f"📥 جاري تحميل `{fname}`...", parse_mode="Markdown")
        
        # معالجة في الخلفية
        asyncio.create_task(_process_document(update, context, doc, fname, ext, uid, status))
        return

    await msg.reply_text("⚠️ أرسل PDF، TXT، أو نص (200 حرف على الأقل)")


async def _process_document(update, context, doc, fname, ext, uid, status):
    """معالجة الملف في الخلفية"""
    try:
        file = await context.bot.get_file(doc.file_id)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp_path = tmp.name
        
        await file.download_to_drive(tmp_path)
        await status.edit_text(f"📥 تم التحميل\n🔍 استخراج النص...")
        
        if ext == "pdf":
            lecture_text = await extract_full_text_from_pdf_path(tmp_path)
            filename = fname.replace(".pdf", "")
        else:
            with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                lecture_text = f.read()
            filename = fname.replace(".txt", "")
        
        os.unlink(tmp_path)
        
        if not lecture_text or len(lecture_text.strip()) < 50:
            await status.edit_text("❌ لم يتم استخراج نص كافٍ")
            return
        
        user_states[uid] = {"state": "awaiting_dialect", "text": lecture_text, "filename": filename}
        words = len(lecture_text.split())
        
        est = "2-3 دقائق" if words < 500 else "3-5 دقائق" if words < 1500 else "5-7 دقائق"
        
        await status.edit_text(
            f"✅ تم استخراج *{words:,}* كلمة\n⏱️ الوقت المتوقع: *{est}*\n\nاختر اللهجة:",
            parse_mode="Markdown",
            reply_markup=DIALECT_KEYBOARD,
        )
        
    except Exception as e:
        await status.edit_text(f"❌ خطأ: {str(e)[:100]}")


# ═════════════════════════════════════════════════════════════════════════════
# 🔘 Callback Handler
# ═════════════════════════════════════════════════════════════════════════════
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

    if data == "cancel_job":
        ev = _cancel_flags.get(uid)
        if ev and not ev.is_set():
            ev.set()
            await q.edit_message_text("⛔ تم الإلغاء.")
        return

    if data == "show_referral":
        stats = get_referral_stats(uid)
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
        await q.message.reply_text(f"🔗 *رابطك*\n`{ref_link}`\n👥 {stats['total_referrals']} | ⭐ {stats['current_points']}", parse_mode="Markdown")
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

        await q.edit_message_text(
            f"🎬 *بدأت المعالجة!*\n🌍 {dial_name}\n\n{_pbar(0)} 0%\n🔍 جاري التحليل...",
            parse_mode="Markdown",
            reply_markup=CANCEL_KB,
        )

        text = state["text"]
        filename = state.get("filename", "lecture")
        user_states.pop(uid, None)

        task = asyncio.create_task(_process_lecture(uid, text, filename, dialect, q.message, context))
        _active_tasks[uid] = task
        return


# ═════════════════════════════════════════════════════════════════════════════
# 🎬 معالجة المحاضرة الرئيسية
# ═════════════════════════════════════════════════════════════════════════════
async def _process_lecture(
    uid: int,
    text: str,
    filename: str,
    dialect: str,
    status_msg,
    context: ContextTypes.DEFAULT_TYPE,
):
    _active_jobs[uid] = "processing"
    cancel_ev = asyncio.Event()
    _cancel_flags[uid] = cancel_ev
    req_id = save_video_request(uid, "text", dialect)
    t_start = time.time()
    video_path = None
    pdf_path = None

    def _check():
        if cancel_ev.is_set():
            raise asyncio.CancelledError()

    async def upd(pct: int, label: str):
        elapsed = time.time() - t_start
        await _safe_edit(
            status_msg,
            f"⏳ *المعالجة*\n\n{_pbar(pct)} *{pct}%*\n{label}\n\n⏱️ {_fmt_elapsed(elapsed)}",
            reply_markup=CANCEL_KB,
        )

    async with _Q_SEM:
        try:
            # 1. تحليل المحاضرة
            _check()
            await upd(5, "🔍 تحليل المحاضرة...")
            
            lecture_data = await _run_or_cancel(uid, analyze_lecture(text, dialect))
            sections = lecture_data.get("sections", [])
            
            if not sections:
                raise RuntimeError("لم يتم استخراج أقسام")
            
            n_sections = len(sections)
            await upd(25, f"✅ تم التحليل — {n_sections} أقسام")

            # 2. جلب الصور
            _check()
            await upd(30, "🎨 جلب الصور...")

            async def fetch_images(section):
                keywords = section.get("keywords", [])[:4]
                kw_descs = section.get("keyword_images", [])
                tasks = [
                    fetch_image_for_keyword(
                        keyword=kw,
                        section_title=section.get("title", ""),
                        lecture_type=lecture_data.get("lecture_type", "other"),
                        image_search_en=kw_descs[i] if i < len(kw_descs) else kw,
                    )
                    for i, kw in enumerate(keywords)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                section["_keyword_images"] = [r if not isinstance(r, Exception) else None for r in results]
                section["_image_bytes"] = next((r for r in results if r and not isinstance(r, Exception)), None)
                return section

            sections = await asyncio.gather(*[fetch_images(s) for s in sections])
            await upd(50, "✅ تم جلب الصور")

            # 3. توليد الصوت
            _check()
            await upd(55, "🎤 توليد الصوت...")
            
            voice_res = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
            audio_results = voice_res["results"]
            await upd(70, "✅ تم توليد الصوت")

            # 4. إنشاء الفيديو
            _check()
            await upd(75, "🎬 إنتاج الفيديو...")

            fd, video_path = tempfile.mkstemp(prefix=f"vid_{uid}_", suffix=".mp4", dir=TEMP_DIR)
            os.close(fd)

            async def v_progress(elapsed, est):
                pct = int(75 + min(elapsed / max(est, 1), 0.95) * 20)
                await upd(pct, "🎬 تشفير الفيديو...")

            total_secs = await create_video_from_sections(
                sections=sections,
                audio_results=audio_results,
                lecture_data=lecture_data,
                output_path=video_path,
                dialect=dialect,
                progress_cb=v_progress,
            )

            await upd(95, "📄 إنشاء PDF...")

            # 5. إنشاء PDF
            pdf_path = os.path.join(TEMP_DIR, f"summary_{uid}_{int(time.time())}.pdf")
            await create_pdf_summary(lecture_data, sections, pdf_path, dialect)

            await upd(99, "✅ اكتمل! جاري الإرسال...")

            # 6. خصم محاولة وإرسال
            decrement_attempts(uid)
            increment_total_videos(uid)
            update_video_request(req_id, "done", video_path, pdf_path)

            elapsed = time.time() - t_start
            title = lecture_data.get("title", filename)
            mins, secs = int(total_secs // 60), int(total_secs % 60)
            remaining = get_user(uid)["attempts_left"]

            # إرسال الفيديو
            caption = (
                f"🎬 *{title}*\n\n"
                f"🌍 {DIALECT_NAMES.get(dialect, dialect)}\n"
                f"📚 {n_sections} أقسام\n"
                f"⏱️ {mins}:{secs:02d}\n"
                f"⚡ {_fmt_elapsed(elapsed)}\n\n"
                f"💳 المتبقي: {remaining}"
            )

            with open(video_path, "rb") as vf:
                await context.bot.send_video(
                    chat_id=uid,
                    video=vf,
                    caption=caption,
                    parse_mode="Markdown",
                    supports_streaming=True,
                )

            # إرسال PDF
            with open(pdf_path, "rb") as pf:
                await context.bot.send_document(
                    chat_id=uid,
                    document=pf,
                    filename=f"{filename}_summary.pdf",
                    caption="📄 *ملخص المحاضرة*\n\nيحتوي على:\n• ملخص كامل\n• النقاط الرئيسية\n• جميع الأقسام مع الصور",
                    parse_mode="Markdown",
                )

            await status_msg.delete()
            await context.bot.send_message(
                uid,
                "✅ *تم بنجاح!*\n\n🎬 الفيديو + 📄 PDF\n\nشارك المعرفة مع أصدقائك 🎓",
                parse_mode="Markdown",
                reply_markup=main_keyboard(),
            )

        except asyncio.CancelledError:
            update_video_request(req_id, "cancelled")
            await status_msg.edit_text("⛔ تم الإلغاء.")

        except QuotaExhaustedError:
            update_video_request(req_id, "quota_error")
            await status_msg.edit_text("⏳ الخدمة مشغولة... حاول بعد قليل.")

        except Exception as e:
            update_video_request(req_id, "failed")
            logger.error(f"Error: {e}")
            await status_msg.edit_text(f"❌ خطأ: {str(e)[:200]}")

        finally:
            _active_jobs.pop(uid, None)
            _active_tasks.pop(uid, None)
            _cancel_flags.pop(uid, None)
            if video_path and os.path.exists(video_path):
                try:
                    os.remove(video_path)
                except:
                    pass
            if pdf_path and os.path.exists(pdf_path):
                try:
                    os.remove(pdf_path)
                except:
                    pass


# ═════════════════════════════════════════════════════════════════════════════
# 👑 Admin
# ═════════════════════════════════════════════════════════════════════════════
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    await handle_admin_command(update, context)


# ═════════════════════════════════════════════════════════════════════════════
# 🚀 Main
# ═════════════════════════════════════════════════════════════════════════════
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

    logger.info("✅ Bot ready")

    app_url = os.getenv("HEROKU_APP_NAME", "")
    webhook_url = f"https://{app_url}.herokuapp.com/telegram" if app_url else os.getenv("WEBHOOK_URL", "").rstrip("/")

    async with app:
        await app.start()

        if webhook_url:
            await app.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            logger.info(f"✅ Webhook: {webhook_url}")
            try:
                import web_server as _ws
                _ws.set_bot_app(app)
            except:
                pass
            await asyncio.Event().wait()
        else:
            logger.info("🔄 Polling...")
            await app.updater.start_polling(drop_pending_updates=True)
            await asyncio.Event().wait()
            await app.updater.stop()

        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
