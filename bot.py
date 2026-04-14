#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import logging
import tempfile
import time
import re
import json
import io
import aiohttp
import random
from datetime import datetime
from PIL import Image as PILImage, ImageDraw, ImageFont

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, filters, ContextTypes
)

# ══════════════════════════════════════════════════════════════════════════════
#  الإعدادات
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "7021542402"))
DEEPSEEK_KEYS = [k.strip() for k in os.getenv("DEEPSEEK_API_KEYS", "").split(",") if k.strip()]
GEMINI_KEYS = [k.strip() for k in os.getenv("GOOGLE_API_KEYS", "").split(",") if k.strip()]
ELEVENLABS_KEYS = [k.strip() for k in os.getenv("ELEVENLABS_API_KEYS", "").split(",") if k.strip()]

TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# حالة المستخدمين
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

DIALECT_NAMES = {"iraq": "🇮🇶 عراقي", "egypt": "🇪🇬 مصري", "syria": "🇸🇾 شامي", "gulf": "🇸🇦 خليجي", "msa": "📚 فصحى"}

# ══════════════════════════════════════════════════════════════════════════════
#  قاعدة بيانات بسيطة (مؤقتة)
# ══════════════════════════════════════════════════════════════════════════════
import sqlite3
DB_PATH = os.path.join(TEMP_DIR, "bot.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, attempts INTEGER DEFAULT 1, videos INTEGER DEFAULT 0, banned INTEGER DEFAULT 0)")
    conn.commit()
    conn.close()

def get_user(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "attempts_left": row[1], "total_videos": row[2], "is_banned": row[3]}
    return None

def create_user(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, attempts) VALUES (?, 1)", (uid,))
    conn.commit()
    conn.close()
    return get_user(uid)

def use_attempt(uid):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET attempts = attempts - 1, videos = videos + 1 WHERE user_id = ? AND attempts > 0", (uid,))
    conn.commit()
    conn.close()

init_db()

# ══════════════════════════════════════════════════════════════════════════════
#  دوال مساعدة
# ══════════════════════════════════════════════════════════════════════════════
def pbar(pct, w=10):
    f = int(w * pct / 100)
    return "▓" * f + "░" * (w - f)

def fmt_time(s):
    if s < 60: return f"{int(s)} ثانية"
    m, sec = divmod(int(s), 60)
    return f"{m} دقيقة و {sec} ثانية"

async def safe_edit(msg, text, markup=None):
    try:
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    except:
        pass

# ══════════════════════════════════════════════════════════════════════════════
#  تحليل المحاضرة باستخدام DeepSeek أو Gemini
# ══════════════════════════════════════════════════════════════════════════════
async def call_ai(prompt):
    # DeepSeek أولاً
    for key in DEEPSEEK_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 4000, "temperature": 0.5}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=90) as r:
                    if r.status == 200:
                        d = await r.json()
                        return d["choices"][0]["message"]["content"].strip()
        except:
            continue
    
    # Gemini ثانياً
    for key in GEMINI_KEYS:
        try:
            from google import genai
            client = genai.Client(api_key=key)
            response = await asyncio.to_thread(client.models.generate_content, model="gemini-2.0-flash", contents=prompt)
            return response.text.strip()
        except:
            continue
    
    return None

def detect_subject(text):
    text_l = text.lower()
    subjects = {"طب": "medicine", "رياضيات": "math", "فيزياء": "physics", "كيمياء": "chemistry", "هندسة": "engineering", "برمجة": "computer", "تاريخ": "history", "أدب": "literature", "اقتصاد": "business"}
    for ar, en in subjects.items():
        if ar in text_l or en in text_l:
            return en
    return "science"

