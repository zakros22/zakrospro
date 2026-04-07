import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import tempfile
import re
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, concatenate_videoclips
import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== قاعدة البيانات ==========
conn = sqlite3.connect("video.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT,
    file_id TEXT
)''')
conn.commit()

def add_image(keyword, file_id):
    c.execute("INSERT INTO images (keyword, file_id) VALUES (?,?)", (keyword, file_id))
    conn.commit()

def get_image_by_keyword(text):
    words = text.lower().split()
    c.execute("SELECT keyword, file_id FROM images")
    images = c.fetchall()
    for keyword, file_id in images:
        if keyword.lower() in text.lower() or keyword.lower() in words:
            return file_id
    return None

def get_all_images():
    c.execute("SELECT keyword, file_id FROM images")
    return c.fetchall()

# ========== تحليل المحاضرة ==========
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

# ========== إنشاء صورة نصية (إذا لم توجد صورة) ==========
def create_text_image(text, output_path, width=1280, height=720):
    try:
        img = Image.new('RGB', (width, height), color=(30, 40, 80))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 35)
        except:
            font = ImageFont.load_default()
        
        words = text.split()
        lines = []
        line = ""
        for w in words:
            if len(line + " " + w) <= 30:
                line += " " + w if line else w
            else:
                lines.append(line)
                line = w
        if line:
            lines.append(line)
        
        y = 250
        for l in lines:
            draw.text((100, y), l, fill=(255, 255, 255), font=font)
            y += 60
        
        img.save(output_path)
        return True
    except:
        return False

# ========== إنشاء فيديو ==========
def create_video(parts, output_path, duration_per_slide=3):
    try:
        clips = []
        for part in parts:
            file_id = get_image_by_keyword(part)
            
            if file_id:
                # تحميل الصورة من تلغرام
                file_info = bot.get_file(file_id)
                downloaded = bot.download_file(file_info.file_path)
                img_path = tempfile.mktemp(suffix='.jpg')
                with open(img_path, 'wb') as f:
                    f.write(downloaded)
            else:
                # إنشاء صورة نصية
                img_path = tempfile.mktemp(suffix='.png')
                if not create_text_image(part, img_path):
                    continue
            
            clip = ImageClip(img_path).set_duration(duration_per_slide).resize(height=720)
            clips.append(clip)
            
            # تنظيف
            if os.path.exists(img_path):
                os.unlink(img_path)
        
        if not clips:
            return False
        
        video = concatenate_videoclips(clips, method="compose")
        video.write_videofile(output_path, fps=24, codec='libx264', threads=2, logger=None)
        video.close()
        return True
    except Exception as e:
        print(f"Video error: {e}")
        return False

# ========== تخزين مؤقت ==========
user_data = {}

# ========== أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎬 تحويل محاضرة", callback_data="convert"),
        InlineKeyboardButton("📸 إضافة صورة", callback_data="add_image")
    )
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin"))
    
    bot.send_message(user_id,
        f"🎬 *بوت تحويل المحاضرات إلى فيديو*\n\n"
        f"• أضف صوراً مع كلمات مفتاحية\n"
        f"• أرسل محاضرة وسأقوم بإنشاء فيديو\n"
        f"• سأعرض الصورة المناسبة لكل قسم\n\n"
        f"@zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

# ========== إضافة الصور ==========
@bot.callback_query_handler(func=lambda call: call.data == "add_image")
def add_image_start(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "🔒 فقط المالك يمكنه إضافة صور", True)
        return
    
    user_data[call.message.chat.id] = {"step": "waiting_keyword"}
    bot.edit_message_text("📝 *أرسل الكلمة المفتاحية لهذه الصورة*\nمثال: قلب, شجرة, ولد", call.message.chat.id, call.message.message_id, parse_mode="Markdown")

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

# ========== تحويل المحاضرة إلى فيديو ==========
@bot.callback_query_handler(func=lambda call: call.data == "convert")
def convert_start(call):
    user_id = call.message.chat.id
    user_data[user_id] = {"step": "waiting_text"}
    bot.edit_message_text("📝 *أرسل المحاضرة (نصاً)*", user_id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.id in user_data and user_data.get(m.chat.id, {}).get("step") == "waiting_text")
def handle_lecture(message):
    user_id = message.chat.id
    text = message.text.strip()
    
    if len(text) < 50:
        bot.reply_to(message, "❌ النص قصير جداً (يحتاج 50 حرفاً)")
        return
    
    status = bot.reply_to(message, "🎬 جاري تحليل المحاضرة وإنشاء الفيديو... (قد يستغرق دقيقة)")
    
    try:
        # تحليل المحاضرة
        parts = analyze_lecture(text)
        
        if not parts:
            bot.edit_message_text("❌ لا يوجد محتوى صالح", user_id, status.message_id)
            return
        
        bot.edit_message_text(f"📊 تم التقسيم إلى {len(parts)} أقسام\n🎬 جاري إنشاء الفيديو...", user_id, status.message_id)
        
        # إنشاء الفيديو
        video_path = tempfile.mktemp(suffix='.mp4')
        
        if create_video(parts, video_path, duration_per_slide=3):
            # إرسال الفيديو
            with open(video_path, 'rb') as f:
                bot.send_video(user_id, f, caption=f"✅ تم إنشاء الفيديو\n📊 عدد الأقسام: {len(parts)}\n\n@zakros_probot", supports_streaming=True)
            os.unlink(video_path)
            
            # إرسال الشرح النصي
            explanation = f"📝 *شرح المحاضرة*\n\n"
            for i, part in enumerate(parts):
                explanation += f"{i+1}. {part}\n\n"
            bot.send_message(user_id, explanation, parse_mode="Markdown")
        else:
            bot.edit_message_text("❌ فشل إنشاء الفيديو", user_id, status.message_id)
        
        bot.delete_message(user_id, status.message_id)
        del user_data[user_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", user_id, status.message_id)

# ========== لوحة تحكم المالك ==========
@bot.callback_query_handler(func=lambda call: call.data == "admin")
def admin_panel(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "غير مصرح", True)
        return
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🖼️ قائمة الصور", callback_data="list_images"))
    bot.send_message(OWNER_ID, "🔧 لوحة التحكم", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "list_images")
def list_images(call):
    images = get_all_images()
    if not images:
        bot.send_message(call.message.chat.id, "📭 لا توجد صور مضافة بعد")
        return
    
    text = "🖼️ *قائمة الصور:*\n\n"
    for keyword, file_id in images:
        text += f"• {keyword}\n"
    
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

if __name__ == "__main__":
    print("✅ بوت تحويل المحاضرات إلى فيديو يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
