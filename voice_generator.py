# -*- coding: utf-8 -*-
import asyncio
import io
import re
from gtts import gTTS

GTTS_LANG_MAP = {
    "iraq": "ar",
    "egypt": "ar",
    "syria": "ar",
    "gulf": "ar",
    "msa": "ar",
    "english": "en",
    "british": "en",
}


def _clean_text(text: str) -> str:
    """
    تنظيف النص من الأحرف غير المرغوبة:
    - null bytes (\x00)
    - أحرف التحكم
    - مسافات زائدة
    """
    if not text:
        return ""
    
    # إزالة null bytes
    text = text.replace('\x00', '')
    text = text.replace('\0', '')
    
    # إزالة أحرف التحكم (ما عدا الأسطر الجديدة وعلامات الترقيم)
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # استبدال المسافات المتعددة بمسافة واحدة
    text = re.sub(r'\s+', ' ', text)
    
    # إزالة المسافات في البداية والنهاية
    text = text.strip()
    
    return text


async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    """
    توليد الصوت باستخدام gTTS المجاني.
    Returns: (audio_bytes, used_elevenlabs) - used_elevenlabs دائماً False
    """
    # تنظيف النص أولاً
    text = _clean_text(text)
    
    if not text:
        # إذا كان النص فارغاً بعد التنظيف، نستخدم نص افتراضي
        text = "المحاضرة التعليمية"
    
    lang = GTTS_LANG_MAP.get(dialect, "ar")
    
    def _synth():
        buf = io.BytesIO()
        try:
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.write_to_fp(buf)
            buf.seek(0)
            return buf.read()
        except Exception as e:
            print(f"[ERROR] gTTS failed: {e}")
            # محاولة أخيرة مع نص مبسط
            try:
                simple_text = " ".join(text.split()[:100])  # أول 100 كلمة فقط
                buf2 = io.BytesIO()
                tts2 = gTTS(text=simple_text, lang=lang, slow=False)
                tts2.write_to_fp(buf2)
                buf2.seek(0)
                return buf2.read()
            except:
                raise

    loop = asyncio.get_event_loop()
    audio_bytes = await loop.run_in_executor(None, _synth)
    return audio_bytes, False


async def get_audio_duration(audio_bytes: bytes) -> float:
    """
    حساب مدة الصوت بالثواني
    """
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
        return len(audio) / 1000.0
    except Exception:
        # تقدير تقريبي: 1 ثانية = 16000 بايت
        return max(5.0, len(audio_bytes) / 16000)


async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """
    توليد الصوت لجميع الأقسام بالتوازي
    """
    _sem = asyncio.Semaphore(3)

    async def _gen_one(i: int, section: dict) -> dict:
        # استخدام النص الأصلي للقسم
        text = section.get("narration", "")
        if not text:
            text = " ".join(section.get("keywords", ["مفهوم"])) * 3
        
        # تنظيف النص
        text = _clean_text(text)
        
        if not text:
            text = f"القسم {i+1}"
        
        async with _sem:
            try:
                audio_bytes, _ = await generate_voice(text, dialect)
                duration = await get_audio_duration(audio_bytes)
                return {
                    "index": i,
                    "audio": audio_bytes,
                    "duration": duration,
                    "ok": True,
                }
            except Exception as e:
                print(f"[ERROR] TTS failed for section {i}: {e}")
                return {
                    "index": i,
                    "audio": None,
                    "duration": 30,
                    "ok": False,
                }

    print(f"[INFO] Generating audio for {len(sections)} sections...")
    raw = await asyncio.gather(*[_gen_one(i, s) for i, s in enumerate(sections)])
    results = sorted(raw, key=lambda r: r["index"])
    
    return {
        "results": results,
        "used_fallback": True,
        "all_failed": all(not r.get("ok") for r in results),
                }
