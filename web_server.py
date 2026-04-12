import os
import asyncio
import json
from aiohttp import web
from config import OWNER_ID

# ============================================================
# متغيرات عامة
# ============================================================
_bot_application = None  # يتم تعيينه من bot.py

def set_bot_app(app):
    """تسجيل تطبيق البوت لاستخدامه في webhook"""
    global _bot_application
    _bot_application = app

PORT = int(os.environ.get("PORT", 5000))
ADMIN_SECRET = str(os.environ.get("ADMIN_SECRET", str(OWNER_ID)))

# ============================================================
# الصفحة الرئيسية
# ============================================================
HOME_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>بوت المحاضرات الذكي | ZAKROS PRO</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body {
      font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
      background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
      min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
      color: #fff;
    }
    .container { text-align:center; padding:40px 20px; max-width:700px; }
    .logo { font-size:80px; margin-bottom:20px; animation:pulse 2s infinite; }
    @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.08)} }
    h1 {
      font-size:2.8rem; font-weight:800; margin-bottom:10px;
      background:linear-gradient(90deg,#a78bfa,#60a5fa,#34d399);
      -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    }
    .subtitle { font-size:1.2rem; color:#c4b5fd; margin-bottom:40px; }
    .features {
      display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
      gap:16px; margin-bottom:40px;
    }
    .feature {
      background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.12);
      border-radius:16px; padding:20px 14px; backdrop-filter:blur(10px);
      transition:transform .2s;
    }
    .feature:hover{transform:translateY(-4px)}
    .feature .icon{font-size:2.2rem;margin-bottom:8px}
    .feature h3{font-size:1rem;color:#e0e7ff;margin-bottom:4px}
    .feature p{font-size:.85rem;color:#94a3b8}
    .btn {
      display:inline-block;
      background:linear-gradient(135deg,#7c3aed,#4f46e5);
      color:#fff; text-decoration:none;
      padding:16px 50px; border-radius:50px;
      font-size:1.2rem; font-weight:700;
      box-shadow:0 8px 32px rgba(124,58,237,.4);
      transition:transform .2s,box-shadow .2s;
      margin-bottom:30px;
    }
    .btn:hover{transform:translateY(-2px);box-shadow:0 12px 40px rgba(124,58,237,.6)}
    .status{margin-top:24px;font-size:.9rem;color:#64748b}
    .dot{display:inline-block;width:10px;height:10px;background:#22c55e;
         border-radius:50%;margin-left:6px;animation:blink 1.4s infinite}
    @keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
    .footer {margin-top:40px; color:#64748b; font-size:.8rem;}
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">🎓</div>
    <h1>ZAKROS PRO</h1>
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
    <p class="status"><span class="dot"></span>البوت يعمل 24/7 على Heroku</p>
    <div class="footer">© 2026 ZAKROS PRO - جميع الحقوق محفوظة</div>
  </div>
</body>
</html>"""


async def handle_index(request):
    """الصفحة الرئيسية"""
    return web.Response(text=HOME_HTML, content_type="text/html")


async def handle_health(request):
    """نقطة فحص الصحة لـ Heroku"""
    mode = "webhook" if _bot_application is not None else "polling"
    return web.json_response({
        "status": "ok",
        "bot": "lecture_bot",
        "mode": mode,
        "host": "heroku",
        "timestamp": str(asyncio.get_event_loop().time())
    })


async def handle_telegram_webhook(request):
    """
    استقبال تحديثات تيليجرام عبر Webhook.
    """
    if _bot_application is None:
        return web.Response(status=503, text="Bot not ready")
    
    try:
        from telegram import Update
        data = await request.json()
        update = Update.de_json(data, _bot_application.bot)
        await _bot_application.process_update(update)
    except Exception as e:
        print(f"[webhook] Error processing update: {e}", flush=True)
    
    return web.Response(status=200)


async def start_web_server():
    """
    بدء تشغيل خادم الويب.
    """
    port = int(os.environ.get("PORT", 5000))
    
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/telegram", handle_telegram_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    print(f"🌐 Web server running on port {port}")
    print(f"📍 Health check: http://localhost:{port}/health")
    print(f"📍 Webhook endpoint: http://localhost:{port}/telegram")
