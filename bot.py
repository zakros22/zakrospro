import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# تفعيل التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# ========== دروس الأدب (20 درساً) ==========
LITERATURE_LESSONS = {
    "lit_1": {
        "title": "الإصلاح ضرورة",
        "section": "الوحدة السادسة - الإصلاح",
        "summary": "الإصلاح هدف رئيس من أهداف الأنبياء والأئمة والمصلحين، والمجتمعات البشرية بحاجة دائمة إلى الإصلاح وتوجيه الناس نحو عبادة الله ومحاربة الفساد وإشاعة القيم والمثل العليا."
    },
    "lit_2": {
        "title": "المسرحية - ثانية يجيء الحسين",
        "section": "الوحدة السادسة - الأدب",
        "summary": "المسرحية هي قصة تمثل على المسرح، والمسرحية الشعرية ظهرت في العصر الحديث، ومن روادها محمد علي الخفاجي ومسرحيته 'ثانية يجيء الحسين' التي تتناول قصة الإمام الحسين عليه السلام."
    },
    "lit_3": {
        "title": "لا لتعنيف الطفل",
        "section": "الوحدة السابعة - حقوق الطفل",
        "summary": "استعمال الأساليب غير الإيجابية في التعامل مثل الشدة أمر مرفوض، ولها آثار نفسية بعيدة المدى على الأطفال، والإسلام أوصى بالطفل خيراً وحث على تقبيله والترفق به."
    },
    "lit_4": {
        "title": "القصة القصيرة - الباب الآخر",
        "section": "الوحدة السابعة - الأدب",
        "summary": "القصة القصيرة هي عمل أدبي نثري يحكي حدثاً واحداً أو حادثة محددة، ومن روادها في العراق فؤاد التكرلي وقصته 'الباب الآخر' التي تتناول العلاقة بين الأم وابنها."
    },
    "lit_5": {
        "title": "جائزة نوبل للآداب",
        "section": "الوحدة الثامنة - جائزة نوبل",
        "summary": "جائزة نوبل هي جائزة سويدية أنشأها ألفريد نوبل عام 1895، تمنح في مجالات الفيزياء والكيمياء والطب والأدب والسلام، وفاز بها المصري نجيب محفوظ عام 1988."
    },
    "lit_6": {
        "title": "الرواية - نشأة وتطور",
        "section": "الوحدة الثامنة - الأدب",
        "summary": "الرواية عمل أدبي طويل يتناول شخصيات وأحداثاً متعددة، وتختلف عن القصة القصيرة بالطول ووفرة الشخصيات، ومن روادها في العراق محمود أحمد السيد وغائب طعمة فرمان."
    },
    "lit_7": {
        "title": "الواقعية في الأدب العربي",
        "section": "الوحدة الثامنة - النقد الأدبي",
        "summary": "الواقعية مذهب أدبي يصور الواقع كما هو، ظهرت في خمسينيات القرن العشرين، وتهتم بتصوير المجتمع وتحليل قضاياه، ومن روادها نجيب محفوظ وغائب طعمة فرمان."
    },
    "lit_8": {
        "title": "رسالة من أب إلى ابنه",
        "section": "الوحدة التاسعة - بين القديم والجديد",
        "summary": "رسالة نصح وإرشاد من أب إلى ابنه، تبين أهمية التوازن بين الماضي والحاضر، وعدم الاستهانة بتجارب الآباء، واحترام كبار السن."
    },
    "lit_9": {
        "title": "المقالة - بين القديم والجديد",
        "section": "الوحدة التاسعة - الأدب",
        "summary": "المقالة قطعة نثرية تعالج موضوعاً معيناً، وهي نوعان: ذاتية (أدبية) وموضوعية (علمية)، ومن روادها الدكتور علي جواد الطاهر."
    },
    "lit_10": {
        "title": "الكالسيكية في الأدب العربي",
        "section": "الوحدة التاسعة - النقد الأدبي",
        "summary": "الكالسيكية مذهب أدبي يعتمد على محاكاة الأدب اليوناني واللاتيني القديم، وتتميز بالعناية بالشكل واللغة الجزلة، ومن روادها محمود سامي البارودي وأحمد شوقي."
    },
    "lit_11": {
        "title": "حسن السيرة من الإيمان",
        "section": "الوحدة العاشرة - السيرة الحسنة",
        "summary": "مكارم الأخلاق من لوازم الحياة الصحيحة، وقد اتسم العرب قديماً بالكرم والشجاعة والصدق والأمانة، وبعث النبي محمد صلى الله عليه وسلم ليتمم مكارم الأخلاق."
    },
    "lit_12": {
        "title": "فن السيرة - الأيام لطه حسين",
        "section": "الوحدة العاشرة - الأدب",
        "summary": "السيرة فن أدبي يسرد حياة شخص، وتنقسم إلى ذاتية (يكتبها الشخص عن نفسه) وموضوعية (يكتبها عن غيره)، ومن أشهرها 'الأيام' لعميد الأدب العربي طه حسين."
    },
    "lit_13": {
        "title": "الرمزية في الأدب العربي",
        "section": "الوحدة العاشرة - النقد الأدبي",
        "summary": "الرمزية ظهرت في فرنسا أواخر القرن التاسع عشر، تعتمد على الرموز والإيحاءات، ومن روادها في الأدب العربي بدر شاكر السياب وعبد الوهاب البياتي وأدونيس."
    },
    "lit_14": {
        "title": "التضحية من أجل الوطن",
        "section": "الوحدة الحادية عشرة - التضحية",
        "summary": "التضحية هي بذل النفس أو المال أو الوقت من أجل غاية أسمى، ومن أبرز مظاهرها تضحيات الحشد الشعبي والجيش العراقي في مواجهة الإرهاب."
    },
    "lit_15": {
        "title": "الأمل مفتاح النجاح",
        "section": "الوحدة الثانية عشرة - الأمل",
        "summary": "الأمل هو الشعور بالتفاؤل والإيجابية تجاه الذات والآخرين، وهو عالج نفسي بديل عن الأدوية، ويموت بالأفكار السلبية والقلق المستمر."
    },
    "lit_16": {
        "title": "مدرسة المهجر - ميخائيل نعيمة",
        "section": "الوحدة الثانية عشرة - الأدب",
        "summary": "مدرسة المهجر أسسها الشعراء العرب في أمريكا، ومن أبرزهم جبران خليل جبران وميخائيل نعيمة وإيليا أبو ماضي، تميزت بالحنين إلى الوطن والتأمل في الطبيعة."
    },
    "lit_17": {
        "title": "المطر نعمة من الله",
        "section": "الوحدة الثالثة عشرة - المطر",
        "summary": "المطر أساس الحياة وسر ديمومتها، وهو نعمة من الله أنزلها لإنبات الزرع وسقيا الحيوان والإنسان، وقد ورد ذكره كثيراً في القرآن الكريم."
    },
    "lit_18": {
        "title": "الشعر الحر - بدر شاكر السياب",
        "section": "الوحدة الثالثة عشرة - الأدب",
        "summary": "الشعر الحر أو شعر التفعيلة ظهر في أربعينيات القرن العشرين، يقوم على تفعيلة واحدة متكررة، ومن رواده بدر شاكر السياب ونازك الملائكة وعبد الوهاب البياتي."
    },
    "lit_19": {
        "title": "شعر المقاومة الفلسطينية",
        "section": "الوحدة الرابعة عشرة - القضية الفلسطينية",
        "summary": "شعر المقاومة يوثق معاناة الشعب الفلسطيني ويحفز على النضال، ومن أبرز شعرائه محمود درويش وفدوى طوقان وسميح القاسم، ويتميز بتكريم الشهادة وإبراز أهمية التضحيات."
    },
    "lit_20": {
        "title": "الرومانسية في الأدب العربي",
        "section": "الوحدة الرابعة عشرة - النقد الأدبي",
        "summary": "الرومانسية تؤكد على العاطفة والشعور، وتهرب من الواقع إلى الماضي الجميل أو الطبيعة، ومن روادها في الأدب العربي مدرسة المهجر."
    }
}

