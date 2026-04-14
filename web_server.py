#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
خادم الويب لاستقبال Webhooks وعرض الصفحة الرئيسية
"""

import os
import asyncio
import logging
from aiohttp import web
from config import OWNER_ID

logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", 5000))
ADMIN_SECRET = str(os.environ.get("ADMIN_SECRET", str(OWNER_ID)))
_bot_application = None


def set_bot_app(app):
    """تسجيل تطبيق البوت لاستقبال التحديثات."""
    global _bot_application
    _bot_application = app


# ══════════════════════════════════════════════════════════════════════════════
#  صفحة البداية
# ══════════════════════════════════════════════════════════════════════════════
HOME_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>بوت المحاضرات الذكي</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
      background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
    }
    .container {
      text-align: center;
      padding: 40px 20px;
      max-width: 600px;
    }
    .logo {
      font-size: 80px;
      margin-bottom: 20px;
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.08); }
    }
    h1 {
      font-size: 2.6rem;
      font-weight: 800;
      margin-bottom: 10px;
      background: linear-gradient(90deg, #a78bfa, #60a5fa, #34d399);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .subtitle {
      font-size: 1.1rem;
      color: #c4b5fd;
      margin-bottom: 40px;
    }
    .features {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 16px;
      margin-bottom: 40px;
    }
    .feature {
      background: rgba(255,255,255,.08);
      border: 1px solid rgba(255,255,255,.12);
      border-radius: 16px;
      padding: 20px 14px;
      backdrop-filter: blur(10px);
      transition: transform .2s;
    }
    .feature:hover { transform: translateY(-4px); }
    .feature .icon { font-size: 2.2rem; margin-bottom: 8px; }
    .feature h3 { font-size: .95rem; color: #e0e7ff; margin-bottom: 4px; }
    .feature p { font-size: .82rem; color: #94a3b8; }
    .btn {
      display: inline-block;
      background: linear-gradient(135deg, #7c3aed, #4f46e5);
      color: #fff;
      text-decoration: none;
      padding: 14px 40px;
      border-radius: 50px;
      font-size: 1.1rem;
      font-weight: 700;
      box-shadow: 0 8px 32px rgba(124,58,237,.4);
      transition: transform .2s, box-shadow .2s;
    }
    .btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 12px 40px rgba(124,58,237,.6);
    }
    .status {
      margin-top: 24px;
      font-size: .85rem;
      color: #64748b;
    }
    .dot {
      display: inline-block;
      width: 10px;
      height: 10px;
      background: #22c55e;
      border-radius: 50%;
      margin-left: 6px;
      animation: blink 1.4s infinite;
    }
    @keyframes blink {
      0%, 100% { opacity: 1; }
      50% { opacity: .3; }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">🎓</div>
    <h1>بوت المحاضرات الذكي</h1>
    <p class="subtitle">حوّل أي PDF أو نص إلى فيديو تعليمي احترافي مع صوت وصور</p>
    <div class="features">
      <div class="feature">
        <div class="icon">📄</div>
        <h3>PDF و نصوص</h3>
        <p>ارفع ملف PDF أو نص</p>
      </div>
      <div class="feature">
        <div class="icon">🎙️</div>
        <h3>صوت بشري</h3>
        <p>7 لهجات مختلفة</p>
      </div>
      <div class="feature">
        <div class="icon">🖼️</div>
        <h3>صور تعليمية</h3>
        <p>كروت احترافية</p>
      </div>
      <div class="feature">
        <div class="icon">🎬</div>
        <h3>فيديو كامل</h3>
        <p>فيديو احترافي جاهز</p>
      </div>
    </div>
    <a class="btn" href="https://t.me/zakros_Quizebot" target="_blank">🚀 ابدأ الآن</a>
    <p class="status"><span class="dot"></span>البوت يعمل الآن</p>
  </div>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
#  معالجات HTTP
# ══════════════════════════════════════════════════════════════════════════════
async def handle_index(request):
    """الصفحة الرئيسية."""
    return web.Response(text=HOME_HTML, content_type="text/html")


async def handle_health(request):
    """نقطة فحص الصحة."""
    mode = "webhook" if _bot_application is not None else "polling"
    return web.json_response({"status": "ok", "bot": "lecture_bot", "mode": mode})


async def handle_telegram_webhook(request):
    """استقبال تحديثات تيليجرام."""
    if _bot_application is None:
        logger.warning("Webhook called but bot not ready")
        return web.Response(status=503, text="Bot not ready")
    
    try:
        from telegram import Update
        data = await request.json()
        update = Update.de_json(data, _bot_application.bot)
        await _bot_application.process_update(update)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    
    return web.Response(status=200)


async def handle_admin(request):
    """لوحة تحكم المالك."""
    key = request.query.get("key", "")
    if key != ADMIN_SECRET:
        return web.Response(
            text="<h2 style='text-align:center;margin-top:60px;color:#ef4444'>⛔ غير مصرح</h2>",
            content_type="text/html",
            status=403
        )
    
    try:
        from database import get_stats, get_all_users
        stats = get_stats()
        users = get_all_users(limit=30)
        
        rows = ""
        for u in users:
            banned = "⛔" if u.get("is_banned") else "✅"
            username = f"@{u['username']}" if u.get("username") else "—"
            rows += f"""
            <tr>
                <td>{u['user_id']}</td>
                <td>{u.get('full_name','—')}</td>
                <td>{username}</td>
                <td>{u.get('total_videos', 0)}</td>
                <td>{banned}</td>
            </tr>"""
        
        html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <title>لوحة التحكم</title>
  <style>
    body {{ font-family: sans-serif; background: #0f172a; color: #e2e8f0; padding: 30px; }}
    h1 {{ color: #a5b4fc; }}
    .cards {{ display: flex; gap: 20px; margin: 20px 0; }}
    .card {{ background: rgba(255,255,255,.05); padding: 20px; border-radius: 16px; text-align: center; }}
    .card .num {{ font-size: 2rem; font-weight: bold; color: #60a5fa; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px; border-bottom: 1px solid rgba(255,255,255,.1); text-align: right; }}
    th {{ color: #818cf8; }}
  </style>
</head>
<body>
  <h1>🎛️ لوحة التحكم</h1>
  <div class="cards">
    <div class="card"><div class="num">{stats['total_users']}</div>المستخدمين</div>
    <div class="card"><div class="num">{stats['total_videos']}</div>الفيديوهات</div>
    <div class="card"><div class="num">{stats['pending_payments']}</div>مدفوعات معلقة</div>
  </div>
  <h2>آخر المستخدمين</h2>
  <table>
    <tr><th>ID</th><th>الاسم</th><th>يوزر</th><th>فيديوهات</th><th>حالة</th></tr>
    {rows}
  </table>
  <p style="margin-top:20px"><a href="?key={key}" style="color:#a78bfa">🔄 تحديث</a></p>
</body>
</html>"""
        
        return web.Response(text=html, content_type="text/html")
    except Exception as e:
        return web.Response(text=f"<pre>خطأ: {e}</pre>", content_type="text/html", status=500)


# ══════════════════════════════════════════════════════════════════════════════
#  بدء الخادم
# ══════════════════════════════════════════════════════════════════════════════
async def start_web_server():
    """بدء خادم الويب."""
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/admin", handle_admin)
    app.router.add_post("/telegram", handle_telegram_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT, reuse_address=True)
    await site.start()
    
    logger.info(f"🌐 Web server running on port {PORT}")
    logger.info(f"   - الصفحة الرئيسية: http://0.0.0.0:{PORT}/")
    logger.info(f"   - فحص الصحة: http://0.0.0.0:{PORT}/health")
    logger.info(f"   - لوحة التحكم: http://0.0.0.0:{PORT}/admin?key=...")
