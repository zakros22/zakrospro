# ai_analyzer.py - تعديل جزء الصور

import requests
from PIL import Image
from io import BytesIO
import uuid

def _fetch_pollinations_image_sync(keyword: str, specialty: str = None) -> Optional[Path]:
    """جلب صورة من Pollinations.ai (متزامن)"""
    try:
        if specialty:
            prompt = f"medical illustration of {keyword} for {specialty} education, clean professional style"
        else:
            prompt = f"medical illustration of {keyword}, educational diagram, clean style"
        
        url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}"
        url += "?width=640&height=480&nologo=true"
        
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            file_path = config.IMAGES_TMP / f"pollinations_{uuid.uuid4().hex[:8]}.png"
            img.save(file_path, "PNG")
            logger.info(f"✅ تم جلب صورة من Pollinations: {keyword}")
            return file_path
    except Exception as e:
        logger.debug(f"Pollinations فشل: {e}")
    return None

def _fetch_unsplash_image_sync(keyword: str) -> Optional[Path]:
    """جلب صورة من Unsplash (متزامن)"""
    if not config.UNSPLASH_ACCESS_KEY:
        return None
    try:
        headers = {"Authorization": f"Client-ID {config.UNSPLASH_ACCESS_KEY}"}
        params = {
            "query": f"{keyword} medical",
            "orientation": "landscape",
            "per_page": 1
        }
        response = requests.get("https://api.unsplash.com/search/photos",
                                headers=headers, params=params, timeout=20)
        if response.status_code == 200:
            data = response.json()
            if data["results"]:
                img_url = data["results"][0]["urls"]["regular"]
                img_response = requests.get(img_url, timeout=20)
                img = Image.open(BytesIO(img_response.content))
                img = img.resize((640, 480), Image.Resampling.LANCZOS)
                file_path = config.IMAGES_TMP / f"unsplash_{uuid.uuid4().hex[:8]}.jpg"
                img.save(file_path, "JPEG")
                logger.info(f"✅ تم جلب صورة من Unsplash: {keyword}")
                return file_path
    except Exception as e:
        logger.debug(f"Unsplash فشل: {e}")
    return None

def _fetch_picsum_image_sync() -> Optional[Path]:
    """جلب صورة عشوائية من Lorem Picsum (متزامن)"""
    try:
        response = requests.get("https://picsum.photos/640/480", timeout=15)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            file_path = config.IMAGES_TMP / f"picsum_{uuid.uuid4().hex[:8]}.jpg"
            img.save(file_path, "JPEG")
            logger.info(f"✅ تم جلب صورة من Picsum")
            return file_path
    except Exception as e:
        logger.debug(f"Picsum فشل: {e}")
    return None

def fetch_image_for_keyword(keyword: str, specialty: str = None) -> Path:
    """
    الدالة الرئيسية لجلب صورة لقسم معين (متزامنة بالكامل).
    تجرب Pollinations -> Unsplash -> Picsum -> صورة مولدة.
    """
    # محاولة Pollinations
    img = _fetch_pollinations_image_sync(keyword, specialty)
    if img:
        return img

    # محاولة Unsplash
    img = _fetch_unsplash_image_sync(keyword)
    if img:
        return img

    # محاولة Picsum
    img = _fetch_picsum_image_sync()
    if img:
        return img

    # الصورة الاحتياطية
    return _make_medical_image(keyword, specialty)

# ==================== دوال تنظيف النصوص ====================

def clean_text(text: str) -> str:
    """
    تنظيف النص من الأحرف غير المرغوبة:
    - null bytes
    - أحرف التحكم
    - المسافات الزائدة
    - ترميز موحد
    """
    if not text:
        return ""

    # إزالة null bytes
    text = text.replace('\x00', '')

    # إزالة أحرف التحكم (عدا الأسطر الجديدة والمسافات)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # استبدال أنواع المسافات المختلفة بمسافة عادية
    text = re.sub(r'\s+', ' ', text)

    # إزالة المسافات في بداية ونهاية النص
    text = text.strip()

    # إصلاح مشاكل الترميز العربية الشائعة
    replacements = {
        'أ': 'ا',  # توحيد الألف
        'إ': 'ا',
        'آ': 'ا',
        'ة': 'ه',  # توحيد التاء المربوطة (اختياري)
        'ى': 'ي',  # توحيد الياء
    }
    # يمكن تفعيلها حسب الحاجة

    return text

