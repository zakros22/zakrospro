#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import asyncio
import signal
import traceback
from datetime import datetime

# ============================================================
# تصحيح PIL
# ============================================================
try:
    import PIL.Image as _pil
    if not hasattr(_pil, "ANTIALIAS"):
        _pil.ANTIALIAS = _pil.LANCZOS
    print("[compat] ✅ PIL.Image.ANTIALIAS patch applied")
except Exception as _e:
    print(f"[compat] ⚠️ PIL patch failed: {_e}", file=sys.stderr)

# ============================================================
# إعدادات
# ============================================================
PORT = int(os.environ.get("PORT", 5000))
_shutdown_event = asyncio.Event()

def signal_handler(signum, frame):
    print(f"\n🛑 Received signal {signum}, shutting down...")
    _shutdown_event.set()

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# ============================================================
# الدالة الرئيسية
# ============================================================
async def main():
    print("🎓 ZAKROS PRO Starting...")
    print(f"📡 Port: {PORT}")
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not set!", file=sys.stderr)
        sys.exit(1)
    
    print("✅ Token found")
    
    # بدء خادم الويب
    try:
        from web_server import start_web_server
        print("🌐 Starting web server...")
        web_task = asyncio.create_task(start_web_server())
        await asyncio.sleep(2)
        print("✅ Web server started")
    except Exception as e:
        print(f"❌ Web server failed: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    # بدء البوت
    try:
        from bot import main as bot_main
        print("🤖 Starting bot...")
        await bot_main()
    except Exception as e:
        print(f"❌ Bot failed: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Interrupted")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)
