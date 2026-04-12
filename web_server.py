# -*- coding: utf-8 -*-
import os
import asyncio
from aiohttp import web

_bot_application = None

def set_bot_app(app):
    global _bot_application
    _bot_application = app

PORT = int(os.environ.get("PORT", 5000))

HOME_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>بوت المحاضرات</title></head>
<body style="font-family:sans-serif;text-align:center;padding:50px;">
<h1>🎓 بوت المحاضرات الذكي</h1><p>البوت يعمل الآن</p>
</body></html>"""

async def handle_index(request):
    return web.Response(text=HOME_HTML, content_type="text/html")

async def handle_health(request):
    mode = "webhook" if _bot_application else "polling"
    return web.json_response({"status": "ok", "mode": mode})

async def handle_telegram_webhook(request):
    if _bot_application is None:
        return web.Response(status=503)
    try:
        from telegram import Update
        data = await request.json()
        update = Update.de_json(data, _bot_application.bot)
        await _bot_application.process_update(update)
    except Exception as e:
        print(f"Webhook error: {e}")
    return web.Response(status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/telegram", handle_telegram_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web server on port {PORT}")
