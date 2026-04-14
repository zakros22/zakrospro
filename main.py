#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import sys
import signal
import logging

# ══════════════════════════════════════════════════════════════════════════════
#  تصحيح PIL.Image.ANTIALIAS (متوافق مع Pillow 10+)
# ══════════════════════════════════════════════════════════════════════════════
try:
    import PIL.Image as _pil
    if not hasattr(_pil, "ANTIALIAS"):
        _pil.ANTIALIAS = _pil.LANCZOS
    
    # Patch __getattr__ للتوافق مع المكتبات القديمة
    _orig_ga = _pil.__dict__.get("__getattr__")
    def _pil_ga(name):
        if name == "ANTIALIAS":
            return _pil.LANCZOS
        if _orig_ga:
            return _orig_ga(name)
        raise AttributeError(f"module 'PIL.Image' has no attribute {name!r}")
    _pil.__getattr__ = _pil_ga
    print("[✓] PIL.Image.ANTIALIAS patch applied")
except Exception as e:
    print(f"[!] PIL patch failed: {e}", file=sys.stderr)

# ══════════════════════════════════════════════════════════════════════════════
#  إعداد التسجيل (Logging)
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  متغيرات عامة للتحكم في الإيقاف النظيف
# ══════════════════════════════════════════════════════════════════════════════
_shutdown_event = asyncio.Event()
_web_server_task = None
_bot_task = None


def handle_signal(signum, frame):
    """معالج إشارات النظام (SIGTERM, SIGINT) للإيقاف النظيف."""
    sig_name = signal.Signals(signum).name
    logger.info(f"⚠️ استلام إشارة {sig_name} - جاري الإيقاف النظيف...")
    _shutdown_event.set()


async def run_web_server_only():
    """تشغيل خادم الويب فقط (عند عدم وجود توكن البوت)."""
    from web_server import start_web_server
    logger.info("🌐 تشغيل خادم الويب فقط (لا يوجد توكن بوت)...")
    await start_web_server()
    
    # انتظار إشارة الإيقاف
    await _shutdown_event.wait()
    logger.info("👋 إيقاف خادم الويب...")


async def run_bot_with_web_server():
    """تشغيل البوت مع خادم الويب (Webhook أو Polling)."""
    from web_server import start_web_server, set_bot_app
    from bot import run_bot
    
    # بدء خادم الويب في الخلفية
    web_task = asyncio.create_task(start_web_server())
    logger.info("🌐 خادم الويب يعمل في الخلفية...")
    
    # إعطاء الخادم فرصة للبدء
    await asyncio.sleep(1)
    
    # تشغيل البوت (يمرر shutdown_event للإيقاف النظيف)
    bot_task = asyncio.create_task(run_bot(_shutdown_event, set_bot_app))
    
    # انتظار إشارة الإيقاف أو انتهاء البوت
    done, pending = await asyncio.wait(
        [asyncio.create_task(_shutdown_event.wait()), bot_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    
    # إلغاء المهام المتبقية
    logger.info("🛑 جاري إيقاف جميع المهام...")
    
    if not bot_task.done():
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
    
    if not web_task.done():
        web_task.cancel()
        try:
            await web_task
        except asyncio.CancelledError:
            pass
    
    # إلغاء أي مهام متبقية
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    
    logger.info("✅ تم إيقاف جميع المهام بنجاح")


async def main():
    """الدالة الرئيسية - نقطة دخول البرنامج."""
    # تسجيل معالجات الإشارات
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    # التحقق من وجود توكن البوت
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    print("=" * 60)
    print("🎓 بوت المحاضرات الذكي - Lecture Video Bot")
    print("=" * 60)
    
    if not token:
        logger.warning("⚠️ TELEGRAM_BOT_TOKEN غير مضبوط - تشغيل خادم الويب فقط")
        await run_web_server_only()
    else:
        logger.info("🤖 جاري تشغيل البوت مع خادم الويب...")
        
        # محاولة تشغيل البوت مع إعادة المحاولة عند الأعطال
        max_restarts = 5
        restart_count = 0
        restart_delay = 5
        
        while restart_count < max_restarts and not _shutdown_event.is_set():
            try:
                await run_bot_with_web_server()
                
                # إذا وصلنا هنا بدون خطأ، نخرج من الحلقة
                break
                
            except asyncio.CancelledError:
                logger.info("🛑 تم إلغاء المهمة الرئيسية")
                break
                
            except Exception as e:
                restart_count += 1
                logger.error(f"❌ خطأ في البوت (محاولة {restart_count}/{max_restarts}): {e}")
                
                if restart_count < max_restarts and not _shutdown_event.is_set():
                    delay = min(restart_delay * restart_count, 60)
                    logger.info(f"⏳ إعادة التشغيل خلال {delay} ثانية...")
                    
                    try:
                        await asyncio.wait_for(_shutdown_event.wait(), timeout=delay)
                        break  # تم استلام إشارة إيقاف
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
