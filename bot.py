import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8443))
APP_NAME = os.environ.get("HEROKU_APP_NAME")

# ========== الدروس ==========
LESSONS = {
    "1": {"title": "المسرحية - ثانية يجيء الحسين", "summary": "المسرحية هي قصة تمثل على المسرح، والمسرحية الشعرية ظهرت في العصر الحديث، ومن روادها محمد علي الخفاجي."},
    "2": {"title": "القصة القصيرة - الباب الآخر", "summary": "القصة القصيرة هي عمل أدبي نثري يحكي حدثاً واحداً، ومن روادها فؤاد التكرلي."},
    "3": {"title": "الرواية - نشأة وتطور", "summary": "الرواية عمل أدبي طويل يتناول شخصيات وأحداثاً متعددة، ومن روادها نجيب محفوظ."},
    "4": {"title": "المقالة - بين القديم والجديد", "summary": "المقالة قطعة نثرية تعالج موضوعاً معيناً، وهي نوعان: ذاتية وموضوعية."},
    "5": {"title": "فن السيرة - الأيام لطه حسين", "summary": "السيرة فن أدبي يسرد حياة شخص، وتنقسم إلى ذاتية وموضوعية."},
    "6": {"title": "أسلوب الاستفهام", "summary": "الاستفهام طلب العلم بشيء مجهول، أدواته: الهمزة، هل، من، ما، متى، أين، كيف، كم، أي."},
    "7": {"title": "أسلوب التعجب", "summary": "التعجب حالة نفسية تعبر عن الدهشة، وله صيغتان: ما أفعله! وأفعل به!"},
    "8": {"title": "أسلوب المدح والذم", "summary": "أفعال المدح: نعم، حبذا، أفعال الذم: بئس، لا حبذا."},
}

# ========== الأزرار ==========
main_keyboard = [
    [InlineKeyboardButton("📚 دروس الأدب", callback_data="lit")],
    [InlineKeyboardButton("✍️ دروس القواعد", callback_data="gram")],
]

lit_keyboard = [
    [InlineKeyboardButton("المسرحية", callback_data="1")],
    [InlineKeyboardButton("القصة القصيرة", callback_data="2")],
    [InlineKeyboardButton("الرواية", callback_data="3")],
    [InlineKeyboardButton("المقالة", callback_data="4")],
    [InlineKeyboardButton("فن السيرة", callback_data="5")],
    [InlineKeyboardButton("🔙 رجوع", callback_data="back")],
]

gram_keyboard = [
    [InlineKeyboardButton("أسلوب الاستفهام", callback_data="6")],
    [InlineKeyboardButton("أسلوب التعجب", callback_data="7")],
    [InlineKeyboardButton("أسلوب المدح والذم", callback_data="8")],
    [InlineKeyboardButton("🔙 رجوع", callback_data="back")],
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎓 **مرحباً بك في بوت شرح الأدب العربي!** 🎓\n\n"
        "📚 اختر القسم الذي تريد:",
        reply_markup=InlineKeyboardMarkup(main_keyboard),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "lit":
        await query.edit_message_text(
            "📚 **دروس الأدب:**\n\nاختر الدرس:",
            reply_markup=InlineKeyboardMarkup(lit_keyboard)
        )
    elif data == "gram":
        await query.edit_message_text(
            "✍️ **دروس القواعد:**\n\nاختر الدرس:",
            reply_markup=InlineKeyboardMarkup(gram_keyboard)
        )
    elif data == "back":
        await query.edit_message_text(
            "🎓 **مرحباً بك في بوت شرح الأدب العربي!** 🎓\n\n"
            "📚 اختر القسم الذي تريد:",
            reply_markup=InlineKeyboardMarkup(main_keyboard)
        )
    elif data in LESSONS:
        lesson = LESSONS[data]
        await query.edit_message_text(
            f"📖 **{lesson['title']}**\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📝 **الملخص:**\n{lesson['summary']}\n\n"
            f"✅ تم الشرح بنجاح",
            parse_mode="Markdown"
        )

def main():
    if not TOKEN:
        logger.error("❌ BOT_TOKEN غير موجود!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("✅ البوت يعمل!")
    
    # استخدام Webhook (الطريقة الصحيحة لـ Heroku)
    if APP_NAME:
        webhook_url = f"https://{APP_NAME}.herokuapp.com/"
        logger.info(f"🔗 Webhook URL: {webhook_url}")
        app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=webhook_url)
    else:
        logger.warning("⚠️ HEROKU_APP_NAME غير موجود، استخدام Polling")
        app.run_polling()

if __name__ == "__main__":
    main()