def extract_full_text_from_pdf(file_path: Path) -> Tuple[str, int]:
    """
    استخراج النص الكامل من ملف PDF.
    تحاول أولاً استخدام pdfplumber، ثم PyPDF2.
    ترجع (النص, عدد الصفحات)
    تستخدم timeout لمنع التعليق.
    """
    text = ""
    pages_count = 0

    # المحاولة الأولى: pdfplumber
    if pdfplumber:
        try:
            with pdfplumber.open(file_path) as pdf:
                pages_count = len(pdf.pages)
                all_text = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        all_text.append(page_text)
                text = "\n".join(all_text)
                if len(text.strip()) > 100:
                    logger.info(f"تم استخراج {len(text)} حرف من PDF باستخدام pdfplumber")
                    return clean_text(text), pages_count
        except Exception as e:
            logger.warning(f"فشل pdfplumber: {e}")

    # المحاولة الثانية: PyPDF2
    if PyPDF2:
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                pages_count = len(reader.pages)
                all_text = []
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        all_text.append(page_text)
                text = "\n".join(all_text)
                logger.info(f"تم استخراج {len(text)} حرف من PDF باستخدام PyPDF2")
                return clean_text(text), pages_count
        except Exception as e:
            logger.error(f"فشل PyPDF2: {e}")

    # إذا فشل كل شيء
    if not text:
        raise ValueError("تعذر استخراج النص من ملف PDF. تأكد من أن الملف غير مشفر أو تالف.")

    return clean_text(text), pages_count

# ==================== قوائم المصطلحات الطبية ====================

# قاموس ضخم للمصطلحات الطبية بالعربية والإنجليزية
MEDICAL_TERMS_AR = {
    "الأمراض": ["السكري", "ارتفاع ضغط الدم", "السرطان", "الربو", "التهاب", "فشل قلبي", "تليف",
                "عدوى", "ورم", "خثار", "نزيف", "صدمة", "حساسية", "مناعة ذاتية", "تصلب", "تشمع"],
    "التشريح": ["القلب", "الرئة", "الكبد", "الكلى", "المعدة", "الأمعاء", "الدماغ", "الأعصاب",
                "الشرايين", "الأوردة", "العظام", "المفاصل", "العضلات", "الجلد", "العين", "الأذن"],
    "الأعراض": ["ألم", "حمى", "سعال", "ضيق تنفس", "غثيان", "إسهال", "إمساك", "دوخة", "صداع",
                "تعب", "فقدان وزن", "طفح", "حكة", "تورم", "نزيف", "تشنجات"],
    "الأدوية": ["مضاد حيوي", "مسكن", "مضاد التهاب", "مدر بول", "خافض ضغط", "منظم سكر",
                "كورتيزون", "علاج كيماوي", "مضاد فيروسات", "مضاد فطريات"],
    "الإجراءات": ["جراحة", "تنظير", "قسطرة", "خزعة", "تصوير", "رنين مغناطيسي", "أشعة", "تحليل دم",
                  "تخطيط قلب", "علاج طبيعي", "غسيل كلوي"],
}

MEDICAL_TERMS_EN = {
    "diseases": ["diabetes", "hypertension", "cancer", "asthma", "inflammation", "heart failure",
                 "fibrosis", "infection", "tumor", "thrombosis", "hemorrhage", "shock", "allergy",
                 "autoimmune", "sclerosis", "cirrhosis"],
    "anatomy": ["heart", "lung", "liver", "kidney", "stomach", "intestine", "brain", "nerves",
                "arteries", "veins", "bones", "joints", "muscles", "skin", "eye", "ear"],
    "symptoms": ["pain", "fever", "cough", "dyspnea", "nausea", "diarrhea", "constipation",
                 "dizziness", "headache", "fatigue", "weight loss", "rash", "itching", "edema",
                 "bleeding", "seizures"],
    "medications": ["antibiotic", "analgesic", "anti-inflammatory", "diuretic", "antihypertensive",
                    "antidiabetic", "corticosteroid", "chemotherapy", "antiviral", "antifungal"],
    "procedures": ["surgery", "endoscopy", "catheterization", "biopsy", "imaging", "MRI", "X-ray",
                   "blood test", "ECG", "physiotherapy", "dialysis"],
}

