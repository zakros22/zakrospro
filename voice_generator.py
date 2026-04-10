import asyncio
import io
import re
from gtts import gTTS

# ── خريطة اللغات ─────────────────────────────────────────────────────────────
GTTS_LANG_MAP = {
    "iraq": "ar",
    "egypt": "ar",
    "syria": "ar",
    "gulf": "ar",
    "msa": "ar",
    "english": "en",
    "british": "en",
}

_ARABIC_INDIC = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')


def _convert_num(raw: str, lang: str) -> str:
    try:
        from num2words import num2words
        clean = raw.replace(',', '')
        val = float(clean) if '.' in clean else int(clean)
        return num2words(val, lang=lang)
    except Exception:
        return raw


def preprocess_text_for_tts(text: str, dialect: str = "msa") -> str:
    """تحضير النص للصوت - تحويل الأرقام إلى كلمات"""
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


async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    """
    توليد الصوت باستخدام gTTS المجاني
    Returns (audio_bytes, used_elevenlabs: bool) - دائماً False لأنه gTTS
    """
    lang = GTTS_LANG_MAP.get(dialect, "ar")
    text = preprocess_text_for_tts(text, dialect)

    def _synth():
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()

    loop = asyncio.get_event_loop()
    audio_bytes = await loop.run_in_executor(None, _synth)
    return audio_bytes, False


async def get_audio_duration(audio_bytes: bytes) -> float:
    """حساب مدة الصوت بالثواني"""
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


async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """
    توليد الصوت لجميع الأقسام بالتوازي
    """
    _sem = asyncio.Semaphore(3)

    async def _gen_one(i: int, section: dict) -> dict:
        narration = section.get("narration", section.get("content", ""))
        async with _sem:
            try:
                audio_bytes, _ = await generate_voice(narration, dialect)
                duration = await get_audio_duration(audio_bytes)
                sentences = split_into_sentences(narration)
                sentence_timings = estimate_sentence_timings(sentences, duration)
                return {
                    "index": i,
                    "audio": audio_bytes,
                    "duration": duration,
                    "narration": narration,
                    "sentence_timings": sentence_timings,
                    "used_fallback": True,
                    "ok": True,
                }
            except Exception as e:
                print(f"TTS failed for section {i}: {e}")
                duration_fallback = float(section.get("duration_estimate", 30))
                sentences = split_into_sentences(narration)
                sentence_timings = estimate_sentence_timings(sentences, duration_fallback)
                return {
                    "index": i,
                    "audio": None,
                    "duration": duration_fallback,
                    "narration": narration,
                    "sentence_timings": sentence_timings,
                    "used_fallback": True,
                    "ok": False,
                    "error": str(e),
                }

    raw = await asyncio.gather(*[_gen_one(i, s) for i, s in enumerate(sections)])
    results = sorted(raw, key=lambda r: r["index"])
    all_failed = all(not r.get("ok") for r in results)

    return {
        "results": results,
        "used_fallback": True,
        "all_failed": all_failed,
    }
