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
    LECTURE_TYPES,
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
    extract_full_text_from_pdf_path,
    fetch_image_for_keyword,
    QuotaExhaustedError,
)
from voice_generator import generate_sections_audio, keys_status
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

# ============================================================
# إعدادات التسجيل
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# حالة المستخدمين والمهام النشطة
# ============================================================
user_states: dict[int, dict] = {}
_Q_SEM = asyncio.Semaphore(3)  # حد أقصى 3 معالجات متوازية
_active_jobs: dict[int, str] = {}
_active_tasks: dict[int, asyncio.Task] = {}
_cancel_flags: dict[int, asyncio.Event] = {}

CANCEL_KB = InlineKeyboardMarkup([[
    InlineKeyboardButton("❌ إلغاء المعالجة", callback_data="cancel_job")
]])

# ============================================================
# لوحات المفاتيح
# ============================================================

def main_keyboard():
    """لوحة المفاتيح الرئيسية"""
    return ReplyKeyboardMarkup(
        [["📤 رفع محاضرة", "📊 رصيدي"], ["🔗 رابط الإحالة", "❓ مساعدة"]],
        resize_keyboard=True,
    )


# لوحة مفاتيح اختيار اللهجة
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


def get_subject_keyboard() -> InlineKeyboardMarkup:
    """لوحة مفاتيح اختيار نوع المحاضرة"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🩺 طب", callback_data="subject_medicine"),
            InlineKeyboardButton("⚙️ هندسة", callback_data="subject_engineering"),
            InlineKeyboardButton("🔬 علوم", callback_data="subject_science"),
        ],
        [
            InlineKeyboardButton("📐 رياضيات", callback_data="subject_math"),
            InlineKeyboardButton("📖 أدب", callback_data="subject_literature"),
            InlineKeyboardButton("🏛️ تاريخ", callback_data="subject_history"),
        ],
        [
            InlineKeyboardButton("🕌 إسلامي", callback_data="subject_islamic"),
            InlineKeyboardButton("🎒 ابتدائي", callback_data="subject_primary"),
            InlineKeyboardButton("🎓 إعدادي", callback_data="subject_high"),
        ],
        [
            InlineKeyboardButton("📚 عام", callback_data="subject_other"),
        ],
    ])


SUBJECT_NAMES = {
    "medicine": "🩺 طب",
    "surgery": "🔪 جراحة",
    "pediatrics": "👶 أطفال",
    "dentistry": "🦷 أسنان",
    "pharmacy": "💊 صيدلة",
    "cardiology": "❤️ قلب",
    "neurology": "🧠 أعصاب",
    "engineering": "⚙️ هندسة",
    "civil": "🏗️ مدنية",
    "electrical": "⚡ كهربائية",
    "mechanical": "🔧 ميكانيكية",
    "aerospace": "🚀 فضاء",
    "software": "💻 برمجيات",
    "chemical": "🧪 كيميائية",
    "science": "🔬 علوم",
    "physics": "⚛️ فيزياء",
    "chemistry": "🧪 كيمياء",
    "biology": "🧬 أحياء",
    "astronomy": "🌌 فلك",
    "math": "📐 رياضيات",
    "literature": "📖 أدب",
    "history": "🏛️ تاريخ",
    "geography": "🌍 جغرافيا",
    "philosophy": "🤔 فلسفة",
    "psychology": "🧠 علم نفس",
    "economics": "📊 اقتصاد",
    "law": "⚖️ قانون",
    "islamic": "🕌 إسلامي",
    "quran": "📖 قرآن",
    "hadith": "📜 حديث",
    "fiqh": "📚 فقه",
    "aqeedah": "🕋 عقيدة",
    "tafseer": "📝 تفسير",
    "seerah": "🌟 سيرة",
    "primary": "🎒 ابتدائي",
    "middle": "📚 متوسط",
    "high": "🎓 إعدادي",
    "university": "🏛️ جامعي",
    "other": "📚 عام",
}


def get_detailed_subject_keyboard(main_subject: str) -> InlineKeyboardMarkup:
    """لوحة مفاتيح التخصصات التفصيلية"""
    keyboards = {
        "medicine": [
            [InlineKeyboardButton("🩺 طب عام", callback_data="subject_medicine")],
            [InlineKeyboardButton("🔪 جراحة", callback_data="subject_surgery")],
            [InlineKeyboardButton("👶 طب أطفال", callback_data="subject_pediatrics")],
            [InlineKeyboardButton("🦷 طب أسنان", callback_data="subject_dentistry")],
            [InlineKeyboardButton("💊 صيدلة", callback_data="subject_pharmacy")],
            [InlineKeyboardButton("❤️ قلب", callback_data="subject_cardiology")],
            [InlineKeyboardButton("🧠 أعصاب", callback_data="subject_neurology")],
            [InlineKeyboardButton("◀️ رجوع", callback_data="back_to_main")],
        ],
        "engineering": [
            [InlineKeyboardButton("⚙️ هندسة عامة", callback_data="subject_engineering")],
            [InlineKeyboardButton("🏗️ مدنية", callback_data="subject_civil")],
            [InlineKeyboardButton("⚡ كهربائية", callback_data="subject_electrical")],
            [InlineKeyboardButton("🔧 ميكانيكية", callback_data="subject_mechanical")],
            [InlineKeyboardButton("🚀 فضاء", callback_data="subject_aerospace")],
            [InlineKeyboardButton("💻 برمجيات", callback_data="subject_software")],
            [InlineKeyboardButton("🧪 كيميائية", callback_data="subject_chemical")],
            [InlineKeyboardButton("◀️ رجوع", callback_data="back_to_main")],
        ],
        "science": [
            [InlineKeyboardButton("🔬 علوم عامة", callback_data="subject_science")],
            [InlineKeyboardButton("⚛️ فيزياء", callback_data="subject_physics")],
            [InlineKeyboardButton("🧪 كيمياء", callback_data="subject_chemistry")],
            [InlineKeyboardButton("🧬 أحياء", callback_data="subject_biology")],
            [InlineKeyboardButton("🌌 فلك", callback_data="subject_astronomy")],
            [InlineKeyboardButton("◀️ رجوع", callback_data="back_to_main")],
        ],
        "islamic": [
            [InlineKeyboardButton("🕌 إسلامي عام", callback_data="subject_islamic")],
            [InlineKeyboardButton("📖 قرآن كريم", callback_data="subject_quran")],
            [InlineKeyboardButton("📜 حديث شريف", callback_data="subject_hadith")],
            [InlineKeyboardButton("📚 فقه", callback_data="subject_fiqh")],
            [InlineKeyboardButton("🕋 عقيدة", callback_data="subject_aqeedah")],
            [InlineKeyboardButton("📝 تفسير", callback_data="subject_tafseer")],
            [InlineKeyboardButton("🌟 سيرة", callback_data="subject_seerah")],
            [InlineKeyboardButton("◀️ رجوع", callback_data="back_to_main")],
        ],
    }
    
    if main_subject in keyboards:
        return InlineKeyboardMarkup(keyboards[main_subject])
    return get_subject_keyboard()


# ============================================================
# دوال مساعدة
# ============================================================
def _pbar(pct: int, width: int = 12) -> str:
    """شريط تقدم نصي"""
    filled = int(width * pct / 100)
    return "▓" * filled + "░" * (width - filled)


def _fmt_elapsed(sec: float) -> str:
    """تنسيق الوقت المنقضي"""
    if sec < 60:
        return f"{int(sec)} ثانية"
    return f"{int(sec // 60)} دقيقة {int(sec % 60)} ثانية"


async def _safe_edit(msg, text: str, parse_mode: str = "Markdown", reply_markup=None):
    """تعديل رسالة بأمان"""
    try:
        await msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        pass


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
                    await update.effective_message.reply_text(f"✅ انضممت عبر رابط إحالة {name}!")
                except Exception:
                    pass
    if user.get("is_banned"):
        await update.effective_message.reply_text("⛔ أنت محظور من استخدام البوت.")
        return None
    return user


# ============================================================
# أوامر البوت الأساسية
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start"""
    args = context.args
    uid = update.effective_user.id

    # معالجة رابط الإحالة
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
        "• ملف TXT 📃\n"
        "• نص المحاضرة مباشرة ✍️\n\n"
        "📚 *اختر نوع المحاضرة* (طب، هندسة، علوم...)\n"
        "🌍 *اختر لهجة الشرح* (عراقي، مصري، خليجي...)\n"
        "🎬 *استلم فيديو* مع شخصية كرتونية مخصصة وصور وصوت\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية\n\n"
        "⬇️ ابدأ الآن — أرسل المحاضرة!",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /help"""
    await update.message.reply_text(
        "📖 *كيفية الاستخدام*\n\n"
        "1️⃣ أرسل ملف PDF أو TXT أو نص مباشر\n"
        "2️⃣ اختر نوع المحاضرة (طب، هندسة، علوم...)\n"
        "3️⃣ اختر التخصص الدقيق (اختياري)\n"
        "4️⃣ اختر لهجة الشرح\n"
        "5️⃣ انتظر — البوت سيحلل ويصنع الفيديو\n"
        "6️⃣ استلم الفيديو التعليمي الكامل\n\n"
        "📊 *محتوى الفيديو:*\n"
        "• مقدمة مع شخصية كرتونية مخصصة\n"
        "• بطاقة لكل قسم\n"
        "• صور تعليمية كبيرة\n"
        "• كلمات مفتاحية واضحة\n"
        "• صوت بشري طبيعي\n"
        "• ملخص نهائي\n\n"
        "🔗 */referral* — رابط إحالة لكسب محاولات مجانية\n"
        "/cancel — إلغاء العملية",
        parse_mode="Markdown",
        reply_markup=main_keyboard(),
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /cancel - إلغاء المعالجة"""
    uid = update.effective_user.id
    user_states.pop(uid, None)
    ev = _cancel_flags.get(uid)
    if ev and not ev.is_set():
        ev.set()
        await update.message.reply_text("⛔ تم إلغاء المعالجة.", reply_markup=main_keyboard())
    else:
        await update.message.reply_text("✅ لا توجد عملية جارية.", reply_markup=main_keyboard())


