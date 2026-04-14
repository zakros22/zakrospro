#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت المحاضرات الذكي - النسخة التفصيلية الكاملة
يدعم: جميع المفاتيح مع تناوب، كروت تعليمية احترافية، صوت احترافي
"""

import asyncio
import os
import logging
import tempfile
import time
import re
import json
import io
import random
import subprocess
from datetime import datetime
from typing import Callable, Awaitable

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    PreCheckoutQueryHandler, filters, ContextTypes
)

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from config import (
    TELEGRAM_BOT_TOKEN, OWNER_ID, FREE_ATTEMPTS, PAID_ATTEMPTS, TEMP_DIR,
    DEEPSEEK_API_KEYS, GEMINI_API_KEYS, OPENROUTER_API_KEYS, GROQ_API_KEYS,
    ELEVENLABS_API_KEYS, OPENAI_API_KEY, VOICES
)
from database import (
    init_db, get_user, create_user, decrement_attempts, add_attempts,
    ban_user, set_attempts, subtract_attempts, increment_total_videos,
    get_stats, get_all_users, get_pending_payments, approve_payment,
    record_referral, get_referral_stats, save_video_request, update_video_request
)

# ══════════════════════════════════════════════════════════════════════════════
#  إعداد التسجيل
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  حالة المستخدمين
# ══════════════════════════════════════════════════════════════════════════════
user_states: dict = {}
active_jobs: dict = {}
active_tasks: dict = {}
cancel_flags: dict = {}

_Q_SEM = asyncio.Semaphore(2)

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
    [InlineKeyboardButton("📚 فصحى", callback_data="dial_msa"),
     InlineKeyboardButton("🇺🇸 English", callback_data="dial_english")],
])

CANCEL_KB = InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء المعالجة", callback_data="cancel_job")]])

DIALECT_NAMES = {
    "iraq": "🇮🇶 عراقي", "egypt": "🇪🇬 مصري", "syria": "🇸🇾 شامي",
    "gulf": "🇸🇦 خليجي", "msa": "📚 فصحى", "english": "🇺🇸 English"
}

# ══════════════════════════════════════════════════════════════════════════════
#  ألوان حسب المادة (للكروت التعليمية)
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
def pbar(pct: int, width: int = 12) -> str:
    filled = int(width * pct / 100)
    return "▓" * filled + "░" * (width - filled)

def fmt_time(sec: float) -> str:
    if sec < 60: return f"{int(sec)} ثانية"
    m, s = divmod(int(sec), 60)
    return f"{m} دقيقة و {s} ثانية"

async def safe_edit(msg, text, markup=None):
    try:
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=markup)
    except:
        pass

def prepare_arabic(text: str) -> str:
    if not text: return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except:
        return text

def get_font(size: int, bold: bool = False):
    try:
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()

async def ensure_user(update: Update):
    tg = update.effective_user
    user = get_user(tg.id)
    if not user:
        ref_by = user_states.get(tg.id, {}).get("ref_by")
        user = create_user(tg.id, tg.username or "", tg.full_name or "", ref_by)
        if ref_by and ref_by != tg.id:
            record_referral(ref_by, tg.id)
    if user and user.get("is_banned"):
        await update.effective_message.reply_text("⛔ أنت محظور من استخدام البوت.")
        return None
    return user

async def _run_or_cancel(uid: int, coro):
    ev = cancel_flags.get(uid)
    if ev and ev.is_set():
        raise asyncio.CancelledError()
    task = asyncio.ensure_future(coro)
    if ev:
        cancel_task = asyncio.ensure_future(ev.wait())
        done, pending = await asyncio.wait([task, cancel_task], return_when=asyncio.FIRST_COMPLETED)
        for p in pending: p.cancel()
        if cancel_task in done:
            task.cancel()
            raise asyncio.CancelledError()
    return await task

# ══════════════════════════════════════════════════════════════════════════════
#  نظام تناوب مفاتيح الذكاء الاصطناعي
# ══════════════════════════════════════════════════════════════════════════════
class QuotaExhaustedError(Exception):
    pass

async def call_deepseek(prompt: str) -> str:
    if not DEEPSEEK_API_KEYS: raise QuotaExhaustedError("لا توجد مفاتيح DeepSeek")
    import aiohttp
    for key in DEEPSEEK_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "max_tokens": 4000}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=90) as r:
                    if r.status == 200:
                        return (await r.json())["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise QuotaExhaustedError("DeepSeek فشل")

async def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEYS: raise QuotaExhaustedError("لا توجد مفاتيح Gemini")
    from google import genai
    from google.genai import types
    for key in GEMINI_API_KEYS:
        try:
            client = genai.Client(api_key=key)
            response = await asyncio.to_thread(client.models.generate_content, model="gemini-2.0-flash", contents=prompt)
            return response.text.strip()
        except:
            continue
    raise QuotaExhaustedError("Gemini فشل")

async def call_openrouter(prompt: str) -> str:
    if not OPENROUTER_API_KEYS: raise QuotaExhaustedError("لا توجد مفاتيح OpenRouter")
    import aiohttp
    for key in OPENROUTER_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "google/gemini-2.0-flash-exp:free", "messages": [{"role": "user", "content": prompt}]}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=90) as r:
                    if r.status == 200:
                        return (await r.json())["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise QuotaExhaustedError("OpenRouter فشل")

async def call_groq(prompt: str) -> str:
    if not GROQ_API_KEYS: raise QuotaExhaustedError("لا توجد مفاتيح Groq")
    import aiohttp
    for key in GROQ_API_KEYS:
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}]}
            async with aiohttp.ClientSession() as s:
                async with s.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=90) as r:
                    if r.status == 200:
                        return (await r.json())["choices"][0]["message"]["content"].strip()
        except:
            continue
    raise QuotaExhaustedError("Groq فشل")

async def call_duckduckgo(prompt: str) -> str:
    import aiohttp
    try:
        headers = {"Content-Type": "application/json", "Origin": "https://duckduckgo.com"}
        payload = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt[:3000]}]}
        async with aiohttp.ClientSession() as s:
            async with s.post("https://duckduckgo.com/duckchat/v1/chat", headers=headers, json=payload, timeout=60) as r:
                if r.status == 200:
                    text = ""
                    async for line in r.content:
                        if line and b'data: ' in line:
                            try:
                                text += json.loads(line.decode().split('data: ')[1])["message"]
                            except:
                                pass
                    if text.strip():
                        return text.strip()
    except:
        pass
    raise QuotaExhaustedError("DuckDuckGo فشل")

async def call_ai(prompt: str) -> str:
    for func in [call_deepseek, call_gemini, call_openrouter, call_groq, call_duckduckgo]:
        try:
            return await func(prompt)
        except QuotaExhaustedError:
            continue
    raise QuotaExhaustedError("جميع المزودين فشلوا")

# ══════════════════════════════════════════════════════════════════════════════
#  تحليل المحاضرة
# ══════════════════════════════════════════════════════════════════════════════
def detect_subject(text: str) -> str:
    subjects = {"طب": "medicine", "مرض": "medicine", "جراحة": "medicine", "رياضيات": "math", "فيزياء": "physics", "كيمياء": "chemistry", "هندسة": "engineering", "برمجة": "computer", "تاريخ": "history", "أدب": "literature", "اقتصاد": "business"}
    for ar, en in subjects.items():
        if ar in text: return en
    return "other"

def local_analyze(text: str, dialect: str) -> dict:
    is_arabic = dialect not in ("english", "british")
    paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 50]
    if len(paragraphs) < 3:
        words = text.split()
        chunk = max(200, len(words) // 4)
        paragraphs = [' '.join(words[i:i+chunk]) for i in range(0, len(words), chunk)]
    sections = []
    for i, para in enumerate(paragraphs[:5]):
        first_sent = para.split('.')[0][:40]
        words_list = re.findall(r'[\u0600-\u06FF]{4,}|[A-Za-z]{4,}', para)
        keywords = list(set(words_list))[:4] or (["مصطلح 1", "مصطلح 2"] if is_arabic else ["Term 1", "Term 2"])
        sections.append({"title": f"القسم {i+1}: {first_sent}" if is_arabic else f"Section {i+1}: {first_sent}", "keywords": keywords, "narration": para[:600]})
    return {"lecture_type": detect_subject(text), "title": "ملخص المحاضرة" if is_arabic else "Lecture Summary", "sections": sections}

async def analyze_lecture(text: str, dialect: str) -> dict:
    is_arabic = dialect not in ("english", "british")
    subject = detect_subject(text)
    num_sections = min(5, max(2, len(text.split()) // 400))
    text_sample = text[:3500]
    
    if is_arabic:
        prompt = f"""حلل النص إلى {num_sections} أقسام. أرجع JSON:
{{"title": "عنوان", "sections": [{{"title": "عنوان القسم", "keywords": ["مصطلح1", "مصطلح2", "مصطلح3"], "narration": "شرح مبسط"}}]}}
النص: {text_sample}"""
    else:
        prompt = f"""Analyze into {num_sections} sections. Return JSON:
{{"title": "Title", "sections": [{{"title": "Section", "keywords": ["term1", "term2"], "narration": "explanation"}}]}}
Text: {text_sample}"""
    
    try:
        response = await call_ai(prompt)
        response = re.sub(r'```json\s*', '', response.strip()).replace('```', '')
        data = json.loads(response)
        data["lecture_type"] = subject
        return data
    except:
        return local_analyze(text, dialect)

async def extract_pdf_text(pdf_bytes: bytes) -> str:
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join([p.extract_text() or "" for p in reader.pages])

# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء الكروت التعليمية الاحترافية (مثل الصور المطلوبة)
# ══════════════════════════════════════════════════════════════════════════════
def create_educational_card(title: str, keywords: list, subject: str, section_num: int, total: int, is_arabic: bool) -> str:
    W, H = 854, 480
    colors = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["other"])
    primary, secondary, accent = colors["primary"], colors["secondary"], colors["accent"]
    
    img = Image.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    # شريط علوي
    draw.rectangle([(0, 0), (W, 8)], fill=primary)
    draw.rectangle([(0, 8), (W, 75)], fill=primary)
    
    # رقم القسم
    font_small = get_font(13, True)
    draw.text((18, 16), f"{section_num}/{total}", fill=(255,255,255,180), font=font_small)
    
    # عنوان القسم
    title_display = prepare_arabic(title[:40]) if is_arabic else title[:40]
    font_title = get_font(24, True)
    bbox = draw.textbbox((0,0), title_display, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 28), title_display, fill=(255,255,255), font=font_title)
    draw.rectangle([(W//4, 72), (W*3//4, 75)], fill=accent)
    
    # إطار المحتوى
    draw.rectangle([(20, 90), (W-20, H-20)], fill=(255,255,255), outline=secondary, width=2)
    
    # عنوان المصطلحات
    font_label = get_font(16, True)
    label = "📌 مصطلحات رئيسية:" if is_arabic else "📌 Key Terms:"
    draw.text((40, 108), prepare_arabic(label) if is_arabic else label, fill=primary, font=font_label)
    
    # المصطلحات في عمودين
    font_kw = get_font(15)
    y = 150
    clean_kw = [str(k) for k in keywords[:8] if k]
    for i, kw in enumerate(clean_kw):
        kw_display = prepare_arabic(f"• {kw}") if is_arabic else f"• {kw}"
        x = 45 if i % 2 == 0 else W//2 + 15
        cy = y + (i//2) * 45
        if cy < H - 60:
            draw.rectangle([(x-5, cy+5), (x-1, cy+9)], fill=secondary)
            draw.text((x+5, cy), kw_display, fill=(60,60,80), font=font_kw)
    
    # رسم توضيحي
    icon_x, icon_y = W - 100, H - 110
    draw.ellipse([icon_x, icon_y, icon_x+60, icon_y+60], outline=primary, width=3)
    draw.ellipse([icon_x+10, icon_y+10, icon_x+50, icon_y+50], fill=accent)
    
    # شريط سفلي
    draw.rectangle([(0, H-6), (W, H)], fill=primary)
    draw.text((W-120, H-22), "@zakros_probot", fill=(150,150,170), font=font_small)
    
    fd, path = tempfile.mkstemp(suffix=".jpg", dir=TEMP_DIR)
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    return path

def create_intro_card(title: str, sections: list, subject: str, is_arabic: bool) -> str:
    W, H = 854, 480
    colors = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["other"])
    primary = colors["primary"]
    
    img = Image.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (W, 8)], fill=primary)
    draw.rectangle([(0, 8), (W, 70)], fill=primary)
    
    font_title = get_font(26, True)
    title_display = prepare_arabic(title[:35]) if is_arabic else title[:35]
    bbox = draw.textbbox((0,0), title_display, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 22), title_display, fill=(255,255,255), font=font_title)
    
    draw.rectangle([(20, 85), (W-20, H-20)], fill=(255,255,255), outline=primary, width=2)
    
    font_sec = get_font(16)
    map_label = "📋 خريطة المحاضرة:" if is_arabic else "📋 Lecture Map:"
    draw.text((40, 105), prepare_arabic(map_label) if is_arabic else map_label, fill=primary, font=font_sec)
    
    y = 145
    for i, sec in enumerate(sections[:6]):
        sec_title = sec.get("title", f"القسم {i+1}")[:40]
        sec_display = prepare_arabic(f"{i+1}. {sec_title}") if is_arabic else f"{i+1}. {sec_title}"
        draw.text((50, y), sec_display, fill=(60,60,80), font=font_sec)
        y += 45
    
    draw.rectangle([(0, H-6), (W, H)], fill=primary)
    draw.text((W-120, H-22), "@zakros_probot", fill=(150,150,170), font=font_sec)
    
    fd, path = tempfile.mkstemp(suffix=".jpg", dir=TEMP_DIR)
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    return path

def create_summary_card(sections: list, title: str, subject: str, is_arabic: bool) -> str:
    W, H = 854, 480
    colors = SUBJECT_COLORS.get(subject, SUBJECT_COLORS["other"])
    primary = colors["primary"]
    
    img = Image.new("RGB", (W, H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (W, 8)], fill=primary)
    draw.rectangle([(0, 8), (W, 60)], fill=primary)
    
    font_title = get_font(24, True)
    summary_label = "📋 ملخص المحاضرة" if is_arabic else "📋 Summary"
    bbox = draw.textbbox((0,0), prepare_arabic(summary_label) if is_arabic else summary_label, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 20), prepare_arabic(summary_label) if is_arabic else summary_label, fill=(255,255,255), font=font_title)
    
    draw.rectangle([(20, 75), (W-20, H-20)], fill=(255,255,255), outline=primary, width=2)
    
    font_sec = get_font(14)
    y = 100
    for i, sec in enumerate(sections[:8]):
        sec_title = sec.get("title", f"القسم {i+1}")[:35]
        sec_display = prepare_arabic(f"✓ {sec_title}") if is_arabic else f"✓ {sec_title}"
        draw.text((40, y), sec_display, fill=(60,60,80), font=font_sec)
        y += 38
    
    draw.rectangle([(0, H-6), (W, H)], fill=primary)
    draw.text((W-120, H-22), "@zakros_probot", fill=(150,150,170), font=font_sec)
    
    fd, path = tempfile.mkstemp(suffix=".jpg", dir=TEMP_DIR)
    os.close(fd)
    img.save(path, "JPEG", quality=92)
    return path

# ══════════════════════════════════════════════════════════════════════════════
#  نظام تناوب مفاتيح الصوت (ElevenLabs + gTTS)
# ══════════════════════════════════════════════════════════════════════════════
_el_key_idx = 0
_el_exhausted = set()

def _get_elevenlabs_key():
    global _el_key_idx
    if not ELEVENLABS_API_KEYS: return None
    for _ in range(len(ELEVENLABS_API_KEYS)):
        k = ELEVENLABS_API_KEYS[_el_key_idx % len(ELEVENLABS_API_KEYS)]
        if k not in _el_exhausted: return k
        _el_key_idx += 1
    return None

async def generate_elevenlabs(text: str, dialect: str) -> bytes:
    import aiohttp
    voice_id = VOICES.get(dialect, VOICES["msa"])["voice_id"]
    payload = {"text": text, "model_id": "eleven_multilingual_v2", "voice_settings": {"stability": 0.6, "similarity_boost": 0.85}}
    while True:
        key = _get_elevenlabs_key()
        if not key: raise Exception("All keys exhausted")
        try:
            headers = {"xi-api-key": key, "Content-Type": "application/json"}
            async with aiohttp.ClientSession() as s:
                async with s.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", json=payload, headers=headers, timeout=60) as r:
                    if r.status == 200: return await r.read()
                    if "quota" in await r.text():
                        _el_exhausted.add(key)
                        _el_key_idx += 1
                        continue
        except:
            continue

async def generate_gtts(text: str, dialect: str) -> bytes:
    from gtts import gTTS
    lang = "ar" if dialect != "english" else "en"
    def _synth():
        buf = io.BytesIO()
        gTTS(text=text, lang=lang, slow=False).write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    return await asyncio.get_event_loop().run_in_executor(None, _synth)

async def generate_voice(text: str, dialect: str) -> bytes:
    if ELEVENLABS_API_KEYS:
        try:
            return await generate_elevenlabs(text, dialect)
        except:
            pass
    return await generate_gtts(text, dialect)

async def generate_sections_audio(sections: list, dialect: str) -> list:
    results = []
    for sec in sections:
        narration = sec.get("narration", "")
        try:
            audio = await generate_voice(narration, dialect)
            duration = max(len(narration) // 10, 8)
            results.append({"audio": audio, "duration": duration})
        except:
            results.append({"audio": None, "duration": 30})
    return results

# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء الفيديو
# ══════════════════════════════════════════════════════════════════════════════
def encode_video(intro_img: str, section_images: list, summary_img: str, audio_data: list, output: str) -> float:
    segments = []
    total_dur = 5
    
    # مقدمة
    intro_out = tempfile.mktemp(suffix=".mp4")
    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-t", "5", "-i", intro_img, "-f", "lavfi", "-i", "anullsrc", "-map", "0:v", "-map", "1:a", "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "64k", intro_out], capture_output=True)
    segments.append(intro_out)
    
    # أقسام
    for img, adata in zip(section_images, audio_data):
        dur = adata["duration"]
        total_dur += dur
        seg_out = tempfile.mktemp(suffix=".mp4")
        audio_bytes = adata.get("audio")
        if audio_bytes:
            fd, ap = tempfile.mkstemp(suffix=".mp3", dir=TEMP_DIR)
            os.close(fd)
            with open(ap, "wb") as f: f.write(audio_bytes)
            aud_args = ["-i", ap]
        else:
            aud_args = ["-f", "lavfi", "-i", "anullsrc"]
            ap = None
        
        cmd = ["ffmpeg", "-y", "-loop", "1", "-t", str(dur), "-i", img, *aud_args, "-map", "0:v", "-map", "1:a", "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "64k", seg_out]
        subprocess.run(cmd, capture_output=True)
        segments.append(seg_out)
        if ap:
            try: os.remove(ap)
            except: pass
    
    # ملخص
    total_dur += 6
    summary_out = tempfile.mktemp(suffix=".mp4")
    subprocess.run(["ffmpeg", "-y", "-loop", "1", "-t", "6", "-i", summary_img, "-f", "lavfi", "-i", "anullsrc", "-map", "0:v", "-map", "1:a", "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "64k", summary_out], capture_output=True)
    segments.append(summary_out)
    
    # دمج
    lst = tempfile.mktemp(suffix=".txt")
    with open(lst, "w") as f:
        for seg in segments: f.write(f"file '{seg}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", output], capture_output=True)
    
    for seg in segments:
        try: os.remove(seg)
        except: pass
    try: os.remove(lst)
    except: pass
    
    return total_dur

# ══════════════════════════════════════════════════════════════════════════════
#  أوامر البوت
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args
    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0][4:])
            if ref_id != uid: user_states.setdefault(uid, {})["ref_by"] = ref_id
        except: pass
    user = await ensure_user(update)
    if not user: return
    name = update.effective_user.first_name or "صديقي"
    await update.message.reply_text(f"👋 *أهلاً {name}!*\n\n🎓 بوت المحاضرات الذكي\n📤 أرسل PDF أو TXT أو نص\n🎁 {user['attempts_left']} محاولة", parse_mode="Markdown", reply_markup=main_keyboard())

async def receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    if msg.text:
        t = msg.text.strip()
        if t == "📤 رفع محاضرة":
            await msg.reply_text("📤 أرسل الملف أو النص:", reply_markup=ReplyKeyboardRemove())
            return
        if t == "📊 رصيدي":
            u = get_user(uid)
            await msg.reply_text(f"💳 *{u['attempts_left']}* محاولة", parse_mode="Markdown")
            return
    user = await ensure_user(update)
    if not user: return
    if user['attempts_left'] <= 0:
        await msg.reply_text("❌ لا تملك محاولات")
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
    else: return
    if not text or len(text.strip()) < 50:
        await msg.reply_text("❌ لم أستطع قراءة النص")
        return
    user_states[uid] = {"text": text}
    await msg.reply_text(f"✅ *تم الاستلام!*\n📝 {len(text.split())} كلمة\n\nاختر اللهجة:", parse_mode="Markdown", reply_markup=DIALECT_KB)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    uid = q.from_user.id
    await q.answer()
    if data == "cancel_job":
        if uid in cancel_flags: cancel_flags[uid].set()
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

async def process_lecture(uid: int, text: str, dialect: str, msg, context):
    t0 = time.time()
    is_arabic = dialect not in ("english", "british")
    
    async def upd(pct, label):
        if cancel_flags.get(uid, asyncio.Event()).is_set(): raise asyncio.CancelledError()
        await safe_edit(msg, f"🎬 *المعالجة*\n{pbar(pct)} {pct}%\n{label}\n⏱️ {fmt_time(time.time()-t0)}", CANCEL_KB)
    
    # تحليل
    await upd(10, "🔍 تحليل المحاضرة...")
    data = await _run_or_cancel(uid, analyze_lecture(text, dialect))
    sections = data.get("sections", [])
    subject = data.get("lecture_type", "other")
    title = data.get("title", "المحاضرة")
    if not sections: raise Exception("لم يتم استخراج أقسام")
    await upd(25, f"✅ {len(sections)} أقسام")
    
    # صور
    section_images = []
    for i, sec in enumerate(sections):
        await upd(30 + i*8, f"🎨 الكرت {i+1}/{len(sections)}...")
        img = create_educational_card(sec["title"], sec.get("keywords", []), subject, i+1, len(sections), is_arabic)
        section_images.append(img)
    intro_img = create_intro_card(title, sections, subject, is_arabic)
    summary_img = create_summary_card(sections, title, subject, is_arabic)
    
    # صوت
    await upd(65, "🎤 توليد الصوت...")
    audio_data = await _run_or_cancel(uid, generate_sections_audio(sections, dialect))
    
    # فيديو
    await upd(80, "🎬 إنتاج الفيديو...")
    fd, video_path = tempfile.mkstemp(suffix=".mp4", dir=TEMP_DIR)
    os.close(fd)
    total_secs = await asyncio.get_event_loop().run_in_executor(None, encode_video, intro_img, section_images, summary_img, audio_data, video_path)
    
    # إرسال
    await upd(98, "📤 إرسال...")
    decrement_attempts(uid)
    vid_min, vid_sec = divmod(int(total_secs), 60)
    with open(video_path, "rb") as vf:
        await context.bot.send_video(uid, vf, caption=f"🎬 *{title}*\n📚 {len(sections)} أقسام\n⏱️ {vid_min}:{vid_sec:02d}", parse_mode="Markdown")
    await msg.delete()
    await context.bot.send_message(uid, "✅ *تم بنجاح!* 🎉", parse_mode="Markdown", reply_markup=main_keyboard())
    
    # تنظيف
    for p in section_images + [intro_img, summary_img, video_path]:
        try: os.remove(p)
        except: pass

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("🎛️ لوحة التحكم", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("تحديث", callback_data="admin_refresh")]]))

        
        def setup_handlers(app: Application):
    """إعداد جميع معالجات البوت."""
    
    from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, PreCheckoutQueryHandler, filters
    
    # الأوامر الأساسية
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("referral", referral_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    
    # أوامر الأدمن (اختيارية)
    try:
        from admin_panel import (
            handle_add_attempts, handle_set_attempts, handle_ban, 
            handle_unban, handle_broadcast, handle_approve_payment_command
        )
        app.add_handler(CommandHandler("add", handle_add_attempts))
        app.add_handler(CommandHandler("set", handle_set_attempts))
        app.add_handler(CommandHandler("ban", handle_ban))
        app.add_handler(CommandHandler("unban", handle_unban))
        app.add_handler(CommandHandler("broadcast", handle_broadcast))
        app.add_handler(CommandHandler("approve", handle_approve_payment_command))
    except ImportError:
        pass
    
    # المدفوعات
    try:
        from payment_handler import handle_pre_checkout, handle_successful_payment
        app.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
        app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    except ImportError:
        pass
    
    # الأزرار والمحتوى
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.Document.ALL) & ~filters.COMMAND,
            receive_content
        )
    )
    
    logger.info("✅ تم إعداد المعالجات")await app.stop()
