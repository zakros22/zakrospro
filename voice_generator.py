import aiohttp
import asyncio
import re
import io
from config import ELEVENLABS_API_KEYS, VOICES

# ══════════════════════════════════════════════════════════════════════════════
# 🎙️ ELEVENLABS KEY POOL — 9 مفاتيح مع تدوير تلقائي
# ══════════════════════════════════════════════════════════════════════════════
_elevenlabs_pool = list(ELEVENLABS_API_KEYS)
_elevenlabs_idx = 0
_elevenlabs_exhausted = set()
_all_keys_exhausted = False

# gTTS fallback
GTTS_LANG_MAP = {
    "iraq": "ar", "egypt": "ar", "syria": "ar", "gulf": "ar",
    "msa": "ar", "english": "en", "british": "en",
}

# بدائل مجانية إضافية
_FREE_TTS_SERVICES = ["gtts", "edge_tts"]

_ARABIC_INDIC = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')


def _convert_num(raw: str, lang: str) -> str:
    """تحويل الأرقام إلى كلمات"""
    try:
        from num2words import num2words
        clean = raw.replace(',', '')
        val = float(clean) if '.' in clean else int(clean)
        return num2words(val, lang=lang)
    except Exception:
        return raw


def preprocess_text_for_tts(text: str, dialect: str = "msa") -> str:
    """تجهيز النص للتحويل الصوتي"""
    if not text:
        return text

    is_arabic = dialect not in ("english", "british")
    lang = "ar" if is_arabic else "en"

    text = text.translate(_ARABIC_INDIC)

    def _pct_replace(m):
        num_str = m.group(1)
        words = _convert_num(num_str, lang)
        suffix = " بالمئة" if is_arabic else " percent"
        return words + suffix

    def _num_replace(m):
        return _convert_num(m.group(0), lang)

    text = re.sub(r'([\d,]+\.?\d*)\s*%', _pct_replace, text)
    text = re.sub(r'\d[\d,]*\.?\d*', _num_replace, text)

    return text


# ══════════════════════════════════════════════════════════════════════════════
# 🔑 دوال تدوير مفاتيح ElevenLabs
# ══════════════════════════════════════════════════════════════════════════════

def _is_quota_error(status: int, body: str) -> bool:
    """التحقق مما إذا كان الخطأ بسبب نفاد الرصيد"""
    body_lower = body.lower()
    if "quota_exceeded" in body_lower:
        return True
    if "quota" in body_lower and ("exceeded" in body_lower or "limit" in body_lower):
        return True
    if status == 429 and ("quota" in body_lower or "credits" in body_lower):
        return True
    if status == 422 and "quota" in body_lower:
        return True
    if status == 401 and ("invalid" in body_lower or "expired" in body_lower):
        return True
    return False


def _get_next_elevenlabs_key() -> str | None:
    """الحصول على المفتاح التالي المتاح"""
    global _elevenlabs_idx, _elevenlabs_exhausted
    
    available = [k for k in _elevenlabs_pool if k not in _elevenlabs_exhausted]
    if not available:
        return None
    
    key = available[_elevenlabs_idx % len(available)]
    _elevenlabs_idx += 1
    return key


def _mark_elevenlabs_exhausted(key: str):
    """تعليم المفتاح على أنه منتهي"""
    global _elevenlabs_idx, _elevenlabs_exhausted
    _elevenlabs_exhausted.add(key)
    
    total = len(_elevenlabs_pool)
    remaining = total - len(_elevenlabs_exhausted)
    
    if remaining > 0:
        print(f"🔑 ElevenLabs key exhausted — {remaining}/{total} remaining")
    else:
        print("🔇 All ElevenLabs keys exhausted — switching to free TTS")


