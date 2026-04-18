import os
import asyncio
from aiohttp import web

PORT = int(os.environ.get("PORT", 8080))

HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>بوت المحاضرات الذكي</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
    }
    .container {
      text-align: center;
      padding: 40px 20px;
      max-width: 600px;
    }
    .logo {
      font-size: 80px;
      margin-bottom: 20px;
    }
    h1 {
      font-size: 2.5rem;
      margin-bottom: 20px;
    }
    .status {
      margin-top: 30px;
      padding: 15px;
      background: rgba(255,255,255,0.1);
      border-radius: 50px;
    }
    .btn {
      display: inline-block;
      background: white;
      color: #667eea;
      text-decoration: none;
      padding: 15px 40px;
      border-radius: 50px;
      font-weight: bold;
      margin-top: 20px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">🤖</div>
    <h1>بوت المحاضرات الذكي</h1>
    <p>حوّل محاضراتك إلى فيديوهات تعليمية احترافية</p>
    <a class="btn" href="https://t.me/zakros_Quizebot">ابدأ الآن</a>
    <div class="status">
      <span>✅ البوت يعمل الآن</span>
    </div>
  </div>
</body>
</html>
"""

async def handle_index(request):
    return web.Response(text=HTML, content_type="text/html")

async def handle_health(request):
    return web.json_response({"status": "ok", "bot": "running"})

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web server running on port {PORT}")

if __name__ == "__main__":
    asyncio.run(start_web_server())
