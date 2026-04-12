# -*- coding: utf-8 -*-
import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

COLORS = [
    (231, 76, 126),   # وردي
    (52, 152, 219),   # أزرق
    (46, 204, 113),   # أخضر
    (155, 89, 182),   # بنفسجي
    (230, 126, 34),   # برتقالي
]


def estimate_encoding_seconds(t):
    return max(20, t * 0.6)


def _get_font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _arabic(text):
    if not text:
        return ""
    if not any('\u0600' <= c <= '\u06FF' for c in text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except:
        return text


def _text_width(text, font):
    text = _arabic(text)
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0]
    except:
        return len(text) * (font.size // 2)


def _draw_text(draw, x, y, text, font, color, shadow=True):
    text = _arabic(text)
    if shadow:
        draw.text((x + 2, y + 2), text, fill=(200, 200, 200), font=font)
    draw.text((x, y), text, fill=color, font=font)


# ═══════════════════════════════════════════════════════════════════════════════
# شريحة السؤال التفاعلي (مؤقت 5 ثواني)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_question_slide(question: str, section_idx: int) -> str:
    """شريحة سؤال مع مؤقت"""
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    col = COLORS[section_idx % len(COLORS)]
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=col)
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=col)

    # أيقونة سؤال
    f = _get_font(50)
    _draw_text(draw, TARGET_W // 2 - 30, 80, "❓", f, col)

    # نص السؤال
    f2 = _get_font(28)
    lines = []
    words = question.split()
    cur = []
    for w in words:
        cur.append(w)
        line = ' '.join(cur)
        if _text_width(line, f2) > TARGET_W - 100:
            cur.pop()
            lines.append(' '.join(cur))
            cur = [w]
    if cur:
        lines.append(' '.join(cur))

    y = 160
    for line in lines:
        w = _text_width(line, f2)
        x = (TARGET_W - w) // 2
        _draw_text(draw, x, y, line, f2, (44, 62, 80))
        y += 45

    # مؤقت
    f3 = _get_font(20)
    timer_text = "⏳ فكر في الإجابة... (5 ثوان)"
    w3 = _text_width(timer_text, f3)
    x3 = (TARGET_W - w3) // 2
    _draw_text(draw, x3, TARGET_H - 100, timer_text, f3, col)

    img.save(path, "JPEG", quality=90)
    return path


def _draw_answer_slide(question: str, answer: str, section_idx: int) -> str:
    """شريحة الإجابة"""
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    col = COLORS[section_idx % len(COLORS)]
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=col)
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=col)

    # أيقونة إجابة
    f = _get_font(40)
    _draw_text(draw, TARGET_W // 2 - 25, 50, "✅", f, col)

    # السؤال (صغير)
    f2 = _get_font(18)
    q_text = question[:60] + "..." if len(question) > 60 else question
    w2 = _text_width(q_text, f2)
    x2 = (TARGET_W - w2) // 2
    _draw_text(draw, x2, 110, q_text, f2, (100, 100, 100))

    # الإجابة
    f3 = _get_font(26)
    lines = []
    words = answer.split()
    cur = []
    for w in words:
        cur.append(w)
        line = ' '.join(cur)
        if _text_width(line, f3) > TARGET_W - 80:
            cur.pop()
            lines.append(' '.join(cur))
            cur = [w]
    if cur:
        lines.append(' '.join(cur))

    y = 180
    for line in lines:
        w = _text_width(line, f3)
        x = (TARGET_W - w) // 2
        _draw_text(draw, x, y, line, f3, col)
        y += 45

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# شريحة المعادلات الرياضية (سبورة بيضاء)
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_equation_slide(equation: str, step: int, total_steps: int, section_idx: int) -> str:
    """شريحة عرض معادلة رياضية على سبورة بيضاء"""
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    col = COLORS[section_idx % len(COLORS)]
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # إطار السبورة
    draw.rectangle([(10, 10), (TARGET_W - 10, TARGET_H - 10)], outline=(180, 180, 180), width=3)
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=col)

    # عنوان
    f = _get_font(20)
    title = f"خطوة {step} من {total_steps}"
    w = _text_width(title, f)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, 25, title, f, col)

    # المعادلة بخط كبير
    f2 = _get_font(36)
    eq_text = equation
    w2 = _text_width(eq_text, f2)
    x2 = (TARGET_W - w2) // 2
    _draw_text(draw, x2, TARGET_H // 2 - 20, eq_text, f2, (44, 62, 80))

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# شرائح الفيديو الأساسية
# ═══════════════════════════════════════════════════════════════════════════════

def _draw_welcome():
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    frame_x, frame_y = 150, 100
    frame_w, frame_h = 550, 200
    draw.rounded_rectangle(
        [(frame_x, frame_y), (frame_x + frame_w, frame_y + frame_h)],
        radius=25, outline=COLORS[0], width=8
    )

    f = _get_font(60)
    w = _text_width(WATERMARK, f)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, TARGET_H // 2 - 40, WATERMARK, f, COLORS[0])

    f2 = _get_font(36)
    welcome = "أهلاً ومرحباً بكم"
    w2 = _text_width(welcome, f2)
    x2 = (TARGET_W - w2) // 2
    _draw_text(draw, x2, TARGET_H // 2 + 30, welcome, f2, (44, 62, 80))

    img.save(path, "JPEG", quality=90)
    return path


def _draw_title(title):
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])

    f = _get_font(38)
    lines = []
    words = title.split()
    cur = []
    for w in words:
        cur.append(w)
        line = ' '.join(cur)
        if _text_width(line, f) > TARGET_W - 80:
            cur.pop()
            lines.append(' '.join(cur))
            cur = [w]
    if cur:
        lines.append(' '.join(cur))

    y = TARGET_H // 2 - (len(lines) * 45) // 2
    for line in lines:
        w = _text_width(line, f)
        x = (TARGET_W - w) // 2
        _draw_text(draw, x, y, line, f, (44, 62, 80))
        y += 45

    img.save(path, "JPEG", quality=90)
    return path