def local_analyze(text, dialect):
    """تحليل محلي احتياطي سريع."""
    # تنظيف النص
    text = re.sub(r'\s+', ' ', text).strip()
    
    # تقسيم إلى جمل
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    
    # تجميع الجمل في 3-4 أقسام
    sections = []
    chunk_size = max(3, len(sentences) // 3)
    
    for i in range(0, min(len(sentences), chunk_size * 4), chunk_size):
        chunk = ' '.join(sentences[i:i+chunk_size])
        if len(chunk) > 100:
            title = chunk.split('.')[0][:40]
            sections.append({
                "title": f"القسم {len(sections)+1}: {title}",
                "narration": chunk[:600]
            })
    
    if not sections:
        sections = [{"title": "المحتوى الرئيسي", "narration": text[:600]}]
    
    return {
        "title": "ملخص المحاضرة",
        "sections": sections[:4],
        "lecture_type": detect_subject(text)
    }

async def analyze_lecture(text, dialect):
    """تحليل النص إلى أقسام."""
    is_arabic = dialect != "english"
    subject = detect_subject(text)
    
    word_count = len(text.split())
    num_sections = 3 if word_count < 600 else 4 if word_count < 1200 else 5
    
    text_sample = text[:3500]
    
    if is_arabic:
        prompt = f"""حلل النص التالي إلى {num_sections} أقسام تعليمية. لكل قسم اكتب:
1. عنوان واضح وجذاب
2. شرح مبسط وممتع (200-300 كلمة) باللهجة {DIALECT_NAMES.get(dialect, 'الفصحى')}

النص:
{text_sample}

أرجع JSON فقط:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "narration": "الشرح..."}}]}}"""
    else:
        prompt = f"""Analyze this text into {num_sections} sections. Return JSON:
{{"title": "Title", "sections": [{{"title": "Section title", "narration": "Explanation..."}}]}}

Text: {text_sample}"""

    try:
        response = await call_ai(prompt)
        if response:
            response = re.sub(r'```json\s*', '', response).strip()
            response = re.sub(r'\s*```', '', response)
            data = json.loads(response)
            data["lecture_type"] = subject
            return data
    except:
        pass
    
    # تحليل محلي احتياطي
    return local_analyze(text, dialect)

# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصور الكرتونية
# ══════════════════════════════════════════════════════════════════════════════
async def generate_cartoon_image(title, subject, is_arabic):
    """توليد صورة كرتونية خرافية."""
    
    # وصف الصورة حسب المادة
    styles = {
        "medicine": "cute cartoon doctor in magical clinic, fantasy medical illustration",
        "math": "cute math wizard with floating numbers, magical geometry",
        "physics": "cute scientist with magical physics, floating planets",
        "chemistry": "cute chemist with magical potions, colorful laboratory",
        "engineering": "cute engineer building magical bridge, fantasy construction",
        "computer": "cute robot with magical code, fantasy programming",
        "history": "cute time traveler in ancient magical kingdom",
        "literature": "cute writer with magical flying books",
        "business": "cute merchant in magical marketplace",
        "science": "cute scientist in magical laboratory"
    }
    style = styles.get(subject, "cute teacher in magical classroom, fantasy education")
    
    prompt = f"{style}, about {title[:40]}, whimsical storybook art, bright colors, simple clean design, no text"
    
    # Pollinations.ai
    import urllib.parse
    seed = random.randint(1, 99999)
    url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt[:250])}?width=854&height=480&seed={seed}&model=flux&nologo=true"
    
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=20) as r:
                if r.status == 200:
                    data = await r.read()
                    if len(data) > 5000:
                        img = PILImage.open(io.BytesIO(data)).convert("RGB")
                        img = img.resize((854, 480), PILImage.LANCZOS)
                        buf = io.BytesIO()
                        img.save(buf, "JPEG", quality=90)
                        return buf.getvalue()
    except:
        pass
    
    # صورة احتياطية
    return create_fallback_image(title, subject, is_arabic)

