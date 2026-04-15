#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت المحاضرات الذكي - Webhook Mode
"""

import asyncio
import os
import sys
import logging
from aiohttp import web

# ══════════════════════════════════════════════════════════════════════════════
#  إعداد التسجيل
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  المتغيرات
# ══════════════════════════════════════════════════════════════════════════════
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", 5000))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")

if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN غير موجود")
    sys.exit(1)

if not WEBHOOK_URL:
    logger.error("❌ WEBHOOK_URL غير موجود")
    sys.exit(1)

logger.info(f"✅ TOKEN: {TOKEN[:10]}...")
logger.info(f"✅ WEBHOOK_URL: {WEBHOOK_URL}")
logger.info(f"✅ PORT: {PORT}")

# ══════════════════════════════════════════════════════════════════════════════
#  استيراد البوت
# ══════════════════════════════════════════════════════════════════════════════
from telegram import Update
from telegram.ext import Application
from bot import setup_handlers

# المتغير العام للبوت
bot_app = None


# ══════════════════════════════════════════════════════════════════════════════
#  معالجات HTTP
# ══════════════════════════════════════════════════════════════════════════════
async def handle_index(request):
    """الصفحة الرئيسية."""
    return web.Response(text="✅ البوت يعمل", content_type="text/html")


async def handle_health(request):
    """فحص الصحة."""
    return web.json_response({"status": "ok"})


async def handle_webhook(request):
    """استقبال تحديثات تيليجرام - هذا هو المهم."""
    global bot_app
    
    if bot_app is None:
        logger.warning("⚠️ البوت غير جاهز")
        return web.Response(status=503, text="Bot not ready")
    
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        logger.debug("✅ تم معالجة تحديث")
    except Exception as e:
        logger.error(f"❌ خطأ في المعالجة: {e}")
    
    return web.Response(status=200)


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    global bot_app
    
    print("=" * 50)
    print("🎓 بوت المحاضرات الذكي - Webhook")
    print("=" * 50)
    
    # 1. إنشاء البوت
    bot_app = Application.builder().token(TOKEN).build()
    setup_handlers(bot_app)
    
    await bot_app.initialize()
    await bot_app.start()
    logger.info("✅ تم بدء البوت")
    
    # 2. حذف Webhook قديم
    await bot_app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ تم حذف Webhook القديم")
    
    # 3. تعيين Webhook جديد
    webhook_path = f"{WEBHOOK_URL}/telegram"
    await bot_app.bot.set_webhook(url=webhook_path, drop_pending_updates=True)
    logger.info(f"✅ Webhook تم تعيينه: {webhook_path}")
    
    # 4. بدء خادم HTTP (هذا هو المهم لاستقبال الطلبات)
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/telegram", handle_webhook)  # هذا المسار يستقبل Webhook
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logger.info(f"🌐 خادم يعمل على المنفذ {PORT}")
    logger.info(f"   - المسار: {WEBHOOK_URL}/telegram")
    logger.info("✅✅✅ البوت جاهز لاستقبال الرسائل! ✅✅✅")
    
    # 5. انتظار
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم الإيقاف")
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        sys.exit(1)
