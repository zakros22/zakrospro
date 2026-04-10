import os
import asyncio
import json
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
  <title>بوت المذكرات</title>
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
    .features {
      display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
      gap:16px; margin-bottom:40px;
    }
    .feature {
      background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.12);
      border-radius:16px; padding:20px 14px; backdrop-filter:blur(10px);
      transition:transform .2s;
    }
    .feature:hover{transform:translateY(-4px)}
    .feature .icon{font-size:2.2rem;margin-bottom:8px}
    .feature h3{font-size:.95rem;color:#e0e7ff;margin-bottom:4px}
    .feature p{font-size:.82rem;color:#94a3b8}
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
    <div class="logo">📒</div>
    <h1>بوت المذكرات</h1>
    <p class="subtitle">احفظ أي شيء — نصوص، صور، ملفات، صوت، فيديو، روابط</p>
    <div class="features">
      <div class="feature"><div class="icon">🖼️</div><h3>صور وملفات</h3><p>احفظ أي ملف أو صورة</p></div>
      <div class="feature"><div class="icon">🎤</div><h3>رسائل صوتية</h3><p>حفظ الصوت والموسيقى</p></div>
      <div class="feature"><div class="icon">⏰</div><h3>تنبيهات</h3><p>تذكير بأي تاريخ ووقت</p></div>
      <div class="feature"><div class="icon">🔗</div><h3>روابط</h3><p>احفظ روابط الإنترنت</p></div>
    </div>
    <a class="btn" href="https://t.me/zakros_Quizebot" target="_blank">🚀 ابدأ الآن</a>
    <p class="status"><span class="dot"></span>البوت يعمل الآن</p>
  </div>
</body>
</html>"""


def make_admin_html(stats: dict, recent: list) -> str:
    rows = ""
    for u in recent:
        banned = "⛔" if u.get("is_banned") else "✅"
        username = f"@{u['username']}" if u.get("username") else "—"
        created = str(u.get("created_at", ""))[:10]
        rows += f"""
        <tr>
          <td>{u['user_id']}</td>
          <td>{u.get('full_name','—')}</td>
          <td>{username}</td>
          <td>{u.get('notes_count', 0)}</td>
          <td>{banned}</td>
          <td>{created}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>لوحة التحكم — بوت المذكرات</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family:'Segoe UI',Tahoma,Arial,sans-serif;
      background:#0f172a; color:#e2e8f0; min-height:100vh;
    }}
    header {{
      background:linear-gradient(135deg,#1e1b4b,#312e81);
      padding:20px 32px;
      display:flex; align-items:center; gap:14px;
      border-bottom:1px solid rgba(255,255,255,.08);
    }}
    header h1 {{ font-size:1.4rem; font-weight:700; color:#a5b4fc; }}
    header span {{ font-size:1.8rem; }}
    .main {{ padding:28px 32px; max-width:1100px; margin:0 auto; }}
    .cards {{
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(200px,1fr));
      gap:20px; margin-bottom:32px;
    }}
    .card {{
      background:rgba(255,255,255,.05);
      border:1px solid rgba(255,255,255,.1);
      border-radius:16px; padding:24px 20px;
      text-align:center;
    }}
    .card .num {{
      font-size:2.6rem; font-weight:800;
      background:linear-gradient(90deg,#818cf8,#60a5fa);
      -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    }}
    .card .label {{ font-size:.9rem; color:#94a3b8; margin-top:6px; }}
    .card .icon  {{ font-size:2rem; margin-bottom:8px; }}
    .card.green .num {{ background:linear-gradient(90deg,#34d399,#10b981); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
    .card.red .num   {{ background:linear-gradient(90deg,#f87171,#ef4444); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
    .card.yellow .num{{ background:linear-gradient(90deg,#fbbf24,#f59e0b); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
    h2 {{ font-size:1.1rem; color:#a5b4fc; margin-bottom:14px; }}
    table {{
      width:100%; border-collapse:collapse;
      background:rgba(255,255,255,.04);
      border-radius:12px; overflow:hidden;
    }}
    th {{
      background:rgba(129,140,248,.15);
      padding:12px 16px; text-align:right;
      font-size:.85rem; color:#818cf8; font-weight:600;
    }}
    td {{
      padding:11px 16px; border-top:1px solid rgba(255,255,255,.06);
      font-size:.88rem; color:#cbd5e1;
    }}
    tr:hover td {{ background:rgba(255,255,255,.04); }}
    .refresh {{
      display:inline-block;
      background:rgba(129,140,248,.2);
      color:#a5b4fc; text-decoration:none;
      padding:8px 20px; border-radius:8px;
      font-size:.85rem; margin-bottom:20px;
      transition:background .2s;
    }}
    .refresh:hover {{ background:rgba(129,140,248,.35); }}
  </style>
</head>
<body>
  <header>
    <span>📒</span>
    <h1>لوحة تحكم — بوت المذكرات</h1>
  </header>
  <div class="main">
    <a class="refresh" href="">🔄 تحديث</a>
    <div class="cards">
      <div class="card">
        <div class="icon">👥</div>
        <div class="num">{stats['total_users']}</div>
        <div class="label">إجمالي المستخدمين</div>
      </div>
      <div class="card green">
        <div class="icon">🆕</div>
        <div class="num">{stats['new_today']}</div>
        <div class="label">مستخدمون جدد اليوم</div>
      </div>
      <div class="card yellow">
        <div class="icon">📒</div>
        <div class="num">{stats['total_notes']}</div>
        <div class="label">إجمالي المذكرات</div>
      </div>
      <div class="card yellow">
        <div class="icon">⏰</div>
        <div class="num">{stats['pending_reminders']}</div>
        <div class="label">تنبيهات قادمة</div>
      </div>
      <div class="card red">
        <div class="icon">⛔</div>
        <div class="num">{stats['banned_users']}</div>
        <div class="label">مستخدمون محظورون</div>
      </div>
    </div>

    <h2>📋 آخر المستخدمين</h2>
    <table>
      <thead>
        <tr>
          <th>المعرّف</th>
          <th>الاسم</th>
          <th>يوزرنيم</th>
          <th>مذكراته</th>
          <th>الحالة</th>
          <th>تاريخ التسجيل</th>
        </tr>
      </thead>
      <tbody>
        {rows if rows else '<tr><td colspan="6" style="text-align:center;padding:20px;color:#64748b">لا يوجد مستخدمون بعد</td></tr>'}
      </tbody>
    </table>
  </div>
</body>
</html>"""


def get_admin_stats() -> tuple[dict, list]:
    from database import get_connection
    conn = get_connection()
    cur  = conn.cursor()

    cur.execute("SELECT COUNT(*) as c FROM users")
    total_users = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM users WHERE DATE(created_at) = CURRENT_DATE")
    new_today = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM users WHERE is_banned = TRUE")
    banned_users = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM notes")
    total_notes = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM notes WHERE reminder_at IS NOT NULL AND reminder_at > NOW() AND reminded = FALSE")
    pending_reminders = cur.fetchone()["c"]

    cur.execute("""
        SELECT u.user_id, u.username, u.full_name, u.is_banned, u.created_at,
               COUNT(n.id) as notes_count
        FROM users u
        LEFT JOIN notes n ON n.user_id = u.user_id
        GROUP BY u.user_id
        ORDER BY u.created_at DESC
        LIMIT 30
    """)
    recent = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    stats = {
        "total_users":      total_users,
        "new_today":        new_today,
        "banned_users":     banned_users,
        "total_notes":      total_notes,
        "pending_reminders": pending_reminders,
    }
    return stats, recent


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
        print(f"[webhook] Error processing update: {e}", flush=True)
    return web.Response(status=200)


async def handle_admin(request):
    key = request.query.get("key", "")
    if key != ADMIN_SECRET:
        return web.Response(
            text="<h2 style='font-family:sans-serif;text-align:center;margin-top:60px;color:#ef4444'>⛔ غير مصرح</h2>",
            content_type="text/html",
            status=403,
        )
    try:
        stats, recent = get_admin_stats()
        html = make_admin_html(stats, recent)
        return web.Response(text=html, content_type="text/html")
    except Exception as e:
        return web.Response(text=f"<pre>خطأ: {e}</pre>", content_type="text/html", status=500)


async def start_web_server():
    import socket
    for _ in range(5):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", PORT))
            s.close()
            break
        except OSError:
            await asyncio.sleep(1)

    app = web.Application()
    app.router.add_get("/",           handle_index)
    app.router.add_get("/health",     handle_health)
    app.router.add_get("/admin",      handle_admin)
    app.router.add_post("/telegram",  handle_telegram_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT, reuse_address=True)
    await site.start()
    print(f"🌐 Web server running on port {PORT}")
