import asyncio
import os
import sys

# ============================================================
# تصحيح مشكلة PIL.Image.ANTIALIAS
# ============================================================
try:
    import PIL.Image as _pil
    if not hasattr(_pil, "ANTIALIAS"):
        _pil.ANTIALIAS = _pil.LANCZOS
    _orig_ga = _pil.__dict__.get("__getattr__")
    def _pil_ga(name):
        if name == "ANTIALIAS":
            return _pil.LANCZOS
        if _orig_ga:
            return _orig_ga(name)
        raise AttributeError(f"module 'PIL.Image' has no attribute {name!r}")
    _pil.__getattr__ = _pil_ga
    print("[compat] ✅ PIL.Image.ANTIALIAS patch applied")
except Exception as _e:
    print(f"[compat] ⚠️ PIL patch failed: {_e}", file=sys.stderr)


async def main():
    """
    الدالة الرئيسية - تشغل خادم الويب والبوت معاً.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not set!", file=sys.stderr)
        sys.exit(1)

    # بدء خادم الويب أولاً (مطلوب لـ Heroku)
    from web_server import start_web_server
    web_task = asyncio.create_task(start_web_server())
    
    # انتظار ثانيتين حتى يبدأ الخادم
    await asyncio.sleep(2)

    # استيراد البوت
    from bot import main as bot_main

    # نظام إعادة التشغيل التلقائي
    restart_delay = 5
    consecutive_crashes = 0

    while True:
        try:
            print(f"[main] 🚀 Starting bot (attempt #{consecutive_crashes + 1})...")
            await bot_main()
            consecutive_crashes = 0
            print("[main] ⚠️ bot_main returned — restarting in 3s...")
            await asyncio.sleep(3)

        except asyncio.CancelledError:
            print("[main] 🛑 Bot cancelled — shutting down.")
            web_task.cancel()
            break

        except Exception as exc:
            consecutive_crashes += 1
            delay = min(restart_delay * consecutive_crashes, 120)
            print(
                f"[main] ❌ Bot crashed (#{consecutive_crashes}): {exc}\n"
                f"       🔄 Restarting in {delay}s...",
                file=sys.stderr,
            )
            await asyncio.sleep(delay)


if __name__ == "__main__":
    print("=" * 60)
    print("🎓 ZAKROS PRO - Lecture Video Bot")
    print("=" * 60)
    asyncio.run(main())
if __name__ == "__main__":
    asyncio.run(main())
