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
    extract_text_from_url,
    QuotaExhaustedError,
)
from voice_generator import generate_sections_audio, keys_status
from video_creator import create_video_from_sections, estimate_encoding_seconds
from image_generator import fetch_image_for_keyword, get_image_keys_status
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
    handle_user_info,
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
# 📝 إعدادات التسجيل
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# 🔄 State Machine
# ══════════════════════════════════════════════════════════════════════════════
user_states: dict[int, dict] = {}

# ══════════════════════════════════════════════════════════════════════════════
# 📊 Queue Management (حد أقصى 2 معالجة متزامنة)
# ══════════════════════════════════════════════════════════════════════════════
_Q_SEM = asyncio.Semaphore(2)
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


# ══════════════════════════════════════════════════════════════════════════════
# 🎛️ لوحة المفاتيح الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
def main_keyboard():
    return ReplyKeyboardMarkup(
        [["📤 رفع محاضرة", "📊 رصيدي"], ["🔗 رابط الإحالة", "❓ مساعدة"]],
        resize_keyboard=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 🌍 لهجات الشرح
# ══════════════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════════════
# 🛠️ دوال مساعدة
# ══════════════════════════════════════════════════════════════════════════════
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
    """التأكد من وجود المستخدم في قاعدة البيانات"""
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
                        f"✅ انضممت عبر رابط إحالة {name}!"
                    )
                except Exception:
                    pass
    if user.get("is_banned"):
        await update.effective_message.reply_text("⛔ أنت محظور من استخدام البوت.")
        return None
    return user


# ══════════════════════════════════════════════════════════════════════════════
# 🚀 /start
# ══════════════════════════════════════════════════════════════════════════════
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
        "• ملف PDF 📄\n"
        "• ملف نصي TXT 📃\n"
        "• رابط مقال 📎\n"
        "• نص المحاضرة مباشرة ✍️\n\n"
        "🌍 اختر لهجة الشرح (عراقي، مصري، خليجي...)\n"
        "🎬 استلم فيديو كامل مع صوت وصور\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية\n\n"
        "⬇️ ابدأ الآن — أرسل المحاضرة!",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


# ══════════════════════════════════════════════════════════════════════════════
# ❓ /help
# ══════════════════════════════════════════════════════════════════════════════
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ أرسل ملف PDF أو رابط أو نص المحاضرة\n"
        "2️⃣ اختر لهجة الشرح (عراقي، مصري، شامي، خليجي، فصحى)\n"
        "3️⃣ انتظر — البوت سيحلل ويصنع الفيديو\n"
        "4️⃣ استلم الفيديو التعليمي الكامل\n\n"
        "📊 *محتوى الفيديو:*\n"
        "• كروت تعليمية احترافية لكل قسم\n"
        "• صور تعليمية لكل موضوع\n"
        "• صوت بشري طبيعي\n"
        "• كلمات مفتاحية\n\n"
        "🔗 */referral* — رابط إحالة لكسب محاولات مجانية\n"
        "/cancel — إلغاء العملية",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