# ========== دروس القواعد (10 دروس) ==========
GRAMMAR_LESSONS = {
    "gram_1": {
        "title": "أسلوب الاستفهام",
        "section": "القواعد",
        "summary": "الاستفهام طلب العلم بشيء مجهول، أدواته: الهمزة، هل، من، ما، متى، أين، كيف، كم، أي. وينقسم إلى حقيقي ومجازي.",
        "examples": ["مَنْ بَنَى بَغْدَادَ؟", "مَا الخَبَرُ؟", "مَتَى عُدْتَ مِنَ السَّفَرِ؟"]
    },
    "gram_2": {
        "title": "أسلوب التعجب",
        "section": "القواعد",
        "summary": "التعجب حالة نفسية تعبر عن الدهشة، وله صيغتان: 'ما أفعله!' للتعجب من شيء، و'أفعل به!' للتعجب من شخص.",
        "examples": ["مَا أَجْمَلَ السَّمَاءَ!", "أَجْمِلْ بِالرَّبِيعِ!", "مَا أَشَدَّ الْحَرَّ!"]
    },
    "gram_3": {
        "title": "أسلوب المدح والذم",
        "section": "القواعد",
        "summary": "المدح والذم من أساليب اللغة، أفعال المدح: نعم، حبذا، أفعال الذم: بئس، لا حبذا. يأتي بعدها فاعل ومخصوص بالمدح أو الذم.",
        "examples": ["نِعْمَ الرَّجُلُ مُحَمَّدٌ", "بِئْسَ الْخُلُقُ الْكِذْبُ", "حَبَّذَا الْعِلْمُ"]
    },
    "gram_4": {
        "title": "أسلوب التمني والترجي",
        "section": "القواعد",
        "summary": "التمني طلب أمر بعيد التحقق أو مستحيل، والترجي طلب أمر ممكن التحقق. أدواتهما: ليت (للتمني)، لعل وعسى (للترجي).",
        "examples": ["لَيْتَ الْفَقْرَ غِنًى", "لَعَلَّ السَّاعَةَ قَرِيبٌ", "عَسَى رَبِّي أَنْ يَهْدِيَنِي"]
    },
    "gram_5": {
        "title": "أسلوب العرض والتحضيض",
        "section": "القواعد",
        "summary": "العرض طلب برفق وليونة، والتحضيض طلب بقوة وشدة. أدوات العرض: ألا، أما، لو. أدوات التحضيض: لولا، لوما، ألا، هلا.",
        "examples": ["أَلَا تُسَاعِدُ الْمُحْتَاجِينَ؟", "لَوْ تُحَارِبُ التَّنَمُّرَ", "هَلَّا تَزُورُنَا؟"]
    },
    "gram_6": {
        "title": "أسلوب النفي",
        "section": "القواعد",
        "summary": "النفي هو نفي حصول الفعل، وأدواته: ليس، غير، ما، إن، لم، لما، لن، لا النافية. وينقسم إلى نفي صريح ونفي ضمني.",
        "examples": ["لَيْسَ الْجَاهِلُ مُكَرَّماً", "مَا سَافَرَ أَخِي", "لَمْ أَذْهَبْ إِلَى الْمَدْرَسَةِ"]
    },
    "gram_7": {
        "title": "أسلوب التحذير والإغراء",
        "section": "القواعد",
        "summary": "التحذير تنبيه على أمر مكروه ليجتنبه المخاطب، والإغراء تنبيه على أمر محبوب ليفعله. من أدواتهما: إياك، الصدق الصدق، النار النار.",
        "examples": ["إِيَّاكَ وَالْكِذْبَ", "الصِّدْقَ الصِّدْقَ فَإِنَّهُ نَجَاةٌ", "النَّارَ النَّارَ"]
    },
    "gram_8": {
        "title": "أسلوب التقديم والتأخير",
        "section": "القواعد",
        "summary": "تقديم الخبر على المبتدأ أو المفعول على الفعل لأسباب بلاغية، وله مواضع يجب فيها التقديم مثل: وجود ضمير يعود على الخبر، أو كون الخبر شبه جملة والمبتدأ نكرة.",
        "examples": ["لِلْمُجْتَهِدِ نَجَاحُهُ", "عَلَى الشَّجَرَةِ طَائِرٌ", "إِيَّاكَ نَعْبُدُ"]
    },
    "gram_9": {
        "title": "أسلوب التوكيد",
        "section": "القواعد",
        "summary": "التوكيد أسلوب لتقوية الكلام ورفع الشك، أنواعه: التوكيد اللفظي (تكرار الكلمة)، والتوكيد المعنوي (نفس، عين، كل، جميع)، والتوكيد بالحروف (إن، أن، لام التوكيد، نوني التوكيد).",
        "examples": ["فَازَ فَازَ الْمُجْتَهِدُ", "جَاءَ الرَّئِيسُ نَفْسُهُ", "إِنَّ الصِّدْقَ مَنْجَاةٌ"]
    },
    "gram_10": {
        "title": "أسلوب النداء",
        "section": "القواعد",
        "summary": "النداء خطاب يوجه للمنادى ليقبل، وأدواته: يا، أيا، هيا، أي. والمنادى أنواع: المفرد العلم، والنكرة المقصودة، والمضاف، والشبيه بالمضاف.",
        "examples": ["يَا عَلِيُّ، أَقْبِلْ", "يَا رَجُلُ، اتَّقِ اللَّهَ", "يَا عِبَادَ اللَّهِ، أَطِيعُوا اللَّهَ"]
    }
}

