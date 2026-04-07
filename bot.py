import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import re

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("BOT_TOKEN not set")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📚 تحليل نص", callback_data="analyze"))
    bot.send_message(message.chat.id,
        "📚 *بوت تحليل النصوص*\n\n"
        "اضغط على الزر لتحليل نص\n\n"
        "@zakros_probot",
        parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "analyze")
def analyze_start(call):
    bot.edit_message_text("📝 *أرسل النص الذي تريد تحليله*", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    bot.register_next_step_handler(call.message, analyze_text)

def analyze_text(message):
    text = message.text.strip()
    
    if len(text) < 20:
        bot.reply_to(message, "❌ النص قصير جداً (يحتاج 20 حرفاً)")
        return
    
    # تقسيم النص إلى جمل
    sentences = re.split(r'(?<=[.!?؟])\s+', text)
    
    # تجميع الجمل في أقسام (كل قسم 3 جمل)
    parts = []
    current = []
    for sent in sentences:
        current.append(sent)
        if len(current) >= 3:
            parts.append(" ".join(current))
            current = []
    if current:
        parts.append(" ".join(current))
    
    # إرسال النتيجة
    result = f"✅ *تم تحليل النص*\n\n"
    result += f"📊 عدد الجمل: {len(sentences)}\n"
    result += f"📚 عدد الأقسام: {len(parts)}\n\n"
    result += f"📝 *الأقسام:*\n"
    
    for i, part in enumerate(parts):
        result += f"\n{i+1}. {part[:150]}..."
    
    bot.send_message(message.chat.id, result, parse_mode="Markdown")

if __name__ == "__main__":
    print("✅ البوت يعمل...")
    bot.remove_webhook()
    bot.infinity_polling()
