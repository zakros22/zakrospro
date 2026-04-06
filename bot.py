
import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import random
import time

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== قاعدة البيانات ==========
conn = sqlite3.connect("draw_bot.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 3,
    total_shares INTEGER DEFAULT 0
)''')
c.execute('''CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    referred_id INTEGER,
    date TEXT
)''')
conn.commit()

def get_user(user_id):
    c.execute("SELECT points, total_shares FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, points, total_shares) VALUES (?,?,?)", (user_id, 3, 0))
        conn.commit()
        return {"points": 3, "total_shares": 0}
    return {"points": row[0], "total_shares": row[1]}

def update_points(user_id, delta):
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (delta, user_id))
    conn.commit()

def add_share(user_id):
    c.execute("UPDATE users SET total_shares = total_shares + 1 WHERE user_id=?", (user_id,))
    c.execute("SELECT total_shares FROM users WHERE user_id=?", (user_id,))
    shares = c.fetchone()[0]
    if shares % 1 == 0:
        c.execute("UPDATE users SET points = points + 3 WHERE user_id=?", (user_id,))
    conn.commit()

def add_referral(referrer_id, referred_id):
    c.execute("SELECT * FROM referrals WHERE referred_id=?", (referred_id,))
    if c.fetchone():
        return False
    c.execute("INSERT INTO referrals (referrer_id, referred_id, date) VALUES (?,?,?)", 
              (referrer_id, referred_id, time.time()))
    update_points(referrer_id, 3)
    conn.commit()
    return True

# ========== كلمات البحث والرسومات النصية ==========
ASCII_ARTS = {
    # أشخاص
    "ولد": "👦\n  ┌─┐\n  │ │\n┌─┘ └─┐\n│     │\n└─────┘",
    "بنت": "👧\n  ╭─╮\n  │ │\n╭─╯ ╰─╮\n│     │\n╰─────╯",
    "رجل": "👨\n  ┌─┐\n  │ │\n┌─┘ └─┐\n│  █  │\n└─────┘",
    "امرأة": "👩\n  ╭─╮\n  │ │\n╭─╯ ╰─╮\n│  █  │\n╰─────╯",
    "طفل": "🧒\n  ┌─┐\n  │ │\n┌─┘ └─┐\n│  O  │\n└─────┘",
    
    # حيوانات
    "قط": "🐱\n  /\\_/\\\n ( o.o )\n  > ^ <",
    "كلب": "🐶\n  ┌───┐\n  │ ○ │\n┌─┘   └─┐\n│   U   │\n└───────┘",
    "أسد": "🦁\n  ┌───┐\n  │ ○ │\n┌─┘ ┌─┘\n│   └─┐\n└─────┘",
    "فيل": "🐘\n    ┌───┐\n    │ ○ │\n┌───┘   └───┐\n│           │\n└───────────┘",
    "سمكة": "🐟\n  ┌─────┐\n  │ ◉   │\n  └──┬──┘\n     │",
    "طائر": "🐦\n  ┌─┐\n  │○│\n┌─┘ └─┐\n│  │  │\n└──┴──┘",
    "نحلة": "🐝\n  ┌─┐\n  │○│\n┌─┘ └─┐\n│  █  │\n└──┴──┘",
    "فراشة": "🦋\n   ┌─┐\n ┌─┘○└─┐\n │     │\n └──┬──┘\n    │",
    
    # طبيعة
    "وردة": "🌹\n    ╭─╮\n    │○│\n╭───╯ ╰───╮\n│         │\n╰─────────╯\n     │\n     │",
    "شجرة": "🌳\n      ▲\n     ▲▲▲\n    ▲▲▲▲▲\n   ▲▲▲▲▲▲▲\n      │\n      │",
    "زهرة": "🌸\n    ╭─╮\n    │○│\n╭───╯ ╰───╮\n│    █    │\n╰─────────╯\n     │\n    / \\",
    "نجمة": "⭐\n    ★\n   ★ ★\n  ★   ★\n ★     ★\n★       ★\n ★     ★\n  ★   ★\n   ★ ★\n    ★",
    "قمر": "🌙\n    ┌─────┐\n    │  ○  │\n    │     │\n    └─────┘",
    "شمس": "☀️\n      ★\n    ★   ★\n   ★  ○  ★\n    ★   ★\n      ★",
    
    # أشياء
    "سيارة": "🚗\n    ┌─────┐\n    │  □  │\n┌───┘     └───┐\n│     ○○     │\n└────────────┘",
    "منزل": "🏠\n    ┌───┐\n    │   │\n┌───┘   └───┐\n│     □     │\n│     □     │\n└───────────┘",
    "قلب": "❤️\n    ┌─┐ ┌─┐\n  ┌─┘ └─┘ └─┐\n  │         │\n  │    ○    │\n  └─────────┘",
    "كرة": "⚽\n      ┌─┐\n    ┌─┘○└─┐\n    │  █  │\n    └──┬──┘\n       │",
    "كتاب": "📖\n    ┌─────┐\n    │     │\n┌───┘     └───┐\n│     ○○     │\n└────────────┘",
    "قلم": "✏️\n    ┌─┐\n    │○│\n┌───┘ └───┐\n│    █    │\n└─────────┘",
    "هاتف": "📱\n    ┌─────┐\n    │  ○  │\n    │     │\n    │  □  │\n    └─────┘",
    "كمبيوتر": "💻\n    ┌─────┐\n    │  ○  │\n┌───┘     └───┐\n│     ██     │\n└────────────┘",
    
    # أفعال
    "يلعب": "⚽\n    ┌─┐\n    │○│\n┌───┘ └───┐\n│    █    │\n│    │    │\n└────┴────┘",
    "يقرأ": "📖\n    ┌─┐\n    │○│\n┌───┘ └───┐\n│    █    │\n│    │    │\n└────┴────┘",
    "يأكل": "🍎\n    ┌─┐\n    │○│\n┌───┘ └───┐\n│    █    │\n│    ○    │\n└────┴────┘",
    "ينام": "😴\n    ┌─┐\n    │○│\n┌───┘ └───┐\n│    █    │\n│    Z    │\n└────┴────┘",
}

# كلمات البحث الإضافية (مرادفات)
SYNONYMS = {
    "ولد": ["ولد", "صبي", "طفل", "وليد"],
    "بنت": ["بنت", "فتاة", "طفلة"],
    "قط": ["قط", "قطة", "بس", "هر"],
    "كلب": ["كلب", "جرو", "كلبة"],
    "وردة": ["وردة", "زهرة", "ورد"],
    "شجرة": ["شجرة", "شجر", "نخلة"],
    "قلب": ["قلب", "حب"],
    "سيارة": ["سيارة", "عربية", "كيا"],
    "منزل": ["منزل", "بيت", "دار"],
}

def find_art(word):
    """البحث عن رسمة نصية للكلمة المطلوبة"""
    word = word.lower().strip()
    
    # البحث المباشر
    if word in ASCII_ARTS:
        return ASCII_ARTS[word]
    
    # البحث في المرادفات
    for key, synonyms in SYNONYMS.items():
        if word in synonyms:
            return ASCII_ARTS[key]
    
    return None

# ========== أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user = get_user(user_id)
    
    if len(message.text.split()) > 1:
        ref = message.text.split()[1]
        if ref.isdigit() and int(ref) != user_id:
            if add_referral(int(ref), user_id):
                bot.send_message(user_id, "✅ تم تفعيل الإحالة! +3 نقاط للداعم.")
                bot.send_message(int(ref), "🎉 مستخدم جديد سجل عبر رابطك! +3 نقاط.")
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎨 رسم", callback_data="new_draw"),
        InlineKeyboardButton("🎁 مشاركة الرابط", callback_data="share_link"),
        InlineKeyboardButton("📋 قائمة الرسومات", callback_data="list_arts")
    )
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin_panel"))
    
    bot.send_message(user_id,
        f"🎨 *بوت الرسم بالنصوص*\n\n"
        f"⭐ رصيدك: {user['points']} نقطة\n"
        f"• كل رسمة تستهلك نقطة واحدة\n"
        f"• احصل على نقاط مجانية عبر مشاركة الرابط (كل مشاركة = 3 نقاط)\n\n"
        f"📝 *الكلمات المدعومة:*\n"
        f"ولد، بنت، قط، كلب، وردة، شجرة، قلب، سيارة، منزل، قمر، شمس، نجمة، سمكة، طائر، فراشة، وغيرها\n\n"
        f"🔗 رابط إحالتك:\nhttps://t.me/{bot.get_me().username}?start={user_id}\n\n"
        f"📌 @zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "share_link")
def share_link(call):
    user_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, f"🎁 رابط إحالتك:\nhttps://t.me/{bot.get_me().username}?start={user_id}\n\nكل مشاركة = 3 نقاط!")

@bot.callback_query_handler(func=lambda call: call.data == "list_arts")
def list_arts(call):
    user_id = call.message.chat.id
    arts_list = list(ASCII_ARTS.keys())
    text = "📋 *قائمة الرسومات المتوفرة:*\n\n"
    for i, art in enumerate(arts_list):
        text += f"• {art}\n"
        if (i + 1) % 20 == 0:
            text += "\n"
    bot.send_message(user_id, text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "new_draw")
def new_draw(call):
    user_id = call.message.chat.id
    user = get_user(user_id)
    if user["points"] < 1:
        bot.answer_callback_query(call.id, f"⚠️ ليس لديك نقاط كافية! رصيدك: {user['points']} نقطة\nشارك الرابط لتحصل على نقاط!", show_alert=True)
        return
    
    bot.edit_message_text("🎨 *أرسل الكلمة التي تريد رسمها*\nمثال: ولد، بنت، قط، وردة، شجرة، قلب، سيارة", user_id, call.message.message_id, parse_mode="Markdown")
    bot.register_next_step_handler(call.message, process_draw)

def process_draw(message):
    user_id = message.chat.id
    word = message.text.strip()
    
    if len(word) < 2:
        bot.reply_to(message, "❌ الكلمة قصيرة جداً")
        return
    
    # استهلاك نقطة
    update_points(user_id, -1)
    
    # البحث عن الرسمة
    art = find_art(word)
    
    if art:
        new_user = get_user(user_id)
        bot.send_message(user_id, f"🎨 *رسمة: {word}*\n```\n{art}\n```\n⭐ النقاط المتبقية: {new_user['points']}", parse_mode="Markdown")
    else:
        # اقتراح كلمات مشابهة
        suggestions = []
        for key in ASCII_ARTS.keys():
            if word in key or key in word:
                suggestions.append(key)
        
        if suggestions:
            suggest_text = "\n".join([f"• {s}" for s in suggestions[:5]])
            bot.send_message(user_id, f"❌ لا توجد رسمة لـ '{word}'\n\n📝 هل تقصد:\n{suggest_text}\n\nلرؤية جميع الرسومات المتوفرة، استخدم /start ثم اضغط '📋 قائمة الرسومات'")
        else:
            bot.send_message(user_id, f"❌ لا توجد رسمة لـ '{word}'\n\nلرؤية جميع الرسومات المتوفرة، استخدم /start ثم اضغط '📋 قائمة الرسومات'")
        
        update_points(user_id, 1)

# ========== لوحة تحكم المالك ==========
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 غير مصرح", True)
        return
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ إضافة نقاط", callback_data="admin_add_points"),
        InlineKeyboardButton("➖ خصم نقاط", callback_data="admin_remove_points"),
        InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats"),
        InlineKeyboardButton("📢 إذاعة", callback_data="admin_broadcast")
    )
    bot.send_message(OWNER_ID, "🔧 لوحة تحكم المالك", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_points")
def admin_add_points(call):
    if call.message.chat.id != OWNER_ID:
        return
    msg = bot.send_message(OWNER_ID, "أرسل معرف المستخدم وعدد النقاط (مثال: 123456789 5):")
    bot.register_next_step_handler(msg, add_points_step)

def add_points_step(message):
    try:
        uid, pts = map(int, message.text.split())
        update_points(uid, pts)
        bot.send_message(OWNER_ID, f"✅ تم إضافة {pts} نقطة للمستخدم {uid}")
    except:
        bot.send_message(OWNER_ID, "❌ صيغة غير صحيحة. أرسل: user_id points")

@bot.callback_query_handler(func=lambda call: call.data == "admin_remove_points")
def admin_remove_points(call):
    if call.message.chat.id != OWNER_ID:
        return
    msg = bot.send_message(OWNER_ID, "أرسل معرف المستخدم وعدد النقاط (مثال: 123456789 3):")
    bot.register_next_step_handler(msg, remove_points_step)

def remove_points_step(message):
    try:
        uid, pts = map(int, message.text.split())
        update_points(uid, -pts)
        bot.send_message(OWNER_ID, f"✅ تم خصم {pts} نقطة من المستخدم {uid}")
    except:
        bot.send_message(OWNER_ID, "❌ صيغة غير صحيحة")

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    if call.message.chat.id != OWNER_ID:
        return
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(points) FROM users")
    points = c.fetchone()[0] or 0
    bot.send_message(OWNER_ID, f"📊 *إحصائيات البوت*\n\n👥 المستخدمون: {users}\n⭐ مجموع النقاط: {points}", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 غير مصرح", True)
        return
    msg = bot.send_message(OWNER_ID, "📢 أرسل الرسالة التي تريد إذاعتها:")
    bot.register_next_step_handler(msg, send_broadcast)

def send_broadcast(message):
    broadcast_text = message.text
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    success = 0
    for (uid,) in users:
        try:
            bot.send_message(uid, f"📢 *إذاعة من المالك*\n\n{broadcast_text}\n\n✨ @zakros_probot ✨", parse_mode="Markdown")
            success += 1
        except:
            pass
        time.sleep(0.05)
    bot.send_message(OWNER_ID, f"✅ تم إرسال الإذاعة إلى {success} مستخدم.")

if __name__ == "__main__":
    print("✅ بوت الرسم بالنصوص يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
