import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# تفعيل التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")

# ========== بيانات الدروس المستخرجة من الكتابين (الجزء الأول والثاني) ==========

# دروس الأدب (من كلا الجزئين)
LITERATURE_LESSONS = {
    # الوحدة الأولى - الإصلاح
    "lit_1": {
        "title": "الإصلاح ضرورة",
        "section": "الوحدة السادسة - الإصلاح",
        "summary": "الإصلاح هدف رئيس من أهداف الأنبياء والأئمة والمصلحين، والمجتمعات البشرية بحاجة دائمة إلى الإصلاح وتوجيه الناس نحو عبادة الله ومحاربة الفساد.",
        "video_url": "https://example.com/videos/lit_1.mp4",
        "images": ["img_lit_1_1.jpg", "img_lit_1_2.jpg"],
        "quiz": [
            {"q": "ما هو الهدف الرئيس من الإصلاح؟", "a": "عبادة الله ومحاربة الفساد"},
            {"q": "من هم أبرز المصلحين؟", "a": "الأنبياء والأئمة"}
        ]
    },
    "lit_2": {
        "title": "المسرحية - ثانية يجيء الحسين",
        "section": "الوحدة السادسة - الأدب",
        "summary": "المسرحية هي قصة تمثل على المسرح، والمسرحية الشعرية ظهرت في العصر الحديث، ومن روادها محمد علي الخفاجي ومسرحيته 'ثانية يجيء الحسين' التي تتناول قصة الإمام الحسين عليه السلام.",
        "video_url": "https://example.com/videos/lit_2.mp4",
        "images": ["img_lit_2_1.jpg", "img_lit_2_2.jpg", "img_lit_2_3.jpg"],
        "quiz": [
            {"q": "ما تعريف المسرحية؟", "a": "قصة تمثل على المسرح"},
            {"q": "من هو رائد المسرحية الشعرية في العراق؟", "a": "محمد علي الخفاجي"},
            {"q": "ما عنوان مسرحية الخفاجي؟", "a": "ثانية يجيء الحسين"}
        ]
    },
    
    # الوحدة الثانية - حقوق الطفل
    "lit_3": {
        "title": "لا لتعنيف الطفل",
        "section": "الوحدة السابعة - حقوق الطفل",
        "summary": "استعمال الأساليب غير الإيجابية في التعامل مثل الشدة أمر مرفوض، ولها آثار نفسية بعيدة المدى على الأطفال، والإسلام أوصى بالطفل خيراً وحث على تقبيله والترفق به.",
        "video_url": "https://example.com/videos/lit_3.mp4",
        "images": ["img_lit_3_1.jpg", "img_lit_3_2.jpg"],
        "quiz": [
            {"q": "ما هي الآثار السلبية للتعنيف على الطفل؟", "a": "آثار نفسية بعيدة المدى"},
            {"q": "ماذا قال النبي عن تقبيل الطفل؟", "a": "من قبل ولده كتب الله له حسنة"}
        ]
    },
    "lit_4": {
        "title": "القصة القصيرة - الباب الآخر",
        "section": "الوحدة السابعة - الأدب",
        "summary": "القصة القصيرة هي عمل أدبي نثري يحكي حدثاً واحداً أو حادثة محددة، ومن روادها في العراق فؤاد التكرلي وقصته 'الباب الآخر' التي تتناول العلاقة بين الأم وابنها.",
        "video_url": "https://example.com/videos/lit_4.mp4",
        "images": ["img_lit_4_1.jpg", "img_lit_4_2.jpg"],
        "quiz": [
            {"q": "ما تعريف القصة القصيرة؟", "a": "عمل أدبي نثري يحكي حدثاً واحداً"},
            {"q": "من رائد القصة القصيرة في العراق؟", "a": "فؤاد التكرلي"},
            {"q": "ما عنوان قصة فؤاد التكرلي؟", "a": "الباب الآخر"}
        ]
    },
    
    # الوحدة الثالثة - جائزة نوبل
    "lit_5": {
        "title": "جائزة نوبل للآداب",
        "section": "الوحدة الثامنة - جائزة نوبل",
        "summary": "جائزة نوبل هي جائزة سويدية أنشأها ألفريد نوبل عام 1895، تمنح في مجالات الفيزياء والكيمياء والطب والأدب والسلام، وفاز بها المصري نجيب محفوظ عام 1988.",
        "video_url": "https://example.com/videos/lit_5.mp4",
        "images": ["img_lit_5_1.jpg", "img_lit_5_2.jpg"],
        "quiz": [
            {"q": "من أنشأ جائزة نوبل؟", "a": "ألفريد نوبل"},
            {"q": "في أي عام أنشئت الجائزة؟", "a": "1895"},
            {"q": "من أول عربي فاز بجائزة نوبل في الأدب؟", "a": "نجيب محفوظ"}
        ]
    },
    "lit_6": {
        "title": "الرواية - نشأة وتطور",
        "section": "الوحدة الثامنة - الأدب",
        "summary": "الرواية عمل أدبي طويل يتناول شخصيات وأحداثاً متعددة، وتختلف عن القصة القصيرة بالطول ووفرة الشخصيات، ومن روادها في العراق محمود أحمد السيد وغائب طعمة فرمان.",
        "video_url": "https://example.com/videos/lit_6.mp4",
        "images": ["img_lit_6_1.jpg", "img_lit_6_2.jpg", "img_lit_6_3.jpg"],
        "quiz": [
            {"q": "ما الفرق بين الرواية والقصة القصيرة؟", "a": "الرواية أطول وأكثر شخصيات"},
            {"q": "من رائد الرواية في العراق؟", "a": "محمود أحمد السيد"},
            {"q": "من رواد الرواية الواقعية في العراق؟", "a": "غائب طعمة فرمان"}
        ]
    },
    "lit_7": {
        "title": "الواقعية في الأدب العربي",
        "section": "الوحدة الثامنة - النقد الأدبي",
        "summary": "الواقعية مذهب أدبي يصور الواقع كما هو، ظهرت في خمسينيات القرن العشرين، وتهتم بتصوير المجتمع وتحليل قضاياه، ومن روادها نجيب محفوظ وغائب طعمة فرمان.",
        "video_url": "https://example.com/videos/lit_7.mp4",
        "images": ["img_lit_7_1.jpg"],
        "quiz": [
            {"q": "متى ظهرت الواقعية في الأدب العربي؟", "a": "خمسينيات القرن العشرين"},
            {"q": "من رواد الواقعية في مصر؟", "a": "نجيب محفوظ"},
            {"q": "من رواد الواقعية في العراق؟", "a": "غائب طعمة فرمان"}
        ]
    },
    
    # الوحدة الرابعة - بين القديم والجديد
    "lit_8": {
        "title": "رسالة من أب إلى ابنه",
        "section": "الوحدة التاسعة - بين القديم والجديد",
        "summary": "رسالة نصح وإرشاد من أب إلى ابنه، تبين أهمية التوازن بين الماضي والحاضر، وعدم الاستهانة بتجارب الآباء، واحترام كبار السن.",
        "video_url": "https://example.com/videos/lit_8.mp4",
        "images": ["img_lit_8_1.jpg"],
        "quiz": [
            {"q": "ما هي أهم وصية في الرسالة؟", "a": "التوازن بين الماضي والحاضر"},
            {"q": "ماذا قال الله عن الوالدين؟", "a": "أمر بالإحسان إليهما"}
        ]
    },
    "lit_9": {
        "title": "المقالة - بين القديم والجديد",
        "section": "الوحدة التاسعة - الأدب",
        "summary": "المقالة قطعة نثرية تعالج موضوعاً معيناً، وهي نوعان: ذاتية (أدبية) وموضوعية (علمية)، ومن روادها الدكتور علي جواد الطاهر.",
        "video_url": "https://example.com/videos/lit_9.mp4",
        "images": ["img_lit_9_1.jpg", "img_lit_9_2.jpg"],
        "quiz": [
            {"q": "ما تعريف المقالة؟", "a": "قطعة نثرية تعالج موضوعاً معيناً"},
            {"q": "ما أنواع المقالة؟", "a": "ذاتية وموضوعية"},
            {"q": "من رواد المقالة في العراق؟", "a": "علي جواد الطاهر"}
        ]
    },
    "lit_10": {
        "title": "الكالسيكية في الأدب العربي",
        "section": "الوحدة التاسعة - النقد الأدبي",
        "summary": "الكالسيكية مذهب أدبي يعتمد على محاكاة الأدب اليوناني واللاتيني القديم، وتتميز بالعناية بالشكل واللغة الجزلة، ومن روادها محمود سامي البارودي وأحمد شوقي.",
        "video_url": "https://example.com/videos/lit_10.mp4",
        "images": ["img_lit_10_1.jpg"],
        "quiz": [
            {"q": "ما تعريف الكالسيكية؟", "a": "محاكاة الأدب اليوناني واللاتيني"},
            {"q": "من رواد الكالسيكية في الشعر العربي؟", "a": "أحمد شوقي وحافظ إبراهيم"}
        ]
    },
    
    # الوحدة الخامسة - السيرة الحسنة
    "lit_11": {
        "title": "حسن السيرة من الإيمان",
        "section": "الوحدة العاشرة - السيرة الحسنة",
        "summary": "مكارم الأخلاق من لوازم الحياة الصحيحة، وقد اتسم العرب قديماً بالكرم والشجاعة والصدق والأمانة، وبعث النبي محمد صلى الله عليه وسلم ليتمم مكارم الأخلاق.",
        "video_url": "https://example.com/videos/lit_11.mp4",
        "images": ["img_lit_11_1.jpg", "img_lit_11_2.jpg"],
        "quiz": [
            {"q": "بماذا اتسم العرب قديماً؟", "a": "الكرم والشجاعة والصدق"},
            {"q": "لماذا بعث النبي محمد؟", "a": "ليتمم مكارم الأخلاق"},
            {"q": "ماذا قال النبي عن حسن الخلق؟", "a": "إن المؤمن يدرك بحسن الخلق درجة الصائم القائم"}
        ]
    },
    "lit_12": {
        "title": "فن السيرة - الأيام لطه حسين",
        "section": "الوحدة العاشرة - الأدب",
        "summary": "السيرة فن أدبي يسرد حياة شخص، وتنقسم إلى ذاتية (يكتبها الشخص عن نفسه) وموضوعية (يكتبها عن غيره)، ومن أشهرها 'الأيام' لعميد الأدب العربي طه حسين.",
        "video_url": "https://example.com/videos/lit_12.mp4",
        "images": ["img_lit_12_1.jpg", "img_lit_12_2.jpg"],
        "quiz": [
            {"q": "ما تعريف السيرة؟", "a": "فن أدبي يسرد حياة شخص"},
            {"q": "ما أنواع السيرة؟", "a": "ذاتية وموضوعية"},
            {"q": "من صاحب كتاب الأيام؟", "a": "طه حسين"}
        ]
    },
    "lit_13": {
        "title": "الرمزية في الأدب العربي",
        "section": "الوحدة العاشرة - النقد الأدبي",
        "summary": "الرمزية ظهرت في فرنسا أواخر القرن التاسع عشر، تعتمد على الرموز والإيحاءات، ومن روادها في الأدب العربي بدر شاكر السياب وعبد الوهاب البياتي وأدونيس.",
        "video_url": "https://example.com/videos/lit_13.mp4",
        "images": ["img_lit_13_1.jpg"],
        "quiz": [
            {"q": "متى ظهرت الرمزية؟", "a": "أواخر القرن التاسع عشر"},
            {"q": "من رواد الرمزية في الأدب العربي؟", "a": "بدر شاكر السياب وأدونيس"}
        ]
    },
    
    # الوحدة السادسة - التضحية
    "lit_14": {
        "title": "التضحية من أجل الوطن",
        "section": "الوحدة الحادية عشرة - التضحية",
        "summary": "التضحية هي بذل النفس أو المال أو الوقت من أجل غاية أسمى، ومن أبرز مظاهرها تضحيات الحشد الشعبي والجيش العراقي في مواجهة الإرهاب.",
        "video_url": "https://example.com/videos/lit_14.mp4",
        "images": ["img_lit_14_1.jpg", "img_lit_14_2.jpg"],
        "quiz": [
            {"q": "ما تعريف التضحية؟", "a": "بذل النفس من أجل غاية أسمى"},
            {"q": "ما هو شعار الحشد الشعبي؟", "a": "إما النصر وإما الشهادة"}
        ]
    },
    
    # الوحدة السابعة - الأمل
    "lit_15": {
        "title": "الأمل مفتاح النجاح",
        "section": "الوحدة الثانية عشرة - الأمل",
        "summary": "الأمل هو الشعور بالتفاؤل والإيجابية تجاه الذات والآخرين، وهو عالج نفسي بديل عن الأدوية، ويموت بالأفكار السلبية والقلق المستمر.",
        "video_url": "https://example.com/videos/lit_15.mp4",
        "images": ["img_lit_15_1.jpg", "img_lit_15_2.jpg"],
        "quiz": [
            {"q": "ما تعريف الأمل؟", "a": "الشعور بالتفاؤل والإيجابية"},
            {"q": "بماذا يموت الأمل؟", "a": "بالأفكار السلبية والقلق"}
        ]
    },
    "lit_16": {
        "title": "مدرسة المهجر - ميخائيل نعيمة",
        "section": "الوحدة الثانية عشرة - الأدب",
        "summary": "مدرسة المهجر أسسها الشعراء العرب في أمريكا، ومن أبرزهم جبران خليل جبران وميخائيل نعيمة وإيليا أبو ماضي، تميزت بالحنين إلى الوطن والتأمل في الطبيعة.",
        "video_url": "https://example.com/videos/lit_16.mp4",
        "images": ["img_lit_16_1.jpg", "img_lit_16_2.jpg"],
        "quiz": [
            {"q": "ما هي مدرسة المهجر؟", "a": "جمعية أدبية أسسها العرب في أمريكا"},
            {"q": "من أبرز شعراء المهجر؟", "a": "جبران وميخائيل نعيمة"},
            {"q": "ما أبرز خصائص شعر المهجر؟", "a": "الحنين إلى الوطن والتأمل"}
        ]
    },
    
    # الوحدة الثامنة - المطر
    "lit_17": {
        "title": "المطر نعمة من الله",
        "section": "الوحدة الثالثة عشرة - المطر",
        "summary": "المطر أساس الحياة وسر ديمومتها، وهو نعمة من الله أنزلها لإنبات الزرع وسقيا الحيوان والإنسان، وقد ورد ذكره كثيراً في القرآن الكريم.",
        "video_url": "https://example.com/videos/lit_17.mp4",
        "images": ["img_lit_17_1.jpg", "img_lit_17_2.jpg"],
        "quiz": [
            {"q": "لماذا المطر أساس الحياة؟", "a": "لإنبات الزرع وسقيا الكائنات"},
            {"q": "ماذا قال الله عن المطر في القرآن؟", "a": "ونزلنا من السماء ماء مباركاً"}
        ]
    },
    "lit_18": {
        "title": "الشعر الحر - بدر شاكر السياب",
        "section": "الوحدة الثالثة عشرة - الأدب",
        "summary": "الشعر الحر أو شعر التفعيلة ظهر في أربعينيات القرن العشرين، يقوم على تفعيلة واحدة متكررة، ومن رواده بدر شاكر السياب ونازك الملائكة وعبد الوهاب البياتي.",
        "video_url": "https://example.com/videos/lit_18.mp4",
        "images": ["img_lit_18_1.jpg", "img_lit_18_2.jpg", "img_lit_18_3.jpg"],
        "quiz": [
            {"q": "متى ظهر الشعر الحر؟", "a": "أربعينيات القرن العشرين"},
            {"q": "ما أساس الشعر الحر؟", "a": "تفعيلة واحدة متكررة"},
            {"q": "من رواد الشعر الحر في العراق؟", "a": "بدر شاكر السياب"}
        ]
    },
    "lit_19": {
        "title": "شعر المقاومة الفلسطينية",
        "section": "الوحدة الرابعة عشرة - القضية الفلسطينية",
        "summary": "شعر المقاومة يوثق معاناة الشعب الفلسطيني ويحفز على النضال، ومن أبرز شعرائه محمود درويش وفدوى طوقان وسميح القاسم، ويتميز بتكريم الشهادة وإبراز أهمية التضحيات.",
        "video_url": "https://example.com/videos/lit_19.mp4",
        "images": ["img_lit_19_1.jpg", "img_lit_19_2.jpg"],
        "quiz": [
            {"q": "من أبرز شعراء المقاومة؟", "a": "محمود درويش وفدوى طوقان"},
            {"q": "بماذا يتميز شعر المقاومة؟", "a": "تكريم الشهادة والتضحيات"}
        ]
    },
    "lit_20": {
        "title": "الرومانسية في الأدب العربي",
        "section": "الوحدة الرابعة عشرة - النقد الأدبي",
        "summary": "الرومانسية تؤكد على العاطفة والشعور، وتهرب من الواقع إلى الماضي الجميل أو الطبيعة، ومن روادها في الأدب العربي مدرسة المهجر.",
        "video_url": "https://example.com/videos/lit_20.mp4",
        "images": ["img_lit_20_1.jpg"],
        "quiz": [
            {"q": "ما أساس الرومانسية؟", "a": "العاطفة والشعور"},
            {"q": "من رواد الرومانسية في الأدب العربي؟", "a": "مدرسة المهجر"}
        ]
    },
}

