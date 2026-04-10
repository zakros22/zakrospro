import asyncio
import os
import sys

# ══════════════════════════════════════════════════════════════════════════════
#  Pillow 10+ removed Image.ANTIALIAS; patch at startup before any import.
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
    print("[compat] PIL.Image.ANTIALIAS patch applied")
except Exception as _e:
    print(f"[compat] PIL patch failed: {_e}", file=sys.stderr)


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set", file=sys.stderr)
        return

    # Start web server as background task
    from web_server import start_web_server
    asyncio.create_task(start_web_server())

    from bot import main as bot_main

    restart_delay = 5

    while True:
        try:
            print("[main] Starting bot...")
            await bot_main()
            print("[main] bot_main returned — restarting in 3s...")
            await asyncio.sleep(3)

        except asyncio.CancelledError:
            print("[main] Bot cancelled — shutting down.")
            break

        except Exception as exc:
            delay = min(restart_delay, 120)
            print(f"[main] Bot crashed: {exc}\nRestarting in {delay}s...", file=sys.stderr)
            await asyncio.sleep(delay)


if __name__ == "__main__":
    asyncio.run(main())
