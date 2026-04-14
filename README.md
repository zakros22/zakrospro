# 🎓 بوت المحاضرات الذكي - Telegram Lecture Video Bot

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Deploy](https://img.shields.io/badge/Deploy-Heroku-430098.svg)](https://heroku.com)

بوت تيليجرام متكامل يحوّل أي محاضرة (نص، PDF) إلى فيديو تعليمي احترافي مع صوت بشري وصور توضيحية.

---

## ✨ المميزات

- 🎬 **تحويل PDF/نص إلى فيديو تعليمي كامل**
- 🎙️ **توليد صوت بشري بـ 7 لهجات** (عراقي، مصري، شامي، خليجي، فصحى، إنجليزي، بريطاني)
- 🖼️ **توليد صور تعليمية تلقائياً لكل قسم** (DALL-E / Pollinations)
- 🔄 **نظام تبادل مفاتيح ذكي** (DeepSeek → Gemini → OpenRouter → Groq)
- 🔊 **تناوب تلقائي بين مفاتيح ElevenLabs** مع احتياطي gTTS مجاني
- 👥 **نظام إحالة** لكسب محاولات مجانية
- 💳 **نظام دفع متكامل** (نجوم تيليجرام، ماستركارد، USDT/TON)
- 📊 **لوحة تحكم للمالك** مع إحصائيات وإدارة المستخدمين
- 🌐 **دعم كامل للغة العربية** (تشكيل، خطوط، RTL)
- 📄 **توليد PDF ملخص** للمحاضرة

---

## 🚀 النشر السريع على Heroku

[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/yourusername/lecture-video-bot)

### خطوات النشر اليدوي:

```bash
# 1. استنساخ المشروع
git clone https://github.com/yourusername/lecture-video-bot.git
cd lecture-video-bot

# 2. تثبيت Heroku CLI وتسجيل الدخول
heroku login

# 3. إنشاء تطبيق جديد
heroku create your-bot-name

# 4. إضافة قاعدة بيانات PostgreSQL
heroku addons:create heroku-postgresql:mini

# 5. رفع متغيرات البيئة (استبدل القيم بمفاتيحك)
heroku config:set TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
heroku config:set OWNER_ID=7021542402
heroku config:set DEEPSEEK_API_KEYS=sk-xxx1,sk-xxx2,sk-xxx3
heroku config:set GOOGLE_API_KEYS=AIzaSyxxx1,AIzaSyxxx2
heroku config:set ELEVENLABS_API_KEYS=key1,key2,key3
heroku config:set WEBHOOK_URL=https://your-bot-name.herokuapp.com

# 6. النشر
git push heroku main

# 7. تشغيل البوت
heroku ps:scale web=1