def _draw_map(titles):
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[2])

    f = _get_font(30)
    mt = "📋 خريطة المحاضرة"
    w = _text_width(mt, f)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, 30, mt, f, COLORS[2])

    y = 90
    for i, t in enumerate(titles):
        col = COLORS[i % len(COLORS)]
        draw.ellipse([(30, y), (52, y + 22)], fill=col)
        draw.text((41, y + 3), str(i + 1), fill=(255, 255, 255), font=_get_font(15))
        _draw_text(draw, 70, y, t[:35], _get_font(20), (44, 62, 80))
        y += 55

    img.save(path, "JPEG", quality=90)
    return path


def _draw_section_title(title, idx):
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    col = COLORS[idx % len(COLORS)]
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=col)

    cx, cy = TARGET_W // 2, TARGET_H // 2 - 40
    draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], fill=col)

    num = str(idx + 1)
    f = _get_font(40)
    nw = _text_width(num, f)
    draw.text((cx - nw // 2, cy - 22), num, fill=(255, 255, 255), font=f)

    f2 = _get_font(30)
    w2 = _text_width(title, f2)
    x = (TARGET_W - w2) // 2
    _draw_text(draw, x, cy + 50, title, f2, (44, 62, 80))

    img.save(path, "JPEG", quality=90)
    return path


def _draw_content(img_bytes, keywords, sec_title, sec_idx, cur, total):
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    col = COLORS[sec_idx % len(COLORS)]
    img = Image.new("RGB", (TARGET_W, TARGET_H), (248, 248, 250))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=col)

    fh = _get_font(18)
    hd = sec_title[:40]
    hw = _text_width(hd, fh)
    hx = (TARGET_W - hw) // 2
    _draw_text(draw, hx, 15, hd, fh, (44, 62, 80))

    if img_bytes:
        try:
            pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            iw, ih = pil.size
            s = min(500 / iw, 250 / ih)
            nw, nh = int(iw * s), int(ih * s)
            pil = pil.resize((nw, nh), Image.LANCZOS)
            px = (TARGET_W - nw) // 2
            py = 50 + (250 - nh) // 2
            draw.rounded_rectangle(
                [(px - 5, py - 5), (px + nw + 5, py + nh + 5)],
                radius=10, outline=col, width=4
            )
            img.paste(pil, (px, py))
        except:
            pass

    fk = _get_font(20)
    vis = keywords[:cur + 1]
    for i, kw in enumerate(vis):
        kcol = COLORS[i % len(COLORS)]
        kwt = kw
        kw_w = _text_width(kwt, fk)
        cx = 100 + (i % 2) * 350
        cy = 330 + (i // 2) * 40
        draw.rounded_rectangle(
            [(cx - 10, cy - 5), (cx + kw_w + 10, cy + 30)],
            radius=8, fill=(*kcol, 20), outline=kcol, width=2
        )
        _draw_text(draw, cx, cy, kwt, fk, kcol)

    dot_y = TARGET_H - 30
    for i in range(total):
        dx = (TARGET_W - total * 25) // 2 + i * 25
        dot_c = col if i <= cur else (200, 200, 200)
        r = 6 if i <= cur else 4
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=dot_c)

    fw = _get_font(12)
    wm_w = _text_width(WATERMARK, fw)
    _draw_text(draw, TARGET_W - wm_w - 20, TARGET_H - 25, WATERMARK, fw, col)

    img.save(path, "JPEG", quality=92)
    return path


def _draw_summary(keywords):
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = Image.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    draw.rectangle([(0, TARGET_H - 8), (TARGET_W, TARGET_H)], fill=COLORS[0])

    f = _get_font(30)
    mt = "📋 ملخص المحاضرة"
    w = _text_width(mt, f)
    x = (TARGET_W - w) // 2
    _draw_text(draw, x, 35, mt, f, (44, 62, 80))

    y = 90
    f2 = _get_font(18)
    for i, kw in enumerate(keywords[:12]):
        col = COLORS[i % len(COLORS)]
        kwt = kw
        kw_w = _text_width(kwt, f2)
        cx = 50 + (i % 3) * 250
        cy = y + (i // 3) * 45
        draw.rounded_rectangle(
            [(cx - 10, cy - 5), (cx + kw_w + 10, cy + 28)],
            radius=8, fill=(*col, 20), outline=col, width=2
        )
        _draw_text(draw, cx, cy, kwt, f2, col)

    f3 = _get_font(26)
    th = "🙏 شكراً لحسن استماعكم"
    w3 = _text_width(th, f3)
    x3 = (TARGET_W - w3) // 2
    _draw_text(draw, x3, TARGET_H - 60, th, f3, COLORS[0])

    img.save(path, "JPEG", quality=90)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# FFmpeg
# ═══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_seg(img, dur, aud, start, out):
    dstr = f"{dur:.3f}"
    if aud and os.path.exists(aud):
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", img,
            "-ss", f"{start:.3f}", "-t", dstr, "-i", aud,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2",
            "-r", "15", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-shortest", "-t", dstr, out
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", img,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2",
            "-r", "15", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            "-shortest", "-t", dstr, out
        ]
    subprocess.run(cmd, capture_output=True)


def _ffmpeg_cat(segs, out):
    fd, lst = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(lst, "w") as f:
        for s in segs:
            f.write(f"file '{s}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], capture_output=True)
    os.remove(lst)


# ═══════════════════════════════════════════════════════════════════════════════
# بناء الفيديو مع الأسئلة التفاعلية
# ═══════════════════════════════════════════════════════════════════════════════

def _build(sections, audio_results, title, all_kw, has_equations):
    segs = []
    tmps = []
    total = 0

    p = _draw_welcome()
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3.5})
    total += 3.5

    p = _draw_title(title)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 4})
    total += 4

    p = _draw_map([s.get("title", "") for s in sections])
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 5})
    total += 5

    for i, (s, a) in enumerate(zip(sections, audio_results)):
        p = _draw_section_title(s.get("title", f"قسم {i+1}"), i)
        tmps.append(p)
        segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3})
        total += 3

        kw = s.get("keywords", ["مفهوم"])
        img = s.get("_image_bytes")
        aud = a.get("audio")
        dur = max(a.get("duration", 30), 5)
        
        # إذا كان هناك معادلات، نعرض خطوات المعادلة
        if has_equations:
            steps = min(3, len(kw))
            kd = dur / (len(kw) + steps + 2)  # +2 للسؤال والجواب
        else:
            kd = dur / (len(kw) + 2)  # +2 للسؤال والجواب

        ap = None
        if aud:
            af, ap = tempfile.mkstemp(suffix=".mp3")
            os.close(af)
            with open(ap, "wb") as f:
                f.write(aud)
            tmps.append(ap)

        # شرائح المحتوى (الكلمات المفتاحية)
        audio_offset = 0
        for j in range(len(kw)):
            p = _draw_content(img, kw, s.get("title", ""), i, j, len(kw))
            tmps.append(p)
            segs.append({"img": p, "audio": ap, "audio_start": audio_offset, "dur": kd})
            audio_offset += kd
            total += kd

        # إذا كان هناك معادلات، نعرض خطوات المعادلة
        if has_equations:
            for step in range(3):
                eq = f"خطوة {step + 1}: {kw[step % len(kw)]} = ..."
                p = _draw_equation_slide(eq, step + 1, 3, i)
                tmps.append(p)
                segs.append({"img": p, "audio": ap, "audio_start": audio_offset, "dur": kd})
                audio_offset += kd
                total += kd

        # سؤال تفاعلي (مؤقت 5 ثواني)
        question = s.get("question", f"❓ ما هو {kw[0]}؟")
        p = _draw_question_slide(question, i)
        tmps.append(p)
        segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 5})
        total += 5

        # شريحة الإجابة
        answer = s.get("answer", f"✅ {kw[0]} هو ...")
        p = _draw_answer_slide(question, answer, i)
        tmps.append(p)
        segs.append({"img": p, "audio": ap, "audio_start": audio_offset, "dur": kd})
        audio_offset += kd
        total += kd

    p = _draw_summary(all_kw)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 6})
    total += 6

    return segs, tmps, total


