import asyncio
import os
import sys

# ══════════════════════════════════════════════════════════════════════════════
# تصحيح PIL.Image.ANTIALIAS
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

    from web_server import start_web_server
    web_task = asyncio.create_task(start_web_server())
    
    from bot import main as bot_main

    restart_delay = 5
    consecutive_crashes = 0

    print("=" * 60)
    print("🤖 Zakros Lecture Bot Starting...")
    print("=" * 60)

    while True:
        try:
            print(f"\n🚀 Starting bot (attempt #{consecutive_crashes + 1})...")
            await bot_main()
            consecutive_crashes = 0
            print("[main] Bot stopped normally — restarting in 3s...")
            await asyncio.sleep(3)

        except asyncio.CancelledError:
            print("\n[main] Bot cancelled — shutting down...")
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
            delay = min(restart_delay * consecutive_crashes, 60)
            print(f"\n❌ [main] Bot crashed: {exc}", file=sys.stderr)
            print(f"⏳ Restarting in {delay}s...", file=sys.stderr)
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