# دروس القواعد (من كلا الجزئين)
GRAMMAR_LESSONS = {
    "gram_1": {
        "title": "أسلوب الاستفهام",
        "section": "القواعد - الوحدة الأولى",
        "summary": "الاستفهام طلب العلم بشيء مجهول، أدواته: الهمزة، هل، من، ما، متى، أين، كيف، كم، أي. وينقسم إلى حقيقي ومجازي.",
        "video_url": "https://example.com/videos/gram_1.mp4",
        "examples": [
            "مَنْ بَنَى بَغْدَادَ؟",
            "مَا الخَبَرُ؟",
            "مَتَى عُدْتَ مِنَ السَّفَرِ؟"
        ],
        "quiz": [
            {"q": "ما هي أدوات الاستفهام؟", "a": "الهمزة، هل، من، ما، متى، أين، كيف، كم، أي"},
            {"q": "ما الفرق بين الاستفهام الحقيقي والمجازي؟", "a": "الحقيقي يحتاج جواباً، والمجازي لا يحتاج"}
        ]
    },
    "gram_2": {
        "title": "أسلوب التعجب",
        "section": "القواعد - الوحدة الأولى",
        "summary": "التعجب حالة نفسية تعبر عن الدهشة، وله صيغتان: 'ما أفعله!' للتعجب من شيء، و'أفعل به!' للتعجب من شخص.",
        "video_url": "https://example.com/videos/gram_2.mp4",
        "examples": [
            "مَا أَجْمَلَ السَّمَاءَ!",
            "أَجْمِلْ بِالرَّبِيعِ!",
            "مَا أَشَدَّ الْحَرَّ!"
        ],
        "quiz": [
            {"q": "ما هي صيغتا التعجب؟", "a": "ما أفعله، وأفعل به"},
            {"q": "مثال على التعجب من شيء؟", "a": "ما أجمل الزهور!"}
        ]
    },
    "gram_3": {
        "title": "أسلوب المدح والذم",
        "section": "القواعد - الوحدة الثانية",
        "summary": "المدح والذم من أساليب اللغة، أفعال المدح: نعم، حبذا، أفعال الذم: بئس، لا حبذا. يأتي بعدها فاعل ومخصوص بالمدح أو الذم.",
        "video_url": "https://example.com/videos/gram_3.mp4",
        "examples": [
            "نِعْمَ الرَّجُلُ مُحَمَّدٌ",
            "بِئْسَ الْخُلُقُ الْكِذْبُ",
            "حَبَّذَا الْعِلْمُ"
        ],
        "quiz": [
            {"q": "ما أفعال المدح؟", "a": "نعم، حبذا"},
            {"q": "ما أفعال الذم؟", "a": "بئس، لا حبذا"}
        ]
    },
    "gram_4": {
        "title": "أسلوب التمني والترجي",
        "section": "القواعد - الوحدة الثالثة",
        "summary": "التمني طلب أمر بعيد التحقق أو مستحيل، والترجي طلب أمر ممكن التحقق. أدواتهما: ليت (للتمني)، لعل وعسى (للترجي).",
        "video_url": "https://example.com/videos/gram_4.mp4",
        "examples": [
            "لَيْتَ الْفَقْرَ غِنًى",
            "لَعَلَّ السَّاعَةَ قَرِيبٌ",
            "عَسَى رَبِّي أَنْ يَهْدِيَنِي"
        ],
        "quiz": [
            {"q": "ما أداة التمني؟", "a": "ليت"},
            {"q": "ما أدوات الترجي؟", "a": "لعل، عسى"}
        ]
    },
    "gram_5": {
        "title": "أسلوب العرض والتحضيض",
        "section": "القواعد - الوحدة الرابعة",
        "summary": "العرض طلب برفق وليونة، والتحضيض طلب بقوة وشدة. أدوات العرض: ألا، أما، لو. أدوات التحضيض: لولا، لوما، ألا، هلا.",
        "video_url": "https://example.com/videos/gram_5.mp4",
        "examples": [
            "أَلَا تُسَاعِدُ الْمُحْتَاجِينَ؟",
            "لَوْ تُحَارِبُ التَّنَمُّرَ",
            "هَلَّا تَزُورُنَا؟"
        ],
        "quiz": [
            {"q": "ما الفرق بين العرض والتحضيض؟", "a": "العرض برفق، والتحضيض بقوة"},
            {"q": "اذكر أدوات التحضيض", "a": "لولا، لوما، ألا، هلا"}
        ]
    },
    "gram_6": {
        "title": "أسلوب النفي",
        "section": "القواعد - الوحدة الخامسة",
        "summary": "النفي هو نفي حصول الفعل، وأدواته: ليس، غير، ما، إن، لم، لما، لن، لا النافية. وينقسم إلى نفي صريح ونفي ضمني.",
        "video_url": "https://example.com/videos/gram_6.mp4",
        "examples": [
            "لَيْسَ الْجَاهِلُ مُكَرَّماً",
            "مَا سَافَرَ أَخِي",
            "لَمْ أَذْهَبْ إِلَى الْمَدْرَسَةِ"
        ],
        "quiz": [
            {"q": "ما أدوات النفي؟", "a": "ليس، ما، لم، لن، لا، غير"},
            {"q": "ما الفرق بين لم ولما؟", "a": "لم تنفي الماضي، ولما تنفي المتصل بالحاضر"}
        ]
    },
    "gram_7": {
        "title": "أسلوب التحذير والإغراء",
        "section": "القواعد - الوحدة السادسة",
        "summary": "التحذير تنبيه على أمر مكروه ليجتنبه المخاطب، والإغراء تنبيه على أمر محبوب ليفعله. من أدواتهما: إياك، الصدق الصدق، النار النار.",
        "video_url": "https://example.com/videos/gram_7.mp4",
        "examples": [
            "إِيَّاكَ وَالْكِذْبَ",
            "الصِّدْقَ الصِّدْقَ فَإِنَّهُ نَجَاةٌ",
            "النَّارَ النَّارَ"
        ],
        "quiz": [
            {"q": "ما تعريف التحذير؟", "a": "تنبيه على أمر مكروه"},
            {"q": "ما تعريف الإغراء؟", "a": "تنبيه على أمر محبوب"}
        ]
    },
    "gram_8": {
        "title": "أسلوب التقديم والتأخير",
        "section": "القواعد - الوحدة السابعة",
        "summary": "تقديم الخبر على المبتدأ أو المفعول على الفعل لأسباب بلاغية، وله مواضع يجب فيها التقديم مثل: وجود ضمير يعود على الخبر، أو كون الخبر شبه جملة والمبتدأ نكرة.",
        "video_url": "https://example.com/videos/gram_8.mp4",
        "examples": [
            "لِلْمُجْتَهِدِ نَجَاحُهُ",
            "عَلَى الشَّجَرَةِ طَائِرٌ",
            "إِيَّاكَ نَعْبُدُ"
        ],
        "quiz": [
            {"q": "متى يجب تقديم الخبر على المبتدأ؟", "a": "إذا كان المبتدأ نكرة والخبر شبه جملة"},
            {"q": "متى يجب تقديم المفعول به على الفعل؟", "a": "إذا كان ضميراً منفصلاً"}
        ]
    },
    "gram_9": {
        "title": "أسلوب التوكيد",
        "section": "القواعد - الوحدة الثامنة",
        "summary": "التوكيد أسلوب لتقوية الكلام ورفع الشك، أنواعه: التوكيد اللفظي (تكرار الكلمة)، والتوكيد المعنوي (نفس، عين، كل، جميع)، والتوكيد بالحروف (إن، أن، لام التوكيد، نوني التوكيد).",
        "video_url": "https://example.com/videos/gram_9.mp4",
        "examples": [
            "فَازَ فَازَ الْمُجْتَهِدُ",
            "جَاءَ الرَّئِيسُ نَفْسُهُ",
            "إِنَّ الصِّدْقَ مَنْجَاةٌ"
        ],
        "quiz": [
            {"q": "ما أنواع التوكيد؟", "a": "لفظي، معنوي، بالحروف"},
            {"q": "اذكر ألفاظ التوكيد المعنوي", "a": "نفس، عين، كل، جميع"}
        ]
    },
    "gram_10": {
        "title": "أسلوب النداء",
        "section": "القواعد - الوحدة التاسعة",
        "summary": "النداء خطاب يوجه للمنادى ليقبل، وأدواته: يا، أيا، هيا، أي. والمنادى أنواع: المفرد العلم، والنكرة المقصودة، والمضاف، والشبيه بالمضاف.",
        "video_url": "https://example.com/videos/gram_10.mp4",
        "examples": [
            "يَا عَلِيُّ، أَقْبِلْ",
            "يَا رَجُلُ، اتَّقِ اللَّهَ",
            "يَا عِبَادَ اللَّهِ، أَطِيعُوا اللَّهَ"
        ],
        "quiz": [
            {"q": "ما أدوات النداء؟", "a": "يا، أيا، هيا، أي"},
            {"q": "ما أنواع المنادى؟", "a": "مفرد، مضاف، شبيه بالمضاف، نكرة مقصودة"}
        ]
    },
}

