# voice_generator.py
# -*- coding: utf-8 -*-
"""
وحدة توليد الصوت من النص باستخدام gTTS المجاني
تدعم تحويل الأرقام إلى كلمات، إزالة التكرار، ومعالجة متوازية للأقسام
"""

import re
import asyncio
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

# مكتبات الصوت
try:
    from gtts import gTTS
except ImportError:
    gTTS = None
    logging.error("مكتبة gTTS غير مثبتة. يرجى تثبيتها: pip install gTTS")

try:
    from pydub import AudioSegment
except ImportError:
    AudioSegment = None
    logging.warning("مكتبة pydub غير مثبتة. لن يتم حساب مدة الصوت بدقة.")

try:
    from num2words import num2words
except ImportError:
    num2words = None
    logging.warning("مكتبة num2words غير مثبتة. لن يتم تحويل الأرقام إلى كلمات.")

from config import config

logger = logging.getLogger(__name__)

# ==================== دوال تنظيف النص للصوت ====================

def clean_text_for_voice(text: str) -> str:
    """
    تنظيف النص خصيصاً للتحويل الصوتي:
    - إزالة الأحرف غير المنطوقة
    - توحيد المسافات
    - إزالة الروابط
    """
    if not text:
        return ""

    # إزالة الروابط
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)

    # إزالة الرموز غير الضرورية للصوت
    text = re.sub(r'[<>{}[\]\\^_`|~]', ' ', text)

    # استبدال الرموز الطبية الشائعة بما ينطق
    replacements = {
        '&': ' و ',
        '%': ' بالمئة ',
        '+': ' زائد ',
        '=': ' يساوي ',
        '@': ' at ',
        '#': ' رقم ',
    }
    for sym, replacement in replacements.items():
        text = text.replace(sym, replacement)

    # توحيد المسافات
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def _convert_numbers_to_words_arabic(text: str) -> str:
    """
    تحويل الأرقام في النص العربي إلى كلمات مكتوبة.
    مثال: "عندي 3 تفاحات" -> "عندي ثلاثة تفاحات"
    """
    if not num2words:
        return text

    def replace_number(match):
        num_str = match.group(0)
        try:
            # محاولة تحويل الرقم
            num = int(num_str) if '.' not in num_str else float(num_str)
            if '.' in num_str:
                # التعامل مع الأعداد العشرية
                parts = num_str.split('.')
                whole = int(parts[0])
                frac = int(parts[1])
                if whole > 0:
                    return f"{num2words(whole, lang='ar')} فاصل {num2words(frac, lang='ar')}"
                else:
                    return f"فاصل {num2words(frac, lang='ar')}"
            else:
                return num2words(num, lang='ar')
        except:
            return num_str

    # البحث عن الأرقام (بما فيها العشرية)
    pattern = r'\b\d+(?:\.\d+)?\b'
    text = re.sub(pattern, replace_number, text)
    return text


def _convert_numbers_to_words_english(text: str) -> str:
    """تحويل الأرقام في النص الإنجليزي إلى كلمات"""
    if not num2words:
        return text

    def replace_number(match):
        num_str = match.group(0)
        try:
            if '.' in num_str:
                num = float(num_str)
                return num2words(num, lang='en')
            else:
                num = int(num_str)
                return num2words(num, lang='en')
        except:
            return num_str

    return re.sub(r'\b\d+(?:\.\d+)?\b', replace_number, text)


def _convert_percentages_to_words(text: str, language: str = 'ar') -> str:
    """
    تحويل النسب المئوية إلى كلمات مناسبة للنطق.
    مثال: "87.5%" -> "سبعة وثمانون فاصل خمسة بالمئة"
    """
    if language == 'ar':
        def replace_pct(match):
            num = match.group(1)
            try:
                if '.' in num:
                    parts = num.split('.')
                    whole = int(parts[0])
                    frac = int(parts[1])
                    return f"{num2words(whole, lang='ar')} فاصل {num2words(frac, lang='ar')} بالمئة"
                else:
                    return f"{num2words(int(num), lang='ar')} بالمئة"
            except:
                return f"{num} بالمئة"
    else:
        def replace_pct(match):
            num = match.group(1)
            try:
                if '.' in num:
                    return f"{num2words(float(num), lang='en')} percent"
                else:
                    return f"{num2words(int(num), lang='en')} percent"
            except:
                return f"{num} percent"

    return re.sub(r'(\d+(?:\.\d+)?)\s*%', replace_pct, text)


