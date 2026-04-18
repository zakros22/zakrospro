import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import random

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# ========== دروس الأدب (28 درساً) ==========
LITERATURE_LESSONS = {
    "lit_1": {"title": "الإصلاح ضرورة", "unit": "الوحدة السادسة"},
    "lit_2": {"title": "المسرحية - ثانية يجيء الحسين", "unit": "الوحدة السادسة"},
    "lit_3": {"title": "لا لتعنيف الطفل", "unit": "الوحدة السابعة"},
    "lit_4": {"title": "القصة القصيرة - الباب الآخر", "unit": "الوحدة السابعة"},
    "lit_5": {"title": "جائزة نوبل للآداب", "unit": "الوحدة الثامنة"},
    "lit_6": {"title": "الرواية - نشأة وتطور", "unit": "الوحدة الثامنة"},
    "lit_7": {"title": "الواقعية في الأدب العربي", "unit": "الوحدة الثامنة"},
    "lit_8": {"title": "رسالة من أب إلى ابنه", "unit": "الوحدة التاسعة"},
    "lit_9": {"title": "المقالة - بين القديم والجديد", "unit": "الوحدة التاسعة"},
    "lit_10": {"title": "الكالسيكية في الأدب العربي", "unit": "الوحدة التاسعة"},
    "lit_11": {"title": "حسن السيرة من الإيمان", "unit": "الوحدة العاشرة"},
    "lit_12": {"title": "فن السيرة - الأيام لطه حسين", "unit": "الوحدة العاشرة"},
    "lit_13": {"title": "الرمزية في الأدب العربي", "unit": "الوحدة العاشرة"},
    "lit_14": {"title": "التضحية من أجل الوطن", "unit": "الوحدة الحادية عشرة"},
    "lit_15": {"title": "الأمل مفتاح النجاح", "unit": "الوحدة الثانية عشرة"},
    "lit_16": {"title": "مدرسة المهجر - ميخائيل نعيمة", "unit": "الوحدة الثانية عشرة"},
    "lit_17": {"title": "المطر نعمة من الله", "unit": "الوحدة الثالثة عشرة"},
    "lit_18": {"title": "الشعر الحر - بدر شاكر السياب", "unit": "الوحدة الثالثة عشرة"},
    "lit_19": {"title": "شعر المقاومة الفلسطينية", "unit": "الوحدة الرابعة عشرة"},
    "lit_20": {"title": "الرومانسية في الأدب العربي", "unit": "الوحدة الرابعة عشرة"},
    "lit_21": {"title": "مدرسة الإحياء", "unit": "الوحدة الثالثة"},
    "lit_22": {"title": "الموشحات - يا غزال الكرخ", "unit": "الوحدة الثالثة"},
    "lit_23": {"title": "علي الشرقي - السيف والقلم", "unit": "الوحدة الثالثة"},
    "lit_24": {"title": "حافظ إبراهيم", "unit": "الوحدة الثالثة"},
    "lit_25": {"title": "الجواهري", "unit": "الوحدة الثالثة"},
    "lit_26": {"title": "بدر شاكر السياب", "unit": "الوحدة الثالثة عشرة"},
    "lit_27": {"title": "محمود درويش", "unit": "الوحدة الرابعة عشرة"},
    "lit_28": {"title": "فدوى طوقان", "unit": "الوحدة الرابعة عشرة"},
}

# ========== دروس القواعد (12 درساً) ==========
GRAMMAR_LESSONS = {
    "gram_1": {"title": "أسلوب الاستفهام"},
    "gram_2": {"title": "أسلوب التعجب"},
    "gram_3": {"title": "أسلوب المدح والذم"},
    "gram_4": {"title": "أسلوب التمني والترجي"},
    "gram_5": {"title": "أسلوب العرض والتحضيض"},
    "gram_6": {"title": "أسلوب النفي"},
    "gram_7": {"title": "أسلوب التحذير والإغراء"},
    "gram_8": {"title": "أسلوب التقديم والتأخير"},
    "gram_9": {"title": "أسلوب التوكيد"},
    "gram_10": {"title": "أسلوب النداء"},
    "gram_11": {"title": "أسلوب القصر"},
    "gram_12": {"title": "التوابع"},
}

