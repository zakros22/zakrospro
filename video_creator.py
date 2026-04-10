import asyncio
import io
import os
import subprocess
import tempfile
from PIL import Image as PILImage, ImageDraw, ImageFont

TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

COLORS = [
    (231, 76, 126),
    (52, 152, 219),
    (46, 204, 113),
    (155, 89, 182),
    (230, 126, 34),
]


def estimate_encoding_seconds(t: float) -> float:
    return max(20, t * 0.6)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _draw_welcome() -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    font = _get_font(60)
    try:
        bbox = font.getbbox(WATERMARK)
        w = bbox[2] - bbox[0]
    except:
        w = len(WATERMARK) * 35
    x = (TARGET_W - w) // 2
    draw.text((x, TARGET_H//2 - 30), WATERMARK, fill=COLORS[0], font=font)
    
    font2 = _get_font(36)
    welcome = "أهلاً ومرحباً بكم"
    try:
        bbox = font2.getbbox(welcome)
        w2 = bbox[2] - bbox[0]
    except:
        w2 = len(welcome) * 20
    x2 = (TARGET_W - w2) // 2
    draw.text((x2, TARGET_H//2 + 40), welcome, fill=(44, 62, 80), font=font2)
    
    img.save(path, "JPEG", quality=90)
    return path


def _draw_title(title: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=COLORS[1])
    font = _get_font(38)
    
    try:
        bbox = font.getbbox(title)
        w = bbox[2] - bbox[0]
    except:
        w = len(title) * 22
    
    x = (TARGET_W - w) // 2
    draw.text((x, TARGET_H//2 - 20), title, fill=(44, 62, 80), font=font)
    
    img.save(path, "JPEG", quality=90)
    return path


def _draw_section_title(title: str, idx: int) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    color = COLORS[idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)
    
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 40, 40
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=color)
    
    font = _get_font(36)
    num = str(idx + 1)
    try:
        bbox = font.getbbox(num)
        w = bbox[2] - bbox[0]
    except:
        w = 20
    draw.text((cx - w//2, cy - 20), num, fill=(255, 255, 255), font=font)
    
    font2 = _get_font(30)
    try:
        bbox = font2.getbbox(title)
        w2 = bbox[2] - bbox[0]
    except:
        w2 = len(title) * 17
    x = (TARGET_W - w2) // 2
    draw.text((x, cy + cr + 30), title, fill=(44, 62, 80), font=font2)
    
    img.save(path, "JPEG", quality=90)
    return path


def _draw_board(keywords: list, images: list, current: int, total: int, section_title: str, sec_idx: int) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    
    color = COLORS[sec_idx % len(COLORS)]
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (248, 248, 250))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=color)
    
    font = _get_font(18)
    try:
        bbox = font.getbbox(section_title[:40])
        w = bbox[2] - bbox[0]
    except:
        w = len(section_title[:40]) * 10
    x = (TARGET_W - w) // 2
    draw.text((x, 15), section_title[:40], fill=(44, 62, 80), font=font)
    
    n = len(keywords)
    if n == 1:
        # صورة واحدة كبيرة
        if images and images[0]:
            try:
                pil = PILImage.open(io.BytesIO(images[0])).convert("RGB")
                pil = pil.resize((500, 340), PILImage.LANCZOS)
                px = (TARGET_W - 500) // 2
                img.paste(pil, (px, 70))
            except:
                pass
    else:
        # شبكة
        for i in range(n):
            col = i % 2
            row = i // 2
            cx = 50 + col * 380
            cy = 70 + row * 290
            
            if i < len(images) and images[i]:
                try:
                    pil = PILImage.open(io.BytesIO(images[i])).convert("RGB")
                    pil = pil.resize((360, 270), PILImage.LANCZOS)
                    img.paste(pil, (cx, cy))
                except:
                    pass
    
    # مؤشر
    dot_y = TARGET_H - 30
    for i in range(total):
        dx = (TARGET_W - total * 25) // 2 + i * 25
        dot_color = color if i <= current else (200, 200, 200)
        r = 6 if i <= current else 4
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=dot_color)
    
    img.save(path, "JPEG", quality=92)
    return path


def _draw_summary(keywords: list) -> str:
    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img = PILImage.new("RGB", (TARGET_W, TARGET_H), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([(0, 0), (TARGET_W, 8)], fill=COLORS[0])
    
    font = _get_font(30)
    title = "📋 ملخص المحاضرة"
    try:
        bbox = font.getbbox(title)
        w = bbox[2] - bbox[0]
    except:
        w = len(title) * 18
    x = (TARGET_W - w) // 2
    draw.text((x, 35), title, fill=(44, 62, 80), font=font)
    
    font2 = _get_font(18)
    y = 90
    for i, kw in enumerate(keywords[:12]):
        color = COLORS[i % len(COLORS)]
        try:
            bbox = font2.getbbox(kw)
            w2 = bbox[2] - bbox[0]
        except:
            w2 = len(kw) * 10
        
        col = i % 3
        row = i // 3
        cx = 50 + col * 250
        cy = y + row * 45
        
        draw.rounded_rectangle([(cx - 10, cy - 5), (cx + w2 + 10, cy + 28)], radius=8, fill=(*color, 20), outline=color, width=2)
        draw.text((cx, cy), kw, fill=color, font=font2)
    
    font3 = _get_font(26)
    thanks = "🙏 شكراً لحسن استماعكم"
    try:
        bbox = font3.getbbox(thanks)
        w3 = bbox[2] - bbox[0]
    except:
        w3 = len(thanks) * 15
    x3 = (TARGET_W - w3) // 2
    draw.text((x3, TARGET_H - 60), thanks, fill=COLORS[0], font=font3)
    
    img.save(path, "JPEG", quality=90)
    return path


def _ffmpeg_segment(img: str, dur: float, audio: str | None, start: float, out: str):
    dur_str = f"{dur:.3f}"
    aud = ["-ss", f"{start:.3f}", "-t", dur_str, "-i", audio] if audio else ["-f", "lavfi", "-i", "anullsrc"]
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-t", dur_str, "-i", img, *aud,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-r", "15",
        "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2",
        "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "96k", "-t", dur_str, out
    ]
    subprocess.run(cmd, capture_output=True)


def _ffmpeg_concat(segs: list, out: str):
    fd, lst = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    with open(lst, "w") as f:
        for p in segs:
            f.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], capture_output=True)
    os.remove(lst)


def _build_segments(sections: list, audio_results: list, title: str, all_kw: list):
    segs, tmps, total = [], [], 0
    
    # مقدمة
    p = _draw_welcome()
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3.5})
    total += 3.5
    
    # عنوان
    p = _draw_title(title)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 4})
    total += 4
    
    # أقسام
    for sec_idx, (sec, aud) in enumerate(zip(sections, audio_results)):
        p = _draw_section_title(sec.get("title", f"قسم {sec_idx+1}"), sec_idx)
        tmps.append(p)
        segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 3})
        total += 3
        
        keywords = sec.get("keywords", ["مفهوم"])
        images = sec.get("_keyword_images", [])
        audio_bytes = aud.get("audio")
        total_dur = max(aud.get("duration", 30), 5)
        kw_dur = total_dur / len(keywords)
        
        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmps.append(apath)
        
        accum_kw, accum_img = [], []
        for kw_idx in range(len(keywords)):
            accum_kw.append(keywords[kw_idx])
            if kw_idx < len(images):
                accum_img.append(images[kw_idx])
            else:
                accum_img.append(None)
            
            p = _draw_board(accum_kw, accum_img, kw_idx, len(keywords), sec.get("title", ""), sec_idx)
            tmps.append(p)
            segs.append({"img": p, "audio": apath, "audio_start": kw_idx * kw_dur, "dur": kw_dur})
            total += kw_dur
    
    # خاتمة
    p = _draw_summary(all_kw)
    tmps.append(p)
    segs.append({"img": p, "audio": None, "audio_start": 0, "dur": 6})
    total += 6
    
    return segs, tmps, total


def _encode(segs: list, out: str):
    paths = []
    for i, s in enumerate(segs):
        fd, p = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        paths.append(p)
        _ffmpeg_segment(s["img"], s["dur"], s["audio"], s["audio_start"], p)
    _ffmpeg_concat(paths, out)
    for p in paths:
        os.remove(p)


async def create_video_from_sections(sections: list, audio_results: list, lecture_data: dict, output_path: str, dialect: str = "msa", progress_cb=None) -> float:
    loop = asyncio.get_event_loop()
    title = lecture_data.get("title", "المحاضرة")
    all_kw = lecture_data.get("all_keywords", [])
    
    segs, tmps, total = await loop.run_in_executor(None, _build_segments, sections, audio_results, title, all_kw)
    await loop.run_in_executor(None, _encode, segs, output_path)
    
    for p in tmps:
        try:
            os.remove(p)
        except:
            pass
    
    return total
