import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
from art import text2art, art
import random

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== قاعدة البيانات ==========
conn = sqlite3.connect("art_bot.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 3,
    total_uses INTEGER DEFAULT 0
)''')
conn.commit()

def get_user(user_id):
    c.execute("SELECT points, total_uses FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, points, total_uses) VALUES (?,?,?)", (user_id, 3, 0))
        conn.commit()
        return {"points": 3, "total_uses": 0}
    return {"points": row[0], "total_uses": row[1]}

def update_points(user_id, delta):
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (delta, user_id))
    conn.commit()

def add_use(user_id):
    c.execute("UPDATE users SET total_uses = total_uses + 1 WHERE user_id=?", (user_id,))
    conn.commit()

# ========== أنماط الرسم ==========
FONTS = [
    'block', 'bubble', 'digital', '3d', '3d_diagonal', '4x4', '5lineoblique',
    'acrobatic', 'alligator', 'alligator2', 'alphabet', 'arrows', 'ascii',
    'ascii_new_roman', 'avatar', 'banner', 'banner3-D', 'banner3', 'banner4',
    'barbwire', 'basic', 'bell', 'big', 'bigchief', 'binary', 'block',
    'bubble', 'bulbhead', 'caligraphy', 'cards', 'catwalk', 'chunky',
    'coinstak', 'colossal', 'computer', 'contessa', 'contrast', 'cosmic',
    'crawford', 'cricket', 'cursive', 'cyberlarge', 'cybermedium', 'cybersmall',
    'diamond', 'digital', 'doh', 'doom', 'dotmatrix', 'drpepper', 'eftichess',
    'eftifont', 'eftipiti', 'eftiroboto', 'eftitalic', 'eftiwall', 'epic',
    'fender', 'fire', 'fourtops', 'fuzzy', 'georgia11', 'ghost', 'gothic',
    'graffiti', 'happy', 'harry_p', 'heart', 'henry3d', 'hex', 'hollywood',
    'horizontal', 'ivrit', 'jazmine', 'jerusalem', 'katakana', 'kawii',
    'keyboard', 'krak', 'larry3d', 'lcd', 'lean', 'letters', 'linux', 'lockergnome',
    'madrid', 'marquee', 'maxfour', 'merlin1', 'merlin2', 'mike', 'mini',
    'mirror', 'mnemonic', 'morse', 'moscow', 'nancyj', 'nipples', 'nscript',
    'ntgreek', 'o8', 'octal', 'ogre', 'oldbanner', 'os2', 'pawp', 'peaks',
    'pebbles', 'pepper', 'poison', 'puffy', 'pyramid', 'rectangles', 'relief',
    'relief2', 'rev', 'rnd', 'roman', 'rot13', 'rotated', 'rounded', 'rowancap',
    'rozzo', 'runic', 'santa', 'sblood', 'script', 'serifcap', 'shadow',
    'shimrod', 'short', 'slant', 'slide', 'slscript', 'small', 'smisome1',
    'smkeyboard', 'smscript', 'smshadow', 'smslant', 'smtengwar', 'speed',
    'stampatello', 'standard', 'starwars', 'stellar', 'stop', 'straight',
    'stretched', 'sub-zero', 'swampland', 'swinging', 'tanja', 'tengwar',
    'term', 'thick', 'thin', 'threepoint', 'ticks', 'ticksslant', 'tiles',
    'times', 'tombstone', 'trek', 'tsalagi', 'twisted', 'univers', 'usaflag',
    'utopia', 'varsity', 'wavy', 'weird', 'wetletter', 'whimsy', 'wikipedia'
]

# ========== أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user = get_user(user_id)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎨 رسم نصي", callback_data="new_art"),
        InlineKeyboardButton("🎁 مشاركة الرابط", callback_data="share_link")
    )
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin_panel"))
    
    bot.send_message(user_id,
        f"🎨 *بوت الرسم النصي (ASCII Art)*\n\n"
        f"⭐ رصيدك: {user['points']} نقطة\n"
        f"• كل رسمة تستهلك نقطة واحدة\n"
        f"• يمكنك الحصول على نقاط مجانية عبر مشاركة الرابط (كل مشاركة = نقطة)\n\n"
        f"🔗 رابط إحالتك:\nhttps://t.me/{bot.get_me().username}?start={user_id}\n\n"
        f"📌 @zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "share_link")
def share_link(call):
    user_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, f"🎁 رابط إحالتك:\nhttps://t.me/{bot.get_me().username}?start={user_id}\n\nكل مشاركة = نقطة إضافية!")

@bot.callback_query_handler(func=lambda call: call.data == "new_art")
def new_art(call):
    user_id = call.message.chat.id
    user = get_user(user_id)
    if user["points"] < 1:
        bot.answer_callback_query(call.id, f"⚠️ ليس لديك نقاط كافية! رصيدك: {user['points']} نقطة\nشارك الرابط لتحصل على نقاط!", show_alert=True)
        return
    
    bot.edit_message_text("🎨 *أرسل النص الذي تريد تحويله إلى رسم نصي*\nمثال: ولد يلعب في الحديقة", user_id, call.message.message_id, parse_mode="Markdown")
    bot.register_next_step_handler(call.message, process_text)

def process_text(message):
    user_id = message.chat.id
    text = message.text.strip()
    
    if len(text) < 3:
        bot.reply_to(message, "❌ النص قصير جداً (يحتاج 3 أحرف على الأقل)")
        return
    if len(text) > 50:
        bot.reply_to(message, "❌ النص طويل جداً (الحد الأقصى 50 حرف)")
        return
    
    # استهلاك نقطة
    update_points(user_id, -1)
    add_use(user_id)
    
    # إرسال رسالة المعالجة
    status = bot.reply_to(message, "🎨 جاري إنشاء الرسم النصي...")
    
    try:
        # اختيار خط عشوائي
        font = random.choice(FONTS)
        
        # إنشاء الرسم النصي
        ascii_art = text2art(text, font=font)
        
        # تنظيف النتيجة
        ascii_art = ascii_art.strip()
        
        # إرسال الرسم
        new_points = get_user(user_id)
        bot.send_message(user_id, f"🎨 *الرسم النصي لـ:* `{text}`\n```\n{ascii_art}\n```\n✨ الخط المستخدم: `{font}`\n⭐ النقاط المتبقية: {new_points['points']}", parse_mode="Markdown")
        
        bot.delete_message(user_id, status.message_id)
        
    except Exception as e:
        # محاولة باستخدام خط بسيط
        try:
            ascii_art = text2art(text, font='block')
            new_points = get_user(user_id)
            bot.send_message(user_id, f"🎨 *الرسم النصي لـ:* `{text}`\n```\n{ascii_art}\n```\n⭐ النقاط المتبقية: {new_points['points']}", parse_mode="Markdown")
            bot.delete_message(user_id, status.message_id)
        except:
            bot.edit_message_text("❌ فشل إنشاء الرسم النصي. حاول بنص أبسط.", user_id, status.message_id)
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
    c.execute("SELECT SUM(total_uses) FROM users")
    uses = c.fetchone()[0] or 0
    bot.send_message(OWNER_ID, f"📊 *إحصائيات البوت*\n\n👥 المستخدمون: {users}\n⭐ مجموع النقاط: {points}\n🎨 عدد الرسومات: {uses}", parse_mode="Markdown")

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
    print("✅ بوت الرسم النصي يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
