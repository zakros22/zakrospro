#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import aiohttp
import asyncio
import re
import io
import logging
from config import ELEVENLABS_API_KEYS, VOICES

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  إعدادات gTTS
# ══════════════════════════════════════════════════════════════════════════════
GTTS_LANG_MAP = {
    "iraq": "ar",
    "egypt": "ar",
    "syria": "ar",
    "gulf": "ar",
    "msa": "ar",
    "english": "en",
    "british": "en",
}

# ══════════════════════════════════════════════════════════════════════════════
#  تحويل الأرقام إلى كلمات
# ══════════════════════════════════════════════════════════════════════════════
_ARABIC_INDIC = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')


def _convert_num(raw: str, lang: str) -> str:
    """تحويل رقم إلى كلمات."""
    try:
        from num2words import num2words
        clean = raw.replace(',', '')
        val = float(clean) if '.' in clean else int(clean)
        return num2words(val, lang=lang)
    except Exception:
        return raw


def preprocess_text_for_tts(text: str, dialect: str = "msa") -> str:
    """
    تجهيز النص لتحويله إلى صوت:
    1. تحويل الأرقام العربية (٠-٩) → أرقام غربية (0-9)
    2. تحويل النسب المئوية إلى كلمات
    3. تحويل الأرقام إلى كلمات منطوقة
    """
    if not text:
        return text
    
    is_arabic = dialect not in ("english", "british")
    lang = "ar" if is_arabic else "en"
    
    # تحويل الأرقام العربية
    text = text.translate(_ARABIC_INDIC)
    
    def _pct_replace(m):
        num_str = m.group(1)
        words = _convert_num(num_str, lang)
        suffix = " بالمئة" if is_arabic else " percent"
        return words + suffix
    
    def _num_replace(m):
        return _convert_num(m.group(0), lang)
    
    # معالجة النسب المئوية أولاً
    text = re.sub(r'([\d,]+\.?\d*)\s*%', _pct_replace, text)
    # ثم معالجة الأرقام العادية
    text = re.sub(r'\d[\d,]*\.?\d*', _num_replace, text)
    
    return text


# ══════════════════════════════════════════════════════════════════════════════
#  نظام تناوب مفاتيح ElevenLabs
# ══════════════════════════════════════════════════════════════════════════════
_key_idx: int = 0
_exhausted: set[str] = set()
_all_keys_exhausted: bool = False


def _is_quota_error(status: int, body: str) -> bool:
    """
    التحقق مما إذا كان الخطأ بسبب نفاد الرصيد.
    
    ElevenLabs ترجع عدة أنواع من الأخطاء:
    • HTTP 422 مع "quota_exceeded"
    • HTTP 429 عند تجاوز الحد الشهري
    • HTTP 401 إذا كان المفتاح غير صالح
    """
    if "quota_exceeded" in body:
        return True
    if status == 429 and ("quota" in body or "credits" in body or "limit" in body):
        return True
    if status == 422 and "quota" in body:
        return True
    return False


def _current_key() -> str | None:
    """الحصول على المفتاح التالي المتاح."""
    global _key_idx
    keys = ELEVENLABS_API_KEYS
    if not keys:
        return None
    
    # محاولة إيجاد مفتاح غير منتهي
    for _ in range(len(keys)):
        k = keys[_key_idx % len(keys)]
        if k not in _exhausted:
            return k
        _key_idx += 1
    
    return None


def _mark_exhausted(key: str):
    """تسجيل أن المفتاح منتهي والانتقال للمفتاح التالي."""
    global _key_idx, _all_keys_exhausted
    _exhausted.add(key)
    _key_idx += 1
    
    total = len(ELEVENLABS_API_KEYS)
    remaining = total - len(_exhausted)
    
    if remaining > 0:
        nk = _current_key() or "???"
        logger.warning(
            f"🔑 ElevenLabs key exhausted — "
            f"switching to next key ({remaining}/{total} remaining, "
            f"starts with {nk[:12]}…)"
        )
    else:
        _all_keys_exhausted = True
        logger.warning("🔑 All ElevenLabs keys exhausted — falling back to gTTS permanently")


