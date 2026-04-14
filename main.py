#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import asyncio
import os
import sys
import logging
from aiohttp import web

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.getenv("PORT", 5000))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")

if not TOKEN:
    logger.error("❌ لا يوجد TOKEN")
    sys.exit(1)

# استيراد البوت
from telegram import Update
from telegram.ext import Application
from bot import setup_handlers

bot_app = None

async def handle_webhook(request):
    global bot_app
    if bot_app is None:
        return web.Response(status=503)
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
    except Exception as e:
        logger.error(f"Error: {e}")
    return web.Response(status=200)

async def main():
    global bot_app
    
    # إنشاء البوت
    bot_app = Application.builder().token(TOKEN).build()
    setup_handlers(bot_app)
    
    await bot_app.initialize()
    await bot_app.start()
    
    # حذف webhook القديم
    await bot_app.bot.delete_webhook(drop_pending_updates=True)
    
    # تعيين webhook
    if WEBHOOK_URL:
        await bot_app.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram", drop_pending_updates=True)
        logger.info(f"✅ Webhook set to {WEBHOOK_URL}/telegram")
    
    # خادم HTTP
    app = web.Application()
    app.router.add_post("/telegram", handle_webhook)
    app.router.add_get("/", lambda r: web.Response(text="OK"))
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"🌐 Server on port {PORT}")
    
    # انتظار
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
