import asyncio
import io
import os
import tempfile
import subprocess
from PIL import Image, ImageDraw, ImageFont

W, H = 854, 480
FONT_AR = "/app/fonts/Amiri-Regular.ttf"
FONT_AR_BOLD = "/app/fonts/Amiri-Bold.ttf"

def _get_font(size, bold=False, arabic=True):
    path = FONT_AR_BOLD if bold else FONT_AR
    try:
        return ImageFont.truetype(path, size) if os.path.exists(path) else ImageFont.load_default()
    except:
        return ImageFont.load_default()

def _prepare_arabic(text):
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except:
        return text

def _create_intro(title, sections, duration):
    """شريحة المقدمة"""
    img = Image.new("RGB", (W, H), (20, 30, 50))
    draw = ImageDraw.Draw(img)
    
    # هيدر
    draw.rectangle([(0, 0), (W, 50)], fill=(15, 25, 45))
    font = _get_font(20, bold=True)
    draw.text((20, 12), "🎓 ZAKROS PRO", fill=(255, 200, 50), font=font)
    
    # عنوان
    title_ar = _prepare_arabic(title)
    font_title = _get_font(28, bold=True)
    bbox = draw.textbbox((0, 0), title_ar, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 70), title_ar, fill=(255, 220, 80), font=font_title)
    
    # الأقسام
    y = 130
    font_sec = _get_font(16)
    for i, s in enumerate(sections[:8]):
        sec_title = _prepare_arabic(s.get("title", f"القسم {i+1}")[:35])
        color = [(255,107,107), (78,205,196), (255,209,102), (170,120,255)][i%4]
        draw.ellipse([30, y+5, 50, y+25], fill=color)
        draw.text((60, y+8), f"{i+1}.", fill=(255,255,255), font=font_sec)
        draw.text((85, y+8), sec_title, fill=(220,230,255), font=font_sec)
        y += 35
    
    # مدة
    mins, secs = int(duration//60), int(duration%60)
    dur_text = _prepare_arabic(f"⏱️ المدة: {mins}:{secs:02d}")
    draw.text((W-150, H-30), dur_text, fill=(150,200,150), font=_get_font(14))
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()

def _create_section_card(section, idx, total):
    """بطاقة القسم"""
    img = Image.new("RGB", (W, H), (25, 35, 55))
    draw = ImageDraw.Draw(img)
    
    color = [(255,107,107), (78,205,196), (255,209,102), (170,120,255)][idx%4]
    draw.rounded_rectangle([(15, 15), (W-15, H-15)], radius=15, outline=(255,200,50), width=3)
    
    # رقم القسم
    num = str(idx+1)
    font_num = _get_font(80, bold=True)
    bbox = draw.textbbox((0, 0), num, font=font_num)
    nw = bbox[2] - bbox[0]
    draw.text(((W-nw)//2, H//2-60), num, fill=color, font=font_num)
    
    # عنوان
    title = _prepare_arabic(section.get("title", f"القسم {idx+1}"))
    font_title = _get_font(24, bold=True)
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, H//2+20), title, fill=(255,220,100), font=font_title)
    
    # تقدم
    prog = f"{idx+1}/{total}"
    draw.text((W-60, H-30), prog, fill=(150,160,180), font=_get_font(14))
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()

def _create_content_slide(image_bytes, keyword, all_keywords, current_idx, section_title, section_idx):
    """شريحة المحتوى"""
    img = Image.new("RGB", (W, H), (20, 25, 45))
    draw = ImageDraw.Draw(img)
    
    color = [(255,107,107), (78,205,196), (255,209,102), (170,120,255)][section_idx%4]
    
    # هيدر
    draw.rectangle([(0, 0), (W, 40)], fill=(15, 20, 40))
    draw.rectangle([(0, 38), (W, 40)], fill=color)
    title = _prepare_arabic(section_title[:40])
    font_title = _get_font(15, bold=True)
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 10), title, fill=(255,255,255), font=font_title)
    
    # صورة
    if image_bytes:
        try:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            pil_img.thumbnail((W-80, H-150), Image.LANCZOS)
            iw, ih = pil_img.size
            px, py = (W-iw)//2, 50
            # إطار أبيض
            frame = Image.new("RGB", (iw+10, ih+10), (255,255,255))
            frame.paste(pil_img, (5, 5))
            img.paste(frame, (px-5, py-5))
        except:
            pass
    
    # كلمات مفتاحية
    kw_y = H - 60
    spacing = W // max(len(all_keywords), 1)
    for i, kw in enumerate(all_keywords[:5]):
        kw_ar = _prepare_arabic(kw[:15])
        x = 20 + i * min(spacing, 140)
        font_kw = _get_font(12, bold=(i==current_idx))
        if i == current_idx:
            bbox = draw.textbbox((0, 0), kw_ar, font=font_kw)
            kw_w = bbox[2] - bbox[0]
            draw.rounded_rectangle([(x-5, kw_y-2), (x+kw_w+8, kw_y+18)], radius=4, fill=color)
            draw.text((x, kw_y), kw_ar, fill=(255,255,255), font=font_kw)
        elif i < current_idx:
            draw.text((x, kw_y+2), "✓ " + kw_ar, fill=(100,200,100), font=font_kw)
        else:
            draw.text((x, kw_y+2), "○ " + kw_ar, fill=(140,150,170), font=font_kw)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()

def _create_summary(data, sections):
    """شريحة الملخص"""
    img = Image.new("RGB", (W, H), (20, 30, 50))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (W, 45)], fill=(25, 35, 55))
    draw.rectangle([(0, 43), (W, 45)], fill=(255, 200, 50))
    
    title = _prepare_arabic("📋 ملخص المحاضرة")
    font = _get_font(22, bold=True)
    bbox = draw.textbbox((0, 0), title, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W-tw)//2, 10), title, fill=(255,220,80), font=font)
    
    # ملخص
    y = 60
    summary = _prepare_arabic(data.get("summary", "")[:300])
    font_sum = _get_font(13)
    words = summary.split()
    line = ""
    for w in words:
        if len(line + w) < 50:
            line += w + " "
        else:
            draw.text((20, y), line, fill=(220,230,255), font=font_sum)
            y += 22
            line = w + " "
    if line:
        draw.text((20, y), line, fill=(220,230,255), font=font_sum)
    
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()