async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض رصيد المستخدم"""
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
    """أمر /referral - عرض رابط الإحالة"""
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


# ============================================================
# استقبال المحتوى (نصوص وملفات)
# ============================================================
async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال المحتوى من المستخدم (PDF, TXT, نص)"""
    user = await ensure_user(update)
    if not user:
        return

    uid = update.effective_user.id
    msg = update.message

    # معالجة أوامر الأدمن
    if is_owner(uid):
        consumed = await handle_admin_text_search(update, context)
        if consumed:
            return

    # أزرار القائمة الرئيسية
    if msg.text:
        text = msg.text.strip()
        if text == "📤 رفع محاضرة":
            await msg.reply_text(
                "📤 *أرسل المحاضرة*\n\n"
                "• ملف PDF 📄 (حتى 50MB)\n"
                "• ملف TXT 📃\n"
                "• أو اكتب النص مباشرة (200 حرف على الأقل)",
                parse_mode="Markdown",
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

    # هل يوجد معالجة جارية؟
    if uid in _active_jobs:
        await msg.reply_text("⏳ محاضرتك قيد المعالجة...")
        return

    # التحقق من المحاولات
    if user["attempts_left"] <= 0:
        await send_payment_required_message(update, context)
        return

    lecture_text = None
    filename = "lecture"

    # ============================================================
    # معالجة الملفات (PDF, TXT)
    # ============================================================
    if msg.document:
        doc = msg.document
        fname = doc.file_name or "file"
        file_size = doc.file_size or 0
        ext = fname.lower().split(".")[-1] if "." in fname else ""

        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ الملف غير مدعوم. أرسل PDF أو TXT فقط.")
            return

        if file_size > 50 * 1024 * 1024:  # 50MB
            await msg.reply_text(f"⚠️ حجم الملف كبير جداً. الحد الأقصى 50MB")
            return

        # رد فوري
        wait = await msg.reply_text(
            f"📥 *جاري تحميل الملف...*\n📄 `{fname}`\n📦 {file_size // 1024}KB",
            parse_mode="Markdown",
        )

        try:
            # تحميل الملف
            file = await context.bot.get_file(doc.file_id)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
                tmp_path = tmp.name
            
            await file.download_to_drive(tmp_path)
            await wait.edit_text(f"📥 *تم التحميل!*\n🔍 جاري استخراج النص...", parse_mode="Markdown")

            # استخراج النص
            if ext == "pdf":
                lecture_text = await extract_full_text_from_pdf_path(tmp_path)
                filename = fname.replace(".pdf", "")
            else:
                with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                    lecture_text = f.read()
                filename = fname.replace(".txt", "")

            # حذف الملف المؤقت
            try:
                os.unlink(tmp_path)
            except:
                pass

            await wait.delete()

        except Exception as e:
            await wait.edit_text(f"❌ خطأ في قراءة الملف: {str(e)[:100]}")
            return

    # ============================================================
    # معالجة النص المباشر
    # ============================================================
    elif msg.text:
        text = msg.text.strip()
        if len(text) >= 200:
            lecture_text = text
            words = len(text.split())
            await msg.reply_text(f"✅ *تم استلام النص!* ({words:,} كلمة)", parse_mode="Markdown")
        else:
            await msg.reply_text(
                "⚠️ النص قصير جداً.\n\n"
                "• أرسل 200 حرف على الأقل\n"
                "• أو أرسل ملف PDF/TXT"
            )
            return
    else:
        await msg.reply_text("⚠️ أرسل ملف PDF، TXT، أو نص مباشر.")
        return

    # ============================================================
    # التحقق من النص المستخرج
    # ============================================================
    if not lecture_text or len(lecture_text.strip()) < 50:
        await msg.reply_text("❌ لم أتمكن من استخراج نص كافٍ. تأكد من محتوى الملف.")
        return

    # ============================================================
    # حفظ الحالة وعرض خيارات نوع المحاضرة
    # ============================================================
    user_states[uid] = {
        "state": "awaiting_subject",
        "text": lecture_text,
        "filename": filename,
    }

    words = len(lecture_text.split())
    if words < 500:
        est_time = "2-3 دقائق"
    elif words < 1500:
        est_time = "3-5 دقائق"
    elif words < 3000:
        est_time = "5-7 دقائق"
    else:
        est_time = "7-10 دقائق"

    await msg.reply_text(
        f"✅ *تم استلام المحاضرة!*\n\n"
        f"📝 عدد الكلمات: *{words:,}*\n"
        f"⏱️ الوقت المتوقع: *{est_time}*\n\n"
        f"📚 *اختر نوع المحاضرة:*",
        parse_mode="Markdown",
        reply_markup=get_subject_keyboard(),
    )


# ============================================================
# معالجة الكول باك (أزرار القوائم)
# ============================================================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع أزرار القوائم"""
    q = update.callback_query
    data = q.data
    uid = q.from_user.id

    # أزرار الأدمن
    if data.startswith("admin_"):
        await handle_admin_callback(update, context)
        return

    await q.answer()

    # ============================================================
    # أزرار الدفع
    # ============================================================
    if data == "pay_stars":
        await handle_pay_stars(update, context)
        return
    if data == "pay_mastercard":
        await handle_pay_mastercard(update, context)
        return
    if data == "pay_crypto":
        await handle_pay_crypto(update, context)
        return
    if data == "pay_sent":
        await handle_payment_sent(update, context)
        return

    # ============================================================
    # زر الإلغاء
    # ============================================================
    if data == "cancel_job":
        ev = _cancel_flags.get(uid)
        if ev and not ev.is_set():
            ev.set()
            try:
                await q.edit_message_text("⛔ تم إلغاء المعالجة.")
            except:
                pass
            await context.bot.send_message(uid, "⛔ تم الإلغاء.", reply_markup=main_keyboard())
        return

    # ============================================================
    # زر الإحالة
    # ============================================================
    if data == "show_referral":
        stats = get_referral_stats(uid)
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
        await q.message.reply_text(
            f"🔗 *رابط الإحالة*\n\n`{ref_link}`\n\n"
            f"👥 المدعوين: *{stats['total_referrals']}*\n"
            f"⭐ النقاط: *{stats['current_points']}*",
            parse_mode="Markdown",
        )
        return

    # ============================================================
    # الرجوع للقائمة الرئيسية للتخصصات
    # ============================================================
    if data == "back_to_main":
        await q.edit_message_text(
            "📚 *اختر نوع المحاضرة:*",
            parse_mode="Markdown",
            reply_markup=get_subject_keyboard(),
        )
        return

    # ============================================================
    # اختيار نوع المحاضرة (رئيسي أو تفصيلي)
    # ============================================================
    if data.startswith("subject_"):
        subject = data[8:]
        state = user_states.get(uid, {})

        if state.get("state") != "awaiting_subject":
            await q.edit_message_text("⚠️ أرسل المحاضرة أولاً.")
            return

        # إذا كان النوع من القائمة الرئيسية، نعرض التخصصات التفصيلية
        if subject in ["medicine", "engineering", "science", "islamic"]:
            user_states[uid]["temp_subject"] = subject
            await q.edit_message_text(
                f"📚 *اختر التخصص الدقيق:*",
                parse_mode="Markdown",
                reply_markup=get_detailed_subject_keyboard(subject),
            )
            return

        # حفظ النوع النهائي
        user_states[uid]["subject"] = subject
        user_states[uid]["state"] = "awaiting_dialect"

        subject_name = SUBJECT_NAMES.get(subject, subject)
        await q.edit_message_text(
            f"✅ نوع المحاضرة: *{subject_name}*\n\n"
            f"🌍 *اختر لهجة الشرح:*",
            parse_mode="Markdown",
            reply_markup=DIALECT_KEYBOARD,
        )
        return

    # ============================================================
    # اختيار اللهجة
    # ============================================================
    if data.startswith("dial_"):
        dialect = data[5:]
        state = user_states.get(uid, {})

        if state.get("state") != "awaiting_dialect":
            await q.edit_message_text("⚠️ اختر نوع المحاضرة أولاً.")
            return

        user = get_user(uid)
        if not user or user["attempts_left"] <= 0:
            await q.edit_message_text("❌ لا تملك محاولات كافية.")
            return

        dial_name = DIALECT_NAMES.get(dialect, dialect)
        subject = state.get("subject", "other")
        subject_name = SUBJECT_NAMES.get(subject, subject)

        await q.edit_message_text(
            f"🎬 *بدأت المعالجة!*\n"
            f"📚 النوع: {subject_name}\n"
            f"🌍 اللهجة: {dial_name}\n\n"
            f"{_pbar(0)} 0%\n"
            f"🔍 جاري التحليل...",
            parse_mode="Markdown",
            reply_markup=CANCEL_KB,
        )

        text = state["text"]
        filename = state.get("filename", "lecture")
        user_states.pop(uid, None)

        task = asyncio.create_task(
            _process_lecture(uid, text, filename, dialect, subject, q.message, context)
        )
        _active_tasks[uid] = task
        return


# ============================================================
# معالجة المحاضرة الرئيسية (إنشاء الفيديو)
# ============================================================
async def _process_lecture(
    uid: int,
    text: str,
    filename: str,
    dialect: str,
    subject: str,
    status_msg,
    context: ContextTypes.DEFAULT_TYPE,
):
    """المعالجة الكاملة للمحاضرة وإنشاء الفيديو"""
    _active_jobs[uid] = "processing"
    cancel_ev = asyncio.Event()
    _cancel_flags[uid] = cancel_ev
    req_id = save_video_request(uid, "text", dialect, subject)
    t_start = time.time()
    video_path = None

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
            # ============================================================
            # المرحلة 1: تحليل المحاضرة (DeepSeek أولاً)
            # ============================================================
            _check()
            await upd(5, "🔍 تحليل المحتوى باستخدام DeepSeek...")

            lecture_data = await _run_or_cancel(uid, analyze_lecture(text, dialect, subject))
            sections = lecture_data.get("sections", [])

            if not sections:
                raise RuntimeError("لم يتم استخراج أي أقسام من المحاضرة")

            n_sections = len(sections)
            await upd(25, f"✅ تم التحليل — {n_sections} أقسام")

            # ============================================================
            # المرحلة 2: جلب الصور
            # ============================================================
            _check()
            await upd(30, "🎨 جلب الصور التعليمية...")

            async def fetch_images(section):
                keywords = section.get("keywords", [])[:4]
                kw_descs = section.get("keyword_images", [])
                tasks = [
                    fetch_image_for_keyword(
                        keyword=kw,
                        section_title=section.get("title", ""),
                        lecture_type=subject,
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

            # ============================================================
            # المرحلة 3: توليد الصوت (gTTS مجاني)
            # ============================================================
            _check()
            await upd(55, "🎤 توليد الصوت (مجاني)...")

            voice_res = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
            audio_results = voice_res["results"]
            await upd(70, "✅ تم توليد الصوت")

            # ============================================================
            # المرحلة 4: إنشاء الفيديو
            # ============================================================
            _check()
            await upd(75, "🎬 إنتاج الفيديو...")

            fd, video_path = tempfile.mkstemp(prefix=f"vid_{uid}_", suffix=".mp4", dir=TEMP_DIR)
            os.close(fd)

            async def v_progress(elapsed, est):
                pct = int(75 + min(elapsed / max(est, 1), 0.95) * 23)
                await upd(pct, "🎬 تشفير الفيديو...")

            total_secs = await create_video_from_sections(
                sections=sections,
                audio_results=audio_results,
                lecture_data=lecture_data,
                output_path=video_path,
                dialect=dialect,
                progress_cb=v_progress,
            )

            await upd(99, "✅ اكتمل! جاري الإرسال...")

            # ============================================================
            # المرحلة 5: خصم محاولة وإرسال الفيديو
            # ============================================================
            decrement_attempts(uid)
            increment_total_videos(uid)
            update_video_request(req_id, "done", video_path)

            elapsed = time.time() - t_start
            title = lecture_data.get("title", filename)
            mins, secs = int(total_secs // 60), int(total_secs % 60)
            remaining = get_user(uid)["attempts_left"]

            caption = (
                f"🎬 *{title}*\n\n"
                f"📚 {SUBJECT_NAMES.get(subject, subject)}\n"
                f"🌍 {DIALECT_NAMES.get(dialect, dialect)}\n"
                f"📖 {n_sections} أقسام\n"
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

            await status_msg.delete()
            await context.bot.send_message(
                uid,
                "✅ *تم بنجاح!*\nشارك الفيديو مع أصدقائك 🎓",
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


# ============================================================
# أوامر الإدارة
# ============================================================
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /admin - لوحة التحكم"""
    if is_owner(update.effective_user.id):
        await handle_admin_command(update, context)


# ============================================================
# الدالة الرئيسية - تشغيل البوت
# ============================================================
async def main():
    """تشغيل البوت"""
    init_db()
    logger.info("🤖 ZAKROS PRO Bot starting...")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # تسجيل الأوامر
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

    # تسجيل معالجات الدفع
    app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    
    # تسجيل معالج الأزرار
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    # تسجيل معالج الرسائل والملفات
    app.add_handler(
        MessageHandler(
            filters.TEXT | filters.Document.ALL,
            receive_content,
        )
    )

    logger.info("✅ Bot ready")

    # ============================================================
    # إعداد Webhook لـ Heroku
    # ============================================================
    app_url = os.getenv("HEROKU_APP_NAME", "")
    webhook_url = f"https://{app_url}.herokuapp.com/telegram" if app_url else os.getenv("WEBHOOK_URL", "").rstrip("/")

    async with app:
        await app.start()

        if webhook_url:
            await app.bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "pre_checkout_query", "successful_payment"],
            )
            logger.info(f"✅ Webhook set to: {webhook_url}")

            try:
                import web_server as _ws
                _ws.set_bot_app(app)
            except:
                pass

            await asyncio.Event().wait()
        else:
            logger.info("🔄 Polling mode active")
            await app.updater.start_polling(drop_pending_updates=True)
            await asyncio.Event().wait()
            await app.updater.stop()

        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
