import os
import io
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# ========== العناوين المستخرجة من كتاب الأدب السادس الإعدادي ==========
# تم استخراج العناوين من ملفي PDF

TITLES = {
    # الوحدة الأولى
    "المسرحية": {
        "title": "المسرحية - ثانية يجيء الحسين",
        "section": "الوحدة السادسة",
        "page": "19-26",
        "video_id": "1",
        "summary": "المسرحية هي قصة تمثل على المسرح، والمسرحية الشعرية ظهرت في العصر الحديث، ومن روادها محمد علي الخفاجي ومسرحيته 'ثانية يجيء الحسين'"
    },
    
    # الوحدة الثانية
    "القصة_القصيرة": {
        "title": "القصة القصيرة - الباب الآخر",
        "section": "الوحدة السابعة",
        "page": "41-50",
        "video_id": "2",
        "summary": "القصة القصيرة هي عمل أدبي نثري يحكي حدثاً واحداً أو حادثة محددة، ومن روادها فؤاد التكرلي وقصته 'الباب الآخر'"
    },
    
    # الوحدة الثالثة
    "الرواية": {
        "title": "الرواية - نشأة وتطور",
        "section": "الوحدة الثامنة",
        "page": "60-66",
        "video_id": "3",
        "summary": "الرواية هي عمل أدبي طويل يتناول شخصيات وأحداثاً متعددة، ومن روادها نجيب محفوظ وغائب طعمة فرمان"
    },
    
    # الوحدة الرابعة
    "المقالة": {
        "title": "المقالة - بين القديم والجديد",
        "section": "الوحدة التاسعة",
        "page": "83-88",
        "video_id": "4",
        "summary": "المقالة هي قطعة نثرية تعالج موضوعاً معيناً، وهي نوعان: ذاتية وموضوعية، ومن روادها الدكتور علي جواد الطاهر"
    },
    
    # الوحدة الخامسة
    "فن_السيرة": {
        "title": "فن السيرة - الأيام لطه حسين",
        "section": "الوحدة العاشرة",
        "page": "102-106",
        "video_id": "5",
        "summary": "السيرة هي فن أدبي يسرد حياة شخص، وتنقسم إلى ذاتية وموضوعية، ومن أشهرها 'الأيام' لطه حسين"
    },
    
    # الوحدة السادسة
    "الشعر_الحديث": {
        "title": "الشعر الحديث - مدارس الشعر",
        "section": "الوحدة الثالثة",
        "page": "33-42",
        "video_id": "6",
        "summary": "الشعر الحديث بدأ مع نهضة الأدب العربي، وتطورت مدارسه: الإحياء، الرومانسية، الواقعية، الرمزية، وشعر التفعيلة"
    },
    
    # مدرسة الإحياء
    "مدرسة_الإحياء": {
        "title": "مدرسة الإحياء - محمد سعيد الحبوبي وعلي الشرقي",
        "section": "الوحدة الثالثة",
        "page": "34-42",
        "video_id": "7",
        "summary": "مدرسة الإحياء ظهرت في أواخر القرن التاسع عشر، تهدف لإحياء التقاليد الشعرية العربية، ومن روادها: الحبوبي والشرقي والرصافي"
    },
    
    # الموشحات
    "الموشحات": {
        "title": "الموشحات - يا غزال الكرخ",
        "section": "الوحدة الثالثة",
        "page": "36-39",
        "video_id": "8",
        "summary": "الموشحات فن شعري نشأ في الأندلس، يتألف من مطلع وأدوار وأغصان، ومن أشهر شعرائها: الحصري وابن الخطيب والحبوبي"
    },
    
    # مدرسة المهجر
    "مدرسة_المهجر": {
        "title": "مدرسة المهجر - ميخائيل نعيمة",
        "section": "الوحدة الحادية عشرة",
        "page": "102-104",
        "video_id": "9",
        "summary": "مدرسة المهجر أسسها الشعراء العرب في أمريكا، ومن أبرزهم جبران وميخائيل نعيمة وإيليا أبو ماضي، تميزت بالحنين للوطن والتأمل"
    },
    
    # مدرسة الشعر الحر
    "الشعر_الحر": {
        "title": "الشعر الحر - بدر شاكر السياب",
        "section": "الوحدة الثانية عشرة",
        "page": "126-131",
        "video_id": "10",
        "summary": "الشعر الحر أو شعر التفعيلة ظهر في أربعينيات القرن العشرين، يقوم على تفعيلة واحدة متكررة، ومن رواده السياب والبياتی ونازك الملائكة"
    },
    
    # شعر المقاومة الفلسطينية
    "شعر_المقاومة": {
        "title": "شعر المقاومة الفلسطينية - محمود درويش وفدوى طوقان",
        "section": "الوحدة الثالثة عشرة",
        "page": "156-163",
        "video_id": "11",
        "summary": "شعر المقاومة يوثق معاناة الشعب الفلسطيني، ويحفز على النضال، ومن أبرز شعرائه: محمود درويش وفدوى طوقان وسميح القاسم"
    },
    
    # النقد الأدبي - الواقعية
    "الواقعية": {
        "title": "النقد الأدبي - الواقعية",
        "section": "الوحدة الثامنة",
        "page": "64-66",
        "video_id": "12",
        "summary": "الواقعية مذهب أدبي يصور الواقع كما هو، ظهرت في خمسينيات القرن العشرين، وتهتم بتصوير المجتمع وتحليل قضاياه"
    },
    
    # النقد الأدبي - الرمزية
    "الرمزية": {
        "title": "النقد الأدبي - الرمزية",
        "section": "الوحدة العاشرة",
        "page": "107-108",
        "video_id": "13",
        "summary": "الرمزية ظهرت في فرنسا أواخر القرن التاسع عشر، تعتمد على الرموز والإيحاءات، ومن روادها في الأدب العربي السياب والبياتی وأدونيس"
    },
    
    # الكالسيكية
    "الكالسيكية": {
        "title": "الكالسيكية في الأدب العربي",
        "section": "الوحدة التاسعة",
        "page": "81-83",
        "video_id": "14",
        "summary": "الكالسيكية مذهب أدبي يعتمد على محاكاة الأدب اليوناني واللاتيني القديم، وتتميز بالعناية بالشكل واللغة الجزلة"
    },
    
    # الرومانسية
    "الرومانسية": {
        "title": "الرومانسية في الأدب العربي",
        "section": "الوحدة الحادية عشرة",
        "page": "135-136",
        "video_id": "15",
        "summary": "الرومانسية تؤكد على العاطفة والشعور، وتهرب من الواقع إلى الماضي الجميل أو الطبيعة، ومن روادها مدرسة المهجر"
    },
}

