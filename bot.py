import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import tempfile
import subprocess
import time
from datetime import datetime
from PIL import Image
import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)
OWNER_ID = 7021542402

# ========== قاعدة البيانات ==========
conn = sqlite3.connect("convert.db", check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    points INTEGER DEFAULT 3,
    total_converts INTEGER DEFAULT 0
)''')
conn.commit()

def get_user(user_id):
    c.execute("SELECT points, total_converts FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, points, total_converts) VALUES (?,?,?)", (user_id, 3, 0))
        conn.commit()
        return {"points": 3, "total_converts": 0}
    return {"points": row[0], "total_converts": row[1]}

def update_points(user_id, delta):
    c.execute("UPDATE users SET points = points + ? WHERE user_id=?", (delta, user_id))
    conn.commit()

def add_convert(user_id):
    c.execute("UPDATE users SET total_converts = total_converts + 1 WHERE user_id=?", (user_id,))
    conn.commit()

# ========== أنواع الملفات والتحويلات ==========
CONVERSIONS = {
    "document": {
        "name": "📄 مستندات",
        "formats": {
            "pdf": "PDF",
            "docx": "Word",
            "txt": "نصي"
        },
        "convert": {
            "pdf_docx": ["pdf", "docx"],
            "pdf_txt": ["pdf", "txt"],
            "docx_pdf": ["docx", "pdf"],
            "docx_txt": ["docx", "txt"],
            "txt_pdf": ["txt", "pdf"],
            "txt_docx": ["txt", "docx"]
        }
    },
    "image": {
        "name": "🖼️ صور",
        "formats": {
            "png": "PNG",
            "jpg": "JPG",
            "webp": "WEBP"
        },
        "convert": {
            "png_jpg": ["png", "jpg"],
            "png_webp": ["png", "webp"],
            "jpg_png": ["jpg", "png"],
            "jpg_webp": ["jpg", "webp"],
            "webp_png": ["webp", "png"],
            "webp_jpg": ["webp", "jpg"]
        }
    },
    "audio": {
        "name": "🎵 صوت",
        "formats": {
            "mp3": "MP3",
            "wav": "WAV",
            "ogg": "OGG"
        },
        "convert": {
            "mp3_wav": ["mp3", "wav"],
            "mp3_ogg": ["mp3", "ogg"],
            "wav_mp3": ["wav", "mp3"],
            "wav_ogg": ["wav", "ogg"],
            "ogg_mp3": ["ogg", "mp3"],
            "ogg_wav": ["ogg", "wav"]
        }
    },
    "video": {
        "name": "🎬 فيديو",
        "formats": {
            "mp4": "MP4",
            "avi": "AVI",
            "mov": "MOV"
        },
        "convert": {
            "mp4_avi": ["mp4", "avi"],
            "mp4_mov": ["mp4", "mov"],
            "avi_mp4": ["avi", "mp4"],
            "avi_mov": ["avi", "mov"],
            "mov_mp4": ["mov", "mp4"],
            "mov_avi": ["mov", "avi"]
        }
    }
}

# ========== دوال التحويل ==========
def convert_image(input_path, output_path, target_format):
    """تحويل الصور"""
    try:
        img = Image.open(input_path)
        if target_format == 'jpg':
            rgb_img = img.convert('RGB')
            rgb_img.save(output_path, 'JPEG')
        else:
            img.save(output_path, target_format.upper())
        return True
    except Exception as e:
        print(f"Image conversion error: {e}")
        return False

def convert_audio(input_path, output_path, target_format):
    """تحويل الصوت باستخدام ffmpeg"""
    try:
        cmd = ['ffmpeg', '-i', input_path, '-y', output_path]
        subprocess.run(cmd, capture_output=True, timeout=60)
        return os.path.exists(output_path)
    except:
        return False

def convert_video(input_path, output_path, target_format):
    """تحويل الفيديو باستخدام ffmpeg"""
    try:
        cmd = ['ffmpeg', '-i', input_path, '-y', output_path]
        subprocess.run(cmd, capture_output=True, timeout=120)
        return os.path.exists(output_path)
    except:
        return False

def convert_document(input_path, output_path, source_format, target_format):
    """تحويل المستندات"""
    try:
        if source_format == 'txt' and target_format == 'pdf':
            # تحويل txt إلى pdf
            from fpdf import FPDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", size=12)
            with open(input_path, 'r', encoding='utf-8') as f:
                for line in f:
                    pdf.cell(0, 6, line.encode('latin-1', 'ignore').decode('latin-1'), ln=1)
            pdf.output(output_path)
            return True
        else:
            # للتحويلات الأخرى نستخدم pandoc إذا كان متاحاً
            cmd = ['pandoc', input_path, '-o', output_path]
            subprocess.run(cmd, capture_output=True, timeout=60)
            return os.path.exists(output_path)
    except:
        return False

# ========== تخزين مؤقت ==========
temp_data = {}

# ========== أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user = get_user(user_id)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📄 مستندات", callback_data="type_document"),
        InlineKeyboardButton("🖼️ صور", callback_data="type_image"),
        InlineKeyboardButton("🎵 صوت", callback_data="type_audio"),
        InlineKeyboardButton("🎬 فيديو", callback_data="type_video")
    )
    if user_id == OWNER_ID:
        markup.add(InlineKeyboardButton("🔧 لوحة التحكم", callback_data="admin_panel"))
    
    bot.send_message(user_id,
        f"🔄 *بوت تحويل الملفات*\n\n"
        f"⭐ رصيدك: {user['points']} نقطة\n"
        f"• كل تحويل يستهلك نقطة واحدة\n"
        f"• اختر نوع الملف الذي تريد تحويله\n\n"
        f"📌 @zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("type_"))
def select_type(call):
    user_id = call.message.chat.id
    file_type = call.data.split("_")[1]
    
    temp_data[user_id] = {"type": file_type, "step": "select_conversion"}
    
    conversions = CONVERSIONS[file_type]["convert"]
    markup = InlineKeyboardMarkup(row_width=2)
    
    for key, conv in conversions.items():
        from_fmt = CONVERSIONS[file_type]["formats"][conv[0]]
        to_fmt = CONVERSIONS[file_type]["formats"][conv[1]]
        markup.add(InlineKeyboardButton(f"{from_fmt} → {to_fmt}", callback_data=f"conv_{key}"))
    
    bot.edit_message_text(f"📁 اختر التحويل الذي تريده:\nنوع الملف: {CONVERSIONS[file_type]['name']}", user_id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("conv_"))
def select_conversion(call):
    user_id = call.message.chat.id
    conv_key = call.data.split("_")[1]
    
    file_type = temp_data[user_id]["type"]
    source_fmt = CONVERSIONS[file_type]["convert"][conv_key][0]
    target_fmt = CONVERSIONS[file_type]["convert"][conv_key][1]
    
    temp_data[user_id]["source_fmt"] = source_fmt
    temp_data[user_id]["target_fmt"] = target_fmt
    temp_data[user_id]["step"] = "upload"
    
    source_name = CONVERSIONS[file_type]["formats"][source_fmt]
    target_name = CONVERSIONS[file_type]["formats"][target_fmt]
    
    bot.edit_message_text(f"✅ التحويل: {source_name} → {target_name}\n\n📤 أرسل الملف الذي تريد تحويله", user_id, call.message.message_id)

@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.chat.id
    data = temp_data.get(user_id)
    
    if not data or data.get("step") != "upload":
        bot.reply_to(message, "❌ ابدأ العملية أولاً بـ /start")
        return
    
    user = get_user(user_id)
    if user["points"] < 1:
        bot.reply_to(message, "⚠️ ليس لديك نقاط كافية! رصيدك: {user['points']} نقطة")
        return
    
    file_name = message.document.file_name
    file_ext = os.path.splitext(file_name)[1][1:].lower()
    
    if file_ext != data["source_fmt"]:
        bot.reply_to(message, f"❌ نوع الملف غير صحيح!\nأرسل ملف بصيغة .{data['source_fmt']}")
        return
    
    status = bot.reply_to(message, "🔄 جاري تحويل الملف...")
    
    try:
        # تحميل الملف
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        # حفظ الملف المؤقت
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{data['source_fmt']}") as tmp_in:
            tmp_in.write(downloaded)
            input_path = tmp_in.name
        
        # إنشاء ملف الإخراج
        output_path = tempfile.mktemp(suffix=f".{data['target_fmt']}")
        
        # استهلاك نقطة
        update_points(user_id, -1)
        add_convert(user_id)
        
        # التحويل حسب النوع
        success = False
        file_type = data["type"]
        
        if file_type == "image":
            success = convert_image(input_path, output_path, data["target_fmt"])
        elif file_type == "audio":
            success = convert_audio(input_path, output_path, data["target_fmt"])
        elif file_type == "video":
            success = convert_video(input_path, output_path, data["target_fmt"])
        elif file_type == "document":
            success = convert_document(input_path, output_path, data["source_fmt"], data["target_fmt"])
        
        if success and os.path.exists(output_path):
            new_user = get_user(user_id)
            with open(output_path, 'rb') as f:
                bot.send_document(user_id, f, caption=f"✅ تم التحويل بنجاح!\n📁 {file_name} → {data['target_fmt'].upper()}\n⭐ النقاط المتبقية: {new_user['points']}\n\n@zakros_probot", visible_file_name=f"converted.{data['target_fmt']}")
        else:
            bot.send_message(user_id, "❌ فشل تحويل الملف. تأكد من أن الملف سليم.")
            update_points(user_id, 1)
        
        # تنظيف الملفات
        os.unlink(input_path)
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        bot.delete_message(user_id, status.message_id)
        del temp_data[user_id]
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", user_id, status.message_id)
        update_points(user_id, 1)

# ========== لوحة تحكم المالك ==========
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel(call):
    if call.message.chat.id != OWNER_ID:
        bot.answer_callback_query(call.id, "غير مصرح", True)
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ إضافة نقاط", callback_data="admin_add_points"),
        InlineKeyboardButton("➖ خصم نقاط", callback_data="admin_remove_points"),
        InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats")
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
    c.execute("SELECT SUM(total_converts) FROM users")
    converts = c.fetchone()[0] or 0
    bot.send_message(OWNER_ID, f"📊 *إحصائيات البوت*\n\n👥 المستخدمون: {users}\n⭐ مجموع النقاط: {points}\n🔄 عدد التحويلات: {converts}", parse_mode="Markdown")

if __name__ == "__main__":
    print("✅ بوت تحويل الملفات يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