# كلمات مفتاحية للتخصصات
SPECIALTY_KEYWORDS = {
    "cardiology": ["قلب", "شرايين", "صمام", "ذبحة", "جلطة قلب", "تخطيط قلب", "heart", "cardiac", "coronary"],
    "pulmonology": ["رئة", "تنفس", "ربو", "سعال", "قصبات", "lung", "pulmonary", "respiratory"],
    "neurology": ["دماغ", "أعصاب", "شلل", "صرع", "باركنسون", "brain", "nerve", "neurology", "seizure"],
    "gastroenterology": ["معدة", "أمعاء", "كبد", "هضم", "قولون", "stomach", "intestine", "liver", "digestive"],
    "nephrology": ["كلى", "بول", "غسيل", "kidney", "renal", "nephrology"],
    "endocrinology": ["غدد", "هرمون", "سكري", "درقية", "endocrine", "diabetes", "thyroid"],
    "oncology": ["ورم", "سرطان", "علاج كيماوي", "cancer", "tumor", "oncology"],
    # ... يمكن إضافة المزيد
}

# ==================== دوال الذكاء الاصطناعي ====================

def _call_deepseek(prompt: str, api_key: str, timeout: int = 60) -> Optional[Dict]:
    """الاتصال بـ DeepSeek API"""
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": config.AI_TEMPERATURE,
            "max_tokens": config.AI_MAX_TOKENS,
            "response_format": {"type": "json_object"}
        }
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=timeout
        )
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            logger.warning(f"DeepSeek API خطأ {response.status_code}: {response.text}")
    except Exception as e:
        logger.error(f"DeepSeek استثناء: {e}")
    return None

def _call_gemini(prompt: str, api_key: str) -> Optional[Dict]:
    """الاتصال بـ Google Gemini API"""
    if not genai:
        logger.error("مكتبة google-generativeai غير مثبتة")
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        # نطلب JSON بشكل صريح
        full_prompt = f"{prompt}\n\nPlease respond with valid JSON only, no markdown formatting."
        response = model.generate_content(full_prompt)
        text = response.text
        # تنظيف JSON من علامات markdown المحتملة
        text = re.sub(r'```json\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        return json.loads(text)
    except Exception as e:
        logger.error(f"Gemini استثناء: {e}")
    return None

def _call_groq(prompt: str, api_key: str) -> Optional[Dict]:
    """الاتصال بـ Groq API"""
    if not Groq:
        logger.error("مكتبة groq غير مثبتة")
        return None
    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=config.AI_TEMPERATURE,
            max_tokens=config.AI_MAX_TOKENS,
            response_format={"type": "json_object"}
        )
        content = completion.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        logger.error(f"Groq استثناء: {e}")
    return None

def _call_ai(prompt: str) -> Dict:
    """
    استدعاء الذكاء الاصطناعي مع آلية احتياطية:
    DeepSeek -> Gemini -> Groq -> fallback
    تجرب المفاتيح المتعددة لكل مزود
    """
    # تجربة DeepSeek
    for key in config.DEEPSEEK_KEYS:
        result = _call_deepseek(prompt, key)
        if result:
            logger.info("تم استخدام DeepSeek بنجاح")
            return result

    # تجربة Gemini
    for key in config.GEMINI_KEYS:
        result = _call_gemini(prompt, key)
        if result:
            logger.info("تم استخدام Gemini بنجاح")
            return result

    # تجربة Groq
    for key in config.GROQ_KEYS:
        result = _call_groq(prompt, key)
        if result:
            logger.info("تم استخدام Groq بنجاح")
            return result

    # إذا فشل الكل، نرفع استثناء لاستخدام fallback
    raise Exception("فشلت جميع محاولات الاتصال بالذكاء الاصطناعي")

# ==================== استخراج المصطلحات وتحديد التخصص ====================

