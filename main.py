#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت المحاضرات - نسخة Webhook فقط
"""

import asyncio
import os
import sys
import logging
from aiohttp import web

# إعداد التسجيل
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  تحميل المتغيرات
# ══════════════════════════════════════════════════════════════════════════════
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", 5000))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")

if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN غير موجود")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  استيراد البوت
# ══════════════════════════════════════════════════════════════════════════════
from telegram import Update
from telegram.ext import Application

# استيراد إعدادات البوت من ملف bot.py
from bot import setup_handlers

# ══════════════════════════════════════════════════════════════════════════════
#  المتغيرات العامة
# ══════════════════════════════════════════════════════════════════════════════
app = None
bot_app = None


# ══════════════════════════════════════════════════════════════════════════════
#  معالجات HTTP
# ══════════════════════════════════════════════════════════════════════════════
async def handle_index(request):
    return web.Response(text="✅ البوت يعمل", content_type="text/html")


async def handle_health(request):
    return web.json_response({"status": "ok"})


async def handle_webhook(request):
    """استقبال تحديثات تيليجرام"""
    global bot_app
    
    if bot_app is None:
        logger.warning("⚠️ البوت غير جاهز")
        return web.Response(status=503)
    
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
    
    return web.Response(status=200)


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    global bot_app
    
    print("=" * 50)
    print("🎓 بوت المحاضرات الذكي")
    print("=" * 50)
    
    # إنشاء تطبيق البوت
    bot_app = Application.builder().token(TOKEN).build()
    
    # إضافة المعالجات
    setup_handlers(bot_app)
    
    # بدء البوت
    await bot_app.initialize()
    await bot_app.start()
    
    # إعداد Webhook
    if WEBHOOK_URL:
        webhook_path = f"{WEBHOOK_URL}/telegram"
        
        # حذف webhook القديم
        await bot_app.bot.delete_webhook(drop_pending_updates=True)
        
        # تعيين webhook جديد
        await bot_app.bot.set_webhook(
            url=webhook_path,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "pre_checkout_query", "successful_payment"]
        )
        logger.info(f"✅ Webhook: {webhook_path}")
    else:
        logger.warning("⚠️ WEBHOOK_URL غير موجود، سيتم استخدام Polling")
        await bot_app.updater.start_polling(drop_pending_updates=True)
    
    # بدء خادم HTTP
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/telegram", handle_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logger.info(f"🌐 خادم يعمل على المنفذ {PORT}")
    
    # انتظار إلى الأبد
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم الإيقاف")
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        sys.exit(1)
