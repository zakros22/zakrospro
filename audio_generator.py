import asyncio
from typing import Dict
import os
import random
from config import KeyManager

class AudioGenerator:
    def __init__(self):
        self.key_manager = KeyManager()
        self.temp_dir = "temp_audio"
        os.makedirs(self.temp_dir, exist_ok=True)
    
    async def generate_audio(self, text: str, section_title: str) -> str:
        """تحويل النص إلى ملف صوتي"""
        
        tts_service = self.key_manager.get_tts_key()
        
        if tts_service['service'] == 'elevenlabs':
            return await self.use_elevenlabs(text, tts_service['key'])
        elif tts_service['service'] == 'edge-tts':
            return await self.use_edge_tts(text)
        elif tts_service['service'] == 'gtts':
            return await self.use_gtts(text)
        else:
            return await self.use_pyttsx3(text)
    
    async def use_elevenlabs(self, text: str, api_key: str) -> str:
        """استخدام ElevenLabs API"""
        try:
            import aiohttp
            
            url = "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM"
            headers = {
                "xi-api-key": api_key,
                "Content-Type": "application/json"
            }
            data = {
                "text": text,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.5
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        filepath = f"{self.temp_dir}/audio_{random.randint(1000, 9999)}.mp3"
                        with open(filepath, 'wb') as f:
                            f.write(audio_data)
                        return filepath
        except Exception as e:
            print(f"ElevenLabs error: {e}")
        
        # استخدام بديل مجاني عند الفشل
        return await self.use_edge_tts(text)
    
    async def use_edge_tts(self, text: str) -> str:
        """استخدام Edge TTS المجاني"""
        try:
            import edge_tts
            
            voice = "ar-SA-HamedNeural"  # صوت عربي
            filepath = f"{self.temp_dir}/audio_{random.randint(1000, 9999)}.mp3"
            
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(filepath)
            
            return filepath
        except Exception as e:
            print(f"Edge TTS error: {e}")
            return await self.use_gtts(text)
    
    async def use_gtts(self, text: str) -> str:
        """استخدام Google TTS المجاني"""
        from gtts import gTTS
        
        filepath = f"{self.temp_dir}/audio_{random.randint(1000, 9999)}.mp3"
        
        # تشغيل في thread منفصل لأن gTTS غير متزامن
        def generate():
            tts = gTTS(text=text, lang='ar', slow=False)
            tts.save(filepath)
        
        await asyncio.to_thread(generate)
        return filepath
    
    async def use_pyttsx3(self, text: str) -> str:
        """استخدام pyttsx3 المحلي"""
        import pyttsx3
        
        filepath = f"{self.temp_dir}/audio_{random.randint(1000, 9999)}.wav"
        
        def generate():
            engine = pyttsx3.init()
            engine.setProperty('rate', 150)
            engine.setProperty('volume', 0.9)
            engine.save_to_file(text, filepath)
            engine.runAndWait()
        
        await asyncio.to_thread(generate)
        return filepath
    
    async def generate_all_audio(self, analyzed_content: Dict) -> Dict[str, str]:
        """توليد الصوت لجميع الأقسام"""
        audio_files = {}
        
        # صوت المقدمة
        intro_text = f"محاضرة: {analyzed_content['title']}. {analyzed_content['summary']}"
        audio_files['intro'] = await self.generate_audio(intro_text, "مقدمة")
        
        # صوت كل قسم
        for i, section in enumerate(analyzed_content['sections']):
            audio_text = f"{section['title']}. {section['explanation']}"
            audio_files[f'section_{i}'] = await self.generate_audio(audio_text, section['title'])
        
        # صوت الملخص
        audio_files['summary'] = await self.generate_audio(analyzed_content['summary'], "ملخص")
        
        return audio_files