def _encode(segs, out):
    paths = []
    try:
        for i, s in enumerate(segs):
            fd, p = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)
            paths.append(p)
            _ffmpeg_seg(s["img"], s["dur"], s["audio"], s["audio_start"], p)
        _ffmpeg_cat(paths, out)
    finally:
        for p in paths:
            try:
                os.remove(p)
            except:
                pass


async def create_video_from_sections(sections, audio_results, lecture_data, output_path, dialect="msa", progress_cb=None):
    loop = asyncio.get_event_loop()

    title = lecture_data.get("title", "المحاضرة التعليمية")
    all_kw = lecture_data.get("all_keywords", [])
    has_equations = lecture_data.get("has_equations", False)

    for s in sections:
        if "keywords" not in s or not s["keywords"]:
            s["keywords"] = ["مفهوم", "تعريف", "شرح", "تحليل"]
        if "_image_bytes" not in s:
            s["_image_bytes"] = None
        if "question" not in s:
            s["question"] = f"❓ ما هو {s['keywords'][0]}؟"
        if "answer" not in s:
            s["answer"] = f"✅ {s['keywords'][0]} هو مفهوم أساسي في هذا المجال."

    segs, tmps, total = await loop.run_in_executor(
        None, _build, sections, audio_results, title, all_kw, has_equations
    )

    await loop.run_in_executor(None, _encode, segs, output_path)

    for p in tmps:
        try:
            os.remove(p)
        except:
            pass

    return total
