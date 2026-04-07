import os
import telebot
import tempfile
from datetime import datetime
from fpdf import FPDF

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,
        "📄 أرسل لي نصاً وسأحوله إلى PDF\n\n@zakros_probot")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    text = message.text.strip()
    
    if len(text) < 10:
        bot.reply_to(message, "النص قصير جداً")
        return
    
    # إنشاء PDF بسيط
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.multi_cell(0, 10, text)
    
    # حفظ الملف
    path = tempfile.mktemp(suffix='.pdf')
    pdf.output(path)
    
    # إرسال الملف
    with open(path, 'rb') as f:
        bot.send_document(message.chat.id, f, visible_file_name="document.pdf")
    
    os.unlink(path)

if __name__ == "__main__":
    print("Bot is running...")
    bot.remove_webhook()
    bot.infinity_polling()