def create_fallback_image(title, subject, is_arabic):
    colors = [(20,30,80), (70,60,160), (255,200,50)]
    W, H = 854, 480
    img = PILImage.new("RGB", (W,H), colors[0])
    draw = ImageDraw.Draw(img)
    
    for y in range(H):
        t = y/H
        r = int(colors[0][0]*(1-t) + colors[1][0]*t)
        g = int(colors[0][1]*(1-t) + colors[1][1]*t)
        b = int(colors[0][2]*(1-t) + colors[1][2]*t)
        draw.line([(0,y), (W,y)], fill=(r,g,b))
    
    for _ in range(15):
        x, y = random.randint(20,W-20), random.randint(20,H-20)
        s = random.randint(3,8)
        draw.ellipse([x-s,y-s,x+s,y+s], fill=(255,255,200))
    
    short = title[:30]
    if is_arabic:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            short = get_display(arabic_reshaper.reshape(short))
        except:
            pass
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 35)
    except:
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0,0), short, font=font)
    tw, th = bbox[2]-bbox[0], bbox[3]-bbox[1]
    draw.text(((W-tw)//2, (H-th)//2), short, fill=(255,255,255), font=font)
    draw.rectangle([15,15,W-15,H-15], outline=colors[2], width=4)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()

# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصوت
# ══════════════════════════════════════════════════════════════════════════════
async def generate_audio(text, dialect):
    # gTTS مجاني
    try:
        from gtts import gTTS
        lang = "ar" if dialect != "english" else "en"
        
        def _synth():
            buf = io.BytesIO()
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.write_to_fp(buf)
            buf.seek(0)
            return buf.read()
        
        return await asyncio.get_event_loop().run_in_executor(None, _synth)
    except:
        return None

# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء الفيديو
# ══════════════════════════════════════════════════════════════════════════════
def create_video_slide(img_bytes, title, idx, is_arabic):
    """إنشاء شريحة فيديو: صورة تملىء الشاشة مع عنوان."""
    W, H = 854, 480
    accent = [(100,180,255), (100,220,160), (255,180,80), (220,120,255), (255,120,120)][idx % 5]
    
    # خلفية الصورة
    if img_bytes:
        try:
            canvas = PILImage.open(io.BytesIO(img_bytes)).convert("RGB")
            canvas = canvas.resize((W, H), PILImage.LANCZOS)
        except:
            canvas = PILImage.new("RGB", (W,H), (30,30,60))
    else:
        canvas = PILImage.new("RGB", (W,H), (30,30,60))
    
    draw = ImageDraw.Draw(canvas)
    
    # شريط العنوان في الأعلى
    overlay = PILImage.new("RGBA", (W, 50), (0,0,0,180))
    canvas.paste(overlay, (0, 0), overlay)
    
    # العنوان
    short_title = title[:45]
    if is_arabic:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            short_title = get_display(arabic_reshaper.reshape(short_title))
        except:
            pass
    
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except:
        font = ImageFont.load_default()
    
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, W, 4], fill=accent)
    bbox = draw.textbbox((0,0), short_title, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 12), short_title, fill=(255,255,255), font=font)
    
    # علامة مائية
    try:
        font2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font2 = ImageFont.load_default()
    draw.text((W-120, H-20), "@zakros_probot", fill=(200,200,200), font=font2)
    
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    canvas.save(path, "JPEG", quality=90)
    return path

def encode_video(segments, audio_paths, output):
    """تشفير الفيديو."""
    import subprocess
    
    # إنشاء فيديو لكل شريحة
    video_segments = []
    for i, (img, dur) in enumerate(segments):
        seg_out = tempfile.mktemp(suffix=".mp4")
        video_segments.append(seg_out)
        
        aud = ["-i", audio_paths[i]] if i < len(audio_paths) and audio_paths[i] else ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-t", str(dur), "-i", img,
            *aud, "-map", "0:v", "-map", "1:a",
            "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10",
            "-c:a", "aac", "-b:a", "64k", "-t", str(dur), seg_out
        ]
        subprocess.run(cmd, capture_output=True)
    
    # دمج المقاطع
    lst = tempfile.mktemp(suffix=".txt")
    with open(lst, "w") as f:
        for v in video_segments:
            f.write(f"file '{v}'\n")
    
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", output], capture_output=True)
    
    # تنظيف
    for v in video_segments:
        try:
            os.remove(v)
        except:
            pass
    try:
        os.remove(lst)
    except:
        pass

