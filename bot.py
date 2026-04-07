import os
import telebot
import tempfile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import requests

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)

# ========== تحميل خط يدعم العربية واللاتينية ==========
FONT_URL = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
FONT_PATH = "NotoSans-Regular.ttf"

if not os.path.exists(FONT_PATH):
    try:
        print("Downloading font...")
        r = requests.get(FONT_URL, timeout=30)
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
        print("Font downloaded.")
    except:
        print("Font download failed, using default.")

# تسجيل الخط
try:
    pdfmetrics.registerFont(TTFont('NotoSans', FONT_PATH))
    FONT_NAME = 'NotoSans'
except:
    FONT_NAME = 'Helvetica'

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,
        "📄 *بوت تحويل النص إلى PDF*\n\n"
        "أرسل لي نصاً (عربي، إنجليزي، أو أي لغة) وسأحوله إلى PDF\n\n"
        "@zakros_probot",
        parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def convert_to_pdf(message):
    text = message.text.strip()
    
    if len(text) < 5:
        bot.reply_to(message, "❌ النص قصير جداً")
        return
    
    status = bot.reply_to(message, "📄 جاري إنشاء PDF...")
    
    try:
        # إنشاء PDF
        pdf_path = tempfile.mktemp(suffix='.pdf')
        c = canvas.Canvas(pdf_path, pagesize=A4)
        c.setFont(FONT_NAME, 12)
        
        width, height = A4
        y = height - 50
        
        # تقسيم النص إلى أسطر
        lines = text.split('\n')
        for line in lines:
            if y < 50:
                c.showPage()
                y = height - 50
                c.setFont(FONT_NAME, 12)
            
            # كتابة السطر (أقصى 100 حرف لكل سطر)
            for i in range(0, len(line), 100):
                c.drawString(50, y, line[i:i+100])
                y -= 20
        
        # إضافة حقوق البوت
        c.setFont(FONT_NAME, 8)
        c.drawString(50, 30, "@zakros_probot")
        c.save()
        
        # إرسال الملف
        with open(pdf_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"✅ تم تحويل النص إلى PDF\n\n@zakros_probot", visible_file_name="document.pdf")
        
        os.remove(pdf_path)
        bot.delete_message(message.chat.id, status.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", message.chat.id, status.message_id)

if __name__ == "__main__":
    print("✅ البوت يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
