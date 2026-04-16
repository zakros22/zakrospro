import re
from typing import Dict, List, Tuple
import asyncio
from config import KeyManager

class ContentAnalyzer:
    def __init__(self):
        self.key_manager = KeyManager()
        
    async def analyze_content(self, text: str, file_type: str = None) -> Dict:
        """تحليل المحتوى واستخراج الأقسام الرئيسية"""
        
        # تنظيف النص
        cleaned_text = self.clean_text(text)
        
        # تحديد نوع المحتوى
        content_type = self.detect_content_type(cleaned_text)
        
        # استخراج العنوان
        title = self.extract_title(cleaned_text)
        
        # تقسيم إلى أقسام
        sections = self.extract_sections(cleaned_text)
        
        # استخراج الكلمات المفتاحية لكل قسم
        enriched_sections = []
        for section in sections:
            keywords = self.extract_keywords(section['content'])
            enriched_sections.append({
                'title': section['title'],
                'content': section['content'],
                'keywords': keywords,
                'explanation': self.generate_explanation(section['content'], keywords)
            })
        
        return {
            'type': content_type,
            'title': title,
            'sections': enriched_sections,
            'summary': self.generate_summary(cleaned_text, title)
        }
    
    def clean_text(self, text: str) -> str:
        """تنظيف النص من الشوائب"""
        # إزالة الأسطر الفارغة المتكررة
        text = re.sub(r'\n\s*\n', '\n\n', text)
        # إزالة المسافات الزائدة
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def detect_content_type(self, text: str) -> str:
        """تحديد نوع المحتوى (طبي، علمي، تاريخي...)"""
        medical_keywords = ['خلية', 'غشاء', 'مرض', 'علاج', 'جراحة', 'ولادة', 'قيصرية']
        science_keywords = ['فيزياء', 'كيمياء', 'أحياء', 'رياضيات']
        
        text_lower = text.lower()
        
        if any(kw in text_lower for kw in medical_keywords):
            return 'medical'
        elif any(kw in text_lower for kw in science_keywords):
            return 'scientific'
        else:
            return 'general'
    
    def extract_title(self, text: str) -> str:
        """استخراج عنوان المحاضرة"""
        lines = text.split('\n')
        for line in lines[:5]:  # البحث في أول 5 أسطر
            line = line.strip()
            if line and len(line) < 100 and ':' not in line:
                if any(keyword in line.lower() for keyword in ['مقدمة', 'تعريف', 'مفهوم']):
                    return line
        return lines[0].strip() if lines else "محاضرة"
    
    def extract_sections(self, text: str) -> List[Dict]:
        """تقسيم النص إلى أقسام"""
        sections = []
        lines = text.split('\n')
        
        current_section = {'title': 'مقدمة', 'content': []}
        
        section_markers = [
            'مقدمة', 'تعريف', 'أنواع', 'أسباب', 'أعراض', 'علاج',
            'خاتمة', 'نتائج', 'خلاصة', 'مراجع', 'مصطلحات'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # فحص إذا كان السطر عنوان قسم
            is_header = False
            for marker in section_markers:
                if marker in line and len(line) < 50:
                    if current_section['content']:
                        sections.append({
                            'title': current_section['title'],
                            'content': '\n'.join(current_section['content'])
                        })
                    current_section = {'title': line, 'content': []}
                    is_header = True
                    break
            
            if not is_header:
                current_section['content'].append(line)
        
        # إضافة القسم الأخير
        if current_section['content']:
            sections.append({
                'title': current_section['title'],
                'content': '\n'.join(current_section['content'])
            })
        
        return sections
    
    def extract_keywords(self, text: str) -> List[str]:
        """استخراج الكلمات المفتاحية"""
        # الكلمات التي تظهر بشكل متكرر أو مكتوبة بأحرف كبيرة
        words = re.findall(r'\b[A-Za-z\u0600-\u06FF]{3,}\b', text)
        
        # إزالة الكلمات الشائعة
        stopwords = ['من', 'إلى', 'عن', 'على', 'في', 'مع', 'هذا', 'هذه', 'ذلك']
        
        keywords = {}
        for word in words:
            if word.lower() not in stopwords:
                keywords[word] = keywords.get(word, 0) + 1
        
        # ترتيب حسب التكرار
        sorted_keywords = sorted(keywords.items(), key=lambda x: x[1], reverse=True)
        return [kw[0] for kw in sorted_keywords[:5]]
    
    def generate_explanation(self, content: str, keywords: List[str]) -> str:
        """توليد شرح للقسم"""
        explanation = f"شرح القسم:\n"
        explanation += f"الكلمات المفتاحية: {', '.join(keywords)}\n\n"
        
        # تلخيص المحتوى
        sentences = content.split('.')
        summary = '. '.join(sentences[:3]) + '.'
        
        explanation += summary
        return explanation
    
    def generate_summary(self, text: str, title: str) -> str:
        """توليد ملخص للمحاضرة"""
        summary = f"ملخص محاضرة: {title}\n\n"
        summary += "النقاط الرئيسية:\n"
        
        # استخراج أهم النقاط
        lines = text.split('\n')
        important_lines = [l for l in lines if any(marker in l for marker in ['•', '-', '*', '1.', '2.'])]
        
        for line in important_lines[:5]:
            summary += f"• {line.strip()}\n"
        
        return summary