def keys_status() -> dict:
    """حالة مفاتيح ElevenLabs للوحة التحكم"""
    total = len(_elevenlabs_pool)
    exhausted = len(_elevenlabs_exhausted)
    return {
        "total": total,
        "active": total - exhausted,
        "exhausted": exhausted,
        "all_gone": exhausted >= total if total else True,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 🎙️ ElevenLabs — التوليد الصوتي الرئيسي
# ══════════════════════════════════════════════════════════════════════════════

async def generate_voice_elevenlabs(text: str, dialect: str = "msa") -> bytes:
    """
    توليد صوت باستخدام ElevenLabs مع تدوير 9 مفاتيح.
    يرمي KeyError إذا نفدت كل المفاتيح.
    """
    voice_config = VOICES.get(dialect, VOICES["msa"])
    voice_id = voice_config["voice_id"]
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

    tried_keys = set()
    
    while True:
        key = _get_next_elevenlabs_key()
        if key is None:
            raise KeyError("all_exhausted")
        
        if key in tried_keys:
            # جربنا كل المفاتيح المتاحة
            raise KeyError("all_exhausted")
        tried_keys.add(key)

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": key,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=payload, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if data:
                            print(f"✅ ElevenLabs success: {key[:12]}...")
                            return data
                        raise Exception("Empty audio response")

                    body = await resp.text()

                    if _is_quota_error(resp.status, body):
                        print(f"⚠️ ElevenLabs quota exhausted: {key[:12]}...")
                        _mark_elevenlabs_exhausted(key)
                        continue

                    raise Exception(f"ElevenLabs API error {resp.status}: {body[:200]}")

        except KeyError:
            raise
        except aiohttp.ClientError as e:
            print(f"⚠️ ElevenLabs network error: {e}")
            continue
        except Exception as e:
            print(f"⚠️ ElevenLabs error: {e}")
            continue


# ══════════════════════════════════════════════════════════════════════════════
# 🆓 gTTS — بديل مجاني
# ══════════════════════════════════════════════════════════════════════════════

async def generate_voice_gtts(text: str, dialect: str = "msa") -> bytes:
    """توليد صوت باستخدام gTTS (Google TTS مجاني)"""
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
    return await loop.run_in_executor(None, _synth)


# ══════════════════════════════════════════════════════════════════════════════
# 🎤 Edge TTS — بديل مجاني إضافي (جودة أفضل)
# ══════════════════════════════════════════════════════════════════════════════

async def generate_voice_edge_tts(text: str, dialect: str = "msa") -> bytes:
    """توليد صوت باستخدام Edge TTS (مجاني، جودة عالية)"""
    try:
        import edge_tts
        
        voice_map = {
            "msa": "ar-SA-HamedNeural",
            "iraq": "ar-IQ-RanaNeural",
            "egypt": "ar-EG-SalmaNeural",
            "syria": "ar-SY-AmanyNeural",
            "gulf": "ar-SA-ZariyahNeural",
            "english": "en-US-JennyNeural",
            "british": "en-GB-SoniaNeural",
        }
        
        voice = voice_map.get(dialect, "ar-SA-HamedNeural")
        text = preprocess_text_for_tts(text, dialect)
        
        communicate = edge_tts.Communicate(text, voice)
        
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        
        buf.seek(0)
        return buf.getvalue()
        
    except ImportError:
        raise Exception("edge-tts not installed")
    except Exception as e:
        raise Exception(f"Edge TTS error: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# 🎬 دالة التوليد الرئيسية
# ══════════════════════════════════════════════════════════════════════════════

async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    """
    توليد صوت مع تجربة:
    1. ElevenLabs (مع تدوير 9 مفاتيح)
    2. Edge TTS (مجاني، جودة عالية)
    3. gTTS (مجاني)
    
    Returns: (audio_bytes, used_elevenlabs)
    """
    global _all_keys_exhausted
    
    # 1️⃣ ElevenLabs
    if not _all_keys_exhausted and _elevenlabs_pool:
        try:
            audio_bytes = await generate_voice_elevenlabs(text, dialect)
            return audio_bytes, True
        except KeyError:
            _all_keys_exhausted = True
            print("🔇 All ElevenLabs keys exhausted — switching permanently to free TTS")
        except Exception as e:
            print(f"⚠️ ElevenLabs error: {e} — trying free TTS")
    
    # 2️⃣ Edge TTS (مجاني، جودة أفضل من gTTS)
    try:
        audio_bytes = await generate_voice_edge_tts(text, dialect)
        print("✅ Edge TTS success")
        return audio_bytes, False
    except Exception as e:
        print(f"⚠️ Edge TTS error: {e} — falling back to gTTS")
    
    # 3️⃣ gTTS
    audio_bytes = await generate_voice_gtts(text, dialect)
    print("✅ gTTS success")
    return audio_bytes, False


def reset_tts_engine():
    """إعادة تعيين محرك TTS (لا يفعل شيئاً حالياً)"""
    pass


# ══════════════════════════════════════════════════════════════════════════════
# 📊 دوال مساعدة
# ══════════════════════════════════════════════════════════════════════════════

async def get_audio_duration(audio_bytes: bytes) -> float:
    """حساب مدة المقطع الصوتي"""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
        return len(audio) / 1000.0
    except Exception:
        return len(audio_bytes) / 16000


def split_into_sentences(text: str) -> list:
    """تقسيم النص إلى جمل"""
    sentence_pattern = re.compile(r'(?<=[.!?؟])\s+|(?<=\n)')
    sentences = [s.strip() for s in sentence_pattern.split(text) if s.strip()]
    if not sentences:
        sentences = [text.strip()] if text.strip() else []
    return sentences


def estimate_sentence_timings(sentences: list, total_duration: float) -> list:
    """تقدير توقيت كل جملة"""
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
    """استخراج الكلمات المفتاحية من الجملة"""
    stop_words = {
        'و', 'في', 'من', 'على', 'إلى', 'أن', 'هو', 'هي', 'هذا', 'هذه',
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'to', 'in',
        'that', 'it', 'be', 'for', 'on', 'with', 'as', 'at', 'by', 'this',
    }
    words = re.findall(r'\b[\w\u0600-\u06FF]{4,}\b', sentence)
    keywords = [w for w in words if w.lower() not in stop_words]
    return keywords[:3]


# ══════════════════════════════════════════════════════════════════════════════
# 🎵 توليد صوت لجميع الأقسام (بالتوازي)
# ══════════════════════════════════════════════════════════════════════════════

async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """
    توليد صوت لجميع الأقسام بالتوازي (حد أقصى 3 متزامنة)
    """
    _sem = asyncio.Semaphore(3)

    async def _gen_one(i: int, section: dict) -> dict:
        narration = section.get("narration", section.get("content", ""))
        async with _sem:
            try:
                audio_bytes, used_elevenlabs = await generate_voice(narration, dialect)
                duration = await get_audio_duration(audio_bytes)
                used_fallback = not used_elevenlabs
                sentences = split_into_sentences(narration)
                sentence_timings = estimate_sentence_timings(sentences, duration)
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
                print(f"❌ All TTS methods failed for section {i}: {e}")
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

    raw = await asyncio.gather(*[_gen_one(i, s) for i, s in enumerate(sections)])
    results = sorted(raw, key=lambda r: r["index"])
    any_fallback = any(r.get("used_fallback") for r in results)
    all_failed = all(not r.get("ok") for r in results)

    return {
        "results": results,
        "used_fallback": any_fallback,
        "all_failed": all_failed,
    }
