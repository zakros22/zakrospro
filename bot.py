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
from PIL import Image as PILImage, ImageDraw, ImageFont, ImageFilter

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

TEMP_DIR = "/tmp/telegram_bot"
os.makedirs(TEMP_DIR, exist_ok=True)

# حالة المستخدمين
user_states = {}
active_jobs = {}
cancel_flags = {}

# ══════════════════════════════════════════════════════════════════════════════
#  قاعدة بيانات SQLite بسيطة
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
#  استدعاء AI للتحليل
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
    subjects = {
        "طب": "medicine", "مرض": "medicine", "جراحة": "medicine", "ولادة": "medicine", "قيصرية": "medicine",
        "رياضيات": "math", "معادلة": "math", "هندسة": "engineering", "بناء": "engineering",
        "فيزياء": "physics", "كيمياء": "chemistry", "برمجة": "computer", "تاريخ": "history"
    }
    for ar, en in subjects.items():
        if ar in text_l or en in text_l:
            return en
    return "science"

def local_analyze(text, dialect):
    """تحليل محلي احتياطي."""
    text = re.sub(r'\s+', ' ', text).strip()
    
    # تقسيم النص إلى أقسام بناءً على العناوين أو الفقرات
    sections = []
    lines = text.split('\n')
    
    current_section = {"title": "مقدمة", "content": "", "keywords": []}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # اكتشاف العناوين (أسطر قصيرة أو تحتوي على كلمات مفتاحية)
        if len(line) < 60 and (':' in line or any(kw in line.lower() for kw in ['مقدمه', 'مقدمة', 'تعريف', 'أنواع', 'أسباب', 'دواعي', 'مضاعفات', 'علاج', 'خلاصة'])):
            if current_section["content"]:
                sections.append(current_section)
            current_section = {"title": line[:50], "content": "", "keywords": []}
        else:
            current_section["content"] += line + " "
            
        # استخراج كلمات مفتاحية
        words = re.findall(r'[\u0600-\u06FF]{4,}|[A-Za-z]{4,}', line)
        for w in words[:3]:
            if w not in current_section["keywords"]:
                current_section["keywords"].append(w)
    
    if current_section["content"]:
        sections.append(current_section)
    
    # تنظيف
    clean_sections = []
    for i, sec in enumerate(sections[:5]):
        clean_sections.append({
            "title": sec["title"],
            "narration": sec["content"][:600],
            "keywords": sec["keywords"][:4]
        })
    
    if not clean_sections:
        clean_sections = [{"title": "المحتوى الرئيسي", "narration": text[:600], "keywords": ["مصطلح1", "مصطلح2"]}]
    
    return {
        "title": "ملخص المحاضرة",
        "sections": clean_sections,
        "lecture_type": detect_subject(text)
    }

