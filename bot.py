import os
import telebot
import tempfile
from fpdf import FPDF

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)

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
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    # تقسيم النص إلى أسطر
    for line in text.split('\n'):
        pdf.cell(0, 10, line, ln=1)
    
    # حفظ الملف
    path = tempfile.mktemp(suffix='.pdf')
    pdf.output(path)
    
    # إرسال الملف
    with open(path, 'rb') as f:
        bot.send_document(message.chat.id, f)
    
    os.remove(path)

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
