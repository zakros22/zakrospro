#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import asyncio
from aiohttp import web

PORT = int(os.environ.get("PORT", 5000))
_bot_app = None

def set_bot_app(app):
    global _bot_app
    _bot_app = app

HOME_HTML = """<!DOCTYPE html><html><head><title>بوت المحاضرات</title></head>
<body style="font-family:sans-serif;text-align:center;padding:50px;background:#0f0c29;color:white">
<h1>🎓 بوت المحاضرات الذكي</h1><p>البوت يعمل ✅</p>
<a href="https://t.me/zakros_Quizebot" style="color:#a78bfa">@zakros_Quizebot</a>
</body></html>"""

async def handle_index(request):
    return web.Response(text=HOME_HTML, content_type="text/html")

async def handle_health(request):
    return web.json_response({"status": "ok"})

async def handle_webhook(request):
    if _bot_app is None:
        return web.Response(status=503)
    from telegram import Update
    data = await request.json()
    update = Update.de_json(data, _bot_app.bot)
    await _bot_app.process_update(update)
    return web.Response(status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/telegram", handle_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"🌐 Web server on port {PORT}")