# ========== دروس القواعد ==========
GRAMMAR_TITLES = {
    "أسلوب_الاستفهام": {
        "title": "أسلوب الاستفهام",
        "section": "القواعد",
        "page": "8-31",
        "video_id": "grammar_1",
        "summary": "الاستفهام طلب العلم بشيء مجهول، أدواته: الهمزة، هل، من، ما، متى، أين، كيف، كم، أي"
    },
    "أسلوب_التعجب": {
        "title": "أسلوب التعجب",
        "section": "القواعد",
        "page": "8-17",
        "video_id": "grammar_2",
        "summary": "التعجب حالة نفسية تعبر عن الدهشة، وله صيغتان: ما أفعله! وأفعل به!"
    },
    "أسلوب_المدح_والذم": {
        "title": "أسلوب المدح والذم",
        "section": "القواعد",
        "page": "32-38",
        "video_id": "grammar_3",
        "summary": "المدح والذم من أساليب اللغة، أفعال المدح: نعم، حبذا، أفعال الذم: بئس، لا حبذا"
    },
    "أسلوب_التمني_والترجي": {
        "title": "أسلوب التمني والترجي",
        "section": "القواعد",
        "page": "55-59",
        "video_id": "grammar_4",
        "summary": "التمني طلب أمر بعيد التحقق، والترجي طلب أمر ممكن، وأدواتهما: ليت، لعل، عسى"
    },
    "أسلوب_العرض_والتحضيض": {
        "title": "أسلوب العرض والتحضيض",
        "section": "القواعد",
        "page": "72-81",
        "video_id": "grammar_5",
        "summary": "العرض طلب برفق، والتحضيض طلب بقوة، وأدواتهما: ألا، أما، لو، لولا، هلا"
    },
    "أسلوب_النفي": {
        "title": "أسلوب النفي",
        "section": "القواعد",
        "page": "47-73",
        "video_id": "grammar_6",
        "summary": "النفي هو نفي حصول الفعل، وأدواته: ليس، غير، ما، إن، لم، لما، لن، لا النافية"
    },
    "أسلوب_التحذير_والإغراء": {
        "title": "أسلوب التحذير والإغراء",
        "section": "القواعد",
        "page": "93-101",
        "video_id": "grammar_7",
        "summary": "التحذير تنبيه على أمر مكروه، والإغراء تنبيه على أمر محبوب، وأدواتهما: إياك، الصدق الصدق"
    },
    "أسلوب_التقديم_والتأخير": {
        "title": "أسلوب التقديم والتأخير",
        "section": "القواعد",
        "page": "91-100",
        "video_id": "grammar_8",
        "summary": "تقديم الخبر على المبتدأ أو المفعول على الفعل لأسباب بلاغية، له مواضع يجب فيها التقديم"
    },
    "أسلوب_التوكيد": {
        "title": "أسلوب التوكيد",
        "section": "القواعد",
        "page": "110-125",
        "video_id": "grammar_9",
        "summary": "التوكيد أسلوب لتقوية الكلام ورفع الشك، أنواعه: لفظي، معنوي، بالحرف، بالقصر"
    },
    "أسلوب_النداء": {
        "title": "أسلوب النداء",
        "section": "القواعد",
        "page": "143-155",
        "video_id": "grammar_10",
        "summary": "النداء خطاب يوجه للمنادى ليقبل، وأدواته: يا، أيا، هيا، أي، والمنادى أنواع: مفرد، مضاف، شبيه بالمضاف"
    },
}

