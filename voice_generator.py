import asyncio
import io
import tempfile
import os
from gtts import gTTS
from pydub import AudioSegment

DIALECT_TLD = {
    "iraq": "com", "egypt": "com.eg", "syria": "com", "gulf": "com.sa",
    "msa": "com", "english": "com", "british": "co.uk"
}

async def generate_audio_for_section(text: str, dialect: str) -> dict:
    """توليد صوت لقسم واحد"""
    lang = "ar" if dialect not in ("english", "british") else "en"
    tld = DIALECT_TLD.get(dialect, "com")
    
    def _gen():
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
        
        tts = gTTS(text=text, lang=lang, tld=tld, slow=False)
        tts.save(path)
        
        with open(path, "rb") as f:
            data = f.read()
        
        audio = AudioSegment.from_file(io.BytesIO(data), format="mp3")
        duration = len(audio) / 1000.0
        
        os.unlink(path)
        return {"audio": data, "duration": duration}
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _gen)

async def generate_sections_audio(sections: list, dialect: str) -> dict:
    """توليد صوت لجميع الأقسام"""
    results = []
    for sec in sections:
        narration = sec.get("narration", sec.get("content", ""))
        r = await generate_audio_for_section(narration, dialect)
        results.append(r)
    return {"results": results}
