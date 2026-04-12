#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZAKROS PRO - بوت المحاضرات الذكي
نقطة الدخول الرئيسية للتطبيق
تعمل على Heroku مع Webhook
"""

import asyncio
import os
import sys
import signal
import traceback
from datetime import datetime

# ============================================================
# تصحيح مشكلة PIL.Image.ANTIALIAS
# ============================================================
try:
    import PIL.Image as _pil
    if not hasattr(_pil, "ANTIALIAS"):
        _pil.ANTIALIAS = _pil.LANCZOS
    
    # تصحيح __getattr__ للتوافق مع المكتبات القديمة
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

# ============================================================
# استيراد المكتبات المطلوبة بعد التصحيح
# ============================================================
try:
    import aiohttp
    from aiohttp import web
except ImportError as e:
    print(f"❌ خطأ في استيراد المكتبات: {e}")
    print("يرجى التأكد من تثبيت جميع المتطلبات: pip install -r requirements.txt")
    sys.exit(1)


# ============================================================
# إعدادات التطبيق
# ============================================================
APP_NAME = "ZAKROS PRO"
VERSION = "2.0.0"
PORT = int(os.environ.get("PORT", 5000))

# راية البداية
BANNER = f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🎓 {APP_NAME} - Lecture Video Bot                          ║
║   📌 Version: {VERSION}                                         ║
║   🚀 Starting...                                             ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""


# ============================================================
# معالج الإشارات (لإيقاف التطبيق بشكل آمن)
# ============================================================
_shutdown_event = asyncio.Event()
_web_task = None
_bot_task = None


def signal_handler(signum, frame):
    """معالج إشارات النظام (SIGTERM, SIGINT)"""
    print(f"\n🛑 Received signal {signum}, shutting down gracefully...")
    _shutdown_event.set()


# تسجيل معالجات الإشارات
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# ============================================================
# خادم ويب بسيط (مطلوب لـ Heroku)
# ============================================================
async def handle_index(request):
    """الصفحة الرئيسية"""
    html = f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        <title>{APP_NAME} - بوت المحاضرات الذكي</title>
        <style>
            * {{ margin:0; padding:0; box-sizing:border-box; }}
            body {{
                font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
                background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
                min-height: 100vh;
                display: flex; align-items: center; justify-content: center;
                color: #fff;
            }}
            .container {{ text-align:center; padding:40px 20px; max-width:700px; }}
            .logo {{ font-size:80px; margin-bottom:20px; animation:pulse 2s infinite; }}
            @keyframes pulse {{ 0%,100%{{transform:scale(1)}} 50%{{transform:scale(1.08)}} }}
            h1 {{
                font-size:2.8rem; font-weight:800; margin-bottom:10px;
                background:linear-gradient(90deg,#a78bfa,#60a5fa,#34d399);
                -webkit-background-clip:text; -webkit-text-fill-color:transparent;
            }}
            .subtitle {{ font-size:1.2rem; color:#c4b5fd; margin-bottom:40px; }}
            .features {{
                display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
                gap:16px; margin-bottom:40px;
            }}
            .feature {{
                background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.12);
                border-radius:16px; padding:20px 14px; backdrop-filter:blur(10px);
                transition:transform .2s;
            }}
            .feature:hover{{transform:translateY(-4px)}}
            .feature .icon{{font-size:2.2rem;margin-bottom:8px}}
            .feature h3{{font-size:1rem;color:#e0e7ff;margin-bottom:4px}}
            .feature p{{font-size:.85rem;color:#94a3b8}}
            .btn {{
                display:inline-block;
                background:linear-gradient(135deg,#7c3aed,#4f46e5);
                color:#fff; text-decoration:none;
                padding:16px 50px; border-radius:50px;
                font-size:1.2rem; font-weight:700;
                box-shadow:0 8px 32px rgba(124,58,237,.4);
                transition:transform .2s,box-shadow .2s;
                margin-bottom:30px;
            }}
            .btn:hover{{transform:translateY(-2px);box-shadow:0 12px 40px rgba(124,58,237,.6)}}
            .status{{margin-top:24px;font-size:.9rem;color:#64748b}}
            .dot{{display:inline-block;width:10px;height:10px;background:#22c55e;
                 border-radius:50%;margin-left:6px;animation:blink 1.4s infinite}}
            @keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
            .footer {{margin-top:40px; color:#64748b; font-size:.8rem;}}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">🎓</div>
            <h1>{APP_NAME}</h1>
            <p class="subtitle">حوّل محاضرتك إلى فيديو تعليمي احترافي مع شخصية كرتونية مخصصة</p>
            <div class="features">
                <div class="feature"><div class="icon">📄</div><h3>PDF و TXT</h3><p>ادعم جميع الصيغ</p></div>
                <div class="feature"><div class="icon">🎙️</div><h3>صوت بشري</h3><p>بجميع اللهجات</p></div>
                <div class="feature"><div class="icon">🖼️</div><h3>صور ذكية</h3><p>ذكاء اصطناعي</p></div>
                <div class="feature"><div class="icon">🎬</div><h3>فيديو احترافي</h3><p>شرح كامل</p></div>
                <div class="feature"><div class="icon">🧑‍🏫</div><h3>شخصية كرتونية</h3><p>حسب تخصصك</p></div>
                <div class="feature"><div class="icon">🌍</div><h3>دعم كامل</h3><p>عربي وإنجليزي</p></div>
            </div>
            <a class="btn" href="https://t.me/zakros_Quizebot" target="_blank">🚀 ابدأ الآن مجاناً</a>
            <p class="status"><span class="dot"></span>البوت يعمل 24/7 على Heroku | الإصدار {VERSION}</p>
            <div class="footer">© 2026 {APP_NAME} - جميع الحقوق محفوظة</div>
        </div>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def handle_health(request):
    """نقطة فحص الصحة لـ Heroku"""
    return web.json_response({
        "status": "healthy",
        "app": APP_NAME,
        "version": VERSION,
        "timestamp": datetime.now().isoformat(),
        "port": PORT,
    })


async def handle_webhook(request):
    """استقبال تحديثات تيليجرام"""
    # هذا المسار سيتم تسجيله من قبل web_server.py
    # هنا فقط للتأكيد على وجوده
    return web.Response(status=404, text="Webhook endpoint should be handled by web_server.py")


async def start_simple_web_server():
    """بدء خادم ويب بسيط (احتياطي)"""
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/telegram", handle_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    print(f"🌐 Simple web server running on port {PORT}")
    print(f"📍 Health check: http://localhost:{PORT}/health")
    
    return runner, site


# ============================================================
# الدالة الرئيسية
# ============================================================
async def main():
    """الدالة الرئيسية - تشغل خادم الويب والبوت معاً"""
    print(BANNER)
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📡 Port: {PORT}")
    print("-" * 60)
    
    # التحقق من وجود توكن البوت
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not set in environment variables!")
        print("   Please set TELEGRAM_BOT_TOKEN in Heroku config vars or .env file")
        sys.exit(1)
    
    print("✅ TELEGRAM_BOT_TOKEN found")
    
    # التحقق من وجود مفاتيح API
    deepseek_keys = os.getenv("DEEPSEEK_API_KEYS", "") or os.getenv("DEEPSEEK_API_KEY", "")
    google_keys = os.getenv("GOOGLE_API_KEYS", "") or os.getenv("GOOGLE_API_KEY", "")
    
    if deepseek_keys:
        print("✅ DeepSeek API keys found (Priority 1)")
    else:
        print("⚠️ No DeepSeek API keys found. Will use fallbacks.")
    
    if google_keys:
        print("✅ Google API keys found (Priority 2)")
    else:
        print("⚠️ No Google API keys found. Will use fallbacks.")
    
    print("-" * 60)
    
    # ============================================================
    # بدء خادم الويب الرئيسي (من web_server.py)
    # ============================================================
    global _web_task
    
    try:
        from web_server import start_web_server
        print("🌐 Starting main web server...")
        _web_task = asyncio.create_task(start_web_server())
        await asyncio.sleep(2)  # انتظار حتى يبدأ الخادم
        print("✅ Main web server started")
    except Exception as e:
        print(f"⚠️ Could not start main web server: {e}")
        print("🌐 Starting simple fallback web server...")
        runner, site = await start_simple_web_server()
        _web_task = asyncio.create_task(asyncio.sleep(0))  # placeholder

    # ============================================================
    # بدء البوت
    # ============================================================
    global _bot_task
    
    try:
        from bot import main as bot_main
        
        print("🤖 Starting Telegram bot...")
        _bot_task = asyncio.create_task(run_bot_with_restart(bot_main))
        
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        traceback.print_exc()
        sys.exit(1)

    # ============================================================
    # انتظار إشارة الإيقاف
    # ============================================================
    try:
        await _shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    
    # ============================================================
    # إيقاف التطبيق بشكل آمن
    # ============================================================
    print("\n🛑 Shutting down...")
    
    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
    
    if _web_task and not _web_task.done():
        _web_task.cancel()
        try:
            await _web_task
        except asyncio.CancelledError:
            pass
    
    print("✅ Shutdown complete. Goodbye!")


async def run_bot_with_restart(bot_main_func):
    """
    تشغيل البوت مع إعادة تشغيل تلقائي في حالة التعطل.
    """
    restart_delay = 5
    max_restart_delay = 120
    consecutive_crashes = 0
    
    while not _shutdown_event.is_set():
        try:
            print(f"[bot] 🚀 Starting bot (attempt #{consecutive_crashes + 1})...")
            await bot_main_func()
            
            # إذا وصلنا إلى هنا، البوت توقف بشكل طبيعي
            consecutive_crashes = 0
            print("[bot] ⚠️ Bot stopped normally — restarting in 3s...")
            await asyncio.sleep(3)
            
        except asyncio.CancelledError:
            print("[bot] 🛑 Bot cancelled — shutting down.")
            break
            
        except Exception as exc:
            consecutive_crashes += 1
            delay = min(restart_delay * consecutive_crashes, max_restart_delay)
            
            print(f"[bot] ❌ Bot crashed (#{consecutive_crashes}): {exc}")
            traceback.print_exc()
            print(f"[bot] 🔄 Restarting in {delay}s...")
            
            # انتظار مع إمكانية الإيقاف
            try:
                await asyncio.wait_for(_shutdown_event.wait(), timeout=delay)
                break  # تم استلام إشارة إيقاف
            except asyncio.TimeoutError:
                pass  # انتهى وقت الانتظار، نعيد التشغيل


# ============================================================
# نقطة الدخول
# ============================================================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        traceback.print_exc()
        sys.exit(1)
