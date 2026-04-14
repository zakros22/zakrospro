#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import io
import asyncio
from gtts import gTTS

# ══════════════════════════════════════════════════════════════════════════════
#  خريطة اللغات
# ══════════════════════════════════════════════════════════════════════════════
LANG_MAP = {
    "iraq": "ar", "egypt": "ar", "syria": "ar", "gulf": "ar", "msa": "ar",
    "english": "en", "british": "en"
}

# ══════════════════════════════════════════════════════════════════════════════
#  توليد الصوت
# ══════════════════════════════════════════════════════════════════════════════
async def generate_voice(text: str, dialect: str = "msa") -> bytes:
    """توليد صوت باستخدام gTTS."""
    lang = LANG_MAP.get(dialect, "ar")
    
    def _synth():
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _synth)


async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """توليد صوت لجميع الأقسام."""
    results = []
    
    for i, section in enumerate(sections):
        narration = section.get("narration", "")
        try:
            audio = await generate_voice(narration, dialect)
            duration = len(narration) // 10  # تقدير المدة
            results.append({
                "index": i, "audio": audio, "duration": max(duration, 5),
                "narration": narration, "ok": True
            })
        except Exception as e:
            results.append({
                "index": i, "audio": None, "duration": 30,
                "narration": narration, "ok": False, "error": str(e)
            })
    
    return {"results": results, "used_fallback": True, "all_failed": False}
