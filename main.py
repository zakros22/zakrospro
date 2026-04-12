# -*- coding: utf-8 -*-
import asyncio
import os
import sys

try:
    import PIL.Image as _pil
    if not hasattr(_pil, "ANTIALIAS"):
        _pil.ANTIALIAS = _pil.LANCZOS
except:
    pass


async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return

    from web_server import start_web_server
    asyncio.create_task(start_web_server())

    from bot import main as bot_main

    while True:
        try:
            print("[main] Starting bot...")
            await bot_main()
            print("[main] Restarting...")
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[main] Crashed: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
