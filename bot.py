import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import tempfile
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, concatenate_videoclips, TextClip, CompositeVideoClip

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)

# ========== إنشاء صورة نصية ==========
def create_text_image(text, output_path, width=1280, height=720):
    try:
        img = Image.new('RGB', (width, height), color=(30, 40, 80))
        draw = ImageDraw.Draw(img)
        
        # استخدام خط بسيط
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        except:
            font = ImageFont.load_default()
        
        # تقسيم النص إلى أسطر
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
        
        # رسم النص
        y = 250
        for l in lines:
            draw.text((100, y), l, fill=(255, 255, 255), font=font)
            y += 60
        
        img.save(output_path)
        return True
    except Exception as e:
        print(f"Error creating image: {e}")
        return False

# ========== إنشاء فيديو ==========
def create_video_from_text(text, output_path):
    try:
        # تقسيم النص إلى أجزاء
        sentences = text.split('.')
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        
        if not sentences:
            sentences = [text[:200]]
        
        # إنشاء كل شريحة
        clips = []
        for i, sentence in enumerate(sentences[:5]):  # حد أقصى 5 شرائح للتجربة
            img_path = tempfile.mktemp(suffix='.png')
            if create_text_image(sentence, img_path):
                clip = ImageClip(img_path).set_duration(3).resize(height=720)
                clips.append(clip)
                os.unlink(img_path)
        
        if not clips:
            return False
        
        # دمج الشرائح
        video = concatenate_videoclips(clips, method="compose")
        video.write_videofile(output_path, fps=24, codec='libx264', threads=2, logger=None)
        video.close()
        return True
    except Exception as e:
        print(f"Error creating video: {e}")
        return False

# ========== أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,
        "🎬 *بوت تحويل النص إلى فيديو (تجريبي)*\n\n"
        "أرسل لي نصاً وسأحوله إلى فيديو.\n"
        "ملاحظة: النص يجب أن يكون باللغة العربية أو الإنجليزية.\n\n"
        "@zakros_probot",
        parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    text = message.text.strip()
    
    if len(text) < 20:
        bot.reply_to(message, "❌ النص قصير جداً (يحتاج 20 حرفاً على الأقل)")
        return
    
    status = bot.reply_to(message, "🎬 جاري إنشاء الفيديو... (قد يستغرق 20-30 ثانية)")
    
    try:
        output_path = tempfile.mktemp(suffix='.mp4')
        
        if create_video_from_text(text, output_path):
            with open(output_path, 'rb') as f:
                bot.send_video(message.chat.id, f, caption=f"✅ تم إنشاء الفيديو\n\n📝 النص: {text[:200]}...\n\n@zakros_probot", supports_streaming=True)
            os.unlink(output_path)
        else:
            bot.edit_message_text("❌ فشل إنشاء الفيديو", message.chat.id, status.message_id)
        
        bot.delete_message(message.chat.id, status.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", message.chat.id, status.message_id)

if __name__ == "__main__":
    print("✅ البوت يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