def _extract_medical_terms(text: str, max_terms: int = 30) -> List[str]:
    """
    استخراج المصطلحات الطبية من النص.
    تستخدم القوائم المضمنة مع وزن أعلى للمصطلحات الطبية.
    """
    text_lower = text.lower()
    terms_found = set()

    # البحث في القوائم العربية
    for category, terms in MEDICAL_TERMS_AR.items():
        for term in terms:
            if term in text:
                terms_found.add(term)

    # البحث في القوائم الإنجليزية
    for category, terms in MEDICAL_TERMS_EN.items():
        for term in terms:
            if term.lower() in text_lower:
                terms_found.add(term)

    # البحث عن كلمات بحروف كبيرة (مصطلحات إنجليزية غالباً)
    uppercase_terms = re.findall(r'\b[A-Z][a-z]*(?:\s+[A-Z][a-z]*)*\b', text)
    for term in uppercase_terms:
        if len(term) > 3 and term.lower() not in ['the', 'and', 'for', 'with']:
            terms_found.add(term)

    # ترتيب المصطلحات حسب تكرارها (تقريبي)
    term_scores = {}
    for term in terms_found:
        count = text_lower.count(term.lower())
        # وزن إضافي للمصطلحات الطبية المعروفة
        bonus = 2 if any(term in med_list for med_list in MEDICAL_TERMS_AR.values()) else 0
        term_scores[term] = count + bonus

    sorted_terms = sorted(term_scores.items(), key=lambda x: x[1], reverse=True)
    return [term for term, _ in sorted_terms[:max_terms]]

def _detect_medical_specialty(text: str) -> Tuple[str, float]:
    """
    تحديد التخصص الطبي الدقيق للمحاضرة.
    ترجع (التخصص, درجة الثقة)
    """
    text_lower = text.lower()
    scores = {}
    for specialty, keywords in SPECIALTY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            count = text_lower.count(kw.lower())
            score += count
        if score > 0:
            scores[specialty] = score

    if not scores:
        return "general", 0.0

    best_specialty = max(scores, key=scores.get)
    confidence = scores[best_specialty] / sum(scores.values()) if scores else 0.0
    return best_specialty, confidence

