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

# تحميل خط يدعم العربية (اختياري)
try:
    # محاولة تحميل خط من الإنترنت
    font_url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
    font_path = "NotoSans-Regular.ttf"
    if not os.path.exists(font_path):
        r = requests.get(font_url, timeout=10)
        with open(font_path, "wb") as f:
            f.write(r.content)
    pdfmetrics.registerFont(TTFont('NotoSans', font_path))
    FONT_NAME = 'NotoSans'
except:
    FONT_NAME = 'Helvetica'

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "أرسل لي نصاً وسأحوله إلى PDF")

@bot.message_handler(func=lambda m: True)
def convert_to_pdf(message):
    text = message.text.strip()
    
    if len(text) < 5:
        bot.reply_to(message, "النص قصير جداً")
        return
    
    # إنشاء PDF
    path = tempfile.mktemp(suffix='.pdf')
    c = canvas.Canvas(path, pagesize=A4)
    c.setFont(FONT_NAME, 12)
    
    # كتابة النص
    y = 800
    for line in text.split('\n'):
        c.drawString(50, y, line[:100])
        y -= 20
        if y < 50:
            c.showPage()
            y = 800
            c.setFont(FONT_NAME, 12)
    
    c.save()
    
    # إرسال الملف
    with open(path, 'rb') as f:
        bot.send_document(message.chat.id, f, visible_file_name="document.pdf")
    
    os.remove(path)

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
