# -*- coding: utf-8 -*-
"""
Voice Generator Module - النسخة الكاملة والمفصلة
=================================================
الميزات:
- توليد صوت باستخدام gTTS (مجاني 100%)
- دعم اللهجات: عراقي، مصري، شامي، خليجي، فصحى، إنجليزي، بريطاني
- تنظيف النص من الأحرف غير المرغوبة
- تحويل الأرقام إلى كلمات (123 → مئة وثلاثة وعشرون)
- تحويل النسب المئوية إلى كلمات (87.5% → سبعة وثمانون فاصل خمسة بالمئة)
- منع تكرار الجمل (إزالة الجمل المكررة)
- توليد متوازي للأقسام (Semaphore للتحكم بعدد الطلبات)
- حساب مدة الصوت بدقة باستخدام pydub
- خطة احتياطية كاملة عند فشل توليد الصوت
"""

import asyncio
import io
import re
from gtts import gTTS


# ═══════════════════════════════════════════════════════════════════════════════
# 1. تنظيف النص
# ═══════════════════════════════════════════════════════════════════════════════

def clean_text(text: str) -> str:
    """
    تنظيف النص من جميع الأحرف غير المرغوبة:
    - null bytes (\x00, \0)
    - أحرف التحكم (control characters)
    - المسافات الزائدة
    """
    if not text:
        return ""
    
    # إزالة null bytes
    text = str(text).replace('\x00', '').replace('\0', '')
    
    # إزالة أحرف التحكم (ما عدا الأسطر الجديدة وعلامات الترقيم)
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # استبدال المسافات المتعددة بمسافة واحدة
    text = re.sub(r'\s+', ' ', text)
    
    # إزالة المسافات في البداية والنهاية
    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. تحويل الأرقام إلى كلمات
# ═══════════════════════════════════════════════════════════════════════════════

def _convert_numbers_to_words(text: str, lang: str) -> str:
    """
    تحويل الأرقام في النص إلى كلمات مكتوبة.
    مثال: "عندي 3 تفاحات" → "عندي ثلاثة تفاحات"
    """
    try:
        from num2words import num2words
        
        def replace_number(match):
            num_str = match.group(0).replace(',', '')
            try:
                if '.' in num_str:
                    num = float(num_str)
                else:
                    num = int(num_str)
                return num2words(num, lang=lang)
            except:
                return match.group(0)
        
        # البحث عن الأرقام (صحيحة وعشرية)
        text = re.sub(r'\d[\d,]*\.?\d*', replace_number, text)
    except ImportError:
        print("[WARN] num2words not installed, skipping number conversion")
    except Exception as e:
        print(f"[WARN] Number conversion failed: {e}")
    
    return text


def _convert_percentages_to_words(text: str, lang: str) -> str:
    """
    تحويل النسب المئوية إلى كلمات مكتوبة.
    مثال: "87.5%" → "سبعة وثمانون فاصل خمسة بالمئة"
    """
    try:
        from num2words import num2words
        
        def replace_percentage(match):
            num_str = match.group(1).replace(',', '')
            try:
                if '.' in num_str:
                    num = float(num_str)
                else:
                    num = int(num_str)
                words = num2words(num, lang=lang)
                suffix = " بالمئة" if lang == "ar" else " percent"
                return words + suffix
            except:
                return match.group(0)
        
        # البحث عن النسب المئوية
        text = re.sub(r'([\d,]+\.?\d*)\s*%', replace_percentage, text)
    except Exception as e:
        print(f"[WARN] Percentage conversion failed: {e}")
    
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# 3. منع تكرار الجمل
# ═══════════════════════════════════════════════════════════════════════════════

def _remove_duplicate_sentences(text: str) -> str:
    """
    إزالة الجمل المكررة من النص.
    هذا يمنع الصوت من تكرار نفس الجملة مراراً.
    """
    if not text:
        return text
    
    # تقسيم النص إلى جمل
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    
    unique_sentences = []
    seen = set()
    
    for s in sentences:
        s_clean = s.strip()
        if s_clean and s_clean not in seen:
            seen.add(s_clean)
            unique_sentences.append(s_clean)
    
    return ' '.join(unique_sentences)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. إعدادات اللغات واللهجات
# ═══════════════════════════════════════════════════════════════════════════════

GTTS_LANG_MAP = {
    # اللهجات العربية
    "iraq": "ar",      # عراقي
    "egypt": "ar",     # مصري
    "syria": "ar",     # شامي
    "gulf": "ar",      # خليجي
    "msa": "ar",       # فصحى
    
    # اللغات الأخرى
    "english": "en",   # إنجليزي
    "british": "en",   # بريطاني (نفس اللغة مع اختلاف النطق)
}

