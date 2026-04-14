#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت المحاضرات الذكي - نقطة الدخول الرئيسية
يدعم: Webhook و Polling
"""

import asyncio
import os
import sys
import signal
import logging
from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
#  إصلاح مشكلة PIL.Image.ANTIALIAS
# ══════════════════════════════════════════════════════════════════════════════
try:
    import PIL.Image as _pil
    if not hasattr(_pil, "ANTIALIAS"):
        _pil.ANTIALIAS = _pil.LANCZOS
    # Patch __getattr__ للتوافق
    _orig_ga = _pil.__dict__.get("__getattr__")
    def _pil_ga(name):
        if name == "ANTIALIAS":
            return _pil.LANCZOS
        if _orig_ga:
            return _orig_ga(name)
        raise AttributeError(f"module 'PIL.Image' has no attribute {name!r}")
    _pil.__getattr__ = _pil_ga
except Exception:
    pass

# ══════════════════════════════════════════════════════════════════════════════
#  إعداد التسجيل
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  متغيرات عامة
# ══════════════════════════════════════════════════════════════════════════════
_shutdown_event = asyncio.Event()
_start_time = datetime.now()


def handle_signal(signum, frame):
    """معالج إشارات النظام للإيقاف النظيف."""
    sig_name = signal.Signals(signum).name
    logger.info(f"⚠️ استلام إشارة {sig_name} - جاري الإيقاف النظيف...")
    _shutdown_event.set()


async def run_web_server_only():
    """تشغيل خادم الويب فقط (عند عدم وجود توكن)."""
    from web_server import start_web_server
    logger.info("🌐 تشغيل خادم الويب فقط...")
    await start_web_server()
    await _shutdown_event.wait()


async def run_bot_with_web_server():
    """تشغيل البوت مع خادم الويب."""
    from web_server import start_web_server, set_bot_app
    from bot import run_bot
    
    # بدء خادم الويب
    web_task = asyncio.create_task(start_web_server())
    logger.info("🌐 خادم الويب يعمل في الخلفية...")
    await asyncio.sleep(1)
    
    # تشغيل البوت
    try:
        await run_bot(_shutdown_event, set_bot_app)
    except Exception as e:
        logger.error(f"❌ خطأ في البوت: {e}")
    
    # إيقاف خادم الويب
    web_task.cancel()
    try:
        await web_task
    except asyncio.CancelledError:
        pass


async def main():
    """الدالة الرئيسية."""
    # تسجيل معالجات الإشارات
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
        
        # نظام إعادة التشغيل التلقائي
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
                logger.error(f"❌ خطأ في البوت (محاولة {restart_count}/{max_restarts}): {e}")
                
                if restart_count < max_restarts and not _shutdown_event.is_set():
                    delay = min(5 * restart_count, 60)
                    logger.info(f"⏳ إعادة التشغيل خلال {delay} ثانية...")
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=delay)
                        break
                    except asyncio.TimeoutError:
                        continue
                else:
                    logger.critical("💥 تجاوز الحد الأقصى لإعادة التشغيل - توقف")
    
    logger.info("👋 تم إيقاف البرنامج")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم إيقاف البرنامج بواسطة المستخدم")
    except Exception as e:
        logger.critical(f"💥 خطأ غير متوقع: {e}", exc_info=True)
        sys.exit(1)