def keys_status() -> dict:
    """إرجاع ملخص حالة المفاتيح (للوحة التحكم)."""
    total = len(ELEVENLABS_API_KEYS)
    exhausted = len(_exhausted)
    return {
        "total": total,
        "active": total - exhausted,
        "exhausted": exhausted,
        "all_gone": exhausted >= total if total else True,
    }


def reset_tts_engine():
    """إعادة تعيين حالة المفاتيح (لا تستخدم إلا للاختبار)."""
    global _key_idx, _exhausted, _all_keys_exhausted
    _key_idx = 0
    _exhausted.clear()
    _all_keys_exhausted = False


# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصوت باستخدام ElevenLabs
# ══════════════════════════════════════════════════════════════════════════════

async def generate_voice_elevenlabs(text: str, dialect: str = "msa") -> bytes:
    """
    توليد صوت باستخدام ElevenLabs مع تناوب تلقائي للمفاتيح.
    
    Args:
        text: النص المراد تحويله
        dialect: اللهجة
    
    Returns:
        bytes: ملف الصوت MP3
    
    Raises:
        KeyError: إذا نفدت جميع المفاتيح
        Exception: في حالة أخطاء API الأخرى
    """
    voice_config = VOICES.get(dialect, VOICES["msa"])
    voice_id = voice_config["voice_id"]
    
    # تجهيز النص
    text = preprocess_text_for_tts(text, dialect)
    
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.6,
            "similarity_boost": 0.85,
            "style": 0.4,
            "use_speaker_boost": True,
        },
    }
    
    while True:
        key = _current_key()
        if key is None:
            raise KeyError("all_exhausted")
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": key,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if data:
                            logger.info(f"✅ ElevenLabs success with key {key[:12]}…")
                            return data
                        raise Exception("ElevenLabs returned empty audio")
                    
                    body = await resp.text()
                    
                    if _is_quota_error(resp.status, body):
                        logger.warning(
                            f"⚠️ Key {key[:12]}… quota exhausted "
                            f"(HTTP {resp.status}) — rotating"
                        )
                        _mark_exhausted(key)
                        continue
                    
                    raise Exception(f"ElevenLabs API error {resp.status}: {body[:300]}")
                    
        except KeyError:
            raise
        except aiohttp.ClientError as net_err:
            raise Exception(f"ElevenLabs network error: {net_err}") from net_err


# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصوت باستخدام gTTS (مجاني - احتياطي)
# ══════════════════════════════════════════════════════════════════════════════

async def generate_voice_gtts(text: str, dialect: str = "msa") -> bytes:
    """توليد صوت باستخدام gTTS (Google TTS المجاني)."""
    from gtts import gTTS
    
    lang = GTTS_LANG_MAP.get(dialect, "ar")
    text = preprocess_text_for_tts(text, dialect)
    
    def _synth():
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    
    loop = asyncio.get_event_loop()
    logger.info(f"🎤 Using gTTS fallback for dialect: {dialect}")
    return await loop.run_in_executor(None, _synth)


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية لتوليد الصوت
# ══════════════════════════════════════════════════════════════════════════════

async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    """
    توليد صوت TTS.
    
    الإستراتيجية:
    1. محاولة ElevenLabs مع تناوب تلقائي للمفاتيح
    2. إذا نفدت جميع المفاتيح → استخدام gTTS
    
    Args:
        text: النص المراد تحويله
        dialect: اللهجة
    
    Returns:
        tuple: (audio_bytes, used_elevenlabs)
    """
    global _all_keys_exhausted
    
    if not _all_keys_exhausted and ELEVENLABS_API_KEYS:
        try:
            audio_bytes = await generate_voice_elevenlabs(text, dialect)
            return audio_bytes, True
        except KeyError:
            _all_keys_exhausted = True
            logger.warning("🔇 All ElevenLabs keys exhausted — switching permanently to gTTS")
        except Exception as e:
            logger.error(f"⚠️ ElevenLabs error: {e} — using gTTS for this section")
    
    audio_bytes = await generate_voice_gtts(text, dialect)
    return audio_bytes, False


# ══════════════════════════════════════════════════════════════════════════════
#  دوال مساعدة للصوت
# ══════════════════════════════════════════════════════════════════════════════

async def get_audio_duration(audio_bytes: bytes) -> float:
    """حساب مدة ملف الصوت بالثواني."""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
        return len(audio) / 1000.0
    except Exception:
        # تقدير تقريبي: 1 ثانية لكل 16000 بايت
        return len(audio_bytes) / 16000