def _remove_duplicate_sentences(text: str) -> str:
    """
    إزالة الجمل المكررة المتتالية لمنع الملل الصوتي.
    تحافظ على التكرار المتعمد للمصطلحات المهمة.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) < 2:
        return text

    cleaned = []
    prev = ""
    for sent in sentences:
        # فقط إذا كانت مطابقة تماماً وطويلة نسبياً (> 30 حرف)
        if sent == prev and len(sent) > 30:
            continue
        cleaned.append(sent)
        prev = sent

    return ' '.join(cleaned)


def prepare_text_for_tts(text: str, language: str = 'ar') -> str:
    """
    تحضير النص للتحويل الصوتي: تنظيف، تحويل أرقام، إزالة تكرار.
    """
    text = clean_text_for_voice(text)

    if language == 'ar':
        text = _convert_numbers_to_words_arabic(text)
        text = _convert_percentages_to_words(text, 'ar')
    else:
        text = _convert_numbers_to_words_english(text)
        text = _convert_percentages_to_words(text, 'en')

    text = _remove_duplicate_sentences(text)
    return text


# ==================== دوال توليد الصوت ====================

def generate_voice(text: str, output_path: Path, language: str = 'ar',
                   dialect: str = 'fusha', slow: bool = False) -> Tuple[Path, float]:
    """
    توليد ملف صوتي MP3 من النص.
    ترجع (مسار الملف, المدة بالثواني)

    المعاملات:
        text: النص المراد تحويله
        output_path: مسار حفظ الملف
        language: 'ar' أو 'en'
        dialect: اللهجة (تؤثر على اختيار نطق Google)
        slow: هل الصوت بطيء
    """
    if not gTTS:
        raise RuntimeError("مكتبة gTTS غير متوفرة")

    # تحضير النص
    text = prepare_text_for_tts(text, language)

    # اختيار رمز اللغة المناسب
    tts_lang = config.GTTS_LANG_MAP.get(dialect, language)
    if not text.strip():
        raise ValueError("النص فارغ بعد التنظيف")

    # إنشاء الصوت في Thread منفصل لأن gTTS متزامنة
    def _generate():
        tts = gTTS(text=text, lang=tts_lang, slow=slow, tld=config.GTTS_TLD)
        tts.save(str(output_path))

    thread = threading.Thread(target=_generate)
    thread.start()
    thread.join(timeout=30)
    if thread.is_alive():
        raise TimeoutError("استغرق توليد الصوت وقتاً طويلاً")

    # حساب المدة
    duration = get_audio_duration(output_path)

    logger.debug(f"تم توليد صوت: {output_path.name} ({duration:.1f} ثانية)")
    return output_path, duration


def get_audio_duration(file_path: Path) -> float:
    """حساب مدة ملف صوتي بالثواني"""
    if AudioSegment:
        try:
            audio = AudioSegment.from_file(file_path)
            return len(audio) / 1000.0
        except Exception as e:
            logger.debug(f"فشل pydub في قراءة المدة: {e}")

    # تقدير تقريبي (حجم الملف / معدل البت)
    file_size = file_path.stat().st_size
    estimated_duration = file_size / (16000 * 2)  # افتراض 16kbps mono
    return estimated_duration


async def generate_sections_audio(sections: List[Dict], language: str = 'ar',
                                  dialect: str = 'fusha',
                                  max_concurrent: int = 3) -> List[Dict]:
    """
    توليد الصوت لجميع الأقسام بالتوازي.
    تستخدم Semaphore للتحكم بعدد الطلبات المتزامنة.

    ترجع قائمة النتائج لكل قسم مضافاً إليها:
        - audio_path: مسار ملف الصوت
        - duration: مدة الصوت بالثواني
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results = [None] * len(sections)

    async def process_section(index: int, section: Dict):
        async with semaphore:
            try:
                # دمج العنوان والمحتوى للقسم
                text_to_speak = f"{section['heading']}. {section['content']}"
                output_path = config.AUDIO_TMP / f"section_{index}_{uuid.uuid4().hex[:6]}.mp3"

                # تشغيل gTTS في ThreadPoolExecutor
                loop = asyncio.get_event_loop()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    path, duration = await loop.run_in_executor(
                        executor,
                        generate_voice,
                        text_to_speak, output_path, language, dialect
                    )

                results[index] = {
                    **section,
                    "audio_path": str(path),
                    "duration": duration,
                }
                logger.info(f"✅ تم توليد صوت القسم {index+1}/{len(sections)}: {section['heading'][:30]}...")

            except Exception as e:
                logger.error(f"❌ فشل توليد صوت القسم {index}: {e}")
                # إنشاء صوت فارغ احتياطي
                results[index] = {
                    **section,
                    "audio_path": None,
                    "duration": 5.0,  # مدة افتراضية
                    "audio_error": str(e)
                }

    # تشغيل المهام بالتوازي
    tasks = [process_section(i, section) for i, section in enumerate(sections)]
    await asyncio.gather(*tasks)

    return results


