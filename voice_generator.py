import asyncio
import io
import tempfile
import os
from typing import List, Dict, Any
from gtts import gTTS
from pydub import AudioSegment


# ============================================================
# إعدادات اللهجات
# ============================================================

# نطاقات TLD للحصول على نطق أقرب للهجة
DIALECT_TLD_MAP = {
    "iraq": "com",
    "egypt": "com.eg",
    "syria": "com",
    "gulf": "com.sa",
    "msa": "com",
    "english": "com",
    "british": "co.uk",
}

# إضافات نصية لتحسين النطق باللهجة المطلوبة
DIALECT_STYLE_HINTS = {
    "iraq": "بلهجة عراقية: ",
    "egypt": "بلهجة مصرية: ",
    "syria": "بلهجة شامية: ",
    "gulf": "بلهجة خليجية: ",
    "msa": "بالعربية الفصحى: ",
    "english": "",
    "british": "",
}

# كلمات تحويل للهجات (لتحسين النطق)
DIALECT_WORD_MAP = {
    "iraq": {
        "كثير": "هواية",
        "ماذا": "شنو",
        "أين": "وين",
        "الآن": "هسة",
        "قال": "كال",
        "يوجد": "أكو",
        "لا يوجد": "ماكو",
    },
    "egypt": {
        "كثير": "أوي",
        "ماذا": "إيه",
        "الآن": "دلوقتي",
        "هذا": "ده",
        "هذه": "دي",
        "ليس": "مش",
        "فقط": "بس",
    },
    "syria": {
        "كثير": "كتير",
        "ماذا": "شو",
        "الآن": "هلق",
        "جيد": "منيح",
        "هكذا": "هيك",
        "شيء": "شي",
    },
    "gulf": {
        "كثير": "وايد",
        "جيد": "زين",
        "الآن": "الحين",
        "ماذا": "وش",
        "هذا": "هاذا",
        "نعم": "إيه",
    },
    "msa": {},
    "english": {},
    "british": {},
}


def _apply_dialect_conversion(text: str, dialect: str) -> str:
    """
    تحويل بعض الكلمات إلى اللهجة المطلوبة لتحسين النطق.
    """
    if dialect not in DIALECT_WORD_MAP:
        return text
    
    word_map = DIALECT_WORD_MAP[dialect]
    result = text
    for standard, dialect_word in word_map.items():
        result = result.replace(standard, dialect_word)
    
    return result


def _add_dialect_flavor(text: str, dialect: str) -> str:
    """
    إضافة مقدمة نصية لتحفيز النطق باللهجة المطلوبة.
    """
    if dialect in DIALECT_STYLE_HINTS and DIALECT_STYLE_HINTS[dialect]:
        return DIALECT_STYLE_HINTS[dialect] + text
    return text


def _generate_single_audio(text: str, dialect: str, lang: str = "ar") -> tuple[bytes, float]:
    """
    توليد ملف صوتي واحد باستخدام gTTS.
    
    Returns:
        tuple: (audio_bytes, duration_in_seconds)
    """
    try:
        tld = DIALECT_TLD_MAP.get(dialect, "com")
        
        # تطبيق تحويلات اللهجة
        converted_text = _apply_dialect_conversion(text, dialect)
        flavored_text = _add_dialect_flavor(converted_text, dialect)

        # إنشاء ملف مؤقت
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        # توليد الصوت
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

        # حساب المدة
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
        duration = len(audio) / 1000.0

        return audio_bytes, duration

    except Exception as e:
        print(f"❌ gTTS error for dialect {dialect}: {e}")
        
        # محاولة مرة أخرى بدون تحويلات
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
            # إرجاع صوت صامت كحل أخير
            silent = AudioSegment.silent(duration=5000)
            buf = io.BytesIO()
            silent.export(buf, format="mp3")
            return buf.getvalue(), 5.0


async def _generate_single_audio_async(text: str, dialect: str) -> Dict[str, Any]:
    """
    نسخة غير متزامنة من توليد الصوت.
    """
    loop = asyncio.get_event_loop()

    # تحديد اللغة
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
        # صوت صامت كحل أخير
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
    توليد الصوت لجميع أقسام المحاضرة.
    
    Args:
        sections: قائمة الأقسام (كل قسم يحتوي على 'narration')
        dialect: اللهجة المطلوبة
    
    Returns:
        Dict: يحتوي على 'results' (قائمة الأصوات) و 'total_duration'
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
            print(f"  ⚠️ Section {idx + 1} failed: {e}")
            # صوت صامت
            silent = AudioSegment.silent(duration=5000)
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
        "provider": "gTTS (مجاني)",
    }


async def generate_audio_for_section(text: str, dialect: str) -> Dict[str, Any]:
    """
    توليد صوت لقسم واحد (دالة مساعدة).
    """
    return await _generate_single_audio_async(text, dialect)


def keys_status() -> Dict[str, Any]:
    """
    حالة المفاتيح - gTTS مجاني دائماً ولا يحتاج مفاتيح.
    """
    return {
        "total": 1,
        "active": 1,
        "exhausted": 0,
        "all_gone": False,
        "provider": "gTTS (مجاني بالكامل)",
    }
