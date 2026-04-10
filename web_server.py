import os
import asyncio
from aiohttp import web
from config import OWNER_ID

_bot_application = None

def set_bot_app(app):
    global _bot_application
    _bot_application = app

PORT = int(os.environ.get("PORT", 5000))
ADMIN_SECRET = str(os.environ.get("ADMIN_SECRET", str(OWNER_ID)))

HOME_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>بوت المحاضرات الذكي</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body {
      font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
      background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
      min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
      color: #fff;
    }
    .container { text-align:center; padding:40px 20px; max-width:600px; }
    .logo { font-size:80px; margin-bottom:20px; animation:pulse 2s infinite; }
    @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.08)} }
    h1 {
      font-size:2.6rem; font-weight:800; margin-bottom:10px;
      background:linear-gradient(90deg,#a78bfa,#60a5fa,#34d399);
      -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    }
    .subtitle { font-size:1.1rem; color:#c4b5fd; margin-bottom:40px; }
    .btn {
      display:inline-block;
      background:linear-gradient(135deg,#7c3aed,#4f46e5);
      color:#fff; text-decoration:none;
      padding:14px 40px; border-radius:50px;
      font-size:1.1rem; font-weight:700;
      box-shadow:0 8px 32px rgba(124,58,237,.4);
      transition:transform .2s,box-shadow .2s;
    }
    .btn:hover{transform:translateY(-2px);box-shadow:0 12px 40px rgba(124,58,237,.6)}
    .status{margin-top:24px;font-size:.85rem;color:#64748b}
    .dot{display:inline-block;width:10px;height:10px;background:#22c55e;
         border-radius:50%;margin-left:6px;animation:blink 1.4s infinite}
    @keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">🎓</div>
    <h1>بوت المحاضرات الذكي</h1>
    <p class="subtitle">حول محاضراتك إلى فيديوهات تعليمية احترافية</p>
    <a class="btn" href="https://t.me/zakros_Quizebot" target="_blank">🚀 ابدأ الآن</a>
    <p class="status"><span class="dot"></span>البوت يعمل الآن</p>
  </div>
</body>
</html>"""


async def handle_index(request):
    return web.Response(text=HOME_HTML, content_type="text/html")


async def handle_health(request):
    mode = "webhook" if _bot_application is not None else "polling"
    return web.json_response({"status": "ok", "bot": "lecture_bot", "mode": mode})


async def handle_telegram_webhook(request):
    if _bot_application is None:
        return web.Response(status=503, text="Bot not ready")
    try:
        from telegram import Update
        data = await request.json()
        update = Update.de_json(data, _bot_application.bot)
        await _bot_application.process_update(update)
    except Exception as e:
        print(f"[webhook] Error processing update: {e}")
    return web.Response(status=200)


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_post("/telegram", handle_telegram_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web server running on port {PORT}")
