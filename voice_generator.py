# -*- coding: utf-8 -*-
import asyncio
import io
import re
from gtts import gTTS

def clean_text(text: str) -> str:
    if not text: return ""
    text = str(text).replace('\x00', '').replace('\0', '')
    text = re.sub(r'[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return re.sub(r'\s+', ' ', text).strip()

GTTS_LANG = {"iraq": "ar", "egypt": "ar", "syria": "ar", "gulf": "ar", "msa": "ar", "english": "en", "british": "en"}

async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    text = clean_text(text) or "محاضرة تعليمية"
    lang = GTTS_LANG.get(dialect, "ar")
    def _synth():
        buf = io.BytesIO()
        gTTS(text=text, lang=lang, slow=False).write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    audio = await asyncio.get_event_loop().run_in_executor(None, _synth)
    return audio, False

async def get_audio_duration(audio: bytes) -> float:
    try:
        from pydub import AudioSegment
        return len(AudioSegment.from_mp3(io.BytesIO(audio))) / 1000.0
    except:
        return max(5.0, len(audio) / 16000)

async def generate_sections_audio(sections: list, dialect: str) -> dict:
    sem = asyncio.Semaphore(3)
    async def _gen(i, s):
        txt = clean_text(s.get("narration", "")) or " ".join(s.get("keywords", ["مفهوم"]))
        async with sem:
            try:
                aud, _ = await generate_voice(txt, dialect)
                dur = await get_audio_duration(aud)
                return {"index": i, "audio": aud, "duration": dur, "ok": True}
            except:
                return {"index": i, "audio": None, "duration": 30, "ok": False}
    raw = await asyncio.gather(*[_gen(i, s) for i, s in enumerate(sections)])
    results = sorted(raw, key=lambda x: x["index"])
    return {"results": results, "used_fallback": True, "all_failed": all(not r["ok"] for r in results)}