# دمج جميع الدروس
ALL_LESSONS = {**LITERATURE_LESSONS, **GRAMMAR_LESSONS}

# أقسام البوت
SECTIONS = {
    "literature": {"name": "📚 دروس الأدب", "lessons": LITERATURE_LESSONS},
    "grammar": {"name": "✍️ دروس القواعد", "lessons": GRAMMAR_LESSONS},
    "all": {"name": "📖 جميع الدروس", "lessons": ALL_LESSONS}
}

# تخزين حالة المستخدم مؤقتاً
user_state = {}

# ========== وظائف البوت ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القائمة الرئيسية"""
    keyboard = [
        [InlineKeyboardButton("📚 دروس الأدب", callback_data="section_literature")],
        [InlineKeyboardButton("✍️ دروس القواعد", callback_data="section_grammar")],
        [InlineKeyboardButton("📖 جميع الدروس", callback_data="section_all")],
    ]
    
    await update.message.reply_text(
        "🎓 **بوت شرح كتاب اللغة العربية - الصف السادس الإعدادي** 🎓\n\n"
        "📚 هذا البوت يحتوي على شروحات كاملة للكتابين (الجزء الأول والثاني)\n"
        "📖 أكثر من 30 درساً في الأدب والقواعد\n"
        "🎥 كل درس يحتوي على:\n"
        "   • فيديو شرح مفصل\n"
        "   • ملخص كامل\n"
        "   • صور توضيحية\n"
        "   • اختبار تفاعلي\n\n"
        "🔽 **اختر القسم الذي تريده:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def show_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض دروس القسم المختار"""
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

async def show_lesson_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة الدرس (شرح، ملخص، اختبار، صور)"""
    query = update.callback_query
    await query.answer()
    
    lesson_key = query.data.replace("lesson_", "")
    
    if lesson_key not in ALL_LESSONS:
        await query.edit_message_text("❌ عذراً، هذا الدرس غير متوفر حالياً")
        return
    
    lesson = ALL_LESSONS[lesson_key]
    user_state[query.from_user.id] = {"lesson_key": lesson_key, "lesson": lesson}
    
    keyboard = [
        [InlineKeyboardButton("🎥 مشاهدة الفيديو", callback_data=f"action_video_{lesson_key}")],
        [InlineKeyboardButton("📝 قراءة الملخص", callback_data=f"action_summary_{lesson_key}")],
        [InlineKeyboardButton("🖼 عرض الصور التوضيحية", callback_data=f"action_images_{lesson_key}")],
        [InlineKeyboardButton("📝 اختبار تفاعلي", callback_data=f"action_quiz_{lesson_key}")],
        [InlineKeyboardButton("📥 تحميل جميع المواد", callback_data=f"action_download_{lesson_key}")],
        [InlineKeyboardButton("🔙 الرجوع للقائمة", callback_data=f"back_to_section_{lesson['section'].split(' - ')[0]}")],
    ]
    
    await query.edit_message_text(
        f"📖 **{lesson['title']}**\n\n"
        f"📂 **القسم:** {lesson['section']}\n\n"
        f"🔽 **اختر ما تريد:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إجراءات الدرس (فيديو، ملخص، اختبار، صور)"""
    query = update.callback_query
    await query.answer()
    
    action_parts = query.data.split("_")
    action = action_parts[1]
    lesson_key = "_".join(action_parts[2:])
    
    if lesson_key not in ALL_LESSONS:
        await query.edit_message_text("❌ عذراً، هذا الدرس غير متوفر")
        return
    
    lesson = ALL_LESSONS[lesson_key]
    
    if action == "video":
        await query.edit_message_text(
            f"🎥 **{lesson['title']}**\n\n"
            f"⏳ جاري تجهيز الفيديو...\n\n"
            f"📹 [رابط الفيديو]({lesson['video_url']})\n\n"
            f"💡 يمكنك تحميل الفيديو أو مشاهدته مباشرة",
            parse_mode="Markdown"
        )
    
    elif action == "summary":
        summary_text = f"📝 **ملخص درس: {lesson['title']}**\n\n"
        summary_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        summary_text += f"📖 **القسم:** {lesson['section']}\n\n"
        summary_text += f"📚 **الملخص:**\n{lesson['summary']}\n\n"
        
        if "examples" in lesson:
            summary_text += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            summary_text += f"📌 **أمثلة:**\n"
            for ex in lesson["examples"]:
                summary_text += f"• {ex}\n"
        
        summary_text += f"\n✅ تم إعداد هذا الملخص بناءً على كتاب اللغة العربية للصف السادس الإعدادي"
        
        await query.edit_message_text(summary_text, parse_mode="Markdown")
    
    elif action == "images":
        if "images" in lesson and lesson["images"]:
            await query.edit_message_text(
                f"🖼 **صور توضيحية لدرس: {lesson['title']}**\n\n"
                f"سيتم إرسال {len(lesson['images'])} صورة توضيحية...",
                parse_mode="Markdown"
            )
            for img in lesson["images"]:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=open(f"images/{img}", 'rb'),
                    caption=f"🖼 صورة توضيحية - {lesson['title']}"
                )
        else:
            await query.edit_message_text(
                f"🖼 **لا توجد صور توضيحية لهذا الدرس**\n\n"
                f"📖 يمكنك قراءة الملخص بدلاً من ذلك",
                parse_mode="Markdown"
            )
    
    elif action == "quiz":
        if "quiz" in lesson and lesson["quiz"]:
            quiz_text = f"📝 **اختبار: {lesson['title']}**\n\n"
            quiz_text += f"أجب عن الأسئلة التالية:\n\n"
            for i, q in enumerate(lesson["quiz"], 1):
                quiz_text += f"{i}. {q['q']}\n"
                quiz_text += f"   ✅ الإجابة: {q['a']}\n\n"
            
            await query.edit_message_text(quiz_text, parse_mode="Markdown")
        else:
            await query.edit_message_text(
                f"📝 **لا يوجد اختبار لهذا الدرس**\n\n"
                f"📖 يمكنك مراجعة الملخص بدلاً من ذلك",
                parse_mode="Markdown"
            )
    
    elif action == "download":
        download_text = f"📥 **تحميل مواد درس: {lesson['title']}**\n\n"
        download_text += f"📹 **فيديو الشرح:** {lesson['video_url']}\n\n"
        download_text += f"📝 **الملخص:** تم إرساله أعلاه\n\n"
        download_text += f"💾 يمكنك حفظ هذه المواد للرجوع إليها لاحقاً"
        
        await query.edit_message_text(download_text, parse_mode="Markdown")