# دمج جميع الدروس
ALL_LESSONS = {**LITERATURE_LESSONS, **GRAMMAR_LESSONS}

# ========== أقسام البوت ==========
SECTIONS = {
    "literature": {"name": "📚 دروس الأدب", "lessons": LITERATURE_LESSONS},
    "grammar": {"name": "✍️ دروس القواعد", "lessons": GRAMMAR_LESSONS},
    "all": {"name": "📖 جميع الدروس", "lessons": ALL_LESSONS}
}

# ========== وظائف البوت ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """القائمة الرئيسية"""
    keyboard = [
        [InlineKeyboardButton("📚 دروس الأدب", callback_data="section_literature")],
        [InlineKeyboardButton("✍️ دروس القواعد", callback_data="section_grammar")],
        [InlineKeyboardButton("📖 جميع الدروس", callback_data="section_all")],
    ]
    await update.message.reply_text(
        "🎓 **بوت شرح كتاب اللغة العربية - الصف السادس الإعدادي** 🎓\n\n"
        "📚 هذا البوت يحتوي على شروحات كاملة للكتابين (الجزء الأول والثاني)\n"
        "📖 أكثر من 30 درساً في الأدب والقواعد\n\n"
        "🔽 **اختر القسم الذي تريده:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def show_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض دروس القسم"""
    query = update.callback_query
    await query.answer()
    
    section_name = query.data.replace("section_", "")
    section = SECTIONS.get(section_name, SECTIONS["all"])
    
    keyboard = []
    for key, lesson in section["lessons"].items():
        keyboard.append([InlineKeyboardButton(f"📖 {lesson['title']}", callback_data=f"lesson_{key}")])
    
    keyboard.append([InlineKeyboardButton("🔙 الرجوع للقائمة الرئيسية", callback_data="back_to_start")])
    
    await query.edit_message_text(
        f"📚 **{section['name']}**\n\nاختر الدرس الذي تريد:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def show_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض تفاصيل الدرس"""
    query = update.callback_query
    await query.answer()
    
    lesson_key = query.data.replace("lesson_", "")
    
    if lesson_key not in ALL_LESSONS:
        await query.edit_message_text("❌ عذراً، هذا الدرس غير متوفر حالياً")
        return
    
    lesson = ALL_LESSONS[lesson_key]
    
    # بناء نص الدرس
    lesson_text = f"📖 **{lesson['title']}**\n\n"
    lesson_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    lesson_text += f"📂 **القسم:** {lesson['section']}\n\n"
    lesson_text += f"📝 **الملخص:**\n{lesson['summary']}\n\n"
    
    if "examples" in lesson:
        lesson_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        lesson_text += f"📌 **أمثلة:**\n"
        for ex in lesson["examples"]:
            lesson_text += f"• {ex}\n"
    
    lesson_text += f"\n✅ تم إعداد هذا الشرح بناءً على كتاب اللغة العربية للصف السادس الإعدادي"
    
    # أزرار إضافية
    keyboard = [
        [InlineKeyboardButton("🔙 الرجوع للقائمة", callback_data=f"back_to_section_{lesson['section'].split(' - ')[0] if ' - ' in lesson['section'] else lesson['section']}")],
    ]
    
    await query.edit_message_text(
        lesson_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def back_to_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرجوع إلى القسم"""
    query = update.callback_query
    await query.answer()
    
    section_name = query.data.replace("back_to_section_", "")
    
    # تحديد القسم المناسب
    if section_name == "القواعد":
        section_key = "grammar"
    elif section_name == "الأدب":
        section_key = "literature"
    else:
        section_key = "all"
    
    section = SECTIONS.get(section_key, SECTIONS["all"])
    
    keyboard = []
    for key, lesson in section["lessons"].items():
        keyboard.append([InlineKeyboardButton(f"📖 {lesson['title']}", callback_data=f"lesson_{key}")])
    
    keyboard.append([InlineKeyboardButton("🔙 الرجوع للقائمة الرئيسية", callback_data="back_to_start")])
    
    await query.edit_message_text(
        f"📚 **{section['name']}**\n\nاختر الدرس الذي تريد:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرجوع للقائمة الرئيسية"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📚 دروس الأدب", callback_data="section_literature")],
        [InlineKeyboardButton("✍️ دروس القواعد", callback_data="section_grammar")],
        [InlineKeyboardButton("📖 جميع الدروس", callback_data="section_all")],
    ]
    
    await query.edit_message_text(
        "🎓 **بوت شرح كتاب اللغة العربية - الصف السادس الإعدادي** 🎓\n\n"
        "📚 هذا البوت يحتوي على شروحات كاملة للكتابين (الجزء الأول والثاني)\n"
        "📖 أكثر من 30 درساً في الأدب والقواعد\n\n"
        "🔽 **اختر القسم الذي تريده:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ========== التشغيل ==========
def main():
    """تشغيل البوت"""
    if not TOKEN:
        logger.error("❌ لم يتم تعيين BOT_TOKEN في متغيرات البيئة")
        return
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    # إضافة المعالجات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(show_section, pattern="^section_"))
    app.add_handler(CallbackQueryHandler(show_lesson, pattern="^lesson_"))
    app.add_handler(CallbackQueryHandler(back_to_section, pattern="^back_to_section_"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    
    logger.info("✅ بوت شرح كتاب اللغة العربية يعمل!")
    logger.info(f"📚 عدد الدروس: {len(ALL_LESSONS)}")
    logger.info(f"   - دروس الأدب: {len(LITERATURE_LESSONS)}")
    logger.info(f"   - دروس القواعد: {len(GRAMMAR_LESSONS)}")
    
    app.run_polling()

if __name__ == "__main__":
    main()
