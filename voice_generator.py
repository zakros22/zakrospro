# -*- coding: utf-8 -*-
import asyncio, io, re
from gtts import gTTS

def clean_text(t):
    if not t: return ""
    t = str(t).replace('\x00','').replace('\0','')
    return re.sub(r'\s+', ' ', t).strip()

GTTS_LANG = {"iraq":"ar","egypt":"ar","syria":"ar","gulf":"ar","msa":"ar","english":"en","british":"en"}

async def generate_voice(text, dialect="msa"):
    text = clean_text(text) or "محاضرة"
    lang = GTTS_LANG.get(dialect, "ar")
    def _synth():
        buf = io.BytesIO()
        gTTS(text=text, lang=lang, slow=False).write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    return await asyncio.get_event_loop().run_in_executor(None, _synth), False

async def get_audio_duration(audio):
    try:
        from pydub import AudioSegment
        return len(AudioSegment.from_mp3(io.BytesIO(audio))) / 1000.0
    except:
        return max(5.0, len(audio) / 16000)

async def generate_sections_audio(sections, dialect):
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
    results = sorted(await asyncio.gather(*[_gen(i,s) for i,s in enumerate(sections)]), key=lambda x: x["index"])
    return {"results": results, "used_fallback": True, "all_failed": all(not r["ok"] for r in results)}