# ══════════════════════════════════════════════════════════════════════════════
# ⛔ /cancel
# ══════════════════════════════════════════════════════════════════════════════
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_states.pop(uid, None)
    ev = _cancel_flags.get(uid)
    if ev and not ev.is_set():
        ev.set()
        await update.message.reply_text("⛔ تم إلغاء المعالجة.", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("✅ لا توجد عملية جارية.", reply_markup=main_keyboard())


# ══════════════════════════════════════════════════════════════════════════════
# 💳 رصيدي
# ══════════════════════════════════════════════════════════════════════════════
async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return
    await update.message.reply_text(
        f"💳 *رصيدك*\n\n"
        f"🎬 المحاولات المتبقية: *{user['attempts_left']}*\n"
        f"📊 إجمالي الفيديوهات: {user.get('total_videos', 0)}\n\n"
        "للحصول على محاولات إضافية:",
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard(user["user_id"]),
    )


# ══════════════════════════════════════════════════════════════════════════════
# 🔗 /referral
# ══════════════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════════════
# 🛡️ /admin
# ══════════════════════════════════════════════════════════════════════════════
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    await handle_admin_command(update, context)


# ══════════════════════════════════════════════════════════════════════════════
# 📥 استقبال المحتوى
# ══════════════════════════════════════════════════════════════════════════════
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

    # أزرار لوحة المفاتيح
    if msg.text:
        text = msg.text.strip()
        if text == "📤 رفع محاضرة":
            await msg.reply_text(
                "📤 أرسل ملف PDF أو اكتب نص المحاضرة مباشرة:",
                reply_markup=ReplyKeyboardRemove(),
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

    # هل هناك معالجة جارية؟
    if uid in _active_jobs:
        await msg.reply_text("⏳ محاضرتك قيد المعالجة، انتظر قليلاً...")
        return

    # استخراج المحتوى
    lecture_text = None
    filename = "lecture"

    if msg.document:
        fname = msg.document.file_name or ""
        ext = fname.lower().split(".")[-1] if "." in fname else ""
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ أرسل ملف PDF أو TXT فقط.")
            return
        
        await context.bot.send_chat_action(uid, "upload_document")
        wait = await msg.reply_text(
            f"📥 *تم استلام الملف!* جاري القراءة...\n📄 `{fname}`",
            parse_mode="Markdown",
        )
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

    elif msg.text and len(msg.text.strip()) >= 100:
        text = msg.text.strip()
        if text.startswith("http://") or text.startswith("https://"):
            await msg.reply_text("🔗 جاري استخراج النص من الرابط...")
            try:
                lecture_text = await extract_text_from_url(text)
                filename = "article"
            except Exception as e:
                await msg.reply_text(f"❌ خطأ في قراءة الرابط: {e}")
                return
        else:
            lecture_text = text
            filename = "text"

    elif msg.text and len(msg.text.strip()) < 100:
        await msg.reply_text(
            "⚠️ النص قصير جداً.\n\n"
            "أرسل:\n"
            "• ملف PDF 📄\n"
            "• ملف TXT 📃\n"
            "• رابط مقال 📎\n"
            "• أو نص المحاضرة مباشرة (100 حرف على الأقل)"
        )
        return

    else:
        await msg.reply_text("⚠️ أرسل ملف PDF أو رابط أو نص المحاضرة.")
        return

    if not lecture_text or len(lecture_text.strip()) < 50:
        await msg.reply_text("❌ لم أتمكن من استخراج نص كافٍ. تأكد من أن المحتوى يحتوي على نص.")
        return

    # التحقق من المحاولات
    if user["attempts_left"] <= 0:
        await send_payment_required_message(update, context)
        return

    # حفظ الحالة وعرض خيارات اللهجة
    user_states[uid] = {
        "state": "awaiting_dialect",
        "text": lecture_text,
        "filename": filename,
    }

    words = len(lecture_text.split())
    await msg.reply_text(
        f"✅ *تم استلام المحاضرة!*\n\n"
        f"📝 عدد الكلمات: {words:,}\n\n"
        "🌍 اختر لهجة الشرح:",
        parse_mode="Markdown",
        reply_markup=DIALECT_KEYBOARD,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 🔘 معالج الأزرار
# ══════════════════════════════════════════════════════════════════════════════
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
    if data.startswith("sent_mastercard") or data.startswith("sent_crypto"):
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
        else:
            try:
                await context.bot.send_message(uid, "لا توجد عملية جارية الآن.")
            except Exception:
                pass
        return

    if data == "show_referral":
        stats = get_referral_stats(uid)
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
        await q.message.reply_text(
            f"🔗 *رابط الإحالة الخاص بك*\n\n"
            f"`{ref_link}`\n\n"
            f"👥 أصدقاء دعوتهم: *{stats['total_referrals']}*\n"
            f"⭐ نقاطك: *{stats['current_points']}*\n\n"
            f"📌 *كيف يعمل؟*\n"
            f"• شارك رابطك مع أصدقائك\n"
            f"• لكل 10 أصدقاء يسجلون = محاولة مجانية 🎉",
            parse_mode="Markdown",
        )
        return

    # Dialect selection
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
            f"🎬 *بدأت المعالجة!*\n"
            f"🌍 اللهجة: {dial_name}\n\n"
            f"{_pbar(0)} 0%\n"
            f"🔍 جاري تحليل المحاضرة...",
            parse_mode="Markdown",
        )

        text = state["text"]
        filename = state.get("filename", "lecture")
        user_states.pop(uid, None)

        task = asyncio.create_task(
            _process_lecture(uid, text, filename, dialect, prog_msg, context)
        )
        _active_tasks[uid] = task
        return


# ══════════════════════════════════════════════════════════════════════════════
# ⚙️ معالجة المحاضرة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
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
            f"⏳ *جاري المعالجة...*\n\n"
            f"{_pbar(pct)} *{pct}%*\n"
            f"{label}\n\n"
            f"⏱️ الوقت: {_fmt_elapsed(elapsed)}",
            reply_markup=CANCEL_KB,
        )

    async with _Q_SEM:
        try:
            # 1️⃣ تحليل المحاضرة
            _check_cancelled()
            await upd(5, "🔍 قراءة المحاضرة وتحليل المحتوى...")
            
            lecture_data = await _run_or_cancel(uid, analyze_lecture(text, dialect))
            
            sections = lecture_data.get("sections", [])
            if not sections:
                raise RuntimeError("لم يتم استخراج أي أقسام من المحاضرة")
            
            lecture_type = lecture_data.get("lecture_type", "other")
            await upd(20, f"✅ تم التحليل — {len(sections)} أقسام")

            # 2️⃣ جلب الصور
            _check_cancelled()
            await upd(22, "🎨 جلب الصور التعليمية...")
            
            _img_sem = asyncio.Semaphore(4)
            
            async def _fetch_one_section_images(section: dict):
                async with _img_sem:
                    keywords = section.get("keywords", [])[:4]
                    kw_img_descs = section.get("keyword_images", [])
                    
                    tasks = [
                        fetch_image_for_keyword(
                            keyword=kw,
                            section_title=section.get("title", ""),
                            lecture_type=lecture_type,
                            image_search_en=kw_img_descs[i] if i < len(kw_img_descs) else kw,
                        )
                        for i, kw in enumerate(keywords)
                    ]
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    section["_keyword_images"] = [
                        r if not isinstance(r, Exception) else None for r in results
                    ]
                    section["_image_bytes"] = next(
                        (r for r in results if not isinstance(r, Exception) and r),
                        None,
                    )
            
            await _run_or_cancel(uid, asyncio.gather(*[_fetch_one_section_images(s) for s in sections]))
            await upd(45, "✅ تم جلب الصور")

            # 3️⃣ توليد الصوت
            _check_cancelled()
            await upd(47, "🎤 توليد الصوت البشري...")
            
            voice_res = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
            audio_results = voice_res["results"]
            used_fallback = voice_res.get("used_fallback", False)
            
            voice_note = " (gTTS)" if used_fallback else " (ElevenLabs)"
            await upd(70, f"✅ تم توليد الصوت{voice_note}")

            # 4️⃣ إنشاء الفيديو
            _check_cancelled()
            await upd(72, "🎬 إنتاج الفيديو...")
            
            total_audio = sum(r.get("duration", 0) for r in audio_results)
            enc_est = estimate_encoding_seconds(total_audio)
            
            fd, video_path = tempfile.mkstemp(
                prefix=f"lecture_{uid}_", suffix=".mp4", dir=TEMP_DIR
            )
            os.close(fd)
            
            async def _video_progress(elapsed_enc: float, est_enc: float):
                frac = min(elapsed_enc / max(est_enc, 1), 0.95)
                pct = int(72 + frac * 26)
                elapsed = time.time() - t_start
                await _safe_edit(
                    prog_msg,
                    f"⏳ *جاري المعالجة...*\n\n"
                    f"{_pbar(pct)} *{pct}%*\n"
                    f"🎬 تشفير الفيديو...\n\n"
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

            # 5️⃣ خصم محاولة وإرسال الفيديو
            decrement_attempts(uid)
            increment_total_videos(uid)
            update_video_request(req_id, "done", video_path, processing_time=time.time() - t_start, sections_count=len(sections))
            
            elapsed_total = time.time() - t_start
            title = lecture_data.get("title", filename)
            n_sec = len(sections)
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
                "✅ *اكتمل الفيديو!*\nشارك المعرفة مع أصدقائك 🎓",
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

        except QuotaExhaustedError as e:
            update_video_request(req_id, "quota_error", error_message=str(e))
            await _safe_edit(
                prog_msg,
                "⏳ *الخدمة مشغولة حالياً*\n\n"
                "حدث ضغط على خوادم الذكاء الاصطناعي.\n"
                "✅ لم يتم خصم محاولتك — حاول مرة أخرى بعد دقائق قليلة.",
                parse_mode="Markdown",
            )
            try:
                await context.bot.send_message(
                    uid,
                    "أرسل المحاضرة مرة أخرى بعد قليل وسيعمل معك 🙂",
                    reply_markup=main_keyboard(),
                )
            except Exception:
                pass
            
            try:
                await context.bot.send_message(
                    OWNER_ID,
                    f"⚠️ *تنبيه Quota*\n\nالمستخدم: `{uid}`\n`{str(e)[:400]}`",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        except Exception as e:
            update_video_request(req_id, "failed", error_message=str(e))
            logger.error(f"Video generation failed for user {uid}: {e}", exc_info=True)
            await _safe_edit(
                prog_msg,
                f"❌ *حدث خطأ أثناء المعالجة*\n\n`{str(e)[:300]}`\n\n"
                "لم يتم خصم محاولتك، حاول مرة أخرى.",
            )
            await context.bot.send_message(
                uid,
                "يمكنك المحاولة مجدداً أو التواصل مع الدعم.",
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


# ══════════════════════════════════════════════════════════════════════════════
# 🚀 الدالة الرئيسية - POLLING MODE
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    init_db()
    logger.info("🤖 Zakros Lecture Bot starting...")
    
    # عرض حالة المفاتيح
    try:
        el_status = keys_status()
        logger.info(f"🔑 ElevenLabs keys: {el_status['active']}/{el_status['total']} active")
    except Exception as e:
        logger.info(f"🔑 ElevenLabs: not configured")
    
    try:
        img_status = get_image_keys_status()
        stability = img_status.get('stability', {})
        logger.info(f"🖼️ Stability keys: {stability.get('active', 0)}/{stability.get('total', 0)} active")
        logger.info(f"🖼️ Replicate: {'✅' if img_status.get('replicate', {}).get('available') else '❌'}")
        logger.info(f"🖼️ Pollinations: {'✅ (free)' if img_status.get('pollinations', {}).get('available') else '❌'}")
    except Exception as e:
        logger.info(f"🖼️ Image services: not configured")

    # بناء التطبيق
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("referral", referral_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("addattempts", handle_add_attempts))
    app.add_handler(CommandHandler("setattempts", handle_set_attempts))
    app.add_handler(CommandHandler("ban", handle_ban))
    app.add_handler(CommandHandler("unban", handle_unban))
    app.add_handler(CommandHandler("broadcast", handle_broadcast))
    app.add_handler(CommandHandler("userinfo", handle_user_info))

    # Payment handlers
    app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    
    # Callback handler
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # Content handler
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.Document.ALL) & ~filters.COMMAND,
            receive_content,
        )
    )

    logger.info("✅ Bot handlers registered")
    logger.info("🔄 Starting polling mode...")
    
    # حذف أي webhook قديم وبدء polling
    await app.initialize()
    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.start()
    
    logger.info("✅ Bot is running! Polling mode active.")
    logger.info("📡 Waiting for messages...")
    
    # بدء polling
    await app.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query", "pre_checkout_query", "successful_payment"],
    )
    
    # انتظار حتى يتم إيقاف البوت
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("🛑 Shutting down...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