def _determine_num_sections(text_length: int, density: float = None) -> int:
    """تحديد عدد الأقسام بناءً على طول النص وكثافة المعلومات"""
    if text_length < 500:
        return 2
    elif text_length < 1500:
        return 3
    elif text_length < 3000:
        return 4
    elif text_length < 6000:
        return 5
    elif text_length < 10000:
        return 6
    else:
        return min(8, text_length // 2000)

# ==================== توليد محتوى احتياطي ====================

def _generate_medical_fallback(text: str, language: str, dialect: str, num_sections: int) -> Dict:
    """
    توليد شرح طبي احتياطي في حالة فشل جميع خدمات الذكاء الاصطناعي.
    تستخدم قوالب جاهزة بالعربية والإنجليزية.
    """
    terms = _extract_medical_terms(text, 20)
    specialty, _ = _detect_medical_specialty(text)
    specialty_name = config.MEDICAL_SPECIALTIES.get(specialty, "طب عام")

    # توليد عنوان
    if terms:
        title = f"شرح مبسط: {terms[0]}"
    else:
        title = "محاضرة طبية تعليمية"

    sections = []
    section_templates = [
        ("المقدمة والتعريف", "في هذا القسم سنتعرف على المفاهيم الأساسية للحالة الطبية ونقدم نظرة عامة شاملة."),
        ("الآلية المرضية", "سنشرح في هذا القسم الآلية التي تحدث بها المشكلة على المستوى الخلوي والجزيئي."),
        ("الأعراض والعلامات", "سنتناول الأعراض الشائعة والعلامات السريرية التي تظهر على المريض."),
        ("التشخيص", "نستعرض طرق التشخيص المختلفة بما فيها الفحوصات المخبرية والتصويرية."),
        ("العلاج", "نناقش الخيارات العلاجية المتاحة والأدوية المستخدمة."),
        ("المضاعفات والوقاية", "نتحدث عن المضاعفات المحتملة وطرق الوقاية منها."),
    ]

    for i in range(min(num_sections, len(section_templates))):
        heading, template = section_templates[i]
        # إضافة مصطلحات طبية للقسم
        section_terms = terms[i*3:(i+1)*3] if terms else ["طبي", "صحي"]
        content = f"{template} تشمل النقاط المهمة: " + "، ".join(section_terms) + "."
        sections.append({
            "heading": heading,
            "content": content,
            "keywords": section_terms[:4] if len(section_terms) >= 4 else section_terms + ["طبي"] * (4 - len(section_terms))
        })

    return {
        "title": title,
        "specialty": specialty_name,
        "language": language,
        "dialect": dialect,
        "sections": sections,
        "fallback": True
    }

# ==================== الدالة الرئيسية لتحليل المحاضرة ====================

def _build_prompt(text: str, language: str, dialect: str, num_sections: int,
                  specialty: str, terms: List[str]) -> str:
    """بناء الـ Prompt المناسب حسب اللغة واللهجة"""
    
    specialty_name = config.MEDICAL_SPECIALTIES.get(specialty, "طب عام")
    
    if language == "ar":
        base_prompt = f"""أنت محاضر طبي خبير ومتخصص في {specialty_name}.
قم بتحليل النص الطبي التالي وإنشاء محاضرة تعليمية منظمة بأسلوب سلس وواضح.
استخدم {dialect} في الشرح مع الحفاظ على الدقة العلمية.

النص الطبي:
{text[:4000]}...

المطلوب:
1. اقترح عنواناً جذاباً ودقيقاً للمحاضرة (بالعربية).
2. قسم المحتوى إلى {num_sections} أقسام رئيسية.
3. لكل قسم، قدم:
   - عنوان فرعي واضح (heading)
   - شرح مفصل ومبسط (content) بطول مناسب (150-300 كلمة)
   - 4 كلمات مفتاحية (keywords) تمثل أهم المفاهيم في هذا القسم

المصطلحات الطبية المستخرجة من النص: {', '.join(terms[:15])}

أعد الرد بصيغة JSON صالحة فقط، بدون أي نص إضافي، بالشكل التالي:
{{
    "title": "عنوان المحاضرة",
    "sections": [
        {{
            "heading": "عنوان القسم الأول",
            "content": "محتوى الشرح المفصل...",
            "keywords": ["كلمة1", "كلمة2", "كلمة3", "كلمة4"]
        }}
    ]
}}
"""
    else:
        base_prompt = f"""You are an expert medical lecturer specializing in {specialty_name}.
Analyze the following medical text and create a structured educational lecture.
Use clear and engaging language.

Medical Text:
{text[:4000]}...

Requirements:
1. Suggest an accurate and engaging title.
2. Divide the content into {num_sections} main sections.
3. For each section, provide:
   - A clear heading
   - Detailed explanation (150-300 words)
   - 4 keywords representing key concepts

Extracted medical terms: {', '.join(terms[:15])}

Respond with valid JSON only, no extra text:
{{
    "title": "Lecture Title",
    "sections": [
        {{
            "heading": "Section Heading",
            "content": "Detailed explanation...",
            "keywords": ["keyword1", "keyword2", "keyword3", "keyword4"]
        }}
    ]
}}
"""
    return base_prompt


def analyze_lecture(text: str, language: str = "ar", dialect: str = "fusha",
                    force_specialty: str = None) -> Dict[str, Any]:
    """
    الدالة الرئيسية لتحليل المحاضرة الطبية.
    
    المعاملات:
        text: النص الطبي المراد تحليله
        language: لغة النص ('ar' أو 'en')
        dialect: اللهجة المطلوبة للشرح العربي
        force_specialty: تخصص إجباري (يتجاوز الاكتشاف التلقائي)
    
    ترجع:
        قاموساً يحتوي على:
        - title: عنوان المحاضرة
        - specialty: التخصص الطبي
        - language: اللغة
        - dialect: اللهجة
        - sections: قائمة الأقسام (كل قسم: heading, content, keywords, image_path)
        - medical_terms: قائمة المصطلحات المستخرجة
        - fallback: هل تم استخدام المحتوى الاحتياطي
    """
    
    # 1. تنظيف النص
    text = clean_text(text)
    if len(text) < config.MIN_TEXT_LENGTH:
        raise ValueError(f"النص قصير جداً ({len(text)} حرف). الحد الأدنى {config.MIN_TEXT_LENGTH} حرف.")
    
    # 2. تحديد اللغة تلقائياً إذا لم تحدد
    if language == "auto":
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', text))
        language = "ar" if arabic_chars > len(text) * 0.3 else "en"
    
    # 3. استخراج المصطلحات الطبية
    medical_terms = _extract_medical_terms(text, 30)
    
    # 4. تحديد التخصص
    if force_specialty:
        specialty = force_specialty
        specialty_confidence = 1.0
    else:
        specialty, specialty_confidence = _detect_medical_specialty(text)
    specialty_name = config.MEDICAL_SPECIALTIES.get(specialty, "طب عام")
    
    # 5. تحديد عدد الأقسام
    num_sections = _determine_num_sections(len(text))
    
    # 6. محاولة الاتصال بالذكاء الاصطناعي
    prompt = _build_prompt(text, language, dialect, num_sections, specialty, medical_terms)
    
    result = None
    used_fallback = False
    ai_model_used = None
    
    try:
        result = _call_ai(prompt)
        # التحقق من صحة النتيجة
        if not result or "sections" not in result or not result["sections"]:
            raise ValueError("الذكاء الاصطناعي أرجع نتيجة غير صالحة")
        used_fallback = False
        ai_model_used = "AI"
        logger.info(f"✅ تم تحليل المحاضرة بنجاح باستخدام الذكاء الاصطناعي")
    except Exception as e:
        logger.warning(f"⚠️ فشل الذكاء الاصطناعي: {e}. استخدام المحتوى الاحتياطي.")
        result = _generate_medical_fallback(text, language, dialect, num_sections)
        used_fallback = True
        ai_model_used = "fallback"
    
    # 7. معالجة النتيجة وإضافة الحقول المفقودة
    sections = result.get("sections", [])
    
    # التأكد من وجود 4 كلمات مفتاحية لكل قسم
    for i, section in enumerate(sections):
        if "keywords" not in section or len(section["keywords"]) < 4:
            # استكمال الكلمات المفتاحية من المصطلحات المستخرجة
            available = medical_terms[i*4:(i+1)*4] if i*4 < len(medical_terms) else ["طبي", "صحي", "علاج", "تشخيص"]
            section["keywords"] = (section.get("keywords", []) + available)[:4]
        
        # التأكد من وجود محتوى كاف
        if "content" not in section or len(section["content"]) < 50:
            section["content"] = f"شرح مفصل حول {section.get('heading', 'هذا الموضوع')}. " + \
                               f"يتضمن المعلومات الأساسية عن {', '.join(section['keywords'][:2])}. " + \
                               f"يجب على الطلاب التركيز على فهم هذه المفاهيم جيداً."
    
    # 8. إضافة الصور لكل قسم
    for section in sections:
        image_path = fetch_image_for_keyword(
            section["keywords"][0] if section["keywords"] else "medical",
            specialty
        )
        section["image_path"] = image_path
    
    # 9. بناء النتيجة النهائية
    final_result = {
        "title": result.get("title", f"محاضرة في {specialty_name}"),
        "specialty": specialty_name,
        "specialty_code": specialty,
        "language": language,
        "dialect": dialect,
        "sections": sections,
        "medical_terms": medical_terms[:20],
        "total_sections": len(sections),
        "fallback": used_fallback,
        "ai_model_used": ai_model_used,
        "text_length": len(text),
    }
    
    return final_result


# ==================== دوال جلب الصور ====================

async def _fetch_pollinations_image(keyword: str, specialty: str = None) -> Optional[Path]:
    """جلب صورة من Pollinations.ai"""
    try:
        async with aiohttp.ClientSession() as session:
            # بناء وصف طبي مناسب
            if specialty:
                prompt = f"medical illustration of {keyword} for {specialty} education, clean professional style"
            else:
                prompt = f"medical illustration of {keyword}, educational diagram, clean style"
            
            url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}"
            url += "?width=640&height=480&nologo=true"
            
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    img = Image.open(BytesIO(data))
                    # حفظ الصورة
                    file_path = config.IMAGES_TMP / f"pollinations_{uuid.uuid4().hex[:8]}.png"
                    img.save(file_path, "PNG")
                    logger.info(f"✅ تم جلب صورة من Pollinations: {keyword}")
                    return file_path
    except Exception as e:
        logger.debug(f"Pollinations فشل: {e}")
    return None


