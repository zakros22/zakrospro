import io
import re
import asyncio
from gtts import gTTS
from config import VOICES

GTTS_LANG_MAP = {k: v["lang"] for k, v in VOICES.items()}

_ARABIC_INDIC = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')

def preprocess_text_for_tts(text: str, dialect: str = "msa") -> str:
    """تجهيز النص للتحويل إلى صوت"""
    if not text:
        return text
    
    # تحويل الأرقام العربية
    text = text.translate(_ARABIC_INDIC)
    return text

async def generate_voice_gtts(text: str, dialect: str = "msa") -> bytes:
    """توليد صوت باستخدام gTTS المجاني"""
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

async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    """توليد صوت - دائماً gTTS"""
    audio_bytes = await generate_voice_gtts(text, dialect)
    return audio_bytes, False

async def get_audio_duration(audio_bytes: bytes) -> float:
    """حساب مدة الصوت"""
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
        return len(audio) / 1000.0
    except:
        return len(audio_bytes) / 16000

def split_into_sentences(text: str) -> list:
    """تقسيم النص إلى جمل"""
    pattern = re.compile(r'(?<=[.!?؟])\s+|(?<=\n)')
    sentences = [s.strip() for s in pattern.split(text) if s.strip()]
    return sentences if sentences else [text.strip()]

def estimate_sentence_timings(sentences: list, total_duration: float) -> list:
    """تقدير توقيت كل جملة"""
    if not sentences:
        return []
    
    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        even = total_duration / len(sentences)
        return [{"text": s, "start": i*even, "end": (i+1)*even} for i, s in enumerate(sentences)]
    
    timings = []
    t = 0.0
    for s in sentences:
        duration = total_duration * (len(s) / total_chars)
        timings.append({"text": s, "start": round(t, 3), "end": round(t + duration, 3)})
        t += duration
    return timings

async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """توليد صوت لكل الأقسام"""
    results = []
    
    for i, section in enumerate(sections):
        narration = section.get("narration", section.get("content", ""))
        try:
            audio_bytes = await generate_voice_gtts(narration, dialect)
            duration = await get_audio_duration(audio_bytes)
            
            sentences = split_into_sentences(narration)
            sentence_timings = estimate_sentence_timings(sentences, duration)
            
            results.append({
                "index": i,
                "audio": audio_bytes,
                "duration": duration,
                "narration": narration,
                "sentence_timings": sentence_timings,
                "used_fallback": False,
            })
        except Exception as e:
            print(f"TTS failed for section {i}: {e}")
            results.append({
                "index": i,
                "audio": None,
                "duration": 30,
                "narration": narration,
                "sentence_timings": [],
                "used_fallback": True,
            })
    
    return {"results": results, "used_fallback": False, "all_failed": False}

def reset_tts_engine():
    """إعادة تعيين محرك الصوت"""
    pass
