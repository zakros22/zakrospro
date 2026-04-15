import asyncio
import os
import sys
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN غير موجود")
    sys.exit(1)

try:
    from telegram.ext import Application
    from bot import setup_handlers
except ImportError as e:
    logger.error(f"❌ خطأ في استيراد المكتبات: {e}")
    sys.exit(1)

async def main():
    print("=" * 50)
    print("🎓 بوت المحاضرات الذكي - Polling Mode")
    print("=" * 50)

    app = Application.builder().token(TOKEN).build()
    setup_handlers(app)

    await app.initialize()
    await app.start()
    logger.info("✅ تم بدء البوت")

    await app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ تم حذف Webhook القديم")

    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("✅ Polling يعمل الآن")
    print("✅✅✅ البوت جاهز لاستقبال الرسائل! ✅✅✅")

    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم إيقاف البوت")
    except Exception as e:
        logger.error(f"❌ خطأ: {e}")
        sys.exit(1)