async def _fetch_unsplash_image(keyword: str) -> Optional[Path]:
    """جلب صورة من Unsplash"""
    if not config.UNSPLASH_ACCESS_KEY:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Client-ID {config.UNSPLASH_ACCESS_KEY}"}
            params = {
                "query": f"{keyword} medical",
                "orientation": "landscape",
                "per_page": 1
            }
            async with session.get("https://api.unsplash.com/search/photos",
                                   headers=headers, params=params,
                                   timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data["results"]:
                        img_url = data["results"][0]["urls"]["regular"]
                        async with session.get(img_url) as img_resp:
                            img_data = await img_resp.read()
                            img = Image.open(BytesIO(img_data))
                            # تغيير حجم الصورة
                            img = img.resize((640, 480), Image.Resampling.LANCZOS)
                            file_path = config.IMAGES_TMP / f"unsplash_{uuid.uuid4().hex[:8]}.jpg"
                            img.save(file_path, "JPEG")
                            logger.info(f"✅ تم جلب صورة من Unsplash: {keyword}")
                            return file_path
    except Exception as e:
        logger.debug(f"Unsplash فشل: {e}")
    return None


async def _fetch_picsum_image(keyword: str = None) -> Optional[Path]:
    """جلب صورة عشوائية من Lorem Picsum"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://picsum.photos/640/480"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    img = Image.open(BytesIO(data))
                    file_path = config.IMAGES_TMP / f"picsum_{uuid.uuid4().hex[:8]}.jpg"
                    img.save(file_path, "JPEG")
                    logger.info(f"✅ تم جلب صورة من Picsum")
                    return file_path
    except Exception as e:
        logger.debug(f"Picsum فشل: {e}")
    return None


def _make_medical_image(keyword: str, specialty: str = None) -> Path:
    """
    إنشاء صورة طبية احتياطية باستخدام PIL.
    ترسم صورة ملونة بسيطة بخلفية طبية ونص توضيحي.
    """
    if not Image:
        raise RuntimeError("مكتبة Pillow غير متوفرة")
    
    width, height = 640, 480
    # خلفية بلون طبي (أزرق فاتح أو وردي حسب التخصص)
    if specialty == "cardiology":
        bg_color = (255, 220, 220)  # وردي فاتح للقلب
    elif specialty == "neurology":
        bg_color = (220, 220, 255)  # أزرق فاتح للأعصاب
    elif specialty == "pulmonology":
        bg_color = (200, 230, 255)  # أزرق سماوي للتنفس
    else:
        bg_color = (230, 245, 255)  # أزرق طبي عام
    
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # محاولة تحميل خط عربي
    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
        font_text = ImageFont.truetype("DejaVuSans.ttf", 24)
    except:
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()
    
    # رسم إطار طبي
    draw.rectangle([10, 10, width-10, height-10], outline=(41, 128, 185), width=3)
    
    # رسم دائرة طبية (رمز)
    circle_x, circle_y = width // 2, height // 2 - 30
    draw.ellipse([circle_x-60, circle_y-60, circle_x+60, circle_y+60],
                 outline=(41, 128, 185), width=4)
    draw.ellipse([circle_x-40, circle_y-40, circle_x+40, circle_y+40],
                 fill=(41, 128, 185, 50), outline=(41, 128, 185), width=2)
    
    # رسم صليب طبي بسيط
    cross_size = 30
    draw.line([(circle_x-cross_size//2, circle_y), (circle_x+cross_size//2, circle_y)],
              fill=(255, 100, 100), width=6)
    draw.line([(circle_x, circle_y-cross_size//2), (circle_x, circle_y+cross_size//2)],
              fill=(255, 100, 100), width=6)
    
    # كتابة النص
    title_text = "Medical Illustration"
    draw.text((width//2, 50), title_text, fill=(41, 128, 185), font=font_title, anchor="mm")
    
    keyword_text = keyword if keyword else "Medical Concept"
    draw.text((width//2, height-80), keyword_text, fill=(52, 73, 94), font=font_text, anchor="mm")
    
    specialty_text = config.MEDICAL_SPECIALTIES.get(specialty, "طب عام") if specialty else "تعليم طبي"
    draw.text((width//2, height-40), specialty_text, fill=(100, 100, 150), font=font_text, anchor="mm")
    
    # حفظ الصورة
    file_path = config.IMAGES_TMP / f"generated_{uuid.uuid4().hex[:8]}.png"
    img.save(file_path, "PNG")
    logger.info(f"✅ تم إنشاء صورة طبية احتياطية: {keyword}")
    return file_path


def fetch_image_for_keyword(keyword: str, specialty: str = None) -> Path:
    """
    الدالة الرئيسية لجلب صورة لقسم معين.
    تجرب Pollinations -> Unsplash -> Picsum -> صورة مولدة.
    """
    # محاولة Pollinations (متزامنة)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        img = loop.run_until_complete(_fetch_pollinations_image(keyword, specialty))
        if img:
            return img
    except:
        pass
    
    try:
        img = loop.run_until_complete(_fetch_unsplash_image(keyword))
        if img:
            return img
    except:
        pass
    
    try:
        img = loop.run_until_complete(_fetch_picsum_image())
        if img:
            return img
    except:
        pass
    
    # الصورة الاحتياطية
    return _make_medical_image(keyword, specialty)


# ==================== دوال مساعدة ====================

def extract_text_from_message(text: str = None, file_path: Path = None) -> Tuple[str, Dict]:
    """
    استخراج النص من رسالة (نص مباشر أو ملف).
    ترجع (النص, معلومات الملف)
    """
    info = {"source": "text", "file_name": None, "pages": 1}
    
    if file_path:
        file_name = file_path.name.lower()
        info["file_name"] = file_name
        if file_name.endswith('.pdf'):
            text, pages = extract_full_text_from_pdf(file_path)
            info["source"] = "pdf"
            info["pages"] = pages
        elif file_name.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            info["source"] = "txt"
        else:
            raise ValueError("نوع الملف غير مدعوم. الرجاء إرسال PDF أو TXT")
    else:
        text = text or ""
    
    text = clean_text(text)
    info["length"] = len(text)
    return text, info


def estimate_video_duration(sections: List[Dict]) -> float:
    """تقدير مدة الفيديو الإجمالية بناءً على عدد الأقسام ومحتواها"""
    total_duration = config.WELCOME_DURATION + config.TITLE_DURATION + config.MAP_DURATION
    
    for section in sections:
        total_duration += config.SECTION_TITLE_DURATION
        # تقدير مدة الشرح: كل 150 كلمة ≈ 60 ثانية
        word_count = len(section.get("content", "").split())
        section_duration = max(15, word_count * 0.4)
        total_duration += section_duration
    
    total_duration += config.SUMMARY_DURATION
    return total_duration


# للاختبار المباشر
if __name__ == "__main__":
    sample_text = """
    مرض السكري من النوع الثاني هو اضطراب استقلابي يتميز بارتفاع مستوى السكر في الدم
    بسبب مقاومة الأنسولين أو نقص إفرازه. تشمل الأعراض الشائعة: العطش الشديد، كثرة التبول،
    التعب، وعدم وضوح الرؤية. يعتمد التشخيص على فحص السكر الصيامي وفحص HbA1c.
    العلاج يشمل تعديل نمط الحياة، الأدوية الفموية مثل الميتفورمين، وقد يحتاج المريض للأنسولين.
    """
    try:
        result = analyze_lecture(sample_text, language="ar", dialect="fusha")
        print(f"العنوان: {result['title']}")
        print(f"التخصص: {result['specialty']}")
        print(f"عدد الأقسام: {result['total_sections']}")
        for i, sec in enumerate(result['sections']):
            print(f"  {i+1}. {sec['heading']} - الكلمات: {sec['keywords']}")
    except Exception as e:
        print(f"خطأ: {e}")