def split_into_sentences(text: str) -> list:
    """تقسيم النص إلى جمل."""
    # نمط لتقسيم الجمل العربية والإنجليزية
    sentence_pattern = re.compile(r'(?<=[.!?؟])\s+|(?<=\n)')
    sentences = [s.strip() for s in sentence_pattern.split(text) if s.strip()]
    if not sentences:
        sentences = [text.strip()] if text.strip() else []
    return sentences


def estimate_sentence_timings(sentences: list, total_duration: float) -> list:
    """تقدير توقيت كل جملة بناءً على طولها."""
    if not sentences:
        return []
    
    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        even_dur = total_duration / len(sentences)
        t = 0.0
        timings = []
        for s in sentences:
            timings.append({"text": s, "start": t, "end": t + even_dur, "keywords": []})
            t += even_dur
        return timings
    
    timings = []
    t = 0.0
    for sentence in sentences:
        proportion = len(sentence) / total_chars
        duration = total_duration * proportion
        timings.append({
            "text": sentence,
            "start": round(t, 3),
            "end": round(t + duration, 3),
            "keywords": _extract_sentence_keywords(sentence),
        })
        t += duration
    
    return timings


def _extract_sentence_keywords(sentence: str) -> list:
    """استخراج الكلمات المفتاحية من الجملة."""
    stop_words = {
        'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه',
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'to', 'in',
        'that', 'it', 'be', 'for', 'on', 'with', 'as', 'at', 'by', 'this',
    }
    words = re.findall(r'\b[\w\u0600-\u06FF]{4,}\b', sentence)
    keywords = [w for w in words if w.lower() not in stop_words]
    return keywords[:3]


# ══════════════════════════════════════════════════════════════════════════════
#  توليد صوت لجميع الأقسام بالتوازي
# ══════════════════════════════════════════════════════════════════════════════

async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """
    توليد صوت لجميع الأقسام بالتوازي (حد أقصى 3 طلبات متزامنة).
    
    Args:
        sections: قائمة الأقسام
        dialect: اللهجة
    
    Returns:
        dict: {
            "results": قائمة نتائج كل قسم,
            "used_fallback": هل تم استخدام gTTS,
            "all_failed": هل فشلت جميع الأقسام
        }
    """
    _sem = asyncio.Semaphore(3)  # 3 طلبات متزامنة كحد أقصى
    
    async def _gen_one(i: int, section: dict) -> dict:
        narration = section.get("narration", section.get("content", ""))
        
        async with _sem:
            try:
                audio_bytes, used_elevenlabs = await generate_voice(narration, dialect)
                duration = await get_audio_duration(audio_bytes)
                used_fallback = not used_elevenlabs
                sentences = split_into_sentences(narration)
                sentence_timings = estimate_sentence_timings(sentences, duration)
                
                logger.info(f"Section {i+1} audio: {duration:.1f}s ({'ElevenLabs' if used_elevenlabs else 'gTTS'})")
                
                return {
                    "index": i,
                    "audio": audio_bytes,
                    "duration": duration,
                    "narration": narration,
                    "sentence_timings": sentence_timings,
                    "used_fallback": used_fallback,
                    "ok": True,
                }
            except Exception as e:
                logger.error(f"All TTS methods failed for section {i+1}: {e}")
                duration_fallback = float(section.get("duration_estimate", 30))
                sentences = split_into_sentences(narration)
                sentence_timings = estimate_sentence_timings(sentences, duration_fallback)
                
                return {
                    "index": i,
                    "audio": None,
                    "duration": duration_fallback,
                    "narration": narration,
                    "sentence_timings": sentence_timings,
                    "used_fallback": False,
                    "ok": False,
                    "error": str(e),
                }
    
    # تنفيذ جميع المهام بالتوازي
    raw = await asyncio.gather(*[_gen_one(i, s) for i, s in enumerate(sections)])
    
    # ترتيب النتائج حسب الفهرس
    results = sorted(raw, key=lambda r: r["index"])
    
    any_fallback = any(r.get("used_fallback") for r in results)
    all_failed = all(not r.get("ok") for r in results)
    
    return {
        "results": results,
        "used_fallback": any_fallback,
        "all_failed": all_failed,
}