# ═══════════════════════════════════════════════════════════════════════════════
# 5. دالة توليد الصوت الرئيسية
# ═══════════════════════════════════════════════════════════════════════════════

async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    """
    توليد الصوت باستخدام gTTS.
    
    Args:
        text: النص المراد تحويله إلى صوت
        dialect: اللهجة المطلوبة (iraq, egypt, syria, gulf, msa, english, british)
    
    Returns:
        tuple: (audio_bytes, used_elevenlabs)
            - audio_bytes: الصوت بصيغة MP3
            - used_elevenlabs: دائماً False لأننا نستخدم gTTS المجاني
    """
    # 1. تنظيف النص
    text = clean_text(text)
    
    # 2. إذا كان النص فارغاً، نستخدم نصاً افتراضياً
    if not text:
        text = "المحاضرة التعليمية" if dialect in ["iraq", "egypt", "syria", "gulf", "msa"] else "Educational lecture"
    
    # 3. تحديد اللغة
    lang = GTTS_LANG_MAP.get(dialect, "ar")
    
    # 4. تحويل النسب المئوية إلى كلمات
    text = _convert_percentages_to_words(text, lang)
    
    # 5. تحويل الأرقام إلى كلمات
    text = _convert_numbers_to_words(text, lang)
    
    # 6. إزالة الجمل المكررة (لمنع التكرار الممل)
    text = _remove_duplicate_sentences(text)
    
    print(f"[TTS] Generating voice for text: {text[:100]}...")
    
    # 7. توليد الصوت في thread منفصل (لأن gTTS مكتبة متزامنة)
    def _synth():
        buf = io.BytesIO()
        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.write_to_fp(buf)
            buf.seek(0)
            return buf.read()
        except Exception as e:
            print(f"[TTS] gTTS failed: {e}")
            # محاولة أخيرة مع نص أقصر
            try:
                short_text = " ".join(text.split()[:100])  # أول 100 كلمة فقط
                buf2 = io.BytesIO()
                tts2 = gTTS(text=short_text, lang=lang, slow=False)
                tts2.write_to_fp(buf2)
                buf2.seek(0)
                return buf2.read()
            except Exception as e2:
                print(f"[TTS] Short text also failed: {e2}")
                raise
    
    loop = asyncio.get_event_loop()
    
    try:
        audio_bytes = await loop.run_in_executor(None, _synth)
        return audio_bytes, False
    except Exception as e:
        print(f"[TTS] Voice generation failed: {e}")
        # إرجاع صوت فارغ كخطة احتياطية
        return b"", False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. حساب مدة الصوت
# ═══════════════════════════════════════════════════════════════════════════════

async def get_audio_duration(audio_bytes: bytes) -> float:
    """
    حساب مدة الصوت بالثواني.
    
    Args:
        audio_bytes: الصوت بصيغة MP3
    
    Returns:
        float: المدة بالثواني
    """
    if not audio_bytes:
        return 30.0  # مدة افتراضية
    
    try:
        from pydub import AudioSegment
        
        # تحميل الصوت من bytes
        audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
        duration = len(audio) / 1000.0  # pydub يعطي المدة بالميلي ثانية
        
        print(f"[TTS] Audio duration: {duration:.1f}s")
        return duration
        
    except ImportError:
        print("[WARN] pydub not installed, estimating duration")
        # تقدير تقريبي: 1 ثانية ≈ 16000 بايت
        estimated = max(5.0, len(audio_bytes) / 16000)
        return estimated
    except Exception as e:
        print(f"[WARN] Failed to get audio duration: {e}")
        return max(5.0, len(audio_bytes) / 16000)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. توليد الصوت لجميع الأقسام (بالتوازي)
# ═══════════════════════════════════════════════════════════════════════════════

