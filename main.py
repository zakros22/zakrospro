import asyncio
import os
import sys

# Patch PIL
try:
    import PIL.Image as _pil
    if not hasattr(_pil, "ANTIALIAS"):
        _pil.ANTIALIAS = _pil.LANCZOS
except:
    pass

async def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN not set!")
        sys.exit(1)

    from web_server import start_web_server
    web_task = asyncio.create_task(start_web_server())
    await asyncio.sleep(2)

    from bot import run_bot
    await run_bot()

if __name__ == "__main__":
    asyncio.run(main())
