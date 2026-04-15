#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت المحاضرات الذكي - وضع Polling (الأسهل والأضمن)
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
#  التحقق من التوكن
# ══════════════════════════════════════════════════════════════════════════════
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    logger.error("❌ TELEGRAM_BOT_TOKEN غير موجود في متغيرات البيئة")
    logger.error("   تأكد من إضافته في Heroku: Settings -> Config Vars")
    sys.exit(1)

logger.info(f"✅ تم العثور على التوكن: {TOKEN[:10]}...")

# ══════════════════════════════════════════════════════════════════════════════
#  استيراد المكتبات
# ══════════════════════════════════════════════════════════════════════════════
try:
    from telegram.ext import Application
    from bot import setup_handlers
    logger.info("✅ تم استيراد المكتبات بنجاح")
except ImportError as e:
    logger.error(f"❌ خطأ في استيراد المكتبات: {e}")
    logger.error("   تأكد من تثبيت: pip install -r requirements.txt")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
async def main():
    """تشغيل البوت في وضع Polling."""

    print("=" * 50)
    print("🎓 بوت المحاضرات الذكي - Polling Mode")
    print("=" * 50)

    # إنشاء تطبيق البوت
    logger.info("🔄 جاري إنشاء البوت...")
    app = Application.builder().token(TOKEN).build()
    logger.info("✅ تم إنشاء تطبيق البوت")

    # إضافة المعالجات
    setup_handlers(app)
    logger.info("✅ تم إعداد جميع المعالجات")

    # بدء البوت
    await app.initialize()
    await app.start()
    logger.info("✅ تم بدء البوت")

    # حذف أي Webhook قديم (للتأكد من عدم وجود تعارض)
    logger.info("🔄 جاري حذف أي Webhook قديم...")
    await app.bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ تم حذف Webhook")

    # بدء Polling
    logger.info("🔄 جاري بدء Polling...")
    await app.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )
    logger.info("✅ Polling يعمل الآن")

    print("=" * 50)
    print("✅✅✅ البوت جاهز لاستقبال الرسائل! ✅✅✅")
    print("=" * 50)

    # انتظار إلى الأبد
    await asyncio.Event().wait()


# ══════════════════════════════════════════════════════════════════════════════
#  نقطة البداية
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}", exc_info=True)
        sys.exit(1)