async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """
    توليد الصوت لجميع الأقسام بالتوازي.
    
    Args:
        sections: قائمة الأقسام، كل قسم يحتوي على "narration"
        dialect: اللهجة المطلوبة
    
    Returns:
        dict: يحتوي على:
            - results: قائمة بنتائج كل قسم (audio, duration, ok)
            - used_fallback: دائماً True (نستخدم gTTS)
            - all_failed: هل فشلت جميع الأقسام؟
    """
    
    # Semaphore للتحكم بعدد الطلبات المتزامنة (3 طلبات كحد أقصى)
    sem = asyncio.Semaphore(3)
    
    async def _generate_one_section(index: int, section: dict) -> dict:
        """
        توليد الصوت لقسم واحد.
        """
        async with sem:
            # استخراج النص من القسم
            text = section.get("narration", "")
            
            # إذا لم يكن هناك نص، نستخدم الكلمات المفتاحية
            if not text:
                keywords = section.get("keywords", ["مفهوم"])
                text = " ".join(keywords) * 3  # تكرار الكلمات 3 مرات
            
            print(f"[TTS] Section {index+1}: generating audio ({len(text.split())} words)...")
            
            try:
                # توليد الصوت
                audio_bytes, _ = await generate_voice(text, dialect)
                
                # حساب المدة
                duration = await get_audio_duration(audio_bytes)
                
                return {
                    "index": index,
                    "audio": audio_bytes,
                    "duration": duration,
                    "narration": text,
                    "ok": True,
                    "error": None
                }
                
            except Exception as e:
                print(f"[TTS] Section {index+1} failed: {e}")
                return {
                    "index": index,
                    "audio": None,
                    "duration": 30.0,  # مدة افتراضية
                    "narration": text,
                    "ok": False,
                    "error": str(e)
                }
    
    # توليد الصوت لجميع الأقسام بالتوازي
    print(f"[TTS] Generating audio for {len(sections)} sections...")
    results = await asyncio.gather(*[
        _generate_one_section(i, s) for i, s in enumerate(sections)
    ])
    
    # ترتيب النتائج حسب الفهرس
    results = sorted(results, key=lambda x: x["index"])
    
    # التحقق من فشل جميع الأقسام
    all_failed = all(not r["ok"] for r in results)
    
    if all_failed:
        print("[TTS] ⚠️ All sections failed to generate audio!")
    else:
        success_count = sum(1 for r in results if r["ok"])
        print(f"[TTS] ✅ Generated audio for {success_count}/{len(sections)} sections")
    
    return {
        "results": results,
        "used_fallback": True,  # gTTS دائماً
        "all_failed": all_failed
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 8. دالة مساعدة: تقسيم النص إلى جمل
# ═══════════════════════════════════════════════════════════════════════════════

def split_into_sentences(text: str) -> list:
    """
    تقسيم النص إلى جمل منفصلة.
    تستخدم لتقدير توقيت الجمل في الفيديو.
    """
    if not text:
        return []
    
    # تقسيم النص عند علامات الترقيم
    sentence_pattern = re.compile(r'(?<=[.!?؟])\s+|(?<=\n)')
    sentences = [s.strip() for s in sentence_pattern.split(text) if s.strip()]
    
    if not sentences:
        sentences = [text.strip()]
    
    return sentences


def estimate_sentence_timings(sentences: list, total_duration: float) -> list:
    """
    تقدير توقيت كل جملة بناءً على طولها.
    
    Args:
        sentences: قائمة الجمل
        total_duration: المدة الكلية للصوت
    
    Returns:
        list: قائمة بالتوقيتات (text, start, end, keywords)
    """
    if not sentences:
        return []
    
    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        # إذا كانت جميع الجمل فارغة، نقسم المدة بالتساوي
        even_dur = total_duration / len(sentences)
        t = 0.0
        timings = []
        for s in sentences:
            timings.append({
                "text": s,
                "start": t,
                "end": t + even_dur,
                "keywords": []
            })
            t += even_dur
        return timings
    
    timings = []
    t = 0.0
    
    for sentence in sentences:
        proportion = len(sentence) / total_chars
        duration = total_duration * proportion
        
        # استخراج الكلمات المفتاحية من الجملة
        keywords = _extract_sentence_keywords(sentence)
        
        timings.append({
            "text": sentence,
            "start": round(t, 3),
            "end": round(t + duration, 3),
            "keywords": keywords
        })
        t += duration
    
    return timings


def _extract_sentence_keywords(sentence: str) -> list:
    """
    استخراج الكلمات المفتاحية من جملة واحدة.
    """
    # قائمة الكلمات المستبعدة (stop words)
    stop_words = {
        'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه',
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'to', 'in',
        'that', 'it', 'be', 'for', 'on', 'with', 'as', 'at', 'by', 'this'
    }
    
    # استخراج الكلمات (4 أحرف فأكثر)
    words = re.findall(r'\b[\w\u0600-\u06FF]{4,}\b', sentence)
    
    keywords = []
    for w in words:
        if w.lower() not in stop_words:
            keywords.append(w)
        if len(keywords) >= 3:
            break
    
    return keywords
