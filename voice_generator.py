import asyncio
import io
import tempfile
import os
from typing import List, Dict, Any
from gtts import gTTS
from pydub import AudioSegment


# ═════════════════════════════════════════════════════════════════════════════
# إعدادات اللهجات - تصحيح كامل
# ═════════════════════════════════════════════════════════════════════════════
DIALECT_LANG_MAP = {
    "iraq": "ar",
    "egypt": "ar",
    "syria": "ar",
    "gulf": "ar",
    "msa": "ar",
    "english": "en",
    "british": "en",
}

DIALECT_TLD_MAP = {
    "iraq": "com",
    "egypt": "com.eg",
    "syria": "com",
    "gulf": "com.sa",
    "msa": "com",
    "english": "com",
    "british": "co.uk",
}


def _generate_single_audio(text: str, dialect: str) -> tuple[bytes, float]:
    """
    توليد ملف صوتي باستخدام gTTS مع دعم اللهجات
    """
    try:
        lang = DIALECT_LANG_MAP.get(dialect, "ar")
        tld = DIALECT_TLD_MAP.get(dialect, "com")
        
        # تنظيف النص من الأحرف غير المدعومة
        import re
        text = re.sub(r'[^\w\s\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF\.\,\!\?\-\:\;\'\"\(\)\[\]\@\&\*\%\#\$\€\£\¥\،\؟\؛\ـ]', ' ', text)
        text = ' '.join(text.split())
        
        if not text or len(text) < 10:
            silent = AudioSegment.silent(duration=5000)
            buf = io.BytesIO()
            silent.export(buf, format="mp3")
            return buf.getvalue(), 5.0
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        
        # إنشاء الصوت
        tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
        tts.save(tmp_path)
        
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
        
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        
        # حساب المدة
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        duration = len(audio) / 1000.0
        
        print(f"✅ Audio generated: {len(audio_bytes)//1024}KB, {duration:.1f}s")
        return audio_bytes, duration

    except Exception as e:
        print(f"❌ gTTS error for dialect {dialect}: {e}")
        # محاولة مرة أخرى بدون TLD
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            
            tts = gTTS(text=text, lang=lang, slow=False)
            tts.save(tmp_path)
            
            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()
            
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            duration = len(audio) / 1000.0
            
            print(f"✅ Audio generated (fallback): {duration:.1f}s")
            return audio_bytes, duration
            
        except Exception as e2:
            print(f"❌ gTTS fallback failed: {e2}")
            silent = AudioSegment.silent(duration=5000)
            buf = io.BytesIO()
            silent.export(buf, format="mp3")
            return buf.getvalue(), 5.0


async def _generate_single_audio_async(text: str, dialect: str) -> Dict[str, Any]:
    """نسخة غير متزامنة من توليد الصوت"""
    loop = asyncio.get_event_loop()
    
    try:
        audio_bytes, duration = await loop.run_in_executor(
            None, _generate_single_audio, text, dialect
        )
        return {
            "audio": audio_bytes,
            "duration": duration,
            "dialect": dialect,
            "used_fallback": False,
            "provider": "gTTS",
        }
    except Exception as e:
        print(f"❌ Audio generation failed: {e}")
        silent = AudioSegment.silent(duration=5000)
        buf = io.BytesIO()
        silent.export(buf, format="mp3")
        return {
            "audio": buf.getvalue(),
            "duration": 5.0,
            "dialect": dialect,
            "used_fallback": True,
            "provider": "silent_fallback",
        }


async def generate_sections_audio(
    sections: List[Dict[str, Any]],
    dialect: str = "msa"
) -> Dict[str, Any]:
    """
    توليد الصوت لجميع الأقسام
    """
    results = []
    total_duration = 0.0

    print(f"🎤 Generating audio for {len(sections)} sections...")
    print(f"🌍 Dialect: {dialect}")

    for idx, section in enumerate(sections):
        # استخدام narration إذا وجد، وإلا content
        narration = section.get("narration", "")
        if not narration:
            narration = section.get("content", "")
        if not narration:
            narration = f"القسم {idx + 1}"

        print(f"  🔊 Section {idx + 1}/{len(sections)}: {narration[:50]}...")

        result = await _generate_single_audio_async(narration, dialect)
        results.append(result)
        total_duration += result["duration"]
        print(f"  ✅ Section {idx + 1} ready ({result['duration']:.1f}s)")

    print(f"🎤 Total audio duration: {total_duration:.1f}s")
    
    return {
        "results": results,
        "total_duration": total_duration,
        "used_fallback": False,
        "provider": "gTTS",
    }


def keys_status() -> Dict[str, Any]:
    """حالة المفاتيح - gTTS مجاني دائماً"""
    return {
        "total": 1,
        "active": 1,
        "exhausted": 0,
        "all_gone": False,
        "provider": "gTTS (مجاني)",
                }
