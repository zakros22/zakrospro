import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== قاعدة البيانات ==========
import sqlite3
conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 2
)''')
c.execute('''CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT,
    file_id TEXT
)''')
conn.commit()

def get_user(user_id):
    c.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, points) VALUES (?,?)", (user_id, 2))
        conn.commit()
        return 2
    return row[0]

def update_points(user_id, delta):
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (delta, user_id))
    conn.commit()

def add_image(keyword, file_id):
    c.execute("INSERT INTO images (keyword, file_id) VALUES (?,?)", (keyword, file_id))
    conn.commit()

def get_all_images():
    c.execute("SELECT keyword, file_id FROM images")
    return c.fetchall()

def analyze_text(text):
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    parts = []
    current = []
    for sent in sentences:
        current.append(sent)
        if len(current) >= 3:
            parts.append(" ".join(current))
            current = []
    if current:
        parts.append(" ".join(current))
    return parts, len(sentences)

user_data = {}

# ========== أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    points = get_user(user_id)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📚 تحليل نص", callback_data="analyze"),
        InlineKeyboardButton("📸 إضافة صورة", callback_data="add_image"),
        InlineKeyboardButton("🖼️ قائمة الصور", callback_data="list_images")
    )
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin"))
    
    bot.send_message(user_id,
        f"بوت تحليل المحاضرات\n\n"
        f"رصيدك: {points} نقطة\n"
        f"كل تحليل = 1 نقطة\n\n"
        f"@zakros_probot",
        reply_markup=markup)

# ========== تحليل النص ==========
@bot.callback_query_handler(func=lambda call: call.data == "analyze")
def analyze_start(call):
    user_id = call.message.chat.id
    points = get_user(user_id)
    if points < 1:
        bot.answer_callback_query(call.id, "ليس لديك نقاط كافية!", True)
        return
    
    user_data[user_id] = {"step": "waiting_text"}
    bot.edit_message_text("أرسل النص الذي تريد تحليله", user_id, call.message.message_id)

@bot.message_handler(func=lambda m: m.chat.id in user_data and user_data.get(m.chat.id, {}).get("step") == "waiting_text")
def handle_text(message):
    user_id = message.chat.id
    text = message.text.strip()
    
    if len(text) < 20:
        bot.reply_to(message, "النص قصير جداً (يحتاج 20 حرفاً)")
        return
    
    update_points(user_id, -1)
    
    parts, sentences_count = analyze_text(text)
    new_points = get_user(user_id)
    
    result = f"تم تحليل النص\n\n"
    result += f"عدد الجمل: {sentences_count}\n"
    result += f"عدد الأقسام: {len(parts)}\n"
    result += f"النقاط المتبقية: {new_points}\n\n"
    result += f"الأقسام:\n"
    
    for i, part in enumerate(parts):
        result += f"\n{i+1}. {part[:100]}..."
    
    bot.send_message(user_id, result)
    del user_data[user_id]

# ========== إضافة الصور (للمالك فقط) ==========
@bot.callback_query_handler(func=lambda call: call.data == "add_image")
def add_image_start(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "فقط المالك يمكنه إضافة صور", True)
        return
    
    user_data[call.message.chat.id] = {"step": "waiting_keyword"}
    bot.edit_message_text("أرسل الكلمة المفتاحية لهذه الصورة\nمثال: قلب, شجرة, ولد", call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda m: m.chat.id in user_data and user_data.get(m.chat.id, {}).get("step") == "waiting_keyword")
def get_keyword(message):
    user_id = message.chat.id
    keyword = message.text.strip()
    user_data[user_id]["keyword"] = keyword
    user_data[user_id]["step"] = "waiting_image"
    bot.send_message(user_id, "أرسل الصورة الآن")

@bot.message_handler(content_types=['photo'])
def handle_image(message):
    user_id = message.chat.id
    data = user_data.get(user_id)
    
    if not data or data.get("step") != "waiting_image":
        bot.reply_to(message, "ابدأ بـ /start ثم اختر إضافة صورة")
        return
    
    keyword = data["keyword"]
    file_id = message.photo[-1].file_id
    
    add_image(keyword, file_id)
    
    bot.reply_to(message, f"تم حفظ الصورة\nالكلمة: {keyword}")
    del user_data[user_id]

@bot.callback_query_handler(func=lambda call: call.data == "list_images")
def list_images(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "فقط المالك يمكنه رؤية الصور", True)
        return
    
    images = get_all_images()
    if not images:
        bot.send_message(call.message.chat.id, "لا توجد صور مضافة بعد")
        return
    
    text = "قائمة الصور:\n\n"
    for keyword, file_id in images:
        text += f"• {keyword}\n"
    
    bot.send_message(call.message.chat.id, text)

# ========== لوحة تحكم المالك ==========
@bot.callback_query_handler(func=lambda call: call.data == "admin")
def admin_panel(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "غير مصرح", True)
        return
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ إضافة نقاط", callback_data="add_pts"))
    markup.add(InlineKeyboardButton("📊 إحصائيات", callback_data="stats"))
    bot.send_message(OWNER_ID, "لوحة تحكم المالك", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_pts")
def add_points(call):
    if call.message.chat.id != OWNER_ID:
        return
    msg = bot.send_message(OWNER_ID, "أرسل: معرف_المستخدم عدد_النقاط\nمثال: 123456789 5")
    bot.register_next_step_handler(msg, add_points_step)

def add_points_step(message):
    try:
        uid, pts = map(int, message.text.split())
        update_points(uid, pts)
        bot.send_message(OWNER_ID, f"تم إضافة {pts} نقطة")
    except:
        bot.send_message(OWNER_ID, "صيغة غير صحيحة")

@bot.callback_query_handler(func=lambda call: call.data == "stats")
def show_stats(call):
    if call.message.chat.id != OWNER_ID:
        return
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(points) FROM users")
    points = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM images")
    images = c.fetchone()[0]
    bot.send_message(OWNER_ID, f"إحصائيات\n\nالمستخدمون: {users}\nالنقاط: {points}\nالصور: {images}")

if __name__ == "__main__":
    print("Bot is running...")
    bot.remove_webhook()
    bot.infinity_polling()