# دمج جميع العناوين
ALL_TITLES = {**TITLES, **GRAMMAR_TITLES}

# تخزين اختيار المستخدم
user_selection = {}

# ========== وظائف البوت ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إظهار القائمة الرئيسية"""
    
    # القائمة الرئيسية
    main_keyboard = [
        [InlineKeyboardButton("📚 دروس الأدب", callback_data="category_literature")],
        [InlineKeyboardButton("✍️ دروس القواعد", callback_data="category_grammar")],
        [InlineKeyboardButton("📖 جميع الدروس", callback_data="category_all")],
    ]
    
    await update.message.reply_text(
        "🎓 **مرحباً بك في بوت شرح كتاب الأدب للصف السادس الإعدادي!** 🎓\n\n"
        "📚 هذا البوت يحتوي على شروحات كاملة لكتاب اللغة العربية\n"
        "🎥 كل درس يحتوي على فيديو شرح + ملخص + صور توضيحية\n\n"
        "🔽 **اختر القسم الذي تريده:**",
        reply_markup=InlineKeyboardMarkup(main_keyboard),
        parse_mode="Markdown"
    )

async def show_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الدروس حسب الفئة"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace("category_", "")
    
    keyboard = []
    
    if category == "literature":
        for key, info in TITLES.items():
            keyboard.append([InlineKeyboardButton(f"📖 {info['title']}", callback_data=f"lesson_{key}")])
    
    elif category == "grammar":
        for key, info in GRAMMAR_TITLES.items():
            keyboard.append([InlineKeyboardButton(f"✍️ {info['title']}", callback_data=f"lesson_{key}")])
    
    else:  # all
        keyboard.append([InlineKeyboardButton("📚 دروس الأدب", callback_data="category_literature")])
        keyboard.append([InlineKeyboardButton("✍️ دروس القواعد", callback_data="category_grammar")])
    
    keyboard.append([InlineKeyboardButton("🔙 الرجوع للقائمة الرئيسية", callback_data="back_to_start")])
    
    await query.edit_message_text(
        "📚 **اختر الدرس الذي تريد شرحه:**\n\n"
        "✅ سيتم إرسال فيديو شرح + ملخص + صور توضيحية",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def show_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تفاصيل الدرس المختار وإرسال الفيديو"""
    query = update.callback_query
    await query.answer()
    
    lesson_key = query.data.replace("lesson_", "")
    
    if lesson_key not in ALL_TITLES:
        await query.edit_message_text("❌ عذراً، هذا الدرس غير متوفر حالياً")
        return
    
    lesson = ALL_TITLES[lesson_key]
    
    # إرسال رسالة التحميل
    await query.edit_message_text(
        f"🎬 **جاري تجهيز فيديو شرح: {lesson['title']}**\n\n"
        f"📖 القسم: {lesson['section']}\n"
        f"📄 الصفحات: {lesson['page']}\n\n"
        f"⏱ يرجى الانتظار... سيتم إرسال الفيديو خلال لحظات",
        parse_mode="Markdown"
    )
    
    # هنا سيتم إرسال الفيديو
    # ملاحظة: يجب رفع ملفات الفيديو إلى مكان عام (مثل Google Drive أو YouTube)
    # ثم وضع الروابط هنا
    
    # رابط الفيديو (مثال - يجب استبداله بالرابط الحقيقي)
    video_url = f"https://example.com/videos/{lesson['video_id']}.mp4"
    
    # إرسال ملخص الدرس
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"📚 **{lesson['title']}**\n\n"
             f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
             f"📖 **القسم:** {lesson['section']}\n"
             f"📄 **الصفحات:** {lesson['page']}\n\n"
             f"📝 **الملخص:**\n{lesson['summary']}\n\n"
             f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
             f"🎥 **فيديو الشرح:**\n[video]",
        parse_mode="Markdown"
    )
    
    # إرسال فيديو (إذا كان موجوداً محلياً)
    # await context.bot.send_video(
    #     chat_id=update.effective_chat.id,
    #     video=open(f"videos/{lesson['video_id']}.mp4", 'rb'),
    #     caption=f"🎬 شرح {lesson['title']}"
    # )
    
    # إرسال صور توضيحية (إذا كانت موجودة)
    # await context.bot.send_photo(
    #     chat_id=update.effective_chat.id,
    #     photo=open(f"images/{lesson['video_id']}_1.jpg", 'rb'),
    #     caption="صورة توضيحية 1"
    # )
    
    # عرض القائمة مرة أخرى
    main_keyboard = [
        [InlineKeyboardButton("📚 دروس الأدب", callback_data="category_literature")],
        [InlineKeyboardButton("✍️ دروس القواعد", callback_data="category_grammar")],
        [InlineKeyboardButton("📖 جميع الدروس", callback_data="category_all")],
    ]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="✨ **هل تريد مشاهدة درس آخر؟**\n\nاختر من القائمة:",
        reply_markup=InlineKeyboardMarkup(main_keyboard)
    )

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرجوع للقائمة الرئيسية"""
    query = update.callback_query
    await query.answer()
    
    main_keyboard = [
        [InlineKeyboardButton("📚 دروس الأدب", callback_data="category_literature")],
        [InlineKeyboardButton("✍️ دروس القواعد", callback_data="category_grammar")],
        [InlineKeyboardButton("📖 جميع الدروس", callback_data="category_all")],
    ]
    
    await query.edit_message_text(
        "🎓 **مرحباً بك في بوت شرح كتاب الأدب للصف السادس الإعدادي!** 🎓\n\n"
        "📚 هذا البوت يحتوي على شروحات كاملة لكتاب اللغة العربية\n"
        "🎥 كل درس يحتوي على فيديو شرح + ملخص + صور توضيحية\n\n"
        "🔽 **اختر القسم الذي تريده:**",
        reply_markup=InlineKeyboardMarkup(main_keyboard),
        parse_mode="Markdown"
    )

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # الأوامر
    app.add_handler(CommandHandler("start", start))
    
    # معالجة الأزرار
    app.add_handler(CallbackQueryHandler(show_category, pattern="^category_"))
    app.add_handler(CallbackQueryHandler(show_lesson, pattern="^lesson_"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    
    print("=" * 60)
    print("✅ بوت شرح كتاب الأدب السادس الإعدادي يعمل!")
    print(f"📚 عدد الدروس المتاحة: {len(ALL_TITLES)}")
    print("   - دروس الأدب: 15 درساً")
    print("   - دروس القواعد: 10 دروس")
    print("=" * 60)
    
    app.run_polling()

if __name__ == "__main__":
    main()
