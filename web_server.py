#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZAKROS PRO - خادم الويب
يدعم Webhook لتلقي تحديثات تيليجرام على Heroku
"""
import sys
import os
import asyncio
import json
from datetime import datetime
from aiohttp import web
from config import OWNER_ID

# ============================================================
# متغيرات عامة
# ============================================================
_bot_application = None  # سيتم تعيينه من bot.py
PORT = int(os.environ.get("PORT", 5000))
ADMIN_SECRET = str(os.environ.get("ADMIN_SECRET", str(OWNER_ID)))


def set_bot_app(app):
    """تسجيل تطبيق البوت لاستخدامه في webhook"""
    global _bot_application
    _bot_application = app
    print("✅ Bot application registered with web server")


# ============================================================
# الصفحة الرئيسية
# ============================================================
HOME_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>ZAKROS PRO - بوت المحاضرات الذكي</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    body {
      font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
      background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
      min-height: 100vh;
      display: flex; align-items: center; justify-content: center;
      color: #fff;
    }
    .container { text-align:center; padding:40px 20px; max-width:800px; }
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
    .stats {display:flex; justify-content:center; gap:30px; margin-top:20px;}
    .stat {text-align:center;}
    .stat-value {font-size:1.5rem; font-weight:bold; color:#a78bfa;}
    .stat-label {font-size:.8rem; color:#94a3b8;}
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
    <div class="stats">
      <div class="stat">
        <div class="stat-value">24/7</div>
        <div class="stat-label">يعمل باستمرار</div>
      </div>
      <div class="stat">
        <div class="stat-value">7+</div>
        <div class="stat-label">لهجات مدعومة</div>
      </div>
      <div class="stat">
        <div class="stat-value">20+</div>
        <div class="stat-label">تخصص علمي</div>
      </div>
    </div>
    <p class="status"><span class="dot"></span>البوت يعمل الآن على Heroku</p>
    <div class="footer">© 2026 ZAKROS PRO - جميع الحقوق محفوظة</div>
  </div>
</body>
</html>"""


async def handle_index(request):
    """الصفحة الرئيسية"""
    return web.Response(text=HOME_HTML, content_type="text/html")


async def handle_health(request):
    """نقطة فحص الصحة"""
    mode = "webhook" if _bot_application is not None else "polling"
    return web.json_response({
        "status": "healthy",
        "bot": "zakros_pro",
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
    })


async def handle_telegram_webhook(request):
    """استقبال تحديثات تيليجرام"""
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


async def handle_admin(request):
    """لوحة تحكم بسيطة للإدارة"""
    key = request.query.get("key", "")
    if key != ADMIN_SECRET:
        return web.Response(
            text="<h2 style='font-family:sans-serif;text-align:center;margin-top:60px;color:#ef4444'>⛔ غير مصرح</h2>",
            content_type="text/html",
            status=403,
        )
    
    try:
        from database import get_stats, get_all_users
        stats = get_stats()
        users = get_all_users(limit=10)
        
        rows = ""
        for u in users:
            banned = "⛔" if u.get("is_banned") else "✅"
            username = f"@{u['username']}" if u.get("username") else "—"
            rows += f"""
            <tr>
                <td>{u['user_id']}</td>
                <td>{u.get('full_name', '—')}</td>
                <td>{username}</td>
                <td>{u.get('total_videos', 0)}</td>
                <td>{u.get('attempts_left', 0)}</td>
                <td>{banned}</td>
            </tr>"""
        
        html = f"""
        <!DOCTYPE html>
        <html lang="ar" dir="rtl">
        <head>
            <meta charset="UTF-8"/>
            <title>لوحة التحكم - ZAKROS PRO</title>
            <style>
                body {{ font-family: sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }}
                h1 {{ color: #a78bfa; }}
                .stats {{ display: flex; gap: 20px; margin-bottom: 30px; }}
                .stat {{ background: #16213e; padding: 20px; border-radius: 10px; text-align: center; }}
                .stat-value {{ font-size: 2rem; font-weight: bold; color: #60a5fa; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ padding: 10px; text-align: right; border-bottom: 1px solid #333; }}
                th {{ background: #0f3460; }}
            </style>
        </head>
        <body>
            <h1>🎓 ZAKROS PRO - لوحة التحكم</h1>
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{stats['total_users']}</div>
                    <div>مستخدم</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{stats['new_today']}</div>
                    <div>جديد اليوم</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{stats['total_videos']}</div>
                    <div>فيديو</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{stats['pending_payments']}</div>
                    <div>مدفوعات معلقة</div>
                </div>
            </div>
            <h2>آخر المستخدمين</h2>
            <table>
                <thead>
                    <tr><th>ID</th><th>الاسم</th><th>المعرف</th><th>فيديوهات</th><th>محاولات</th><th>الحالة</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </body>
        </html>
        """
        return web.Response(text=html, content_type="text/html")
    except Exception as e:
        return web.Response(text=f"<pre>خطأ: {e}</pre>", content_type="text/html", status=500)


async def start_web_server():
    """بدء تشغيل خادم الويب"""
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/admin", handle_admin)
    app.router.add_post("/telegram", handle_telegram_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    
    print(f"🌐 Web server running on port {PORT}")
    print(f"📍 Health check: http://localhost:{PORT}/health")
    print(f"📍 Webhook endpoint: http://localhost:{PORT}/telegram")
    print(f"📍 Admin panel: http://localhost:{PORT}/admin?key=ADMIN_SECRET")
    
    # الانتظار حتى يتم إيقاف التطبيق
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        pass
    
    await runner.cleanup()