# دمج جميع الدروس
ALL_LESSONS = {**LITERATURE_LESSONS, **GRAMMAR_LESSONS}

# ========== أسئلة الاختبارات ==========
QUIZZES = {
    "lit_1": {
        "questions": [
            {"q": "الإصلاح هدف رئيس من أهداف الأنبياء والأئمة", "type": "true_false", "answer": True, "correct": "صحيح"},
            {"q": "ما هو الهدف الرئيس من الإصلاح؟", "type": "text", "answer": "عبادة الله ومحاربة الفساد", "correct": "عبادة الله ومحاربة الفساد"},
            {"q": "من هم أبرز المصلحين؟", "options": ["الأنبياء", "الفلاسفة", "التجار", "الجنود"], "type": "choice", "answer": "الأنبياء", "correct": "الأنبياء"},
            {"q": "الإصلاح يبدأ من ________", "type": "fill", "answer": "النفس", "correct": "النفس"}
        ]
    },
    "lit_2": {
        "questions": [
            {"q": "المسرحية قصة تمثل على المسرح", "type": "true_false", "answer": True, "correct": "صحيح"},
            {"q": "من رائد المسرحية الشعرية في العراق؟", "type": "text", "answer": "محمد علي الخفاجي", "correct": "محمد علي الخفاجي"},
            {"q": "ما عنوان مسرحية محمد علي الخفاجي؟", "options": ["ثانية يجيء الحسين", "الباب الآخر", "الأيام", "زينب"], "type": "choice", "answer": "ثانية يجيء الحسين", "correct": "ثانية يجيء الحسين"},
            {"q": "المسرحية الشعرية ظهرت في العصر ________", "type": "fill", "answer": "الحديث", "correct": "الحديث"}
        ]
    },
    "lit_3": {
        "questions": [
            {"q": "استعمال الشدة في التعامل مع الأطفال أمر محمود", "type": "true_false", "answer": False, "correct": "خطأ"},
            {"q": "ماذا قال النبي عن تقبيل الطفل؟", "type": "text", "answer": "من قبل ولده كتب الله له حسنة", "correct": "من قبل ولده كتب الله له حسنة"},
            {"q": "من قال: 'لا تقسروا أولادكم على آدابكم'؟", "options": ["الإمام علي", "الإمام الحسين", "النبي محمد", "الإمام الصادق"], "type": "choice", "answer": "الإمام علي", "correct": "الإمام علي"},
            {"q": "التعنيف يترك آثاراً ________ على الطفل", "type": "fill", "answer": "نفسية", "correct": "نفسية"}
        ]
    },
    "lit_4": {
        "questions": [
            {"q": "القصة القصيرة عمل أدبي طويل", "type": "true_false", "answer": False, "correct": "خطأ"},
            {"q": "من رائد القصة القصيرة في العراق؟", "type": "text", "answer": "فؤاد التكرلي", "correct": "فؤاد التكرلي"},
            {"q": "ما عنوان قصة فؤاد التكرلي؟", "options": ["الباب الآخر", "ثانية يجيء الحسين", "الأيام", "زينب"], "type": "choice", "answer": "الباب الآخر", "correct": "الباب الآخر"},
            {"q": "القصة القصيرة تحكي حدثاً ________", "type": "fill", "answer": "واحداً", "correct": "واحداً"}
        ]
    },
    "gram_1": {
        "questions": [
            {"q": "الاستفهام طلب العلم بشيء مجهول", "type": "true_false", "answer": True, "correct": "صحيح"},
            {"q": "من أدوات الاستفهام التي تسأل عن العاقل؟", "type": "text", "answer": "من", "correct": "من"},
            {"q": "ما الأداة المناسبة للسؤال عن المكان؟", "options": ["متى", "أين", "كيف", "كم"], "type": "choice", "answer": "أين", "correct": "أين"},
            {"q": "أداة الاستفهام ________ تسأل عن غير العاقل", "type": "fill", "answer": "ما", "correct": "ما"}
        ]
    },
    "gram_2": {
        "questions": [
            {"q": "التعجب له صيغتان: ما أفعله! وأفعل به!", "type": "true_false", "answer": True, "correct": "صحيح"},
            {"q": "ماذا نقول للتعجب من شيء؟", "type": "text", "answer": "ما أجمله", "correct": "ما أجمله"},
            {"q": "أي الجمل التالية صيغة تعجب؟", "options": ["ما أجمل السماء", "السماء جميلة", "أحب السماء", "السماء زرقاء"], "type": "choice", "answer": "ما أجمل السماء", "correct": "ما أجمل السماء"},
            {"q": "صيغة التعجب للشخص هي ________ به", "type": "fill", "answer": "أفعل", "correct": "أفعل"}
        ]
    },
}

