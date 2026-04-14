#!/bin/bash

echo "🚀 إعداد بوت المحاضرات..."

# إنشاء بيئة افتراضية
python3 -m venv venv
source venv/bin/activate

# تثبيت المكتبات
pip install --upgrade pip
pip install -r requirements.txt

# إنشاء المجلدات المطلوبة
mkdir -p /tmp/telegram_bot
mkdir -p fonts

# نسخ .env.example إذا لم يوجد .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  تم إنشاء .env - قم بتعبئة المفاتيح المطلوبة!"
fi

echo "✅ تم الإعداد! شغّل البوت بـ: python main.py"
