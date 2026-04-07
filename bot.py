import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import tempfile
import re

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== 1. قاعدة البيانات ==========
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

# ========== 2. تحليل المحاضرة ==========
def analyze_lecture(text):
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    parts = []
    current = ""
    for sent in sentences:
        if len(current) + len(sent) + 2 <= 200:
            current += sent + " "
        else:
            if current:
                parts.append(current.strip())
            current = sent + " "
    if current:
        parts.append(current.strip())
    
    if not parts:
        parts = [text[:200]]
    
    return parts

# ========== 3. تخزين مؤقت ==========
user_data = {}

# ========== 4. أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    points = get_user(user_id)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎬 تحليل محاضرة", callback_data="convert"),
        InlineKeyboardButton("📸 إضافة صورة", callback_data="add_image"),
        InlineKeyboardButton("🖼️ قائمة الصور", callback_data="list_images")
    )
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin"))
    
    bot.send_message(user_id,
        f"🎬 *بوت تحليل المحاضرات*\n\n"
        f"⭐ رصيدك: {points} نقطة\n"
        f"• كل تحليل = 1 نقطة\n\n"
        f"📸 *كيف يعمل؟*\n"
        f"1. أضف صوراً مع كلمات مفتاحية\n"
        f"2. أرسل محاضرة (نص)\n"
        f"3. سأقسم المحاضرة وأرسل الشرح\n\n"
        f"@zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

# ========== 5. إضافة الصور ==========
@bot.callback_query_handler(func=lambda call: call.data == "add_image")
def add_image_start(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 فقط المالك يمكنه إضافة صور", True)
        return
    
    user_data[call.message.chat.id] = {"step": "waiting_keyword"}
    bot.edit_message_text("📝 *أرسل الكلمة المفتاحية لهذه الصورة*\nمثال: قلب، شجرة، ولد", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.id in user_data and user_data.get(m.chat.id, {}).get("step") == "waiting_keyword")
def get_keyword(message):
    user_id = message.chat.id
    keyword = message.text.strip()
    user_data[user_id]["keyword"] = keyword
    user_data[user_id]["step"] = "waiting_image"
    bot.send_message(user_id, "🖼️ *أرسل الصورة الآن*", parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_image(message):
    user_id = message.chat.id
    data = user_data.get(user_id)
    
    if not data or data.get("step") != "waiting_image":
        bot.reply_to(message, "❌ ابدأ بـ /start ثم اختر 'إضافة صورة'")
        return
    
    keyword = data["keyword"]
    file_id = message.photo[-1].file_id
    
    add_image(keyword, file_id)
    
    bot.reply_to(message, f"✅ تم حفظ الصورة\n📌 الكلمة: {keyword}")
    del user_data[user_id]

@bot.callback_query_handler(func=lambda call: call.data == "list_images")
def list_images(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 فقط المالك يمكنه رؤية الصور", True)
        return
    
    images = get_all_images()
    if not images:
        bot.send_message(call.message.chat.id, "📭 لا توجد صور مضافة بعد")
        return
    
    text = "🖼️ *قائمة الصور:*\n\n"
    for keyword, file_id in images:
        text += f"• {keyword}\n"
    
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

# ========== 6. تحليل المحاضرة ==========
@bot.callback_query_handler(func=lambda call: call.data == "convert")
def convert_start(call):
    user_id = call.message.chat.id
    points = get_user(user_id)
    if points < 1:
        bot.answer_callback_query(call.id, "ليس لديك نقاط كافية!", True)
        return
    
    user_data[user_id] = {"step": "waiting_content"}
    bot.edit_message_text("📝 *أرسل المحاضرة (نصاً)*", user_id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.id in user_data and user_data.get(m.chat.id, {}).get("step") == "waiting_content")
def handle_lecture(message):
    user_id = message.chat.id
    data = user_data.get(user_id)
    
    if not data or data.get("step") != "waiting_content":
        return
    
    text = message.text.strip()
    
    if not text or len(text) < 50:
        bot.reply_to(message, "❌ المحتوى قصير جداً (يحتاج 50 حرفاً)")
        return
    
    # استهلاك نقطة
    update_points(user_id, -1)
    
    status = bot.reply_to(message, "🎬 جاري تحليل المحاضرة...")
    
    try:
        # تحليل المحاضرة
        parts = analyze_lecture(text)
        
        new_points = get_user(user_id)
        
        # إرسال الشرح
        explanation = f"✅ *تم تحليل المحاضرة*\n\n"
        explanation += f"📊 عدد الأقسام: {len(parts)}\n"
        explanation += f"⭐ النقاط المتبقية: {new_points}\n\n"
        explanation += f"📝 *الأقسام:*\n"
        
        for i, part in enumerate(parts):
            explanation += f"\n{i+1}. {part}\n"
        
        # إرسال الصور المناسبة لكل قسم (اختياري)
        bot.send_message(user_id, explanation, parse_mode="Markdown")
        
        # إرسال الصور المرتبطة بالكلمات المفتاحية
        images = get_all_images()
        if images:
            bot.send_message(user_id, "🖼️ *الصور المرتبطة:*", parse_mode="Markdown")
            for keyword, file_id in images:
                if keyword in text.lower():
                    try:
                        bot.send_photo(user_id, file_id, caption=f"📌 صورة: {keyword}")
                    except:
                        pass
        
        bot.delete_message(user_id, status.message_id)
        del user_data[user_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", user_id, status.message_id)
        update_points(user_id, 1)

# ========== 7. لوحة تحكم المالك ==========
@bot.callback_query_handler(func=lambda call: call.data == "admin")
def admin_panel(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "غير مصرح", True)
        return
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ إضافة نقاط", callback_data="add_pts"))
    markup.add(InlineKeyboardButton("📊 إحصائيات", callback_data="stats"))
    bot.send_message(OWNER_ID, "🔧 لوحة التحكم", reply_markup=markup)

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
        bot.send_message(OWNER_ID, f"✅ تم إضافة {pts} نقطة")
    except:
        bot.send_message(OWNER_ID, "❌ صيغة غير صحيحة")

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
    bot.send_message(OWNER_ID, f"📊 إحصائيات\n👥 المستخدمون: {users}\n⭐ النقاط: {points}\n🖼️ الصور: {images}")

if __name__ == "__main__":
    print("✅ البوت يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
