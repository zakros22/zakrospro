#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت المحاضرات الذكي - نسخة مبسطة تنتج فيديو احترافي
"""

import asyncio
import os
import logging
import tempfile
import time
import io
import subprocess
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from PIL import Image, ImageDraw, ImageFont

# ══════════════════════════════════════════════════════════════════════════════
#  الإعدادات
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# قاعدة بيانات بسيطة
import sqlite3
DB_PATH = os.path.join(TEMP_DIR, "bot.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, attempts INTEGER DEFAULT 1)")
    conn.commit()
    conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT attempts FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 1

def use_attempt(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, attempts) VALUES (?, 1)", (uid,))
    c.execute("UPDATE users SET attempts = attempts - 1 WHERE user_id = ? AND attempts > 0", (uid,))
    conn.commit()
    conn.close()

init_db()

# ══════════════════════════════════════════════════════════════════════════════
#  لوحات المفاتيح
# ══════════════════════════════════════════════════════════════════════════════
def main_keyboard():
    return ReplyKeyboardMarkup([["📤 رفع محاضرة", "📊 رصيدي"]], resize_keyboard=True)

DIALECT_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🇮🇶 عراقي", callback_data="dial_iraq"),
     InlineKeyboardButton("🇪🇬 مصري", callback_data="dial_egypt")],
    [InlineKeyboardButton("🇸🇾 شامي", callback_data="dial_syria"),
     InlineKeyboardButton("🇸🇦 خليجي", callback_data="dial_gulf")],
    [InlineKeyboardButton("📚 فصحى", callback_data="dial_msa")]
])

# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء صورة كرتونية خرافية
# ══════════════════════════════════════════════════════════════════════════════
def create_cartoon_image(title, keywords, section_num, total_sections, is_arabic=True):
    """إنشاء صورة كرتونية خرافية احترافية"""
    W, H = 854, 480
    
    # ألوان زاهية
    colors = [
        ((180, 30, 80), (255, 200, 100)),   # أحمر وذهبي
        ((30, 100, 150), (200, 255, 150)),  # أزرق وأخضر
        ((80, 30, 150), (255, 220, 100)),   # بنفسجي وذهبي
        ((20, 80, 100), (255, 200, 150)),   # أزرق مخضر وبرتقالي
        ((100, 20, 100), (255, 200, 220)),  # وردي وأرجواني
    ]
    primary, accent = colors[section_num % len(colors)]
    
    # خلفية
    img = Image.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    # شريط علوي
    draw.rectangle([(0, 0), (W, 60)], fill=primary)
    draw.rectangle([(0, 0), (W, 8)], fill=accent)
    
    # تحضير النص العربي
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        def ar(text): return get_display(arabic_reshaper.reshape(text))
    except:
        def ar(text): return text
    
    # خطوط
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_kw = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_num = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except:
        font_title = font_kw = font_num = ImageFont.load_default()
    
    # رقم القسم
    draw.text((20, 18), f"{section_num}/{total_sections}", fill=(255,255,255,180), font=font_num)
    
    # عنوان القسم
    title_display = ar(title[:40]) if is_arabic else title[:40]
    bbox = draw.textbbox((0,0), title_display, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 18), title_display, fill=(255,255,255), font=font_title)
    
    # إطار المحتوى
    draw.rectangle([(20, 75), (W-20, H-20)], fill=(255,255,255), outline=primary, width=3)
    
    # "مصطلحات رئيسية"
    label = "📌 مصطلحات رئيسية:" if is_arabic else "📌 Key Terms:"
    draw.text((40, 95), ar(label) if is_arabic else label, fill=primary, font=font_kw)
    
    # المصطلحات
    y = 135
    for i, kw in enumerate(keywords[:6]):
        if not kw:
            continue
        kw_display = ar(f"• {kw}") if is_arabic else f"• {kw}"
        
        if i % 2 == 0:
            x = 45
        else:
            x = W//2 + 15
        
        if i % 2 == 0 and i > 0:
            y += 45
        
        if y < H - 60:
            draw.rectangle([(x-5, y+5), (x-1, y+9)], fill=accent)
            draw.text((x+5, y), kw_display, fill=(60,60,80), font=font_kw)
    
    # رسم توضيحي
    icon_x, icon_y = W - 120, H - 120
    draw.ellipse([icon_x, icon_y, icon_x+80, icon_y+80], outline=primary, width=3)
    draw.ellipse([icon_x+15, icon_y+15, icon_x+65, icon_y+65], fill=accent)
    
    # شريط سفلي
    draw.rectangle([(0, H-6), (W, H)], fill=primary)
    draw.text((W-120, H-22), "@zakros_probot", fill=(150,150,170), font=font_num)
    
    # حفظ
    fd, path = tempfile.mkstemp(suffix=".jpg", dir=TEMP_DIR)
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    return path


def create_intro_image(title, sections, is_arabic=True):
    """صورة المقدمة مع خريطة المحاضرة"""
    W, H = 854, 480
    primary = (40, 40, 120)
    accent = (255, 200, 50)
    
    img = Image.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (W, 70)], fill=primary)
    draw.rectangle([(0, 0), (W, 8)], fill=accent)
    
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        def ar(text): return get_display(arabic_reshaper.reshape(text))
    except:
        def ar(text): return text
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font_sec = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except:
        font_title = font_sec = ImageFont.load_default()
    
    title_display = ar(title[:35]) if is_arabic else title[:35]
    bbox = draw.textbbox((0,0), title_display, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 22), title_display, fill=(255,255,255), font=font_title)
    
    draw.rectangle([(20, 85), (W-20, H-20)], fill=(255,255,255), outline=primary, width=3)
    
    map_label = "📋 خريطة المحاضرة:" if is_arabic else "📋 Lecture Map:"
    draw.text((40, 105), ar(map_label) if is_arabic else map_label, fill=primary, font=font_sec)
    
    y = 145
    for i, sec in enumerate(sections[:6]):
        sec_title = sec.get("title", f"القسم {i+1}")[:40]
        sec_display = ar(f"{i+1}. {sec_title}") if is_arabic else f"{i+1}. {sec_title}"
        draw.text((50, y), sec_display, fill=(60,60,80), font=font_sec)
        y += 45
    
    draw.rectangle([(0, H-6), (W, H)], fill=primary)
    draw.text((W-120, H-22), "@zakros_probot", fill=(150,150,170), font=font_sec)
    
    fd, path = tempfile.mkstemp(suffix=".jpg", dir=TEMP_DIR)
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    return path


def create_summary_image(sections, title, is_arabic=True):
    """صورة الملخص النهائي"""
    W, H = 854, 480
    primary = (20, 80, 60)
    
    img = Image.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (W, 60)], fill=primary)
    draw.rectangle([(0, 0), (W, 8)], fill=(255, 220, 100))
    
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        def ar(text): return get_display(arabic_reshaper.reshape(text))
    except:
        def ar(text): return text
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_sec = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        font_title = font_sec = ImageFont.load_default()
    
    summary_label = "📋 ملخص المحاضرة" if is_arabic else "📋 Summary"
    bbox = draw.textbbox((0,0), ar(summary_label) if is_arabic else summary_label, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 20), ar(summary_label) if is_arabic else summary_label, fill=(255,255,255), font=font_title)
    
    draw.rectangle([(20, 75), (W-20, H-20)], fill=(255,255,255), outline=primary, width=3)
    
    y = 100
    for i, sec in enumerate(sections[:8]):
        sec_title = sec.get("title", f"القسم {i+1}")[:35]
        sec_display = ar(f"✓ {sec_title}") if is_arabic else f"✓ {sec_title}"
        draw.text((40, y), sec_display, fill=(60,60,80), font=font_sec)
        y += 38
    
    draw.rectangle([(0, H-6), (W, H)], fill=primary)
    draw.text((W-120, H-22), "@zakros_probot", fill=(150,150,170), font=font_sec)
    
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
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    
    return await asyncio.get_event_loop().run_in_executor(None, _synth)


# ══════════════════════════════════════════════════════════════════════════════
#  تحليل بسيط للنص
# ══════════════════════════════════════════════════════════════════════════════
def simple_analyze(text, dialect):
    """تحليل بسيط للنص إلى أقسام"""
    is_arabic = dialect != "english"
    
    # تنظيف
    text = ' '.join(text.split())
    
    # تقسيم إلى فقرات
    paragraphs = []
    for p in text.split('\n'):
        p = p.strip()
        if len(p) > 80:
            paragraphs.append(p)
    
    if len(paragraphs) < 3:
        words = text.split()
        chunk = max(200, len(words) // 4)
        for i in range(0, len(words), chunk):
            para = ' '.join(words[i:i+chunk])
            if len(para) > 50:
                paragraphs.append(para)
    
    # إنشاء أقسام
    sections = []
    for i, para in enumerate(paragraphs[:5]):
        first_sent = para.split('.')[0][:40]
        title = f"القسم {i+1}: {first_sent}" if is_arabic else f"Section {i+1}: {first_sent}"
        
        # كلمات مفتاحية
        import re
        words_list = re.findall(r'[\u0600-\u06FF]{4,}|[A-Za-z]{4,}', para)
        keywords = list(set(words_list))[:4]
        if not keywords:
            keywords = ["مصطلح 1", "مصطلح 2", "مصطلح 3"] if is_arabic else ["Term 1", "Term 2", "Term 3"]
        
        sections.append({
            "title": title,
            "keywords": keywords,
            "narration": para[:600]
        })
    
    return {
        "title": "ملخص المحاضرة" if is_arabic else "Lecture Summary",
        "sections": sections
    }


# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء الفيديو
# ══════════════════════════════════════════════════════════════════════════════
def create_video(intro_img, section_images, summary_img, audio_paths, durations, output):
    """إنشاء الفيديو باستخدام ffmpeg"""
    segments = []
    
    # 1. المقدمة (5 ثواني)
    intro_out = tempfile.mktemp(suffix=".mp4")
    cmd = ["ffmpeg", "-y", "-loop", "1", "-t", "5", "-i", intro_img,
           "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-map", "0:v", "-map", "1:a", "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast",
           "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "64k", intro_out]
    subprocess.run(cmd, capture_output=True)
    segments.append(intro_out)
    
    # 2. الأقسام
    for i, (img, audio, dur) in enumerate(zip(section_images, audio_paths, durations)):
        seg_out = tempfile.mktemp(suffix=".mp4")
        aud_args = ["-i", audio] if audio and os.path.exists(audio) else ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd = ["ffmpeg", "-y", "-loop", "1", "-t", str(dur), "-i", img, *aud_args,
               "-map", "0:v", "-map", "1:a", "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast",
               "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "64k", seg_out]
        subprocess.run(cmd, capture_output=True)
        segments.append(seg_out)
    
    # 3. الملخص (6 ثواني)
    summary_out = tempfile.mktemp(suffix=".mp4")
    cmd = ["ffmpeg", "-y", "-loop", "1", "-t", "6", "-i", summary_img,
           "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
           "-map", "0:v", "-map", "1:a", "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast",
           "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "64k", summary_out]
    subprocess.run(cmd, capture_output=True)
    segments.append(summary_out)
    
    # دمج
    lst = tempfile.mktemp(suffix=".txt")
    with open(lst, "w") as f:
        for seg in segments:
            f.write(f"file '{seg}'\n")
    
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", output], capture_output=True)
    
    # تنظيف
    for seg in segments:
        try: os.remove(seg)
        except: pass
    try: os.remove(lst)
    except: pass


# ══════════════════════════════════════════════════════════════════════════════
#  أوامر البوت
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.first_name or "صديقي"
    attempts = get_user(uid)
    
    await update.message.reply_text(
        f"👋 *أهلاً {name}!*\n\n"
        f"🎓 أنا *بوت المحاضرات الذكي*\n"
        f"أحوّل محاضرتك إلى فيديو تعليمي احترافي!\n\n"
        f"📤 أرسل ملف PDF أو TXT أو نص المحاضرة\n"
        f"🎁 لديك *{attempts}* محاولة مجانية",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )


async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    
    if msg.text:
        text = msg.text.strip()
        if text == "📤 رفع محاضرة":
            await msg.reply_text("📤 أرسل الملف أو النص:", reply_markup=ReplyKeyboardMarkup([[]], resize_keyboard=True))
            return
        if text == "📊 رصيدي":
            await msg.reply_text(f"💳 رصيدك: *{get_user(uid)}* محاولة", parse_mode="Markdown")
            return
    
    attempts = get_user(uid)
    if attempts <= 0:
        await msg.reply_text("❌ لا تملك محاولات كافية")
        return
    
    # استخراج النص
    text = None
    if msg.document:
        doc = msg.document
        fname = doc.file_name or ""
        ext = fname.lower().split(".")[-1] if "." in fname else ""
        
        if ext not in ("pdf", "txt"):
            await msg.reply_text("⚠️ PDF أو TXT فقط")
            return
        
        wait = await msg.reply_text("📥 جاري القراءة...")
        try:
            file = await doc.get_file()
            raw = await file.download_as_bytearray()
            if ext == "pdf":
                import PyPDF2
                reader = PyPDF2.PdfReader(io.BytesIO(bytes(raw)))
                text = "\n".join([p.extract_text() or "" for p in reader.pages])
            else:
                text = raw.decode("utf-8", errors="ignore")
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ خطأ: {e}")
            return
    elif msg.text:
        if len(msg.text) < 100:
            await msg.reply_text("⚠️ النص قصير جداً")
            return
        text = msg.text
    else:
        return
    
    if not text or len(text.strip()) < 50:
        await msg.reply_text("❌ لم أستطع قراءة النص")
        return
    
    context.user_data["lecture_text"] = text
    await msg.reply_text(
        f"✅ *تم الاستلام!*\n📝 {len(text.split())} كلمة\n\nاختر لهجة الشرح:",
        parse_mode="Markdown",
        reply_markup=DIALECT_KB
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    
    await q.answer()
    
    if data.startswith("dial_"):
        dialect = data[5:]
        text = context.user_data.get("lecture_text")
        
        if not text:
            await q.edit_message_text("⚠️ انتهت الجلسة")
            return
        
        msg = await q.edit_message_text("🎬 *جاري المعالجة...*", parse_mode="Markdown")
        
        try:
            # 1. تحليل
            is_arabic = dialect != "english"
            data = simple_analyze(text, dialect)
            sections = data.get("sections", [])
            title = data.get("title", "المحاضرة")
            
            if not sections:
                raise Exception("لم يتم استخراج أقسام")
            
            await msg.edit_text(f"🔍 تم التحليل إلى {len(sections)} أقسام\n🎨 جاري إنشاء الصور...")
            
            # 2. صور
            section_images = []
            for i, sec in enumerate(sections):
                img = create_cartoon_image(
                    sec["title"], sec["keywords"], i+1, len(sections), is_arabic
                )
                section_images.append(img)
            
            intro_img = create_intro_image(title, sections, is_arabic)
            summary_img = create_summary_image(sections, title, is_arabic)
            
            await msg.edit_text("🎤 جاري توليد الصوت...")
            
            # 3. صوت
            audio_paths = []
            durations = []
            for sec in sections:
                narration = sec.get("narration", "")
                audio = await generate_audio(narration, dialect)
                
                fd, ap = tempfile.mkstemp(suffix=".mp3", dir=TEMP_DIR)
                os.close(fd)
                with open(ap, "wb") as f:
                    f.write(audio)
                audio_paths.append(ap)
                durations.append(max(len(narration) // 10, 8))
            
            await msg.edit_text("🎬 جاري إنتاج الفيديو...")
            
            # 4. فيديو
            fd, video_path = tempfile.mkstemp(suffix=".mp4", dir=TEMP_DIR)
            os.close(fd)
            
            create_video(intro_img, section_images, summary_img, audio_paths, durations, video_path)
            
            # 5. خصم وإرسال
            use_attempt(uid)
            
            await msg.edit_text("📤 جاري إرسال الفيديو...")
            
            with open(video_path, "rb") as vf:
                await context.bot.send_video(
                    uid, vf,
                    caption=f"🎬 *{title}*\n📚 {len(sections)} أقسام\n⏱️ {sum(durations)+11} ثانية",
                    parse_mode="Markdown"
                )
            
            await msg.delete()
            await context.bot.send_message(uid, "✅ *تم بنجاح!* 🎉", parse_mode="Markdown", reply_markup=main_keyboard())
            
            # تنظيف
            for p in section_images + [intro_img, summary_img] + audio_paths + [video_path]:
                try: os.remove(p)
                except: pass
                
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {str(e)[:200]}")


# ══════════════════════════════════════════════════════════════════════════════
#  دالة run_bot
# ══════════════════════════════════════════════════════════════════════════════
async def run_bot(shutdown_event: asyncio.Event, set_bot_app_cb=None):
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_content))
    app.add_handler(MessageHandler(filters.Document.ALL, receive_content))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
    
    async with app:
        await app.start()
        
        if webhook_url:
            await app.bot.set_webhook(f"{webhook_url}/telegram")
            logger.info(f"✅ Webhook: {webhook_url}")
            if set_bot_app_cb:
                set_bot_app_cb(app)
            await shutdown_event.wait()
        else:
            logger.info("🔄 Polling")
            await app.updater.start_polling()
            await shutdown_event.wait()
            await app.updater.stop()
        
        await app.stop()
