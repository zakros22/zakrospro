# web_server.py
# -*- coding: utf-8 -*-
"""
خادم ويب بسيط لدعم Webhook على Heroku أو أي بيئة سحابية.
يستقبل طلبات تيليجرام ويمررها إلى البوت.
"""

import logging
from aiohttp import web

logger = logging.getLogger(__name__)

# سيتم تعيين تطبيق البوت من الخارج
telegram_app = None

async def health_check(request):
    """مسار /health للتحقق من حالة الخدمة"""
    return web.Response(text="✅ Bot is running")

async def index(request):
    """الصفحة الرئيسية"""
    return web.Response(text="Medical Lecture Bot - Telegram Bot Service")

async def webhook_handler(request):
    """مسار /webhook/{token} لاستقبال تحديثات تيليجرام"""
    global telegram_app
    if not telegram_app:
        return web.Response(status=503, text="Bot not initialized")

    token = request.match_info.get('token')
    if token != telegram_app.bot.token:
        return web.Response(status=403, text="Invalid token")

    try:
        data = await request.json()
        # معالجة التحديث بشكل غير متزامن
        await telegram_app.update_queue.put(data)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500, text="Internal error")

def create_app(bot_app=None):
    """إنشاء تطبيق aiohttp"""
    global telegram_app
    telegram_app = bot_app

    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/health', health_check)
    # مسار webhook ديناميكي يحمل التوكن
    app.router.add_post('/webhook/{token}', webhook_handler)

    return app

async def run_web_server(host='0.0.0.0', port=5000, bot_app=None):
    """تشغيل خادم الويب"""
    app = create_app(bot_app)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"🌐 Web server started at http://{host}:{port}")
    return runner
