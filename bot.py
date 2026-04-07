import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import tempfile
from datetime import datetime
from fpdf import FPDF

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)

# ========== إنشاء PDF ==========
def create_pdf(text, title, output_path):
    class PDF(FPDF):
        def header(self):
            if self.page_no() > 1:
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(150, 150, 150)
                self.cell(0, 10, f"صفحة {self.page_no()}", 0, 0, 'C')
                self.ln(10)
        
        def footer(self):
            self.set_y(-20)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, "@zakros_probot", 0, 0, 'C')
    
    pdf = PDF()
    pdf.add_page()
    
    # العنوان
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 15, title, 0, 1, 'C')
    pdf.ln(5)
    
    # التاريخ
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1, 'C')
    pdf.ln(10)
    
    # خط فاصل
    pdf.set_draw_color(0, 102, 204)
    pdf.line(30, 55, 180, 55)
    pdf.ln(15)
    
    # المحتوى
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(0, 0, 0)
    
    # تقسيم النص إلى فقرات
    paragraphs = text.split('\n')
    for para in paragraphs:
        if para.strip():
            pdf.multi_cell(0, 8, para.strip())
            pdf.ln(4)
    
    pdf.output(output_path)

# ========== أوامر البوت ==========
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id,
        "📄 *بوت تحويل النص إلى PDF*\n\n"
        "أرسل لي النص الذي تريد تحويله إلى ملف PDF\n"
        "يمكنك إرسال نص عادي أو ملف .txt\n\n"
        "سأقوم بإنشاء PDF منسق ومرتب\n\n"
        "@zakros_probot",
        parse_mode="Markdown")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.chat.id
    text = message.text.strip()
    
    if len(text) < 10:
        bot.reply_to(message, "❌ النص قصير جداً (يحتاج 10 أحرف على الأقل)")
        return
    
    # طلب عنوان
    msg = bot.reply_to(message, "📝 *أرسل عنوان المستند* (مثال: ملاحظاتي)", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_text, text)

def process_text(message, text):
    title = message.text.strip()
    if len(title) < 3:
        title = "مستند جديد"
    
    status = bot.reply_to(message, "📄 جاري إنشاء ملف PDF...")
    
    try:
        output_path = tempfile.mktemp(suffix='.pdf')
        create_pdf(text, title, output_path)
        
        with open(output_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"✅ تم إنشاء ملف PDF\n📄 العنوان: {title}\n\n@zakros_probot", visible_file_name=f"{title}.pdf")
        
        os.unlink(output_path)
        bot.delete_message(message.chat.id, status.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", message.chat.id, status.message_id)

@bot.message_handler(content_types=['document'])
def handle_file(message):
    if not message.document.file_name.endswith('.txt'):
        bot.reply_to(message, "❌ أرسل ملف .txt فقط")
        return
    
    status = bot.reply_to(message, "📥 جاري تحميل الملف...")
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        text = downloaded.decode('utf-8')
        
        if len(text) < 10:
            bot.edit_message_text("❌ الملف فارغ أو قصير جداً", message.chat.id, status.message_id)
            return
        
        # استخدام اسم الملف كعنوان
        title = os.path.splitext(message.document.file_name)[0]
        
        output_path = tempfile.mktemp(suffix='.pdf')
        create_pdf(text, title, output_path)
        
        with open(output_path, 'rb') as f:
            bot.send_document(message.chat.id, f, caption=f"✅ تم تحويل الملف إلى PDF\n📄 العنوان: {title}\n\n@zakros_probot", visible_file_name=f"{title}.pdf")
        
        os.unlink(output_path)
        bot.delete_message(message.chat.id, status.message_id)
        
    except Exception as e:
        bot.edit_message_text(f"❌ خطأ: {str(e)[:100]}", message.chat.id, status.message_id)

if __name__ == "__main__":
    print("✅ بوت تحويل النص إلى PDF يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
