#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
البوت الرئيسي - النسخة النهائية
"""

import asyncio
import os
import logging
import tempfile
import time
import re
import json
import io
import subprocess
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from PIL import Image, ImageDraw, ImageFont

from config import (
    TELEGRAM_BOT_TOKEN, OWNER_ID, FREE_ATTEMPTS, TEMP_DIR,
    DEEPSEEK_API_KEYS, GEMINI_API_KEYS, OPENROUTER_API_KEYS, GROQ_API_KEYS,
    ELEVENLABS_API_KEYS, VOICES
)
from database import (
    get_user, create_user, decrement_attempts, add_attempts,
    record_referral, get_referral_stats, save_video_request, update_video_request
)

# ══════════════════════════════════════════════════════════════════════════════
#  إعداد التسجيل
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  حالة المستخدمين
# ══════════════════════════════════════════════════════════════════════════════
user_states = {}
active_jobs = {}
cancel_flags = {}

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
    [InlineKeyboardButton("📚 فصحى", callback_data="dial_msa")]
])

CANCEL_KB = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="cancel_job")]])

DIALECT_NAMES = {
    "iraq": "🇮🇶 عراقي", "egypt": "🇪🇬 مصري", "syria": "🇸🇾 شامي",
    "gulf": "🇸🇦 خليجي", "msa": "📚 فصحى"
}

# ══════════════════════════════════════════════════════════════════════════════
#  ألوان الكروت
# ══════════════════════════════════════════════════════════════════════════════
SUBJECT_COLORS = {
    "medicine": {"primary": (180, 30, 60), "secondary": (220, 50, 80), "accent": (255, 220, 200)},
    "science": {"primary": (20, 80, 120), "secondary": (40, 140, 200), "accent": (220, 255, 200)},
    "math": {"primary": (80, 30, 140), "secondary": (130, 60, 200), "accent": (255, 220, 100)},
    "physics": {"primary": (30, 40, 120), "secondary": (70, 100, 200), "accent": (200, 220, 255)},
    "chemistry": {"primary": (100, 20, 90), "secondary": (180, 40, 150), "accent": (255, 200, 220)},
    "engineering": {"primary": (20, 70, 100), "secondary": (60, 130, 180), "accent": (255, 230, 150)},
    "computer": {"primary": (20, 60, 100), "secondary": (60, 130, 180), "accent": (200, 255, 150)},
    "history": {"primary": (120, 60, 30), "secondary": (200, 140, 80), "accent": (255, 230, 150)},
    "literature": {"primary": (60, 30, 80), "secondary": (140, 80, 160), "accent": (255, 200, 220)},
    "business": {"primary": (20, 80, 60), "secondary": (80, 160, 120), "accent": (255, 220, 100)},
    "other": {"primary": (40, 40, 120), "secondary": (100, 100, 200), "accent": (255, 200, 100)},
}

# ══════════════════════════════════════════════════════════════════════════════
#  دوال مساعدة
# ══════════════════════════════════════════════════════════════════════════════
def pbar(pct, w=12):
    f = int(w * pct / 100)
    return "▓" * f + "░" * (w - f)

def fmt_time(s):
    if s < 60:
        return f"{int(s)} ثانية"
    m, sec = divmod(int(s), 60)
    return f"{m} دقيقة و {sec} ثانية"

async def safe_edit(msg, text, markup=None):
    try:
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    except:
        pass

def prepare_arabic(text):
    if not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except:
        return text

def get_font(size, bold=False):
    try:
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()

async def ensure_user(update):
    tg = update.effective_user
    user = get_user(tg.id)
    if not user:
        ref_by = user_states.get(tg.id, {}).get("ref_by")
        user = create_user(tg.id, tg.username or "", tg.full_name or "", ref_by)
        if ref_by and ref_by != tg.id:
            record_referral(ref_by, tg.id)
    if user and user.get("is_banned"):
        await update.effective_message.reply_text("⛔ أنت محظور")
        return None
    return user

# ══════════════════════════════════════════════════════════════════════════════
#  تحليل النص
# ══════════════════════════════════════════════════════════════════════════════
def detect_subject(text):
    subjects = {"طب": "medicine", "رياضيات": "math", "فيزياء": "physics", "كيمياء": "chemistry", "هندسة": "engineering", "برمجة": "computer", "تاريخ": "history", "أدب": "literature", "اقتصاد": "business"}
    for ar, en in subjects.items():
        if ar in text:
            return en
    return "other"

def simple_analyze(text, dialect):
    is_arabic = dialect != "english"
    text = ' '.join(text.split())
    paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 50]
    if len(paragraphs) < 3:
        words = text.split()
        chunk = max(200, len(words) // 4)
        paragraphs = [' '.join(words[i:i+chunk]) for i in range(0, len(words), chunk)]
    sections = []
    for i, para in enumerate(paragraphs[:5]):
        first = para.split('.')[0][:40]
        title = f"القسم {i+1}: {first}" if is_arabic else f"Section {i+1}: {first}"
        words_list = re.findall(r'[\u0600-\u06FF]{4,}|[A-Za-z]{4,}', para)
        keywords = list(set(words_list))[:4] or (["مصطلح 1", "مصطلح 2"] if is_arabic else ["Term 1", "Term 2"])
        sections.append({"title": title, "keywords": keywords, "narration": para[:600]})
    return {"title": "ملخص المحاضرة" if is_arabic else "Lecture", "sections": sections, "lecture_type": detect_subject(text)}

# ══════════════════════════════════════════════════════════════════════════════
#  استخراج PDF
# ══════════════════════════════════════════════════════════════════════════════
async def extract_pdf_text(pdf_bytes):
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join([p.extract_text() or "" for p in reader.pages])

# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء الكروت التعليمية
# ══════════════════════════════════════════════════════════════════════════════
def create_card(title, keywords, subject, num, total, is_arabic):
    W, H = 854, 480
    colors = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["other"])
    p, s, a = colors["primary"], colors["secondary"], colors["accent"]
    
    img = Image.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (W, 8)], fill=p)
    draw.rectangle([(0, 8), (W, 75)], fill=p)
    
    font_s = get_font(13, True)
    draw.text((18, 16), f"{num}/{total}", fill=(255,255,255,180), font=font_s)
    
    title_d = prepare_arabic(title[:40]) if is_arabic else title[:40]
    font_t = get_font(24, True)
    bbox = draw.textbbox((0,0), title_d, font=font_t)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 28), title_d, fill=(255,255,255), font=font_t)
    draw.rectangle([(W//4, 72), (W*3//4, 75)], fill=a)
    
    draw.rectangle([(20, 90), (W-20, H-20)], fill=(255,255,255), outline=s, width=2)
    
    font_l = get_font(16, True)
    label = "📌 مصطلحات:" if is_arabic else "📌 Terms:"
    draw.text((40, 108), prepare_arabic(label) if is_arabic else label, fill=p, font=font_l)
    
    font_k = get_font(15)
    y = 150
    clean = [str(k) for k in keywords[:8] if k]
    for i, kw in enumerate(clean):
        kw_d = prepare_arabic(f"• {kw}") if is_arabic else f"• {kw}"
        x = 45 if i % 2 == 0 else W//2 + 15
        cy = y + (i//2) * 45
        if cy < H - 60:
            draw.rectangle([(x-5, cy+5), (x-1, cy+9)], fill=s)
            draw.text((x+5, cy), kw_d, fill=(60,60,80), font=font_k)
    
    # رسم توضيحي
    ix, iy = W - 100, H - 110
    draw.ellipse([ix, iy, ix+60, iy+60], outline=p, width=3)
    draw.ellipse([ix+10, iy+10, ix+50, iy+50], fill=a)
    
    draw.rectangle([(0, H-6), (W, H)], fill=p)
    draw.text((W-120, H-22), "@zakros_probot", fill=(150,150,170), font=font_s)
    
    fd, path = tempfile.mkstemp(suffix=".jpg", dir=TEMP_DIR)
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    return path

def create_intro(title, sections, subject, is_arabic):
    W, H = 854, 480
    colors = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["other"])
    p = colors["primary"]
    
    img = Image.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (W, 8)], fill=p)
    draw.rectangle([(0, 8), (W, 70)], fill=p)
    
    font_t = get_font(26, True)
    title_d = prepare_arabic(title[:35]) if is_arabic else title[:35]
    bbox = draw.textbbox((0,0), title_d, font=font_t)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 22), title_d, fill=(255,255,255), font=font_t)
    
    draw.rectangle([(20, 85), (W-20, H-20)], fill=(255,255,255), outline=p, width=2)
    
    font_s = get_font(16)
    label = "📋 خريطة المحاضرة:" if is_arabic else "📋 Map:"
    draw.text((40, 105), prepare_arabic(label) if is_arabic else label, fill=p, font=font_s)
    
    y = 145
    for i, sec in enumerate(sections[:6]):
        sec_t = sec.get("title", f"قسم {i+1}")[:40]
        sec_d = prepare_arabic(f"{i+1}. {sec_t}") if is_arabic else f"{i+1}. {sec_t}"
        draw.text((50, y), sec_d, fill=(60,60,80), font=font_s)
        y += 45
    
    draw.rectangle([(0, H-6), (W, H)], fill=p)
    draw.text((W-120, H-22), "@zakros_probot", fill=(150,150,170), font=font_s)
    
    fd, path = tempfile.mkstemp(suffix=".jpg", dir=TEMP_DIR)
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    return path

def create_summary(sections, title, subject, is_arabic):
    W, H = 854, 480
    colors = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["other"])
    p = colors["primary"]
    
    img = Image.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (W, 8)], fill=p)
    draw.rectangle([(0, 8), (W, 60)], fill=p)
    
    font_t = get_font(24, True)
    label = "📋 ملخص المحاضرة" if is_arabic else "📋 Summary"
    label_d = prepare_arabic(label) if is_arabic else label
    bbox = draw.textbbox((0,0), label_d, font=font_t)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 20), label_d, fill=(255,255,255), font=font_t)
    
    draw.rectangle([(20, 75), (W-20, H-20)], fill=(255,255,255), outline=p, width=2)
    
    font_s = get_font(14)
    y = 100
    for i, sec in enumerate(sections[:8]):
        sec_t = sec.get("title", f"قسم {i+1}")[:35]
        sec_d = prepare_arabic(f"✓ {sec_t}") if is_arabic else f"✓ {sec_t}"
        draw.text((40, y), sec_d, fill=(60,60,80), font=font_s)
        y += 38
    
    draw.rectangle([(0, H-6), (W, H)], fill=p)
    draw.text((W-120, H-22), "@zakros_probot", fill=(150,150,170), font=font_s)
    
    fd, path = tempfile.mkstemp(suffix=".jpg", dir=TEMP_DIR)
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    return path

# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصوت
# ══════════════════════════════════════════════════════════════════════════════
async def generate_audio(text, dialect):
    from gtts import gTTS
    lang = "ar" if dialect != "english" else "en"
    def _synth():
        buf = io.BytesIO()
        gTTS(text=text, lang=lang, slow=False).write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    return await asyncio.get_event_loop().run_in_executor(None, _synth)

# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء الفيديو
# ══════════════════════════════════════════════════════════════════════════════
def create_video(intro, images, summary, audios, durations, output):
    segments = []
    temp_files = []
    
    # مقدمة
    intro_out = tempfile.mktemp(suffix=".mp4")
    temp_files.append(intro_out)
    cmd = ["ffmpeg", "-y", "-loop", "1", "-t", "5", "-i", intro, "-f", "lavfi", "-i", "anullsrc", "-map", "0:v", "-map", "1:a", "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "64k", intro_out]
    subprocess.run(cmd, capture_output=True)
    segments.append(intro_out)
    
    # أقسام
    for img, aud, dur in zip(images, audios, durations):
        seg_out = tempfile.mktemp(suffix=".mp4")
        temp_files.append(seg_out)
        aud_args = ["-i", aud] if aud and os.path.exists(aud) else ["-f", "lavfi", "-i", "anullsrc"]
        cmd = ["ffmpeg", "-y", "-loop", "1", "-t", str(dur), "-i", img, *aud_args, "-map", "0:v", "-map", "1:a", "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "64k", seg_out]
        subprocess.run(cmd, capture_output=True)
        segments.append(seg_out)
    
    # ملخص
    summary_out = tempfile.mktemp(suffix=".mp4")
    temp_files.append(summary_out)
    cmd = ["ffmpeg", "-y", "-loop", "1", "-t", "6", "-i", summary, "-f", "lavfi", "-i", "anullsrc", "-map", "0:v", "-map", "1:a", "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "64k", summary_out]
    subprocess.run(cmd, capture_output=True)
    segments.append(summary_out)
    
    # دمج
    lst = tempfile.mktemp(suffix=".txt")
    temp_files.append(lst)
    with open(lst, "w") as f:
        for seg in segments:
            f.write(f"file '{seg}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", output], capture_output=True)
    
    for f in temp_files:
        try:
            os.remove(f)
        except:
            pass

# ══════════════════════════════════════════════════════════════════════════════
#  أوامر البوت
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args
    if args and args[0].startswith("ref_"):
        try:
            ref = int(args[0][4:])
            if ref != uid:
                user_states.setdefault(uid, {})["ref_by"] = ref
        except:
            pass
    user = await ensure_user(update)
    if not user:
        return
    name = update.effective_user.first_name or "صديقي"
    await update.message.reply_text(
        f"👋 *أهلاً {name}!*\n\n🎓 بوت المحاضرات الذكي\n📤 أرسل PDF أو TXT أو نص\n🎁 *{user['attempts_left']}* محاولة",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 أرسل ملف أو نص للمحاضرة", reply_markup=main_keyboard())

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in cancel_flags:
        cancel_flags[uid].set()
    await update.message.reply_text("⛔ تم الإلغاء", reply_markup=main_keyboard())

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if user:
        await update.message.reply_text(f"💳 *{user['attempts_left']}* محاولة", parse_mode="Markdown")

async def referral_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await ensure_user(update)
    if not user:
        return
    uid = update.effective_user.id
    stats = get_referral_stats(uid)
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{uid}"
    await update.message.reply_text(f"🔗 *رابطك*\n`{link}`\n👥 {stats['total_referrals']} صديق\n⭐ {stats['current_points']:.1f} نقطة", parse_mode="Markdown")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text("🎛️ لوحة التحكم")

# ══════════════════════════════════════════════════════════════════════════════
#  استقبال المحتوى
# ══════════════════════════════════════════════════════════════════════════════
async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    
    if msg.text:
        t = msg.text.strip()
        if t == "📤 رفع محاضرة":
            await msg.reply_text("📤 أرسل الملف أو النص:", reply_markup=ReplyKeyboardRemove())
            return
        if t == "📊 رصيدي":
            await balance_cmd(update, context)
            return
        if t == "🔗 رابط الإحالة":
            await referral_cmd(update, context)
            return
        if t == "❓ مساعدة":
            await help_cmd(update, context)
            return
    
    user = await ensure_user(update)
    if not user:
        return
    
    if user['attempts_left'] <= 0:
        await msg.reply_text("❌ لا تملك محاولات")
        return
    
    if uid in active_jobs:
        await msg.reply_text("⏳ معالجة جارية...")
        return
    
    text = None
    if msg.document:
        doc = msg.document
        ext = doc.file_name.lower().split(".")[-1] if "." in doc.file_name else ""
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ PDF أو TXT فقط")
            return
        wait = await msg.reply_text("📥 جاري القراءة...")
        try:
            file = await doc.get_file()
            raw = await file.download_as_bytearray()
            text = await extract_pdf_text(bytes(raw)) if ext == "pdf" else raw.decode("utf-8", errors="ignore")
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ خطأ: {e}")
            return
    elif msg.text:
        if len(msg.text) < 100:
            await msg.reply_text("⚠️ النص قصير")
            return
        text = msg.text
    else:
        return
    
    if not text or len(text.strip()) < 50:
        await msg.reply_text("❌ لم أستطع قراءة النص")
        return
    
    user_states[uid] = {"text": text}
    await msg.reply_text(
        f"✅ *تم الاستلام!*\n📝 {len(text.split())} كلمة\n\nاختر اللهجة:",
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
    await q.answer()
    
    if data == "cancel_job":
        if uid in cancel_flags:
            cancel_flags[uid].set()
        await q.edit_message_text("⛔ تم الإلغاء")
        return
    
    if data.startswith("dial_"):
        dialect = data[5:]
        state = user_states.pop(uid, {})
        text = state.get("text")
        
        if not text:
            await q.edit_message_text("⚠️ انتهت الجلسة")
            return
        
        user = get_user(uid)
        if user['attempts_left'] <= 0:
            await q.edit_message_text("❌ لا تملك محاولات")
            return
        
        msg = await q.edit_message_text(f"🎬 *بدأت المعالجة*\n{pbar(0)} 0%", parse_mode="Markdown", reply_markup=CANCEL_KB)
        cancel_flags[uid] = asyncio.Event()
        active_jobs[uid] = True
        
        try:
            await process_lecture(uid, text, dialect, msg, context)
        except asyncio.CancelledError:
            await safe_edit(msg, "⛔ تم الإلغاء")
        except Exception as e:
            await safe_edit(msg, f"❌ خطأ: {str(e)[:200]}")
        finally:
            active_jobs.pop(uid, None)
            cancel_flags.pop(uid, None)

# ══════════════════════════════════════════════════════════════════════════════
#  معالجة المحاضرة
# ══════════════════════════════════════════════════════════════════════════════
async def process_lecture(uid, text, dialect, msg, context):
    t0 = time.time()
    is_arabic = dialect != "english"
    
    async def upd(pct, label):
        if cancel_flags.get(uid, asyncio.Event()).is_set():
            raise asyncio.CancelledError()
        await safe_edit(msg, f"🎬 *المعالجة*\n{pbar(pct)} {pct}%\n{label}\n⏱️ {fmt_time(time.time()-t0)}", CANCEL_KB)
    
    # تحليل
    await upd(10, "🔍 تحليل...")
    data = simple_analyze(text, dialect)
    sections = data.get("sections", [])
    subject = data.get("lecture_type", "other")
    title = data.get("title", "المحاضرة")
    
    if not sections:
        raise Exception("لم يتم استخراج أقسام")
    
    await upd(25, f"✅ {len(sections)} أقسام")
    
    # صور
    images = []
    for i, sec in enumerate(sections):
        await upd(30 + i*8, f"🎨 الكرت {i+1}/{len(sections)}")
        img = create_card(sec["title"], sec.get("keywords", []), subject, i+1, len(sections), is_arabic)
        images.append(img)
    
    intro = create_intro(title, sections, subject, is_arabic)
    summary = create_summary(sections, title, subject, is_arabic)
    
    # صوت
    await upd(65, "🎤 الصوت...")
    audios = []
    durations = []
    for sec in sections:
        narration = sec.get("narration", "")
        audio = await generate_audio(narration, dialect)
        fd, ap = tempfile.mkstemp(suffix=".mp3", dir=TEMP_DIR)
        os.close(fd)
        with open(ap, "wb") as f:
            f.write(audio)
        audios.append(ap)
        durations.append(max(len(narration) // 10, 8))
    
    # فيديو
    await upd(80, "🎬 الفيديو...")
    fd, video = tempfile.mkstemp(suffix=".mp4", dir=TEMP_DIR)
    os.close(fd)
    
    await asyncio.get_event_loop().run_in_executor(None, create_video, intro, images, summary, audios, durations, video)
    
    # إرسال
    await upd(98, "📤 إرسال...")
    decrement_attempts(uid)
    user = get_user(uid)
    
    with open(video, "rb") as vf:
        await context.bot.send_video(uid, vf, caption=f"🎬 *{title}*\n📚 {len(sections)} أقسام\n💳 {user['attempts_left']} محاولة", parse_mode="Markdown")
    
    await msg.delete()
    await context.bot.send_message(uid, "✅ *تم بنجاح!* 🎉", parse_mode="Markdown", reply_markup=main_keyboard())
    
    # تنظيف
    for f in images + [intro, summary] + audios + [video]:
        try:
            os.remove(f)
        except:
            pass

# ══════════════════════════════════════════════════════════════════════════════
#  دالة إعداد المعالجات
# ══════════════════════════════════════════════════════════════════════════════
def setup_handlers(app: Application):
    """إعداد جميع معالجات البوت."""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("referral", referral_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, receive_content))
    logger.info("✅ تم إعداد المعالجات")
