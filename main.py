import asyncio
import os
import sys

# ══════════════════════════════════════════════════════════════════════════════
# تصحيح PIL.Image.ANTIALIAS (للتأكد من التوافق)
# ══════════════════════════════════════════════════════════════════════════════
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
    """الدالة الرئيسية لتشغيل البوت"""
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        print("⚠️ Running web server only...", file=sys.stderr)
        from web_server import start_web_server
        await start_web_server()
        await asyncio.Event().wait()
        return

    # تشغيل خادم الويب في الخلفية
    from web_server import start_web_server
    web_task = asyncio.create_task(start_web_server())
    
    # استيراد الدالة الرئيسية للبوت
    from bot import main as bot_main

    # إعدادات إعادة التشغيل التلقائي
    restart_delay = 5
    consecutive_crashes = 0
    max_crashes_before_long_wait = 5

    print("=" * 60)
    print("🤖 Zakros Lecture Bot Starting...")
    print("=" * 60)
    print(f"📁 Temp directory: /tmp/telegram_bot")
    print(f"🌐 Web server port: {os.getenv('PORT', 5000)}")
    print("=" * 60)

    while True:
        try:
            print(f"\n🚀 Starting bot (attempt #{consecutive_crashes + 1})...")
            await bot_main()
            
            # إذا وصلنا إلى هنا، البوت توقف بشكل طبيعي
            consecutive_crashes = 0
            print("[main] Bot stopped normally — restarting in 3s...")
            await asyncio.sleep(3)

        except asyncio.CancelledError:
            print("\n[main] Bot cancelled — shutting down gracefully...")
            web_task.cancel()
            try:
                await web_task
            except:
                pass
            break

        except KeyboardInterrupt:
            print("\n[main] Keyboard interrupt — shutting down...")
            web_task.cancel()
            try:
                await web_task
            except:
                pass
            break

        except Exception as exc:
            consecutive_crashes += 1
            
            # حساب وقت الانتظار
            if consecutive_crashes >= max_crashes_before_long_wait:
                delay = 60  # انتظار دقيقة كاملة بعد 5 أعطال متتالية
            else:
                delay = min(restart_delay * consecutive_crashes, 30)
            
            print(
                f"\n❌ [main] Bot crashed (#{consecutive_crashes}): {exc.__class__.__name__}: {exc}",
                file=sys.stderr,
            )
            print(f"⏳ Restarting in {delay}s...", file=sys.stderr)
            
            # طباعة تفاصيل الخطأ للتتبع
            import traceback
            traceback.print_exc()
            
            await asyncio.sleep(delay)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutdown complete.")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        sys.exit(1)
