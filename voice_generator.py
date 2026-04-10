import asyncio
import io
from gtts import gTTS

GTTS_LANG_MAP = {
    "iraq": "ar", "egypt": "ar", "syria": "ar", "gulf": "ar", "msa": "ar",
}

async def generate_voice(text: str, dialect: str = "msa") -> tuple[bytes, bool]:
    lang = GTTS_LANG_MAP.get(dialect, "ar")
    
    def _synth():
        buf = io.BytesIO()
        tts = gTTS(text=text, lang=lang, slow=False)
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()

    loop = asyncio.get_event_loop()
    audio_bytes = await loop.run_in_executor(None, _synth)
    return audio_bytes, False


async def get_audio_duration(audio_bytes: bytes) -> float:
    try:
        from pydub import AudioSegment
        audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
        return len(audio) / 1000.0
    except:
        return len(audio_bytes) / 16000


async def generate_sections_audio(sections: list, dialect: str) -> dict:
    _sem = asyncio.Semaphore(3)

    async def _gen_one(i: int, section: dict) -> dict:
        text = section.get("narration", "")
        if not text:
            text = " ".join(section.get("keywords", ["مفهوم"]))
        
        async with _sem:
            try:
                audio_bytes, _ = await generate_voice(text, dialect)
                duration = await get_audio_duration(audio_bytes)
                return {"index": i, "audio": audio_bytes, "duration": duration, "ok": True}
            except Exception as e:
                print(f"TTS failed: {e}")
                return {"index": i, "audio": None, "duration": 30, "ok": False}

    raw = await asyncio.gather(*[_gen_one(i, s) for i, s in enumerate(sections)])
    results = sorted(raw, key=lambda r: r["index"])
    
    return {"results": results, "used_fallback": True, "all_failed": False}