# ══════════════════════════════════════════════════════════════════════════════
#  أوامر البوت
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid) or create_user(uid)
    name = update.effective_user.first_name or "صديقي"
    
    await update.message.reply_text(
        f"👋 *أهلاً {name}!*\n\n"
        f"🎓 أنا *بوت المحاضرات الذكي*\n"
        f"أحوّل محاضرتك إلى فيديو تعليمي بصوت وصور كرتونية!\n\n"
        f"📤 أرسل ملف PDF أو نص المحاضرة للبدء.\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية.",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    
    user = get_user(uid)
    if not user:
        user = create_user(uid)
    
    if user["is_banned"]:
        await msg.reply_text("⛔ أنت محظور.")
        return
    
    if user["attempts_left"] <= 0:
        await msg.reply_text("❌ لا تملك محاولات كافية.")
        return
    
    if uid in active_jobs:
        await msg.reply_text("⏳ لديك معالجة جارية...")
        return
    
    # استخراج النص
    text = None
    if msg.document:
        doc = msg.document
        if not doc.file_name.lower().endswith(('.pdf', '.txt')):
            await msg.reply_text("⚠️ PDF أو TXT فقط")
            return
        
        wait = await msg.reply_text("📥 جاري قراءة الملف...")
        try:
            file = await doc.get_file()
            raw = await file.download_as_bytearray()
            
            if doc.file_name.lower().endswith('.pdf'):
                import PyPDF2
                reader = PyPDF2.PdfReader(io.BytesIO(bytes(raw)))
                text = "\n".join([p.extract_text() or "" for p in reader.pages])
            else:
                text = raw.decode('utf-8', errors='ignore')
            
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ خطأ: {e}")
            return
    elif msg.text:
        text = msg.text.strip()
        if len(text) < 100:
            await msg.reply_text("⚠️ النص قصير جداً (أقل من 100 حرف)")
            return
    else:
        return
    
    if not text or len(text.strip()) < 50:
        await msg.reply_text("❌ لم أستطع قراءة النص")
        return
    
    user_states[uid] = {"text": text}
    
    await msg.reply_text(
        f"✅ *تم استلام المحاضرة!*\n📝 {len(text.split())} كلمة\n\nاختر لهجة الشرح:",
        parse_mode="Markdown",
        reply_markup=DIALECT_KB
    )

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
        if user["attempts_left"] <= 0:
            await q.edit_message_text("❌ لا تملك محاولات")
            return
        
        msg = await q.edit_message_text(
            f"🎬 *بدأت المعالجة*\n{pbar(0)} 0%\n🔍 تحليل المحاضرة...",
            parse_mode="Markdown",
            reply_markup=CANCEL_KB
        )
        
        cancel_flags[uid] = asyncio.Event()
        active_jobs[uid] = True
        
        try:
            await process_lecture(uid, text, dialect, msg, context, cancel_flags[uid])
        except asyncio.CancelledError:
            await safe_edit(msg, "⛔ تم الإلغاء")
        except Exception as e:
            logger.error(f"Error: {e}")
            await safe_edit(msg, f"❌ خطأ: {str(e)[:200]}")
        finally:
            active_jobs.pop(uid, None)
            cancel_flags.pop(uid, None)

async def process_lecture(uid, text, dialect, msg, context, cancel_ev):
    """معالجة المحاضرة كاملة."""
    t0 = time.time()
    
    async def update(pct, label):
        if cancel_ev.is_set():
            raise asyncio.CancelledError()
        e = time.time() - t0
        await safe_edit(msg, f"🎬 *المعالجة*\n{pbar(pct)} {pct}%\n{label}\n⏱️ {fmt_time(e)}", CANCEL_KB)
    
    # 1. تحليل
    await update(10, "🔍 تحليل المحتوى...")
    data = await analyze_lecture(text, dialect)
    sections = data.get("sections", [])
    subject = data.get("lecture_type", "science")
    is_arabic = dialect != "english"
    
    if not sections:
        raise Exception("لم يتم استخراج أقسام")
    
    await update(20, f"✅ تم التحليل إلى {len(sections)} أقسام")
    
    # 2. صور لكل قسم
    images = []
    for i, sec in enumerate(sections):
        if cancel_ev.is_set():
            raise asyncio.CancelledError()
        await update(25 + i*10, f"🎨 رسم الصورة الكرتونية للقسم {i+1}...")
        img = await generate_cartoon_image(sec.get("title", ""), subject, is_arabic)
        images.append(img)
        sec["_image"] = img
    
    # 3. صوت لكل قسم
    audios = []
    audio_paths = []
    for i, sec in enumerate(sections):
        if cancel_ev.is_set():
            raise asyncio.CancelledError()
        await update(55 + i*8, f"🎤 توليد الصوت للقسم {i+1}...")
        
        audio_bytes = await generate_audio(sec.get("narration", ""), dialect)
        audios.append(audio_bytes)
        
        if audio_bytes:
            fd, ap = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            with open(ap, "wb") as f:
                f.write(audio_bytes)
            audio_paths.append(ap)
        else:
            audio_paths.append(None)
    
    # 4. إنشاء شرائح الفيديو
    await update(85, "🎬 تجهيز الفيديو...")
    
    segments = []
    tmp_images = []
    
    for i, sec in enumerate(sections):
        img_path = create_video_slide(sec["_image"], sec.get("title", f"قسم {i+1}"), i, is_arabic)
        tmp_images.append(img_path)
        
        dur = max(len(sec.get("narration", "")) // 12, 10)
        segments.append((img_path, dur))
    
    # 5. تشفير الفيديو
    await update(90, "🎥 تشفير الفيديو...")
    
    fd, video_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    
    await asyncio.get_event_loop().run_in_executor(
        None, encode_video, segments, audio_paths, video_path
    )
    
    # 6. خصم المحاولة وإرسال
    use_attempt(uid)
    user = get_user(uid)
    
    await update(99, "📤 جاري الإرسال...")
    
    caption = f"🎬 *{data.get('title', 'المحاضرة')}*\n📚 {len(sections)} أقسام\n⏱️ {fmt_time(time.time()-t0)}\n💳 متبقي: {user['attempts_left']}"
    
    with open(video_path, "rb") as vf:
        await context.bot.send_video(uid, vf, caption=caption, parse_mode="Markdown")
    
    await msg.delete()
    await context.bot.send_message(uid, "✅ *تم بنجاح!* 🎉", parse_mode="Markdown", reply_markup=main_keyboard())
    
    # تنظيف
    for p in tmp_images + audio_paths + [video_path]:
        try:
            os.remove(p)
        except:
            pass

async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid in cancel_flags:
        cancel_flags[uid].set()
    await update.message.reply_text("✅ تم الإلغاء", reply_markup=main_keyboard())

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid) or create_user(uid)
    await update.message.reply_text(f"💳 رصيدك: *{user['attempts_left']}* محاولة", parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 أرسل PDF أو نص للمحاضرة وسأحوّله لفيديو تعليمي!")

# ══════════════════════════════════════════════════════════════════════════════
#  تشغيل البوت
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_content))
    app.add_handler(MessageHandler(filters.Document.ALL, receive_content))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("✅ البوت يعمل...")
    
    webhook = os.getenv("WEBHOOK_URL", "")
    if webhook:
        await app.bot.set_webhook(f"{webhook}/telegram")
        logger.info(f"Webhook: {webhook}")
        await asyncio.Event().wait()
    else:
        await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
