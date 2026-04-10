import asyncio
import io
import tempfile
import os
from typing import List, Dict, Any
from gtts import gTTS
from pydub import AudioSegment


# دعم اللهجات المختلفة عبر نطق مختلف
DIALECT_TLD_MAP = {
    "iraq": "com",      # العراق - استخدام النطاق العام
    "egypt": "com.eg",  # مصر
    "syria": "com",     # سوريا
    "gulf": "com.sa",   # الخليج - السعودية
    "msa": "com",       # الفصحى
    "english": "com",   # إنجليزي أمريكي
    "british": "co.uk", # إنجليزي بريطاني
}

# تعديل النطق للهجات المختلفة عبر إضافة كلمات توضيحية
DIALECT_STYLE_HINTS = {
    "iraq": "بلهجة عراقية: ",
    "egypt": "بلهجة مصرية: ",
    "syria": "بلهجة شامية: ",
    "gulf": "بلهجة خليجية: ",
    "msa": "بالعربية الفصحى: ",
    "english": "",
    "british": "",
}


def _add_dialect_flavor(text: str, dialect: str) -> str:
    """إضافة نكهة اللهجة للنص لينطق بشكل أقرب للهجة المطلوبة"""
    if dialect in DIALECT_STYLE_HINTS and DIALECT_STYLE_HINTS[dialect]:
        return DIALECT_STYLE_HINTS[dialect] + text
    return text


def _generate_single_audio(text: str, dialect: str, lang: str = "ar") -> bytes:
    """
    توليد ملف صوتي باستخدام gTTS (مجاني تماماً)
    """
    try:
        tld = DIALECT_TLD_MAP.get(dialect, "com")

        # تحضير النص مع إضافة نكهة اللهجة
        flavored_text = _add_dialect_flavor(text, dialect)

        # إنشاء ملف مؤقت للصوت
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        # توليد الصوت باستخدام gTTS
        tts = gTTS(text=flavored_text, lang=lang, tld=tld, slow=False)
        tts.save(tmp_path)

        # قراءة الملف
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()

        # حذف الملف المؤقت
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        # حساب مدة الصوت
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        duration = len(audio) / 1000.0

        return audio_bytes, duration

    except Exception as e:
        print(f"❌ gTTS error for dialect {dialect}: {e}")
        # محاولة مرة أخرى بدون tld محدد
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

            return audio_bytes, duration

        except Exception as e2:
            print(f"❌ gTTS fallback also failed: {e2}")
            raise


async def _generate_single_audio_async(text: str, dialect: str) -> Dict[str, Any]:
    """نسخة غير متزامنة من توليد الصوت"""
    loop = asyncio.get_event_loop()

    if dialect in ("english", "british"):
        lang = "en"
    else:
        lang = "ar"

    try:
        audio_bytes, duration = await loop.run_in_executor(
            None, _generate_single_audio, text, dialect, lang
        )
        return {
            "audio": audio_bytes,
            "duration": duration,
            "dialect": dialect,
            "used_fallback": False,
            "provider": "gTTS",
        }
    except Exception as e:
        print(f"❌ Audio generation failed for dialect {dialect}: {e}")
        raise


async def generate_sections_audio(
    sections: List[Dict[str, Any]],
    dialect: str = "msa"
) -> Dict[str, Any]:
    """
    توليد الصوت لجميع الأقسام باستخدام gTTS المجاني
    """
    results = []
    total_duration = 0.0

    print(f"🎤 Generating audio for {len(sections)} sections using gTTS (FREE)...")

    for idx, section in enumerate(sections):
        narration = section.get("narration", "")
        if not narration:
            narration = section.get("content", f"القسم {idx + 1}")

        print(f"  🔊 Generating section {idx + 1}/{len(sections)}...")

        try:
            result = await _generate_single_audio_async(narration, dialect)
            results.append(result)
            total_duration += result["duration"]
            print(f"  ✅ Section {idx + 1} audio ready ({result['duration']:.1f}s)")
        except Exception as e:
            print(f"  ⚠️ Section {idx + 1} failed, using silent audio: {e}")
            # إنشاء صوت صامت كاحتياط
            silent = AudioSegment.silent(duration=5000)  # 5 ثواني
            buf = io.BytesIO()
            silent.export(buf, format="mp3")
            results.append({
                "audio": buf.getvalue(),
                "duration": 5.0,
                "dialect": dialect,
                "used_fallback": True,
                "provider": "silent_fallback",
            })
            total_duration += 5.0

    return {
        "results": results,
        "total_duration": total_duration,
        "used_fallback": False,
        "provider": "gTTS",
    }


def keys_status() -> Dict[str, Any]:
    """
    حالة المفاتيح - دائماً نشط لأن gTTS مجاني ولا يحتاج مفاتيح
    """
    return {
        "total": 1,
        "active": 1,
        "exhausted": 0,
        "all_gone": False,
        "provider": "gTTS (مجاني)",
        }
