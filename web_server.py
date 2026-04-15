import os
import asyncio
import json
from aiohttp import web
from config import OWNER_ID

# ───────────────────────────────────────────────────────────────────────────────
# Webhook support
# ───────────────────────────────────────────────────────────────────────────────
_bot_application = None   # set by bot.py when webhook mode is active

def set_bot_app(app):
    """Register the PTB Application so webhook updates can be forwarded to it."""
    global _bot_application
    _bot_application = app

PORT = int(os.environ.get("PORT", 5000))

ADMIN_SECRET = str(os.environ.get("ADMIN_SECRET", str(OWNER_ID)))

HOME_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>بوت المحاضرات التعليمي</title>
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
    .feature h3{font-size:1rem;color:#e0e7ff;margin-bottom:4px}
    .feature p{font-size:.85rem;color:#94a3b8}
    .btn {
      display:inline-block;
      background:linear-gradient(135deg,#7c3aed,#4f46e5);
      color:#fff; text-decoration:none;
      padding:14px 40px; border-radius:50px;
      font-size:1.2rem; font-weight:700;
      box-shadow:0 8px 32px rgba(124,58,237,.4);
      transition:transform .2s,box-shadow .2s;
    }
    .btn:hover{transform:translateY(-2px);box-shadow:0 12px 40px rgba(124,58,237,.6)}
    .status{margin-top:24px;font-size:.9rem;color:#64748b}
    .dot{display:inline-block;width:10px;height:10px;background:#22c55e;
         border-radius:50%;margin-left:6px;animation:blink 1.4s infinite}
    @keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
  </style>
</head>
<body>
  <div class="container">
    <div class="logo">🎓</div>
    <h1>بوت المحاضرات التعليمي</h1>
    <p class="subtitle">حوّل محاضرتك إلى فيديو تعليمي احترافي مع صوت وصور</p>
    <div class="features">
      <div class="feature"><div class="icon">📄</div><h3>PDF ونصوص</h3><p>ارفع ملف PDF أو نص</p></div>
      <div class="feature"><div class="icon">🎙️</div><h3>صوت بشري</h3><p>شرح بلهجتك المفضلة</p></div>
      <div class="feature"><div class="icon">🖼️</div><h3>صور تعليمية</h3><p>كروت احترافية لكل قسم</p></div>
      <div class="feature"><div class="icon">🎬</div><h3>فيديو كامل</h3><p>فيديو تعليمي متكامل</p></div>
    </div>
    <a class="btn" href="https://t.me/zakros_probot" target="_blank">🚀 ابدأ الآن</a>
    <p class="status"><span class="dot"></span>البوت يعمل الآن</p>
  </div>
</body>
</html>"""


def make_admin_html(stats: dict, recent: list, image_status: dict = None, voice_status: dict = None) -> str:
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
          <td>{u.get('total_videos', 0)}</td>
          <td>{u.get('attempts_left', 0)}</td>
          <td>{banned}</td>
          <td>{created}</td>
        </tr>"""

    # Voice status section
    voice_html = ""
    if voice_status:
        voice_html = f"""
        <div class="card">
          <div class="icon">🎙️</div>
          <div class="num">{voice_status.get('active', 0)}/{voice_status.get('total', 0)}</div>
          <div class="label">مفاتيح ElevenLabs نشطة</div>
        </div>
        """

    # Image status section
    image_html = ""
    if image_status:
        stability = image_status.get('stability', {})
        replicate = image_status.get('replicate', {})
        pollinations = image_status.get('pollinations', {})
        image_html = f"""
        <div class="card green">
          <div class="icon">🖼️</div>
          <div class="num">{stability.get('active', 0)}/{stability.get('total', 0)}</div>
          <div class="label">مفاتيح Stability نشطة</div>
        </div>
        <div class="card yellow">
          <div class="icon">🎨</div>
          <div class="num">{'✅' if replicate.get('available') else '❌'}</div>
          <div class="label">Replicate متاح</div>
        </div>
        <div class="card">
          <div class="icon">🆓</div>
          <div class="num">{'✅' if pollinations.get('available') else '❌'}</div>
          <div class="label">Pollinations مجاني</div>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>لوحة التحكم — بوت المحاضرات</title>
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
    header h1 {{ font-size:1.5rem; font-weight:700; color:#a5b4fc; }}
    header span {{ font-size:2rem; }}
    .main {{ padding:28px 32px; max-width:1200px; margin:0 auto; }}
    .cards {{
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
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
    .card .icon {{ font-size:2rem; margin-bottom:8px; }}
    .card.green .num {{ background:linear-gradient(90deg,#34d399,#10b981); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
    .card.red .num {{ background:linear-gradient(90deg,#f87171,#ef4444); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
    .card.yellow .num {{ background:linear-gradient(90deg,#fbbf24,#f59e0b); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
    h2 {{ font-size:1.2rem; color:#a5b4fc; margin-bottom:14px; margin-top:30px; }}
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
    .section-title {{
      display:flex; align-items:center; gap:10px;
      margin:30px 0 15px 0;
    }}
    .section-title h2 {{ margin:0; }}
    .badge {{
      background:rgba(129,140,248,.2);
      padding:4px 12px; border-radius:20px;
      font-size:.8rem; color:#a5b4fc;
    }}
  </style>
</head>
<body>
  <header>
    <span>🎓</span>
    <h1>لوحة تحكم — بوت المحاضرات التعليمي</h1>
  </header>
  <div class="main">
    <a class="refresh" href="">🔄 تحديث</a>
    
    <h2>📊 إحصائيات عامة</h2>
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
        <div class="icon">🎬</div>
        <div class="num">{stats['total_videos']}</div>
        <div class="label">إجمالي الفيديوهات</div>
      </div>
      <div class="card green">
        <div class="icon">📊</div>
        <div class="num">{stats.get('active_users', 0)}</div>
        <div class="label">نشط (24 ساعة)</div>
      </div>
      <div class="card red">
        <div class="icon">⛔</div>
        <div class="num">{stats['banned_users']}</div>
        <div class="label">مستخدمون محظورون</div>
      </div>
      <div class="card">
        <div class="icon">💰</div>
        <div class="num">{stats.get('pending_payments', 0)}</div>
        <div class="label">مدفوعات معلقة</div>
      </div>
    </div>

    <div class="section-title">
      <h2>🎙️ حالة الصوت</h2>
      <span class="badge">ElevenLabs</span>
    </div>
    <div class="cards">
      {voice_html}
    </div>

    <div class="section-title">
      <h2>🖼️ حالة الصور</h2>
      <span class="badge">Stability / Replicate / Pollinations</span>
    </div>
    <div class="cards">
      {image_html}
    </div>

    <h2>📋 آخر المستخدمين</h2>
    <table>
      <thead>
        <tr>
          <th>المعرّف</th>
          <th>الاسم</th>
          <th>يوزرنيم</th>
          <th>فيديوهات</th>
          <th>محاولات</th>
          <th>الحالة</th>
          <th>تاريخ التسجيل</th>
        </tr>
      </thead>
      <tbody>
        {rows if rows else '<tr><td colspan="7" style="text-align:center;padding:20px;color:#64748b">لا يوجد مستخدمون بعد</td></tr>'}
      </tbody>
    </table>
  </div>
</body>
</html>"""


def get_admin_stats() -> tuple[dict, list]:
    from database import get_connection
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as c FROM users")
    total_users = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM users WHERE DATE(created_at) = CURRENT_DATE")
    new_today = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM users WHERE is_banned = TRUE")
    banned_users = cur.fetchone()["c"]

    cur.execute("SELECT COALESCE(SUM(total_videos), 0) as c FROM users")
    total_videos = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM payments WHERE status = 'pending'")
    pending_payments = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) as c FROM users WHERE last_active > NOW() - INTERVAL '24 hours'")
    active_users = cur.fetchone()["c"]

    cur.execute("""
        SELECT u.user_id, u.username, u.full_name, u.is_banned, u.created_at,
               u.total_videos, u.attempts_left, u.last_active
        FROM users u
        ORDER BY u.created_at DESC
        LIMIT 30
    """)
    recent = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    stats = {
        "total_users": total_users,
        "new_today": new_today,
        "banned_users": banned_users,
        "total_videos": total_videos,
        "pending_payments": pending_payments,
        "active_users": active_users,
    }
    return stats, recent


async def handle_index(request):
    return web.Response(text=HOME_HTML, content_type="text/html")


async def handle_health(request):
    mode = "webhook" if _bot_application is not None else "polling"
    
    # جمع حالة الخدمات
    status_info = {"status": "ok", "bot": "lecture_bot", "mode": mode}
    
    try:
        from voice_generator import keys_status as voice_keys_status
        status_info["voice"] = voice_keys_status()
    except:
        status_info["voice"] = {"error": "not available"}
    
    try:
        from image_generator import get_image_keys_status
        status_info["images"] = get_image_keys_status()
    except:
        status_info["images"] = {"error": "not available"}
    
    return web.json_response(status_info)


async def handle_telegram_webhook(request):
    """Receive Telegram updates via POST /telegram and feed them to the bot."""
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
        
        # Get voice status
        try:
            from voice_generator import keys_status as voice_keys_status
            voice_status = voice_keys_status()
        except:
            voice_status = {"total": 0, "active": 0}
        
        # Get image status
        try:
            from image_generator import get_image_keys_status
            image_status = get_image_keys_status()
        except:
            image_status = {
                "stability": {"total": 0, "active": 0},
                "replicate": {"available": False},
                "pollinations": {"available": True}
            }
        
        html = make_admin_html(stats, recent, image_status, voice_status)
        return web.Response(text=html, content_type="text/html")
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return web.Response(text=f"<pre>خطأ: {e}\n\n{error_detail}</pre>", content_type="text/html", status=500)


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
    app.router.add_get("/", handle_index)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/admin", handle_admin)
    app.router.add_post("/telegram", handle_telegram_webhook)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT, reuse_address=True)
    await site.start()
    print(f"🌐 Web server running on port {PORT}")
    print(f"   - Home: http://0.0.0.0:{PORT}/")
    print(f"   - Health: http://0.0.0.0:{PORT}/health")
    print(f"   - Admin: http://0.0.0.0:{PORT}/admin?key=...")
