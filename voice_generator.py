# -*- coding: utf-8 -*-
import asyncio
import io
import re
from gtts import gTTS


def clean_text(text: str) -> str:
    """تنظيف النص"""
    if not text:
        return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _convert_numbers(text: str, lang: str) -> str:
    """تحويل الأرقام إلى كلمات"""
    try:
        from num2words import num2words
        
        def replace_num(match):
            num_str = match.group(0).replace(',', '')
            try:
                if '.' in num_str:
                    num = float(num_str)
                else:
                    num = int(num_str)
                return num2words(num, lang=lang)
            except:
                return match.group(0)
        
        text = re.sub(r'\d[\d,]*\.?\d*', replace_num, text)
    except:
        pass
    return text


def _convert_percentages(text: str, lang: str) -> str:
    """تحويل النسب المئوية إلى كلمات"""
    try:
        from num2words import num2words
        
        def replace_pct(match):
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
        
        text = re.sub(r'([\d,]+\.?\d*)\s*%', replace_pct, text)
    except:
        pass
    return text


GTTS_LANG_MAP = {
    "iraq": "ar",
    "egypt": "ar",
    "syria": "ar",
    "gulf": "ar",
    "msa": "ar",
    "english": "en",
    "british": "en"
}


async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    """توليد الصوت باستخدام gTTS مع تحويل الأرقام"""
    text = clean_text(text) or "محاضرة"
    lang = GTTS_LANG_MAP.get(dialect, "ar")
    
    # تحويل الأرقام والنسب المئوية
    text = _convert_percentages(text, lang)
    text = _convert_numbers(text, lang)
    
    def _synth():
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    
    loop = asyncio.get_event_loop()
    audio = await loop.run_in_executor(None, _synth)
    return audio, False


async def get_audio_duration(audio: bytes) -> float:
    """حساب مدة الصوت"""
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(io.BytesIO(audio))
        return len(seg) / 1000.0
    except:
        return max(5.0, len(audio) / 16000)


async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """توليد الصوت لجميع الأقسام"""
    sem = asyncio.Semaphore(3)
    
    async def _gen_one(i: int, section: dict):
        txt = clean_text(section.get("narration", ""))
        if not txt:
            txt = " ".join(section.get("keywords", ["مفهوم"]))
        
        async with sem:
            try:
                aud, _ = await generate_voice(txt, dialect)
                dur = await get_audio_duration(aud)
                return {"index": i, "audio": aud, "duration": dur, "ok": True}
            except Exception as e:
                print(f"TTS error: {e}")
                return {"index": i, "audio": None, "duration": 30, "ok": False}
    
    results = await asyncio.gather(*[_gen_one(i, s) for i, s in enumerate(sections)])
    results = sorted(results, key=lambda x: x["index"])
    
    return {
        "results": results,
        "used_fallback": True,
        "all_failed": all(not r["ok"] for r in results)
            }        "all_gone": False,
        "provider": "gTTS (مجاني)",
}
