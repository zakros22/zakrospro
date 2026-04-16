import os
import random
from typing import List, Optional
from datetime import datetime, timedelta
import json

class KeyManager:
    def __init__(self):
        # مفاتيح تحليل النص (9 مفاتيح أساسية + بدائل مجانية)
        self.analysis_keys = {
            'primary': [
                os.getenv('OPENAI_KEY_1', ''),
                os.getenv('OPENAI_KEY_2', ''),
                os.getenv('OPENAI_KEY_3', ''),
                os.getenv('OPENAI_KEY_4', ''),
                os.getenv('OPENAI_KEY_5', ''),
                os.getenv('OPENAI_KEY_6', ''),
                os.getenv('OPENAI_KEY_7', ''),
                os.getenv('OPENAI_KEY_8', ''),
                os.getenv('OPENAI_KEY_9', ''),
            ],
            'free_alternatives': [
                'claude-3-haiku',  # Anthropic مجاني محدود
                'gemini-pro',       # Google مجاني محدود
                'llama-2-70b',      # Meta (عبر Replicate)
                'mixtral-8x7b',     # Mistral AI مجاني
            ]
        }
        
        # مفاتيح تحويل النص إلى صوت
        self.tts_keys = {
            'elevenlabs': [
                os.getenv('ELEVENLABS_KEY_1', ''),
                os.getenv('ELEVENLABS_KEY_2', ''),
            ],
            'free_alternatives': [
                'edge-tts',      # Microsoft Edge TTS مجاني
                'gtts',          # Google TTS مجاني
                'pyttsx3',       # TTS محلي مجاني
                'coqui-ai',      # Coqui TTS مفتوح المصدر
            ]
        }
        
        self.current_key_index = 0
        self.key_usage = {}
        self.usage_file = 'key_usage.json'
        self.load_usage()
    
    def load_usage(self):
        try:
            with open(self.usage_file, 'r') as f:
                self.key_usage = json.load(f)
        except:
            self.key_usage = {}
    
    def save_usage(self):
        with open(self.usage_file, 'w') as f:
            json.dump(self.key_usage, f)
    
    def get_analysis_key(self) -> str:
        """الحصول على مفتاح تحليل متاح مع التدوير"""
        # محاولة المفاتيح الأساسية
        for i in range(len(self.analysis_keys['primary'])):
            idx = (self.current_key_index + i) % len(self.analysis_keys['primary'])
            key = self.analysis_keys['primary'][idx]
            if key and self.check_key_quota(key):
                self.current_key_index = (idx + 1) % len(self.analysis_keys['primary'])
                return key
        
        # استخدام البدائل المجانية
        return self.get_free_alternative('analysis')
    
    def get_tts_key(self) -> dict:
        """الحصول على خدمة TTS متاحة"""
        # محاولة ElevenLabs أولاً
        for key in self.tts_keys['elevenlabs']:
            if key and self.check_tts_quota(key):
                return {'service': 'elevenlabs', 'key': key}
        
        # استخدام البدائل المجانية
        return {'service': random.choice(self.tts_keys['free_alternatives']), 'key': None}
    
    def check_key_quota(self, key: str) -> bool:
        """فحص حصة المفتاح المتبقية"""
        today = datetime.now().strftime('%Y-%m-%d')
        usage = self.key_usage.get(key, {}).get(today, 0)
        return usage < 50000  # حد الرموز اليومي
    
    def check_tts_quota(self, key: str) -> bool:
        """فحص حصة TTS"""
        today = datetime.now().strftime('%Y-%m-%d')
        usage = self.key_usage.get(f"tts_{key}", {}).get(today, 0)
        return usage < 10000  # حد الأحرف الشهري
    
    def increment_usage(self, key: str, tokens: int):
        """زيادة عداد الاستخدام"""
        today = datetime.now().strftime('%Y-%m-%d')
        if key not in self.key_usage:
            self.key_usage[key] = {}
        self.key_usage[key][today] = self.key_usage[key].get(today, 0) + tokens
        self.save_usage()
    
    def get_free_alternative(self, type_: str) -> str:
        """الحصول على بديل مجاني"""
        if type_ == 'analysis':
            return random.choice(self.analysis_keys['free_alternatives'])
        return random.choice(self.tts_keys['free_alternatives'])
