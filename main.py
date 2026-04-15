#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت المحاضرات الذكي - Webhook Mode (لـ Heroku)
"""

import asyncio
import os
import sys
import logging

# ══════════════════════════════════════════════════════════════════════════════
#  إعداد التسجيل
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  المتغيرات الأساسية
# ══════════════════════════════════════════════════════════════════════════════
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", 5000))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")

if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN غير موجود")
    sys.exit(1)

if not WEBHOOK_URL:
    logger.error("❌ WEBHOOK_URL غير موجود")
    logger.error("   أضفه في Heroku: heroku config:set WEBHOOK_URL=https://zakrosclock.herokuapp.com")
    sys.exit(1)

logger.info(f"✅ TOKEN: {TOKEN[:10]}...")
logger.info(f"✅ WEBHOOK_URL: {WEBHOOK_URL}")
logger.info(f"✅ PORT: {PORT}")

# ══════════════════════════════════════════════════════════════════════════════
#  استيراد المكتبات
# ══════════════════════════════════════════════════════════════════════════════
try:
    from telegram import Update
    from telegram.ext import Application
    from aiohttp import web
    from bot import setup_handlers
    logger.info("✅ تم استيراد جميع المكتبات")
except ImportError as e:
    logger.error(f"❌ خطأ في الاستيراد: {e}")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
#  المتغير العام للبوت
# ══════════════════════════════════════════════════════════════════════════════
bot_app = None


# ══════════════════════════════════════════════════════════════════════════════
#  معالجات HTTP
# ══════════════════════════════════════════════════════════════════════════════
async def handle_index(request):
    """الصفحة الرئيسية - للتأكد أن الخادم يعمل."""
    return web.Response(
        text="✅ بوت المحاضرات الذكي يعمل!",
        content_type="text/html"
    )


async def handle_health(request):
    """نقطة فحص الصحة - لـ Heroku."""
    return web.json_response({
        "status": "ok",
        "bot": "ready" if bot_app else "initializing",
        "webhook": WEBHOOK_URL
    })


async def handle_webhook(request):
    """استقبال تحديثات تيليجرام."""
    global bot_app
    
    if bot_app is None:
        logger.warning("⚠️ البوت غير جاهز بعد")
        return web.Response(status=503, text="Bot initializing")
    
    try:
        # قراءة البيانات من تيليجرام
        data = await request.json()
        
        # تحويلها إلى Update
        update = Update.de_json(data, bot_app.bot)
        
        # معالجتها
        await bot_app.process_update(update)
        
        logger.debug(f"✅ تم معالجة تحديث من {update.effective_user.id if update.effective_user else 'unknown'}")
        
    except Exception as e:
        logger.error(f"❌ خطأ في معالجة webhook: {e}")
    
    return web.Response(status=200)


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    global bot_app
    
    print("=" * 60)
    print("🎓 بوت المحاضرات الذكي - Lecture Video Bot")
    print("=" * 60)
    
    # ═════════════════════════════════════════════════════════════════════════
    # 1. إنشاء البوت
    # ═════════════════════════════════════════════════════════════════════════
    logger.info("🔄 جاري إنشاء البوت...")
    bot_app = Application.builder().token(TOKEN).build()
    
    # إضافة المعالجات
    setup_handlers(bot_app)
    logger.info("✅ تم إعداد المعالجات")
    
    # بدء البوت
    await bot_app.initialize()
    await bot_app.start()
    logger.info("✅ تم بدء البوت")
    
    # ═════════════════════════════════════════════════════════════════════════
    # 2. إعداد Webhook
    # ═════════════════════════════════════════════════════════════════════════
    webhook_path = f"{WEBHOOK_URL}/telegram"
    
    logger.info(f"🔄 جاري حذف webhook القديم...")
    await bot_app.bot.delete_webhook(drop_pending_updates=True)
    
    logger.info(f"🔄 جاري تعيين webhook على: {webhook_path}")
    result = await bot_app.bot.set_webhook(
        url=webhook_path,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )
    
    if result:
        logger.info(f"✅ Webhook تم تعيينه بنجاح")
    else:
        logger.error(f"❌ فشل تعيين Webhook")
    
    # ═════════════════════════════════════════════════════════════════════════
    # 3. بدء خادم HTTP
    # ═════════════════════════════════════════════════════════════════════════
    app_web = web.Application()
    app_web.router.add_get("/", handle_index)
    app_web.router.add_get("/health", handle_health)
    app_web.router.add_post("/telegram", handle_webhook)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    logger.info(f"🌐 خادم الويب يعمل على المنفذ {PORT}")
    logger.info(f"   - الصفحة الرئيسية: {WEBHOOK_URL}")
    logger.info(f"   - فحص الصحة: {WEBHOOK_URL}/health")
    logger.info(f"   - Webhook: {WEBHOOK_URL}/telegram")
    logger.info("")
    logger.info("✅✅✅ البوت جاهز لاستقبال الرسائل! ✅✅✅")
    
    # ═════════════════════════════════════════════════════════════════════════
    # 4. انتظار إلى الأبد
    # ═════════════════════════════════════════════════════════════════════════
    await asyncio.Event().wait()


# ══════════════════════════════════════════════════════════════════════════════
#  نقطة البداية
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم إيقاف البوت")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
        sys.exit(1)