# ==================== دوال تقدير توقيت الجمل ====================

def split_into_sentences(text: str) -> List[str]:
    """تقسيم النص إلى جمل منفصلة"""
    # نمط لتقسيم الجمل العربية والإنجليزية
    pattern = r'(?<=[.!?؟])\s+'
    sentences = re.split(pattern, text)
    return [s.strip() for s in sentences if s.strip()]


def estimate_sentence_timings(sentences: List[str], total_duration: float,
                              keywords: List[str] = None) -> List[Dict]:
    """
    تقدير توقيت كل جملة بناءً على طولها بالنسبة للمدة الكلية.
    ترجع قائمة بها: النص، وقت البدء، المدة، والكلمات المفتاحية الموجودة.
    """
    if not sentences:
        return []

    # حساب طول كل جملة (عدد الأحرف)
    lengths = [len(s) for s in sentences]
    total_length = sum(lengths)

    timings = []
    current_time = 0.0

    for i, sentence in enumerate(sentences):
        # توزيع المدة نسبياً
        proportion = lengths[i] / total_length if total_length > 0 else 1/len(sentences)
        duration = total_duration * proportion

        # البحث عن الكلمات المفتاحية في الجملة
        found_keywords = []
        if keywords:
            sent_lower = sentence.lower()
            found_keywords = [kw for kw in keywords if kw.lower() in sent_lower]

        timings.append({
            "text": sentence,
            "start_time": current_time,
            "duration": duration,
            "keywords_found": found_keywords[:3],  # أول 3 كلمات مفتاحية
        })
        current_time += duration

    return timings


def calculate_total_audio_duration(sections_with_audio: List[Dict]) -> float:
    """حساب المدة الإجمالية لجميع المقاطع الصوتية"""
    total = 0.0
    for section in sections_with_audio:
        total += section.get("duration", 0)
    return total


# ==================== دوال الدمج والتحسين ====================

def combine_audio_files(audio_paths: List[Path], output_path: Path) -> Path:
    """دمج عدة ملفات صوتية في ملف واحد"""
    if not AudioSegment:
        raise RuntimeError("مكتبة pydub غير متوفرة لدمج الصوتيات")

    combined = AudioSegment.empty()
    for path in audio_paths:
        if path and path.exists():
            segment = AudioSegment.from_file(path)
            combined += segment
            # إضافة صمت قصير بين المقاطع (0.3 ثانية)
            combined += AudioSegment.silent(duration=300)

    combined.export(output_path, format="mp3", bitrate=config.AUDIO_BITRATE)
    return output_path


def generate_silence(duration_seconds: float, output_path: Path) -> Path:
    """توليد ملف صوتي صامت لمدة محددة"""
    if AudioSegment:
        silence = AudioSegment.silent(duration=int(duration_seconds * 1000))
        silence.export(output_path, format="mp3")
    else:
        # إنشاء ملف فارغ
        output_path.touch()
    return output_path


# ==================== الدالة الرئيسية ====================

async def process_lecture_audio(sections: List[Dict], language: str = 'ar',
                                dialect: str = 'fusha') -> Dict[str, Any]:
    """
    المعالجة الكاملة لصوت المحاضرة.
    ترجع قاموساً يحتوي على:
        - sections_with_audio: الأقسام مع مسارات الصوت والمدة
        - total_duration: المدة الإجمالية
        - success: هل نجحت العملية
    """
    logger.info(f"بدء توليد الصوت لـ {len(sections)} أقسام...")

    try:
        sections_with_audio = await generate_sections_audio(
            sections, language, dialect, max_concurrent=3
        )

        total_duration = calculate_total_audio_duration(sections_with_audio)

        # التحقق من نجاح كل الأقسام
        all_success = all(s.get("audio_path") for s in sections_with_audio)

        logger.info(f"✅ اكتمل توليد الصوت. المدة الإجمالية: {total_duration:.1f} ثانية")

        return {
            "sections": sections_with_audio,
            "total_duration": total_duration,
            "success": all_success,
        }

    except Exception as e:
        logger.error(f"❌ فشل توليد الصوت: {e}")
        return {
            "sections": sections,
            "total_duration": 0,
            "success": False,
            "error": str(e)
        }


# للاختبار
if __name__ == "__main__":
    async def test():
        test_sections = [
            {"heading": "مقدمة عن السكري", "content": "مرض السكري هو اضطراب في التمثيل الغذائي."},
            {"heading": "الأعراض", "content": "تشمل الأعراض العطش الشديد وكثرة التبول."},
        ]
        result = await process_lecture_audio(test_sections, 'ar', 'fusha')
        print(f"المدة: {result['total_duration']}")

    asyncio.run(test())