async def back_to_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الرجوع إلى قسم الدروس"""
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
    """الرجوع إلى القائمة الرئيسية"""
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
        "📖 أكثر من 30 درساً في الأدب والقواعد\n"
        "🎥 كل درس يحتوي على:\n"
        "   • فيديو شرح مفصل\n"
        "   • ملخص كامل\n"
        "   • صور توضيحية\n"
        "   • اختبار تفاعلي\n\n"
        "🔽 **اختر القسم الذي تريده:**",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ========== التشغيل ==========
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    
    # الأوامر
    app.add_handler(CommandHandler("start", start))
    
    # معالجة الأزرار
    app.add_handler(CallbackQueryHandler(show_section, pattern="^section_"))
    app.add_handler(CallbackQueryHandler(show_lesson_menu, pattern="^lesson_"))
    app.add_handler(CallbackQueryHandler(handle_action, pattern="^action_"))
    app.add_handler(CallbackQueryHandler(back_to_section, pattern="^back_to_section_"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    
    print("=" * 70)
    print("✅ بوت شرح كتاب اللغة العربية - الصف السادس الإعدادي يعمل!")
    print(f"📚 عدد الدروس المتاحة: {len(ALL_LESSONS)}")
    print(f"   - دروس الأدب: {len(LITERATURE_LESSONS)} درساً")
    print(f"   - دروس القواعد: {len(GRAMMAR_LESSONS)} درساً")
    print("=" * 70)
    
    app.run_polling()

if __name__ == "__main__":
    main()
