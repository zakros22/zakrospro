#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نقطة الدخول الرئيسية للبوت
"""

import asyncio
import os
import sys
import signal
import logging
from datetime import datetime

# إصلاح PIL
try:
    import PIL.Image as _pil
    if not hasattr(_pil, "ANTIALIAS"):
        _pil.ANTIALIAS = _pil.LANCZOS
except:
    pass

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

_shutdown_event = asyncio.Event()
_start_time = datetime.now()


def handle_signal(signum, frame):
    sig_name = signal.Signals(signum).name
    logger.info(f"⚠️ استلام إشارة {sig_name} - جاري الإيقاف...")
    _shutdown_event.set()


async def run_web_server_only():
    from web_server import start_web_server
    logger.info("🌐 تشغيل خادم الويب فقط...")
    await start_web_server()
    await _shutdown_event.wait()


async def run_bot_with_web_server():
    from web_server import start_web_server, set_bot_app
    from bot import run_bot
    
    web_task = asyncio.create_task(start_web_server())
    logger.info("🌐 خادم الويب يعمل في الخلفية...")
    await asyncio.sleep(1)
    
    try:
        await run_bot(_shutdown_event, set_bot_app)
    except Exception as e:
        logger.error(f"❌ خطأ في البوت: {e}")
    
    web_task.cancel()
    try:
        await web_task
    except asyncio.CancelledError:
        pass


async def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    print("=" * 60)
    print("🎓 بوت المحاضرات الذكي - Lecture Video Bot")
    print(f"⏰ بدء التشغيل: {_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN غير مضبوط - تشغيل خادم الويب فقط")
        await run_web_server_only()
    else:
        logger.info("🤖 جاري تشغيل البوت مع خادم الويب...")
        
        restart_count = 0
        max_restarts = 10
        
        while restart_count < max_restarts and not _shutdown_event.is_set():
            try:
                await run_bot_with_web_server()
                break
            except asyncio.CancelledError:
                logger.info("🛑 تم إلغاء المهمة الرئيسية")
                break
            except Exception as e:
                restart_count += 1
                logger.error(f"❌ خطأ (محاولة {restart_count}/{max_restarts}): {e}")
                
                if restart_count < max_restarts and not _shutdown_event.is_set():
                    delay = min(5 * restart_count, 60)
                    logger.info(f"⏳ إعادة التشغيل خلال {delay} ثانية...")
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=delay)
                        break
                    except asyncio.TimeoutError:
                        continue
                else:
                    logger.critical("💥 تجاوز الحد الأقصى لإعادة التشغيل")
    
    logger.info("👋 تم إيقاف البرنامج")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم الإيقاف بواسطة المستخدم")
    except Exception as e:
        logger.critical(f"💥 خطأ غير متوقع: {e}", exc_info=True)
        sys.exit(1)
