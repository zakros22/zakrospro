import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import tempfile
import re
import requests
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, concatenate_videoclips, CompositeVideoClip, TextClip

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== 1. قاعدة البيانات ==========
conn = sqlite3.connect("video.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT,
    url TEXT
)''')
conn.commit()

# ========== 2. إضافة صور تجريبية ==========
def add_sample_images():
    images = [
        ("قلب", "https://png.pngtree.com/png-vector/20240830/ourlarge/pngtree-cartoon-of-broken-heart-png-image_13744684.png"),
        ("شجرة", "https://png.pngtree.com/png-vector/20240830/ourlarge/pngtree-cartoon-tree-png-image_13747696.png"),
        ("ولد", "https://png.pngtree.com/png-vector/20240830/ourlarge/pngtree-a-little-boy-png-image_13747694.png")
    ]
    
    for keyword, url in images:
        c.execute("SELECT * FROM images WHERE keyword=?", (keyword,))
        if not c.fetchone():
            c.execute("INSERT INTO images (keyword, url) VALUES (?,?)", (keyword, url))
    conn.commit()

add_sample_images()

def get_image_url(keyword):
    c.execute("SELECT url FROM images WHERE keyword=?", (keyword,))
    row = c.fetchone()
    return row[0] if row else None

def download_image(url, output_path):
    try:
        response = requests.get(url, timeout=30)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        return True
    except:
        return False

# ========== 3. إنشاء فيديو من الصور مع نص ==========
def create_video_with_text(parts, output_path):
    try:
        clips = []
        for part in parts:
            # تحميل الصورة
            img_url = get_image_url(part["keyword"])
            if img_url:
                img_path = tempfile.mktemp(suffix='.jpg')
                download_image(img_url, img_path)
            else:
                # صورة افتراضية إذا لم توجد
                img_path = create_fallback_image(part["text"])
            
            # إنشاء مقطع من الصورة
            clip = ImageClip(img_path).set_duration(part["duration"]).resize(height=720)
            
            # إضافة النص على الصورة
            txt_clip = TextClip(part["text"], fontsize=40, color='white', font='Arial', size=(800, 100))
            txt_clip = txt_clip.set_position(('center', 'bottom')).set_duration(part["duration"])
            
            # دمج الصورة والنص
            composite = CompositeVideoClip([clip, txt_clip])
            clips.append(composite)
            
            # تنظيف
            if os.path.exists(img_path):
                os.unlink(img_path)
        
        # دمج جميع المقاطع
        video = concatenate_videoclips(clips, method="compose")
        video.write_videofile(output_path, fps=24, codec='libx264', threads=2)
        video.close()
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def create_fallback_image(text):
    img_path = tempfile.mktemp(suffix='.png')
    img = Image.new('RGB', (1280, 720), color=(30, 40, 80))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        font = ImageFont.load_default()
    
    # تقسيم النص
    lines = []
    words = text.split()
    line = ""
    for w in words:
        if len(line + " " + w) <= 35:
            line += " " + w if line else w
        else:
            lines.append(line)
            line = w
    if line:
        lines.append(line)
    
    y = 250
    for l in lines:
        draw.text((100, y), l, fill=(255, 255, 255), font=font)
        y += 50
    
    img.save(img_path)
    return img_path

# ========== 4. تحليل المحاضرة ==========
def analyze_lecture(text, duration_per_slide=3):
    """تقسيم المحاضرة إلى أقسام وتحديد الكلمات المفتاحية"""
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    parts = []
    
    for sent in sentences:
        if len(sent.strip()) < 10:
            continue
        
        # تحديد الكلمة المفتاحية
        keyword = None
        if "قلب" in sent:
            keyword = "قلب"
        elif "شجرة" in sent:
            keyword = "شجرة"
        elif "ولد" in sent:
            keyword = "ولد"
        
        parts.append({
            "text": sent.strip(),
            "keyword": keyword,
            "duration": duration_per_slide
        })
    
    return parts

# ========== 5. أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎬 تحويل محاضرة", callback_data="convert"))
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin"))
    
    bot.send_message(user_id,
        f"🎬 *بوت تحويل المحاضرات إلى فيديو (تجريبي)*\n\n"
        f"📸 *الصور المتوفرة:*\n"
        f"• قلب ❤️ - عندما يتحدث النص عن القلب\n"
        f"• شجرة 🌳 - عندما يتحدث النص عن الشجرة\n"
        f"• ولد 👦 - عندما يتحدث النص عن الولد\n\n"
        f"📝 أرسل محاضرة وسأقوم بعرض الصور المناسبة\n\n"
        f"@zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "convert")
def convert_start(call):
    user_id = call.message.chat.id
    bot.edit_message_text("📝 *أرسل المحاضرة (نصاً)*\n\nمثال:\nالولد كان يلعب في الحديقة. رأى شجرة كبيرة. قلبه فرح.", user_id, call.message.message_id, parse_mode="Markdown")
    bot.register_next_step_handler(call.message, process_lecture)

def process_lecture(message):
    user_id = message.chat.id
    text = message.text.strip()
    
    if len(text) < 20:
        bot.reply_to(message, "❌ النص قصير جداً (يحتاج 20 حرفاً)")
        return
    
    status = bot.reply_to(message, "🎬 جاري إنشاء الفيديو...")
    
    try:
        # تحليل المحاضرة
        parts = analyze_lecture(text, duration_per_slide=3)
        
        if not parts:
            bot.edit_message_text("❌ لا يوجد محتوى صالح للتحويل", user_id, status.message_id)
            return
        
        # إنشاء الفيديو
        video_path = tempfile.mktemp(suffix='.mp4')
        
        if create_video_with_text(parts, video_path):
            with open(video_path, 'rb') as f:
                bot.send_video(user_id, f, caption=f"✅ تم إنشاء الفيديو\n\n📝 *نص المحاضرة:*\n{text[:500]}\n\n@zakros_probot", supports_streaming=True, parse_mode="Markdown")
            os.unlink(video_path)
        else:
            bot.edit_message_text("❌ فشل إنشاء الفيديو", user_id, status.message_id)
        
        bot.delete_message(user_id, status.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", user_id, status.message_id)

# ========== 6. لوحة تحكم المالك ==========
@bot.callback_query_handler(func=lambda call: call.data == "admin")
def admin_panel(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "غير مصرح", True)
        return
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📸 إضافة صورة", callback_data="add_image"))
    markup.add(InlineKeyboardButton("🖼️ قائمة الصور", callback_data="list_images"))
    bot.send_message(OWNER_ID, "🔧 لوحة التحكم", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "add_image")
def add_image_start(call):
    user_data[call.message.chat.id] = {"step": "waiting_keyword"}
    bot.edit_message_text("📝 *أرسل الكلمة المفتاحية لهذه الصورة*\nمثال: قلب، شجرة، ولد", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

user_data = {}

@bot.message_handler(func=lambda m: m.chat.id in user_data and user_data[m.chat.id].get("step") == "waiting_keyword")
def get_keyword(message):
    user_id = message.chat.id
    keyword = message.text.strip()
    user_data[user_id]["keyword"] = keyword
    user_data[user_id]["step"] = "waiting_url"
    bot.send_message(user_id, "🔗 *أرسل رابط الصورة*", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.id in user_data and user_data[m.chat.id].get("step") == "waiting_url")
def get_url(message):
    user_id = message.chat.id
    url = message.text.strip()
    keyword = user_data[user_id]["keyword"]
    
    c.execute("INSERT INTO images (keyword, url) VALUES (?,?)", (keyword, url))
    conn.commit()
    
    bot.send_message(user_id, f"✅ تم حفظ الصورة\n📌 الكلمة: {keyword}")
    del user_data[user_id]

@bot.callback_query_handler(func=lambda call: call.data == "list_images")
def list_images(call):
    c.execute("SELECT keyword, url FROM images")
    images = c.fetchall()
    
    if not images:
        bot.send_message(call.message.chat.id, "📭 لا توجد صور")
        return
    
    text = "🖼️ *قائمة الصور:*\n\n"
    for keyword, url in images:
        text += f"• {keyword}\n"
    
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

if __name__ == "__main__":
    print("✅ بوت تحويل المحاضرات إلى فيديو يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
