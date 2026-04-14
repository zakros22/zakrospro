#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
توليد الصوت - ElevenLabs مع تناوب المفاتيح و gTTS احتياطي
"""

import io
import re
import asyncio
import aiohttp
import logging
from config import ELEVENLABS_API_KEYS, VOICES

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  إعدادات gTTS
# ══════════════════════════════════════════════════════════════════════════════
GTTS_LANG_MAP = {
    "iraq": "ar", "egypt": "ar", "syria": "ar", "gulf": "ar", "msa": "ar",
    "english": "en", "british": "en"
}

# ══════════════════════════════════════════════════════════════════════════════
#  نظام تناوب مفاتيح ElevenLabs
# ══════════════════════════════════════════════════════════════════════════════
_key_idx = 0
_exhausted = set()
_all_exhausted = False


def _current_key():
    global _key_idx
    if not ELEVENLABS_API_KEYS:
        return None
    for _ in range(len(ELEVENLABS_API_KEYS)):
        k = ELEVENLABS_API_KEYS[_key_idx % len(ELEVENLABS_API_KEYS)]
        if k not in _exhausted:
            return k
        _key_idx += 1
    return None


def _mark_exhausted(key):
    global _key_idx, _all_exhausted
    _exhausted.add(key)
    _key_idx += 1
    if len(_exhausted) >= len(ELEVENLABS_API_KEYS):
        _all_exhausted = True


def _is_quota_error(status, body):
    return "quota_exceeded" in body or status in (429, 422)


# ══════════════════════════════════════════════════════════════════════════════
#  تحويل الأرقام إلى كلمات
# ══════════════════════════════════════════════════════════════════════════════
_ARABIC_INDIC = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')


def _convert_num(raw, lang):
    try:
        from num2words import num2words
        clean = raw.replace(',', '')
        val = float(clean) if '.' in clean else int(clean)
        return num2words(val, lang=lang)
    except:
        return raw


def preprocess_text(text: str, dialect: str = "msa") -> str:
    """تجهيز النص للتحويل إلى صوت."""
    if not text:
        return text
    
    is_arabic = dialect not in ("english", "british")
    lang = "ar" if is_arabic else "en"
    
    text = text.translate(_ARABIC_INDIC)
    
    def pct_replace(m):
        words = _convert_num(m.group(1), lang)
        return words + (" بالمئة" if is_arabic else " percent")
    
    def num_replace(m):
        return _convert_num(m.group(0), lang)
    
    text = re.sub(r'([\d,]+\.?\d*)\s*%', pct_replace, text)
    text = re.sub(r'\d[\d,]*\.?\d*', num_replace, text)
    
    return text


# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصوت
# ══════════════════════════════════════════════════════════════════════════════
async def generate_elevenlabs(text: str, dialect: str) -> bytes:
    """توليد صوت باستخدام ElevenLabs."""
    global _all_exhausted
    
    if _all_exhausted or not ELEVENLABS_API_KEYS:
        raise Exception("No ElevenLabs keys")
    
    voice_id = VOICES.get(dialect, VOICES["msa"])["voice_id"]
    text = preprocess_text(text, dialect)
    
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.6, "similarity_boost": 0.85, "style": 0.4, "use_speaker_boost": True}
    }
    
    while True:
        key = _current_key()
        if not key:
            _all_exhausted = True
            raise Exception("All keys exhausted")
        
        try:
            headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": key}
            async with aiohttp.ClientSession() as s:
                async with s.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}", json=payload, headers=headers, timeout=60) as r:
                    if r.status == 200:
                        data = await r.read()
                        if data:
                            return data
                    body = await r.text()
                    if _is_quota_error(r.status, body):
                        _mark_exhausted(key)
                        continue
                    raise Exception(f"ElevenLabs error: {r.status}")
        except Exception as e:
            if "quota" in str(e).lower():
                _mark_exhausted(key)
                continue
            raise


async def generate_gtts(text: str, dialect: str) -> bytes:
    """توليد صوت باستخدام gTTS."""
    from gtts import gTTS
    
    lang = GTTS_LANG_MAP.get(dialect, "ar")
    text = preprocess_text(text, dialect)
    
    def _synth():
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    
    return await asyncio.get_event_loop().run_in_executor(None, _synth)


async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    """
    توليد صوت. ترجع (audio_bytes, used_elevenlabs)
    """
    if not _all_exhausted and ELEVENLABS_API_KEYS:
        try:
            return await generate_elevenlabs(text, dialect), True
        except:
            pass
    
    return await generate_gtts(text, dialect), False


async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """توليد صوت لجميع الأقسام."""
    results = []
    
    for i, sec in enumerate(sections):
        narration = sec.get("narration", "")
        try:
            audio, used_el = await generate_voice(narration, dialect)
            duration = max(len(narration) // 10, 8)
            results.append({
                "index": i, "audio": audio, "duration": duration,
                "narration": narration, "ok": True, "used_elevenlabs": used_el
            })
            logger.info(f"Section {i+1} audio: {duration}s ({'ElevenLabs' if used_el else 'gTTS'})")
        except Exception as e:
            logger.error(f"Section {i+1} audio failed: {e}")
            results.append({
                "index": i, "audio": None, "duration": 30,
                "narration": narration, "ok": False, "error": str(e)
            })
    
    any_el = any(r.get("used_elevenlabs") for r in results)
    all_failed = all(not r.get("ok") for r in results)
    
    return {"results": results, "used_elevenlabs": any_el, "all_failed": all_failed}


def keys_status() -> dict:
    """حالة مفاتيح ElevenLabs."""
    total = len(ELEVENLABS_API_KEYS)
    exhausted = len(_exhausted)
    return {
        "total": total,
        "active": total - exhausted,
        "exhausted": exhausted,
        "all_gone": exhausted >= total if total else True
        }
