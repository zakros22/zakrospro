#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import signal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_shutdown_event = asyncio.Event()

def handle_signal(signum, frame):
    logger.info("🛑 إيقاف...")
    _shutdown_event.set()

async def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    from bot import run_bot
    from web_server import start_web_server, set_bot_app
    
    web_task = asyncio.create_task(start_web_server())
    await asyncio.sleep(1)
    
    await run_bot(_shutdown_event, set_bot_app)
    
    web_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