async def analyze_lecture(text, dialect):
    """تحليل النص إلى أقسام مع كلمات مفتاحية."""
    is_arabic = dialect != "english"
    subject = detect_subject(text)
    
    text_sample = text[:3500]
    
    if is_arabic:
        prompt = f"""أنت محلل محتوى تعليمي. حلل النص التالي إلى 3-5 أقسام.

المطلوب لكل قسم:
1. title: عنوان القسم
2. keywords: 3-4 كلمات مفتاحية (مصطلحات مهمة)
3. narration: شرح مبسط للقسم (200-300 كلمة) باللهجة {DIALECT_NAMES.get(dialect, 'الفصحى')}

النص:
{text_sample}

أرجع JSON فقط:
{{"title": "عنوان المحاضرة", "sections": [{{"title": "عنوان القسم", "keywords": ["مصطلح1", "مصطلح2"], "narration": "الشرح..."}}]}}"""
    else:
        prompt = f"""Analyze this text into 3-5 sections. Return JSON:
{{"title": "Title", "sections": [{{"title": "Section", "keywords": ["term1", "term2"], "narration": "explanation..."}}]}}
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
    
    return local_analyze(text, dialect)

# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء صورة كرت تعليمي احترافية (مثل الصور اللي أرسلتها)
# ══════════════════════════════════════════════════════════════════════════════
def create_educational_card(section_title, keywords, subject, section_num, total_sections):
    """إنشاء كرت تعليمي احترافي يشبه الصور المرسلة."""
    W, H = 854, 480
    
    # ألوان حسب المادة
    colors = {
        "medicine": ((180, 30, 60), (220, 50, 80), (255, 220, 200)),
        "science": ((20, 80, 120), (40, 140, 200), (220, 255, 200)),
        "math": ((80, 30, 140), (130, 60, 200), (255, 220, 100)),
        "engineering": ((20, 70, 100), (60, 130, 180), (255, 230, 150)),
        "physics": ((30, 40, 120), (70, 100, 200), (200, 220, 255)),
        "chemistry": ((100, 20, 90), (180, 40, 150), (255, 200, 220)),
        "computer": ((20, 60, 100), (60, 130, 180), (200, 255, 150)),
        "other": ((40, 40, 120), (100, 100, 200), (255, 200, 100))
    }
    primary, secondary, accent = colors.get(subject, colors["other"])
    
    # إنشاء الصورة
    img = PILImage.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    # شريط علوي
    draw.rectangle([(0, 0), (W, 8)], fill=primary)
    
    # رأس الكرت - خلفية ملونة
    draw.rectangle([(0, 8), (W, 70)], fill=primary)
    
    # رقم القسم
    try:
        font_num = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
    except:
        font_num = ImageFont.load_default()
    draw.text((20, 15), f"{section_num}/{total_sections}", fill=(255,255,255,180), font=font_num)
    
    # عنوان القسم
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        title_display = get_display(arabic_reshaper.reshape(section_title[:40]))
    except:
        title_display = section_title[:40]
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
    except:
        font_title = ImageFont.load_default()
    
    bbox = draw.textbbox((0,0), title_display, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 25), title_display, fill=(255,255,255), font=font_title)
    
    # خط تحت العنوان
    draw.rectangle([(W//4, 65), (W*3//4, 68)], fill=accent)
    
    # منطقة المحتوى - خلفية فاتحة
    draw.rectangle([(20, 85), (W-20, H-20)], fill=(255, 255, 255), outline=secondary, width=2)
    
    # عنوان "مصطلحات رئيسية"
    try:
        font_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
    except:
        font_label = ImageFont.load_default()
    
    label = "📌 مصطلحات رئيسية:"
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        label_display = get_display(arabic_reshaper.reshape(label))
    except:
        label_display = label
    
    draw.text((40, 100), label_display, fill=primary, font=font_label)
    
    # المصطلحات
    try:
        font_kw = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 15)
    except:
        font_kw = ImageFont.load_default()
    
    y = 135
    for i, kw in enumerate(keywords[:6]):
        if not kw:
            continue
        
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            kw_display = get_display(arabic_reshaper.reshape(f"• {kw}"))
        except:
            kw_display = f"• {kw}"
        
        # توزيع المصطلحات في عمودين
        if i % 2 == 0:
            x = 50
        else:
            x = W//2 + 20
        
        draw.text((x, y), kw_display, fill=(60, 60, 80), font=font_kw)
        
        if i % 2 == 1:
            y += 40
    
    # رسم توضيحي بسيط حسب المادة
    icon_y = H - 120
    
    if subject == "medicine":
        # رسم رمز طبي
        draw.ellipse([W-120, icon_y, W-40, icon_y+80], outline=primary, width=3)
        draw.line([W-80, icon_y+20, W-80, icon_y+60], fill=primary, width=3)
        draw.line([W-60, icon_y+40, W-100, icon_y+40], fill=primary, width=3)
    elif subject == "math":
        # رسم معادلة
        draw.text((W-150, icon_y+20), "f(x) = x² + 2x + 1", fill=primary, font=font_kw)
    elif subject == "science":
        # رسم دورق
        draw.ellipse([W-100, icon_y+20, W-50, icon_y+70], outline=primary, width=2)
        draw.rectangle([W-85, icon_y-10, W-65, icon_y+20], outline=primary, width=2)
    else:
        # رسم نجمة
        for i in range(5):
            angle = i * 72 - 90
            import math
            x1 = W-80 + 30 * math.cos(math.radians(angle))
            y1 = icon_y+40 + 30 * math.sin(math.radians(angle))
            x2 = W-80 + 15 * math.cos(math.radians(angle+36))
            y2 = icon_y+40 + 15 * math.sin(math.radians(angle+36))
            draw.line([x1, y1, x2, y2], fill=accent, width=3)
    
    # شريط سفلي
    draw.rectangle([(0, H-6), (W, H)], fill=primary)
    
    # علامة مائية
    try:
        font_wm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except:
        font_wm = ImageFont.load_default()
    draw.text((W-130, H-20), "@zakros_probot", fill=(150, 150, 170), font=font_wm)
    
    # حفظ
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    return path

# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصوت
# ══════════════════════════════════════════════════════════════════════════════
async def generate_audio(text, dialect):
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
#  إنشاء شريحة فيديو من الصورة
# ══════════════════════════════════════════════════════════════════════════════
def create_video_frame(img_path):
    """تجهيز الصورة للفيديو."""
    return img_path

def encode_video(segments, audio_paths, output):
    """تشفير الفيديو."""
    import subprocess
    
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
    
    lst = tempfile.mktemp(suffix=".txt")
    with open(lst, "w") as f:
        for v in video_segments:
            f.write(f"file '{v}'\n")
    
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", output], capture_output=True)
    
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
        f"أحوّل محاضرتك إلى فيديو تعليمي بصور احترافية وصوت!\n\n"
        f"📤 أرسل ملف PDF أو نص المحاضرة للبدء.\n\n"
        f"🎁 لديك *{user['attempts_left']}* محاولة مجانية.",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    
    user = get_user(uid) or create_user(uid)
    
    if user["is_banned"]:
        await msg.reply_text("⛔ أنت محظور.")
        return
    
    if user["attempts_left"] <= 0:
        await msg.reply_text("❌ لا تملك محاولات كافية.")
        return
    
    if uid in active_jobs:
        await msg.reply_text("⏳ لديك معالجة جارية...")
        return
    
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
        if len(text) < 50:
            await msg.reply_text("⚠️ النص قصير جداً")
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
    lecture_title = data.get("title", "المحاضرة")
    
    if not sections:
        raise Exception("لم يتم استخراج أقسام")
    
    await update(20, f"✅ تم التحليل إلى {len(sections)} أقسام")
    
    # 2. إنشاء صور كروت تعليمية لكل قسم
    images = []
    for i, sec in enumerate(sections):
        if cancel_ev.is_set():
            raise asyncio.CancelledError()
        await update(25 + i*10, f"🎨 تصميم الكرت التعليمي للقسم {i+1}...")
        
        keywords = sec.get("keywords", [])
        title = sec.get("title", f"القسم {i+1}")
        
        img_path = create_educational_card(title, keywords, subject, i+1, len(sections))
        images.append(img_path)
        sec["_image_path"] = img_path
    
    # 3. صوت لكل قسم
    audios = []
    audio_paths = []
    for i, sec in enumerate(sections):
        if cancel_ev.is_set():
            raise asyncio.CancelledError()
        await update(55 + i*8, f"🎤 توليد الصوت للقسم {i+1}...")
        
        narration = sec.get("narration", "")
        audio_bytes = await generate_audio(narration, dialect)
        audios.append(audio_bytes)
        
        if audio_bytes:
            fd, ap = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            with open(ap, "wb") as f:
                f.write(audio_bytes)
            audio_paths.append(ap)
        else:
            audio_paths.append(None)
    
    # 4. تجهيز الفيديو
    await update(85, "🎬 تجهيز الفيديو...")
    
    segments = []
    for i, sec in enumerate(sections):
        dur = max(len(sec.get("narration", "")) // 12, 8)
        segments.append((sec["_image_path"], dur))
    
    # 5. تشفير
    await update(90, "🎥 تشفير الفيديو...")
    
    fd, video_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    
    await asyncio.get_event_loop().run_in_executor(
        None, encode_video, segments, audio_paths, video_path
    )
    
    # 6. خصم وإرسال
    use_attempt(uid)
    user = get_user(uid)
    
    await update(99, "📤 جاري الإرسال...")
    
    caption = f"🎬 *{lecture_title}*\n📚 {len(sections)} أقسام\n⏱️ {fmt_time(time.time()-t0)}\n💳 متبقي: {user['attempts_left']}"
    
    with open(video_path, "rb") as vf:
        await context.bot.send_video(uid, vf, caption=caption, parse_mode="Markdown")
    
    await msg.delete()
    await context.bot.send_message(uid, "✅ *تم بنجاح!* 🎉", parse_mode="Markdown", reply_markup=main_keyboard())
    
    # تنظيف
    for sec in sections:
        try:
            if "_image_path" in sec:
                os.remove(sec["_image_path"])
        except:
            pass
    for ap in audio_paths:
        try:
            if ap:
                os.remove(ap)
        except:
            pass
    try:
        os.remove(video_path)
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
    await update.message.reply_text("📖 أرسل PDF أو نص للمحاضرة وسأحوّله لفيديو تعليمي بصور احترافية!")

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
