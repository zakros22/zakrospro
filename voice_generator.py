import asyncio
import io
import tempfile
import os
from typing import List, Dict, Any

# ============================================================
# توليد الصوت - مع نظام احتياطي يضمن عدم الفشل
# ============================================================

def _generate_silent_audio(duration: float = 5.0) -> bytes:
    """توليد صوت صامت كحل أخير"""
    try:
        from pydub import AudioSegment
        silent = AudioSegment.silent(duration=int(duration * 1000))
        buf = io.BytesIO()
        silent.export(buf, format="mp3")
        return buf.getvalue()
    except:
        # إذا فشل pydub، نرجع صوت فارغ
        return b""


def _generate_with_gtts(text: str, lang: str = "ar", tld: str = "com") -> tuple[bytes, float]:
    """توليد صوت باستخدام gTTS"""
    try:
        from gtts import gTTS
        
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name
        
        # محاولة توليد الصوت
        tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
        tts.save(tmp_path)
        
        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
        
        try:
            os.unlink(tmp_path)
        except:
            pass
        
        # حساب المدة
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            duration = len(audio) / 1000.0
        except:
            # تقدير المدة: حوالي 150 كلمة في الدقيقة
            duration = len(text.split()) * 0.4
        
        return audio_bytes, max(duration, 3.0)
        
    except Exception as e:
        print(f"⚠️ gTTS failed: {str(e)[:50]}")
        raise


async def _generate_single_audio(text: str, dialect: str) -> Dict[str, Any]:
    """توليد صوت لقسم واحد مع نظام احتياطي"""
    
    # تحديد اللغة
    if dialect in ("english", "british"):
        lang = "en"
        tld = "co.uk" if dialect == "british" else "com"
    else:
        lang = "ar"
        tld_map = {
            "iraq": "com", "egypt": "com.eg", "syria": "com", 
            "gulf": "com.sa", "msa": "com"
        }
        tld = tld_map.get(dialect, "com")
    
    # تنظيف النص
    text = text.strip()
    if not text:
        text = "المحتوى غير متوفر"
    
    # المحاولة الأولى - gTTS مع الإعدادات المحددة
    try:
        loop = asyncio.get_event_loop()
        audio_bytes, duration = await loop.run_in_executor(
            None, _generate_with_gtts, text, lang, tld
        )
        print(f"✅ Audio generated: {duration:.1f}s")
        return {
            "audio": audio_bytes,
            "duration": duration,
            "used_fallback": False,
        }
    except Exception as e:
        print(f"⚠️ First attempt failed: {str(e)[:50]}")
    
    # المحاولة الثانية - gTTS بدون tld محدد
    try:
        loop = asyncio.get_event_loop()
        audio_bytes, duration = await loop.run_in_executor(
            None, _generate_with_gtts, text, lang, "com"
        )
        print(f"✅ Audio generated (fallback): {duration:.1f}s")
        return {
            "audio": audio_bytes,
            "duration": duration,
            "used_fallback": True,
        }
    except Exception as e:
        print(f"⚠️ Second attempt failed: {str(e)[:50]}")
    
    # المحاولة الثالثة - نص مختصر
    try:
        short_text = text[:500] + "..."
        loop = asyncio.get_event_loop()
        audio_bytes, duration = await loop.run_in_executor(
            None, _generate_with_gtts, short_text, lang, "com"
        )
        print(f"✅ Audio generated (short): {duration:.1f}s")
        return {
            "audio": audio_bytes,
            "duration": duration,
            "used_fallback": True,
        }
    except Exception as e:
        print(f"⚠️ Third attempt failed: {str(e)[:50]}")
    
    # الحل الأخير - صوت صامت
    print("🔇 Using silent audio as last resort")
    duration = max(len(text.split()) * 0.4, 5.0)
    silent_audio = _generate_silent_audio(duration)
    
    return {
        "audio": silent_audio,
        "duration": duration,
        "used_fallback": True,
    }


async def generate_sections_audio(
    sections: List[Dict[str, Any]],
    dialect: str = "msa"
) -> Dict[str, Any]:
    """توليد الصوت لجميع الأقسام"""
    results = []
    total_duration = 0.0
    
    print(f"🎤 Generating audio for {len(sections)} sections...")
    
    for idx, section in enumerate(sections):
        narration = section.get("narration", "")
        if not narration:
            narration = section.get("content", f"القسم {idx + 1}")
        
        print(f"  🔊 Section {idx + 1}/{len(sections)}...")
        
        result = await _generate_single_audio(narration, dialect)
        results.append(result)
        total_duration += result["duration"]
        
        status = "⚠️" if result.get("used_fallback") else "✅"
        print(f"  {status} Section {idx + 1}: {result['duration']:.1f}s")
    
    return {
        "results": results,
        "total_duration": total_duration,
        "used_fallback": any(r.get("used_fallback") for r in results),
    }


async def generate_audio_for_section(text: str, dialect: str) -> Dict[str, Any]:
    """توليد صوت لقسم واحد"""
    return await _generate_single_audio(text, dialect)