# تخزين نتائج الاختبارات
user_quiz_results = {}

# ========== الأزرار ==========
main_keyboard = [
    [InlineKeyboardButton("📚 دروس الأدب", callback_data="section_literature")],
    [InlineKeyboardButton("✍️ دروس القواعد", callback_data="section_grammar")],
]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎓 **مرحباً بك في بوت شرح الأدب العربي!** 🎓\n\n"
        "📚 هذا البوت يحتوي على:\n"
        "• 28 درساً في الأدب\n"
        "• 12 درساً في القواعد\n\n"
        "🔽 **اختر القسم الذي تريد:**",
        reply_markup=InlineKeyboardMarkup(main_keyboard),
        parse_mode="Markdown"
    )

async def show_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    section = query.data.replace("section_", "")
    
    if section == "literature":
        lessons = LITERATURE_LESSONS
        title = "📚 دروس الأدب"
    else:
        lessons = GRAMMAR_LESSONS
        title = "✍️ دروس القواعد"
    
    keyboard = []
    for key, lesson in lessons.items():
        keyboard.append([InlineKeyboardButton(f"📖 {lesson['title']}", callback_data=f"lesson_{key}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
    
    await query.edit_message_text(
        f"{title}\n\nاختر الدرس:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_lesson_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lesson_key = query.data.replace("lesson_", "")
    
    if lesson_key not in ALL_LESSONS:
        await query.edit_message_text("❌ درس غير موجود")
        return
    
    lesson = ALL_LESSONS[lesson_key]
    
    keyboard = [
        [InlineKeyboardButton("🎥 فيديو الشرح", callback_data=f"video_{lesson_key}")],
        [InlineKeyboardButton("📝 ملخص PDF", callback_data=f"pdf_{lesson_key}")],
        [InlineKeyboardButton("📝 اختبار", callback_data=f"quiz_{lesson_key}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back")],
    ]
    
    unit_text = f"📂 {lesson['unit']}\n\n" if "unit" in lesson else ""
    
    await query.edit_message_text(
        f"📖 **{lesson['title']}**\n\n"
        f"{unit_text}"
        f"🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lesson_key = query.data.replace("video_", "")
    lesson = ALL_LESSONS[lesson_key]
    
    # هنا رابط الفيديو - يجب وضع الرابط الحقيقي
    video_text = f"""🎥 **فيديو شرح: {lesson['title']}**

📖 **محتوى الفيديو:**
━━━━━━━━━━━━━━━━━━━━━━
📌 **المقدمة:** تعريف عام بالدرس وأهميته

📌 **الأقسام:**
• القسم الأول: شرح المفاهيم الأساسية
• القسم الثاني: تحليل الموضوع
• القسم الثالث: الأمثلة والتطبيقات

📌 **الخاتمة:** ملخص الفيديو

━━━━━━━━━━━━━━━━━━━━━━
📹 [رابط الفيديو](https://youtube.com/...)

✅ يمكنك مشاهدة الفيديو للاستفادة أكثر"""
    
    await query.edit_message_text(video_text, parse_mode="Markdown")

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lesson_key = query.data.replace("pdf_", "")
    lesson = ALL_LESSONS[lesson_key]
    
    pdf_text = f"""📝 **ملخص درس: {lesson['title']}**

━━━━━━━━━━━━━━━━━━━━━━
📚 **الملخص:**

{get_summary(lesson_key)}

━━━━━━━━━━━━━━━━━━━━━━
✅ يمكنك حفظ هذا الملخص للمراجعة

📥 **لتحميل ملف PDF:** [رابط التحميل]"""
    
    await query.edit_message_text(pdf_text, parse_mode="Markdown")

def get_summary(lesson_key):
    """إرجاع ملخص الدرس"""
    summaries = {
        "lit_1": "الإصلاح هو هدف رئيس من أهداف الأنبياء والأئمة، والمجتمعات البشرية بحاجة دائمة إلى الإصلاح وتوجيه الناس نحو عبادة الله ومحاربة الفساد وإشاعة القيم والمثل العليا.",
        "lit_2": "المسرحية هي قصة تمثل على المسرح، والمسرحية الشعرية ظهرت في العصر الحديث، ومن روادها محمد علي الخفاجي ومسرحيته 'ثانية يجيء الحسين'.",
        "lit_3": "استعمال الأساليب غير الإيجابية في التعامل مثل الشدة أمر مرفوض، ولها آثار نفسية بعيدة المدى على الأطفال، والإسلام أوصى بالطفل خيراً.",
        "lit_4": "القصة القصيرة هي عمل أدبي نثري يحكي حدثاً واحداً، ومن روادها في العراق فؤاد التكرلي وقصته 'الباب الآخر'.",
        "gram_1": "الاستفهام طلب العلم بشيء مجهول، أدواته: الهمزة، هل، من، ما، متى، أين، كيف، كم، أي.",
        "gram_2": "التعجب حالة نفسية تعبر عن الدهشة، وله صيغتان: 'ما أفعله!' للتعجب من شيء، و'أفعل به!' للتعجب من شخص.",
    }
    return summaries.get(lesson_key, "ملخص الدرس غير متوفر حالياً")

async def handle_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lesson_key = query.data.replace("quiz_", "")
    
    if lesson_key not in QUIZZES:
        await query.edit_message_text("📝 **لا يوجد اختبار لهذا الدرس حالياً**\n\nسيتم إضافة اختبار قريباً")
        return
    
    quiz = QUIZZES[lesson_key]
    user_id = query.from_user.id
    
    # تخزين بداية الاختبار
    user_quiz_results[user_id] = {
        "lesson_key": lesson_key,
        "current_question": 0,
        "score": 0,
        "questions": quiz["questions"]
    }
    
    await send_question(update, context, user_id, query)

async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, query):
    """إرسال سؤال الاختبار"""
    quiz_data = user_quiz_results.get(user_id)
    if not quiz_data:
        return
    
    current = quiz_data["current_question"]
    questions = quiz_data["questions"]
    
    if current >= len(questions):
        # انتهى الاختبار
        score = quiz_data["score"]
        total = len(questions)
        percentage = (score / total) * 100
        
        result_text = f"📊 **نتيجة الاختبار**\n\n"
        result_text += f"✅ الإجابات الصحيحة: {score}/{total}\n"
        result_text += f"📈 النسبة: {percentage}%\n\n"
        
        if percentage >= 80:
            result_text += "🎉 ممتاز! أبدعت!"
        elif percentage >= 60:
            result_text += "👍 جيد، حاول مرة أخرى لتحسين نتيجتك"
        else:
            result_text += "📚 راجع الدرس ثم حاول مرة أخرى"
        
        await query.edit_message_text(result_text, parse_mode="Markdown")
        del user_quiz_results[user_id]
        return
    
    q = questions[current]
    
    if q["type"] == "true_false":
        keyboard = [
            [InlineKeyboardButton("✅ صحيح", callback_data=f"quiz_answer_true")],
            [InlineKeyboardButton("❌ خطأ", callback_data=f"quiz_answer_false")],
        ]
        text = f"📝 **السؤال {current + 1}/{len(questions)}**\n\n{q['q']}"
        
    elif q["type"] == "choice":
        keyboard = []
        for option in q["options"]:
            keyboard.append([InlineKeyboardButton(option, callback_data=f"quiz_answer_{option}")])
        text = f"📝 **السؤال {current + 1}/{len(questions)}**\n\n{q['q']}"
        
    elif q["type"] == "text":
        keyboard = [[InlineKeyboardButton("📝 أكتب إجابتك", callback_data="noop")]]
        text = f"📝 **السؤال {current + 1}/{len(questions)}**\n\n{q['q']}\n\n✏️ أرسل إجابتك في رسالة نصية"
        await query.edit_message_text(text, parse_mode="Markdown")
        return
        
    elif q["type"] == "fill":
        keyboard = [[InlineKeyboardButton("📝 أكمل الفراغ", callback_data="noop")]]
        text = f"📝 **السؤال {current + 1}/{len(questions)}**\n\n{q['q']}\n\n✏️ أرسل إجابتك في رسالة نصية"
        await query.edit_message_text(text, parse_mode="Markdown")
        return
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    quiz_data = user_quiz_results.get(user_id)
    
    if not quiz_data:
        await query.edit_message_text("❌ لا يوجد اختبار نشط")
        return
    
    current = quiz_data["current_question"]
    questions = quiz_data["questions"]
    q = questions[current]
    
    answer_data = query.data.replace("quiz_answer_", "")
    
    # تصحيح الإجابة
    is_correct = False
    if q["type"] == "true_false":
        user_answer = answer_data == "true"
        is_correct = (user_answer == q["answer"])
    elif q["type"] == "choice":
        is_correct = (answer_data == q["answer"])
    
    if is_correct:
        quiz_data["score"] += 1
        await query.answer("✅ إجابة صحيحة!")
    else:
        correct_text = q.get("correct", q.get("answer", "غير معروف"))
        await query.answer(f"❌ إجابة خاطئة! الإجابة الصحيحة: {correct_text}")
    
    quiz_data["current_question"] += 1
    
    # إرسال السؤال التالي
    await send_question(update, context, user_id, query)

async def handle_text_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الإجابات النصية (فراغات وأسئلة مقالية)"""
    user_id = update.effective_user.id
    quiz_data = user_quiz_results.get(user_id)
    
    if not quiz_data:
        return
    
    current = quiz_data["current_question"]
    questions = quiz_data["questions"]
    
    if current >= len(questions):
        return
    
    q = questions[current]
    user_answer = update.message.text.strip()
    
    # تصحيح الإجابة
    is_correct = (user_answer.lower() == q["answer"].lower())
    
    if is_correct:
        quiz_data["score"] += 1
        await update.message.reply_text(f"✅ إجابة صحيحة!\n\nإجابتك: {user_answer}")
    else:
        await update.message.reply_text(f"❌ إجابة خاطئة!\n\nالإجابة الصحيحة: {q['correct']}\n\nإجابتك: {user_answer}")
    
    quiz_data["current_question"] += 1
    
    # إرسال السؤال التالي
    # نحتاج إلى إنشاء callback query وهمي
    class MockQuery:
        def __init__(self, message):
            self.message = message
        async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
            pass
        async def answer(self):
            pass
    
    mock_query = MockQuery(update.message)
    await send_question(update, context, user_id, mock_query)

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎓 **مرحباً بك في بوت شرح الأدب العربي!** 🎓\n\n"
        "📚 هذا البوت يحتوي على:\n"
        "• 28 درساً في الأدب\n"
        "• 12 درساً في القواعد\n\n"
        "🔽 **اختر القسم الذي تريد:**",
        reply_markup=InlineKeyboardMarkup(main_keyboard),
        parse_mode="Markdown"
    )

# ========== التشغيل ==========
def main():
    if not TOKEN:
        logger.error("❌ BOT_TOKEN غير موجود!")
        return
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(show_section, pattern="^section_"))
    app.add_handler(CallbackQueryHandler(show_lesson_menu, pattern="^lesson_"))
    app.add_handler(CallbackQueryHandler(handle_video, pattern="^video_"))
    app.add_handler(CallbackQueryHandler(handle_pdf, pattern="^pdf_"))
    app.add_handler(CallbackQueryHandler(handle_quiz, pattern="^quiz_"))
    app.add_handler(CallbackQueryHandler(handle_quiz_answer, pattern="^quiz_answer_"))
    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_answer))
    
    logger.info("✅ البوت يعمل!")
    logger.info(f"📚 عدد الدروس: {len(ALL_LESSONS)}")
    
    app.run_polling()

if __name__ == "__main__":
    from telegram.ext import MessageHandler, filters
    main()