def _encode_segment(img_bytes, duration, audio_bytes, audio_start, out_path):
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(img_bytes)
        img_path = f.name
    
    audio_path = None
    if audio_bytes:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            audio_path = f.name
    
    dur = f"{duration:.3f}"
    
    if audio_path:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-t", dur, "-i", img_path,
            "-ss", f"{audio_start:.3f}", "-t", dur, "-i", audio_path,
            "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k",
            "-shortest", out_path
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-t", dur, "-i", img_path,
            "-vf", "scale=854:480", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", out_path
        ]
    
    subprocess.run(cmd, capture_output=True, check=True)
    
    os.unlink(img_path)
    if audio_path:
        os.unlink(audio_path)

def _concat(segments, output):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for s in segments:
            f.write(f"file '{s}'\n")
        list_path = f.name
    
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output], check=True)
    os.unlink(list_path)

async def create_video(sections, audio_results, data, output_path, dialect):
    segments = []
    total_dur = 0
    is_arabic = dialect not in ("english", "british")
    
    # 1. مقدمة
    total_audio = sum(r["duration"] for r in audio_results)
    intro_dur = min(12, max(6, len(sections) * 1.5))
    intro_bytes = _create_intro(data.get("title", "المحاضرة"), sections, total_audio + intro_dur + 8)
    
    seg_paths = []
    seg = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    seg_paths.append(seg.name)
    seg.close()
    _encode_segment(intro_bytes, intro_dur, None, 0, seg.name)
    total_dur += intro_dur
    
    # 2. الأقسام
    for i, (sec, aud) in enumerate(zip(sections, audio_results)):
        # بطاقة القسم
        card_bytes = _create_section_card(sec, i, len(sections))
        seg = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        seg_paths.append(seg.name)
        seg.close()
        _encode_segment(card_bytes, 2.5, None, 0, seg.name)
        total_dur += 2.5
        
        # شرائح المحتوى
        keywords = sec.get("keywords", ["القسم"])
        images = sec.get("_images", [])
        dur = aud["duration"]
        kw_dur = dur / len(keywords)
        
        for j, kw in enumerate(keywords):
            img = images[j] if j < len(images) else None
            if not img:
                # صورة بديلة
                img = _create_content_slide(None, kw, keywords, j, sec.get("title", ""), i)
            slide_bytes = _create_content_slide(img, kw, keywords, j, sec.get("title", ""), i)
            
            seg = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            seg_paths.append(seg.name)
            seg.close()
            _encode_segment(slide_bytes, kw_dur, aud["audio"], j * kw_dur, seg.name)
            total_dur += kw_dur
    
    # 3. ملخص
    summary_bytes = _create_summary(data, sections)
    seg = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    seg_paths.append(seg.name)
    seg.close()
    _encode_segment(summary_bytes, 8, None, 0, seg.name)
    total_dur += 8
    
    # دمج
    _concat(seg_paths, output_path)
    
    for p in seg_paths:
        try:
            os.unlink(p)
        except:
            pass
    
    return total_dur
