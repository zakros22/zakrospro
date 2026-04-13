# main.py
# -*- coding: utf-8 -*-
"""
نقطة بدء تشغيل البوت مع خادم الويب وإعادة التشغيل التلقائي
"""

import os
import sys
import asyncio
import logging
import signal
import time
from pathlib import Path

# إضافة المسار الرئيسي
sys.path.insert(0, str(Path(__file__).parent))

from config import config, logger
from database import init_db
from web_server import run_web_server

# استيراد bot بعد التأكد من التهيئة
import bot

shutdown_flag = False

def handle_shutdown(signum, frame):
    """معالجة إشارات الإيقاف"""
    global shutdown_flag
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_flag = True

async def run_bot_with_webhook():
    """تشغيل البوت في وضع Webhook (لـ Heroku)"""
    # تهيئة قاعدة البيانات
    try:
        init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        # نستمر حتى بدون قاعدة بيانات (بعض الوظائف ستفشل)

    # بناء تطبيق البوت
    if bot.application is None:
        # نعيد بناء التطبيق إذا لم يكن موجوداً
        from telegram.ext import Application
        builder = Application.builder().token(config.BOT_TOKEN)
        bot.application = builder.build()
        # إضافة المعالجات (نفس ما في bot.main)
        from bot import (
            start, help_command, balance_command, referral_command,
            subscribe_command, admin_command, cancel_command,
            handle_document, handle_text, handle_receipt_photo,
            button_callback, handle_payment_callback, admin_callback,
            handle_broadcast_message, error_handler
        )
        from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters

        app = bot.application
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("balance", balance_command))
        app.add_handler(CommandHandler("referral", referral_command))
        app.add_handler(CommandHandler("subscribe", subscribe_command))
        app.add_handler(CommandHandler("admin", admin_command))
        app.add_handler(CommandHandler("cancel", cancel_command))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        app.add_handler(MessageHandler(filters.PHOTO, handle_receipt_photo))
        app.add_handler(MessageHandler(
            filters.User(user_id=config.OWNER_ID) & (filters.TEXT | filters.PHOTO | filters.VIDEO),
            handle_broadcast_message
        ), group=1)
        app.add_handler(CallbackQueryHandler(button_callback, pattern="^(spec_|dialect_|level_|back_)"))
        app.add_handler(CallbackQueryHandler(handle_payment_callback, pattern="^pay_"))
        app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
        app.add_error_handler(error_handler)

    # تهيئة التطبيق
    await bot.application.initialize()
    await bot.application.start()

    # إعداد Webhook
    webhook_url = config.WEBHOOK_URL
    if webhook_url:
        webhook_path = f"/webhook/{config.BOT_TOKEN}"
        full_url = f"{webhook_url.rstrip('/')}{webhook_path}"
        await bot.application.bot.set_webhook(url=full_url)
        logger.info(f"🔗 Webhook set to {full_url}")

    # تشغيل خادم الويب
    runner = await run_web_server(host='0.0.0.0', port=config.PORT, bot_app=bot.application)

    # انتظار إشارة الإيقاف
    while not shutdown_flag:
        await asyncio.sleep(1)

    # تنظيف
    logger.info("Shutting down...")
    await bot.application.stop()
    await runner.cleanup()

async def run_bot_polling():
    """تشغيل البوت في وضع Polling (للتطوير المحلي)"""
    # تهيئة قاعدة البيانات
    try:
        init_db()
    except Exception as e:
        logger.error(f"Database init error: {e}")

    # بناء التطبيق وتشغيله مباشرة
    # نستدعي main من bot.py بعد تعديله ليكون async
    from bot import main as bot_main
    # بما أن bot.main() يحتوي على run_polling متزامن، نحتاج لتشغيله في thread
    import threading
    bot_thread = threading.Thread(target=bot_main)
    bot_thread.start()

    # انتظار الإيقاف
    while not shutdown_flag:
        await asyncio.sleep(1)

def main():
    """الدالة الرئيسية مع إعادة التشغيل التلقائي"""
    # تسجيل معالجات الإشارات
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    while not shutdown_flag:
        try:
            if config.WEBHOOK_URL:
                asyncio.run(run_bot_with_webhook())
            else:
                asyncio.run(run_bot_polling())
        except Exception as e:
            logger.error(f"Bot crashed: {e}", exc_info=True)
            if not shutdown_flag:
                logger.info("Restarting in 5 seconds...")
                time.sleep(5)
            else:
                break

if __name__ == "__main__":
    main()
