#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import io
import os
import subprocess
import tempfile
from typing import Callable, Awaitable

from PIL import Image as PILImage, ImageDraw, ImageFont

# ══════════════════════════════════════════════════════════════════════════════
#  الإعدادات
# ══════════════════════════════════════════════════════════════════════════════
TARGET_W, TARGET_H = 854, 480
WATERMARK = "@zakros_probot"

# الخطوط
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "fonts")
FONT_AR_BOLD = os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")
FONT_AR_REG = os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")

# إعدادات التشفير
_ENC_FACTOR = 0.5
_MIN_ENC_SEC = 15.0

# مدد الشرائح
_INTRO_SEC_PER_SECTION = 2.0
_INTRO_MIN = 6.0
_INTRO_MAX = 20.0
_SECTION_TITLE_DUR = 3.0
_SUMMARY_SEC_PER_SECTION = 1.2
_SUMMARY_MIN = 4.0
_SUMMARY_MAX = 12.0

# ألوان
ACCENT_COLORS = [
    (100, 180, 255), (100, 220, 160), (255, 180, 80),
    (220, 120, 255), (255, 120, 120), (80, 220, 220),
    (255, 200, 100), (160, 255, 160),
]

_ROOM_BG = (22, 35, 55)
_WB_BG = (252, 250, 240)
_WB_FRAME = (80, 60, 40)
_WB_SHADOW = (60, 50, 40)
_CARD_BG = (255, 255, 255)
_CARD_SHD = (200, 196, 188)
_INK = (20, 20, 30)
_HDR_LINE = (220, 175, 40)
_WM_CLR = (170, 175, 185)


# ══════════════════════════════════════════════════════════════════════════════
#  دوال مساعدة للغة العربية
# ══════════════════════════════════════════════════════════════════════════════

def _prepare_arabic_text(text: str) -> str:
    """تحضير النص العربي للعرض الصحيح."""
    if not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _get_font(size: int, bold: bool = False, arabic: bool = False) -> ImageFont.FreeTypeFont:
    """تحميل الخط المناسب."""
    if arabic:
        path = FONT_AR_BOLD if bold else FONT_AR_REG
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _draw_text_centered(draw, text: str, y: int, font, color, is_arabic: bool = False):
    """رسم نص في المنتصف مع دعم العربية."""
    display_text = _prepare_arabic_text(text) if is_arabic else text
    
    try:
        bbox = draw.textbbox((0, 0), display_text, font=font)
        tw = bbox[2] - bbox[0]
    except Exception:
        tw = len(display_text) * (font.size // 2)
    
    x = max((TARGET_W - tw) // 2, 8)
    
    # ظل
    draw.text((x + 2, y + 2), display_text, fill=(0, 0, 0, 140), font=font)
    draw.text((x, y), display_text, fill=color, font=font)


def _gradient_bg(color_top=(10, 20, 50), color_bot=(5, 40, 70)) -> PILImage.Image:
    """خلفية متدرجة."""
    bg = PILImage.new("RGB", (TARGET_W, TARGET_H), color_top)
    draw = ImageDraw.Draw(bg)
    for y in range(TARGET_H):
        t = y / TARGET_H
        r = int(color_top[0] * (1 - t) + color_bot[0] * t)
        g = int(color_top[1] * (1 - t) + color_bot[1] * t)
        b = int(color_top[2] * (1 - t) + color_bot[2] * t)
        draw.line([(0, y), (TARGET_W, y)], fill=(r, g, b))
    return bg


def _arabic_ordinal(n: int) -> str:
    """ترتيبي عربي."""
    ordinals = {
        1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع",
        5: "الخامس", 6: "السادس", 7: "السابع", 8: "الثامن",
        9: "التاسع", 10: "العاشر"
    }
    return ordinals.get(n, str(n))


def estimate_encoding_seconds(total_video_seconds: float) -> float:
    """تقدير وقت التشفير."""
    return max(_MIN_ENC_SEC, total_video_seconds * _ENC_FACTOR)


# ══════════════════════════════════════════════════════════════════════════════
#  شريحة المقدمة
# ══════════════════════════════════════════════════════════════════════════════

def _draw_intro_slide(lecture_data: dict, sections: list, is_arabic: bool) -> str:
    """شريحة المقدمة مع خريطة المحاضرة."""
    fd, path = tempfile.mkstemp(prefix="intro_", suffix=".jpg")
    os.close(fd)
    
    bg = _gradient_bg((10, 20, 50), (5, 40, 70))
    draw = ImageDraw.Draw(bg)
    
    draw.rectangle([(0, 0), (TARGET_W, 5)], fill=(220, 170, 30))
    
    raw_title = lecture_data.get("title", "المحاضرة" if is_arabic else "Lecture")
    title_font = _get_font(24, bold=True, arabic=is_arabic)
    _draw_text_centered(draw, raw_title, 12, title_font, (255, 220, 80), is_arabic)
    
    map_raw = "خريطة المحاضرة" if is_arabic else "Lecture Map"
    map_font = _get_font(14, arabic=is_arabic)
    _draw_text_centered(draw, map_raw, 42, map_font, (180, 200, 230), is_arabic)
    
    draw.rectangle([(40, 62), (TARGET_W - 40, 64)], fill=(220, 170, 30))
    
    sections_to_show = sections[:9]
    n = len(sections_to_show)
    
    body_top = 72
    body_bottom = TARGET_H - 28
    body_h = body_bottom - body_top
    row_h = body_h / max(n, 1)
    
    num_font = _get_font(15, bold=True)
    sec_font = _get_font(16, bold=True, arabic=is_arabic)
    
    for idx, section in enumerate(sections_to_show):
        sec_y = int(body_top + idx * row_h) + 6
        accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
        
        cx, cy, cr = 22, sec_y + 10, 12
        draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=accent)
        
        num_str = str(idx + 1)
        try:
            nb = draw.textbbox((0, 0), num_str, font=num_font)
            nw, nh = nb[2] - nb[0], nb[3] - nb[1]
        except:
            nw, nh = 10, 14
        draw.text((cx - nw // 2, cy - nh // 2), num_str, fill=(10, 20, 50), font=num_font)
        
        draw.rectangle([(cx + cr + 4, cy - 1), (cx + cr + 30, cy + 1)], fill=accent)
        
        sec_title = section.get("title", f"Section {idx + 1}")
        display_title = _prepare_arabic_text(sec_title) if is_arabic else sec_title
        if len(display_title) > 45:
            display_title = display_title[:42] + "..."
        
        draw.text((52, sec_y), display_title, fill=(240, 240, 255), font=sec_font)
    
    # علامة مائية
    wm_font = _get_font(13)
    try:
        wb = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = wb[2] - wb[0]
    except:
        ww = len(WATERMARK) * 8
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 20), WATERMARK, fill=(140, 160, 190), font=wm_font)
    
    bg.save(path, "JPEG", quality=85)
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  شريحة عنوان القسم
# ══════════════════════════════════════════════════════════════════════════════

def _draw_section_title_card(section: dict, idx: int, total: int, is_arabic: bool) -> str:
    """شريحة عنوان القسم."""
    fd, path = tempfile.mkstemp(prefix=f"sec_title_{idx}_", suffix=".jpg")
    os.close(fd)
    
    accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
    dark_accent = tuple(max(0, c - 60) for c in accent)
    
    bg = _gradient_bg((8, 15, 40), dark_accent)
    draw = ImageDraw.Draw(bg)
    
    draw.rectangle([(0, 0), (TARGET_W, 6)], fill=accent)
    draw.rectangle([(0, TARGET_H - 6), (TARGET_W, TARGET_H)], fill=accent)
    
    cx, cy, cr = TARGET_W // 2, TARGET_H // 2 - 55, 48
    draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=accent)
    
    num_str = str(idx + 1)
    num_font = _get_font(42, bold=True)
    try:
        nb = draw.textbbox((0, 0), num_str, font=num_font)
        nw, nh = nb[2] - nb[0], nb[3] - nb[1]
    except:
        nw, nh = 24, 42
    draw.text((cx - nw // 2, cy - nh // 2), num_str, fill=(10, 15, 35), font=num_font)
    
    label_raw = f"القسم {_arabic_ordinal(idx + 1)}" if is_arabic else f"Section {idx + 1} of {total}"
    label_font = _get_font(18, arabic=is_arabic)
    _draw_text_centered(draw, label_raw, cy + cr + 8, label_font, (200, 220, 255), is_arabic)
    
    raw_title = section.get("title", f"Section {idx + 1}")
    title_font = _get_font(28, bold=True, arabic=is_arabic)
    display_title = _prepare_arabic_text(raw_title) if is_arabic else raw_title
    
    try:
        test_bb = draw.textbbox((0, 0), display_title, font=title_font)
        tw = test_bb[2] - test_bb[0]
    except:
        tw = len(display_title) * 16
    
    if tw > TARGET_W - 80:
        words = display_title.split()
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])
        _draw_text_centered(draw, line1, cy + cr + 34, title_font, accent, is_arabic)
        _draw_text_centered(draw, line2, cy + cr + 70, title_font, accent, is_arabic)
    else:
        _draw_text_centered(draw, display_title, cy + cr + 34, title_font, accent, is_arabic)
    
    draw.rectangle([(TARGET_W // 4, cy - cr - 10), (TARGET_W * 3 // 4, cy - cr - 8)], fill=accent)
    
    wm_font = _get_font(13)
    try:
        wb = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = wb[2] - wb[0]
    except:
        ww = len(WATERMARK) * 8
    draw.text(((TARGET_W - ww) // 2, TARGET_H - 22), WATERMARK, fill=(140, 160, 190), font=wm_font)
    
    bg.save(path, "JPEG", quality=85)
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  شريحة المحتوى - السبورة
# ══════════════════════════════════════════════════════════════════════════════

def _draw_board_slide(
    image_bytes: bytes | None,
    keywords: list[str],
    current_kw_idx: int,
    is_arabic: bool,
    section_title: str = "",
    section_idx: int = 0,
    total_sections: int = 1,
    revealed_images: list[bytes | None] | None = None,
) -> str:
    """شريحة السبورة مع البطاقات."""
    fd, path = tempfile.mkstemp(prefix="board_", suffix=".jpg")
    os.close(fd)
    
    n_kws = max(len(keywords), 1)
    accent = ACCENT_COLORS[section_idx % len(ACCENT_COLORS)]
    n_revealed = current_kw_idx + 1
    
    if revealed_images and len(revealed_images) == len(keywords):
        kw_imgs = revealed_images
    else:
        kw_imgs = [image_bytes] * len(keywords)
    
    canvas = PILImage.new("RGB", (TARGET_W, TARGET_H), _ROOM_BG)
    draw = ImageDraw.Draw(canvas)
    
    BM = 14
    BSH = 5
    draw.rounded_rectangle(
        [(BM + BSH, BM + BSH), (TARGET_W - BM + BSH, TARGET_H - BM + BSH)],
        radius=6, fill=_WB_SHADOW
    )
    
    FRAME = 6
    draw.rounded_rectangle(
        [(BM, BM), (TARGET_W - BM, TARGET_H - BM)],
        radius=6, fill=_WB_FRAME
    )
    
    BX1 = BM + FRAME
    BY1 = BM + FRAME
    BX2 = TARGET_W - BM - FRAME
    BY2 = TARGET_H - BM - FRAME
    draw.rounded_rectangle([(BX1, BY1), (BX2, BY2)], radius=4, fill=_WB_BG)
    
    for ly in range(BY1 + 30, BY2, 22):
        draw.line([(BX1 + 10, ly), (BX2 - 10, ly)], fill=(240, 237, 225), width=1)
    
    HDR_H = 40
    draw.rectangle([(BX1, BY1), (BX2, BY1 + 4)], fill=accent)
    
    title_font = _get_font(19, bold=True, arabic=is_arabic)
    raw_title = (section_title or "")[:50]
    display_title = _prepare_arabic_text(raw_title) if is_arabic else raw_title
    
    try:
        tb = draw.textbbox((0, 0), display_title, font=title_font)
        t_w, t_h = tb[2] - tb[0], tb[3] - tb[1]
    except:
        t_w, t_h = len(display_title) * 11, 20
    
    tx = max((BX1 + BX2 - t_w) // 2, BX1 + 8)
    ty = BY1 + 4 + (HDR_H - 4 - t_h) // 2
    draw.text((tx + 1, ty + 1), display_title, fill=(160, 155, 140), font=title_font)
    draw.text((tx, ty), display_title, fill=_INK, font=title_font)
    
    draw.rectangle([(BX1 + 8, BY1 + HDR_H - 2), (BX2 - 8, BY1 + HDR_H)], fill=_HDR_LINE)
    
    num_str = f"{section_idx + 1} / {total_sections}"
    num_font = _get_font(11)
    try:
        nb = draw.textbbox((0, 0), num_str, font=num_font)
        n_w = nb[2] - nb[0]
    except:
        n_w = len(num_str) * 7
    num_x = (BX1 + 8) if is_arabic else (BX2 - n_w - 8)
    draw.text((num_x, BY1 + 6), num_str, fill=(160, 155, 140), font=num_font)
    
    FOOT_H = 22
    CONTENT_TOP = BY1 + HDR_H + 6
    CONTENT_BOT = BY2 - FOOT_H
    CONTENT_W = BX2 - BX1
    CONTENT_H = CONTENT_BOT - CONTENT_TOP
    
    if n_revealed == 1:
        cols, rows = 1, 1
    elif n_revealed == 2:
        cols, rows = 2, 1
    else:
        cols, rows = 2, 2
    
    CARD_PAD = 10
    card_w = (CONTENT_W - (cols + 1) * CARD_PAD) // cols
    card_h = (CONTENT_H - (rows + 1) * CARD_PAD) // rows
    
    kw_font = _get_font(14, bold=True, arabic=is_arabic)
    
    for slot in range(n_revealed):
        col = slot % cols
        row = slot // cols
        
        cx = BX1 + CARD_PAD + col * (card_w + CARD_PAD)
        cy = CONTENT_TOP + CARD_PAD + row * (card_h + CARD_PAD)
        
        draw.rounded_rectangle(
            [(cx + 3, cy + 3), (cx + card_w + 3, cy + card_h + 3)],
            radius=5, fill=_CARD_SHD
        )
        draw.rounded_rectangle(
            [(cx, cy), (cx + card_w, cy + card_h)],
            radius=5, fill=_CARD_BG
        )
        
        tape_clr = ACCENT_COLORS[slot % len(ACCENT_COLORS)]
        draw.rectangle(
            [(cx + card_w // 2 - 20, cy - 4), (cx + card_w // 2 + 20, cy + 6)],
            fill=tape_clr
        )
        
        LABEL_H = 30
        IMG_H = card_h - LABEL_H - 6
        
        img_bytes_slot = kw_imgs[slot] if slot < len(kw_imgs) else None
        IMG_PAD = 6
        if img_bytes_slot:
            try:
                img = PILImage.open(io.BytesIO(img_bytes_slot)).convert("RGB")
                iw, ih = img.size
                max_iw = card_w - IMG_PAD * 2
                max_ih = IMG_H - IMG_PAD
                scale = min(max_iw / iw, max_ih / ih)
                nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
                img = img.resize((nw, nh), PILImage.LANCZOS)
                px = cx + (card_w - nw) // 2
                py = cy + IMG_PAD + (IMG_H - IMG_PAD - nh) // 2
                canvas.paste(img, (px, py))
            except:
                pass
        
        draw = ImageDraw.Draw(canvas)
        
        kw_raw = (keywords[slot] if slot < len(keywords) else "")[:28]
        kw_disp = _prepare_arabic_text(kw_raw) if is_arabic else kw_raw
        
        try:
            kb = draw.textbbox((0, 0), kw_disp, font=kw_font)
            kw_w, kw_h = kb[2] - kb[0], kb[3] - kb[1]
        except:
            kw_w, kw_h = len(kw_disp) * 9, 16
        
        label_y = cy + card_h - LABEL_H + (LABEL_H - kw_h) // 2
        lx = cx + (card_w - kw_w) // 2
        lx = max(lx, cx + 4)
        
        draw.rectangle(
            [(cx + 8, cy + card_h - 4), (cx + card_w - 8, cy + card_h - 2)],
            fill=tape_clr
        )
        draw.text((lx + 1, label_y + 1), kw_disp, fill=(180, 175, 165), font=kw_font)
        draw.text((lx, label_y), kw_disp, fill=_INK, font=kw_font)
    
    draw = ImageDraw.Draw(canvas)
    
    dot_r = 4
    dot_gap = 16
    dot_total_w = n_kws * dot_gap
    dot_start = (TARGET_W - dot_total_w) // 2
    dot_y = BY2 - BM // 2 - 3
    for i in range(n_kws):
        dx = dot_start + i * dot_gap
        clr = accent if i < n_revealed else (180, 175, 165)
        r = dot_r if i < n_revealed else dot_r - 1
        draw.ellipse([(dx - r, dot_y - r), (dx + r, dot_y + r)], fill=clr)
    
    wm_font = _get_font(10)
    try:
        wb = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww2 = wb[2] - wb[0]
    except:
        ww2 = len(WATERMARK) * 6
    draw.text(((TARGET_W - ww2) // 2, BY2 - 10), WATERMARK, fill=_WM_CLR, font=wm_font)
    
    canvas.save(path, "JPEG", quality=93)
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  شريحة الملخص
# ══════════════════════════════════════════════════════════════════════════════

def _draw_summary_slide(sections: list, lecture_data: dict, is_arabic: bool) -> str:
    """شريحة الملخص النهائي."""
    fd, path = tempfile.mkstemp(prefix="summary_", suffix=".jpg")
    os.close(fd)
    
    canvas = PILImage.new("RGB", (TARGET_W, TARGET_H), _ROOM_BG)
    draw = ImageDraw.Draw(canvas)
    
    BM = 14
    draw.rounded_rectangle(
        [(BM + 4, BM + 4), (TARGET_W - BM + 4, TARGET_H - BM + 4)],
        radius=8, fill=_WB_SHADOW
    )
    draw.rounded_rectangle(
        [(BM, BM), (TARGET_W - BM, TARGET_H - BM)],
        radius=8, fill=_WB_BG
    )
    
    HDR_H = 40
    draw.rounded_rectangle(
        [(BM, BM), (TARGET_W - BM, BM + HDR_H)],
        radius=8, fill=(28, 44, 68)
    )
    draw.rectangle([(BM, BM), (TARGET_W - BM, BM + 5)], fill=(220, 175, 40))
    
    lecture_title = lecture_data.get("title", "")
    hdr_raw = f"📋 ملخص — {lecture_title[:30]}" if is_arabic else f"Summary — {lecture_title[:30]}"
    hdr_font = _get_font(18, bold=True, arabic=is_arabic)
    display_hdr = _prepare_arabic_text(hdr_raw) if is_arabic else hdr_raw
    
    try:
        hb = draw.textbbox((0, 0), display_hdr, font=hdr_font)
        h_w, h_h = hb[2] - hb[0], hb[3] - hb[1]
    except:
        h_w, h_h = len(display_hdr) * 11, 20
    
    hx = max((TARGET_W - h_w) // 2, BM + 10)
    hy = BM + (HDR_H - h_h) // 2
    draw.text((hx, hy), display_hdr, fill=(255, 220, 80), font=hdr_font)
    
    GRID_TOP = BM + HDR_H + 8
    GRID_BOT = TARGET_H - BM - 20
    GRID_LEFT = BM + 8
    GRID_RIGHT = TARGET_W - BM - 8
    
    n = min(len(sections), 9)
    if n == 0:
        canvas.save(path, "JPEG", quality=90)
        return path
    
    if n <= 2:
        cols, rows = n, 1
    elif n <= 4:
        cols, rows = 2, 2
    else:
        cols, rows = 3, 3
    
    cell_w = (GRID_RIGHT - GRID_LEFT) // cols
    cell_h = (GRID_BOT - GRID_TOP) // rows
    CARD_PAD = 5
    
    title_font = _get_font(12, bold=True, arabic=is_arabic)
    
    for idx, section in enumerate(sections[:n]):
        col = idx % cols
        row = idx // cols
        cx1 = GRID_LEFT + col * cell_w + CARD_PAD
        cy1 = GRID_TOP + row * cell_h + CARD_PAD
        cx2 = cx1 + cell_w - CARD_PAD * 2
        cy2 = cy1 + cell_h - CARD_PAD * 2
        
        accent = ACCENT_COLORS[idx % len(ACCENT_COLORS)]
        
        draw.rounded_rectangle([(cx1, cy1), (cx2, cy2)], radius=5, fill=(245, 243, 238))
        draw.rounded_rectangle([(cx1, cy1), (cx2, cy2)], radius=5, outline=accent, width=2)
        
        badge_r = 12
        bx, by = cx1 + badge_r + 3, cy1 + badge_r + 3
        draw.ellipse([(bx - badge_r, by - badge_r), (bx + badge_r, by + badge_r)], fill=accent)
        
        num_str = str(idx + 1)
        num_font = _get_font(12, bold=True)
        try:
            nb = draw.textbbox((0, 0), num_str, font=num_font)
            nw, nh = nb[2] - nb[0], nb[3] - nb[1]
        except:
            nw, nh = 8, 12
        draw.text((bx - nw // 2, by - nh // 2), num_str, fill=(255, 255, 255), font=num_font)
        
        TEXT_TOP = cy1 + (cy2 - cy1) // 3
        raw_t = section.get("title", f"Section {idx+1}")[:28]
        display_t = _prepare_arabic_text(raw_t) if is_arabic else raw_t
        
        try:
            tb = draw.textbbox((0, 0), display_t, font=title_font)
            t_w = tb[2] - tb[0]
        except:
            t_w = len(display_t) * 7
        
        t_x = cx1 + (cx2 - cx1 - t_w) // 2
        t_x = max(t_x, cx1 + 2)
        draw.text((t_x, TEXT_TOP), display_t, fill=(30, 35, 50), font=title_font)
    
    wm_font = _get_font(11)
    try:
        wb = draw.textbbox((0, 0), WATERMARK, font=wm_font)
        ww = wb[2] - wb[0]
    except:
        ww = len(WATERMARK) * 7
    draw.text(((TARGET_W - ww) // 2, TARGET_H - BM - 14), WATERMARK, fill=_WM_CLR, font=wm_font)
    
    canvas.save(path, "JPEG", quality=90)
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  دوال FFmpeg
# ══════════════════════════════════════════════════════════════════════════════

def _ffmpeg_segment(img_path: str, duration: float, audio_path: str | None,
                    audio_start: float, out_path: str, gentle_zoom: bool = False,
                    motion_idx: int = 0) -> None:
    """تشفير مقطع فيديو."""
    dur_str = f"{duration:.3f}"
    fps_main = 15
    
    def _audio_args():
        if audio_path and os.path.exists(audio_path):
            return ["-ss", f"{audio_start:.3f}", "-t", dur_str, "-i", audio_path]
        return ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    
    if gentle_zoom:
        n_frames = max(int(duration * fps_main), 2)
        patterns = [
            f"zoompan=z='min(zoom+0.00015,1.03)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s={TARGET_W}x{TARGET_H}:fps={fps_main}",
            f"zoompan=z='1.02':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s={TARGET_W}x{TARGET_H}:fps={fps_main}",
        ]
        vf = f"scale=900:506,{patterns[motion_idx % len(patterns)]}"
        aud = _audio_args()
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", dur_str, "-i", img_path,
            *aud,
            "-vf", vf,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-r", str(fps_main),
            "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
            "-t", dur_str, out_path,
        ]
    else:
        vf = "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2"
        aud = _audio_args()
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", dur_str, "-i", img_path,
            *aud,
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-r", "10", "-vf", vf,
            "-map", "0:v", "-map", "1:a",
            "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
            "-t", dur_str, out_path,
        ]
    
    subprocess.run(cmd, capture_output=True)


def _ffmpeg_concat(segment_paths: list[str], output_path: str) -> None:
    """دمج المقاطع."""
    fd, list_path = tempfile.mkstemp(suffix=".txt")
    try:
        os.close(fd)
        with open(list_path, "w") as f:
            for p in segment_paths:
                f.write(f"file '{p}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", list_path,
            "-c", "copy", output_path,
        ]
        subprocess.run(cmd, capture_output=True)
    finally:
        try:
            os.remove(list_path)
        except:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  بناء المقاطع
# ══════════════════════════════════════════════════════════════════════════════

def _build_segment_list(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    is_arabic: bool,
) -> tuple[list[dict], list[str], float]:
    """بناء قائمة المقاطع."""
    segments = []
    tmp_files = []
    total_secs = 0.0
    n_sections = len(sections)
    
    # مقدمة
    intro_dur = min(_INTRO_MAX, max(_INTRO_MIN, n_sections * _INTRO_SEC_PER_SECTION))
    intro_path = _draw_intro_slide(lecture_data, sections, is_arabic)
    tmp_files.append(intro_path)
    segments.append({"img": intro_path, "audio": None, "audio_start": 0.0, "dur": intro_dur})
    total_secs += intro_dur
    
    # أقسام
    for sec_idx, (section, audio_info) in enumerate(zip(sections, audio_results)):
        title_path = _draw_section_title_card(section, sec_idx, n_sections, is_arabic)
        tmp_files.append(title_path)
        segments.append({"img": title_path, "audio": None, "audio_start": 0.0, "dur": _SECTION_TITLE_DUR})
        total_secs += _SECTION_TITLE_DUR
        
        keywords = section.get("keywords") or [section.get("title", f"Section {sec_idx + 1}")]
        kw_images = section.get("_keyword_images") or []
        audio_bytes = audio_info.get("audio")
        total_dur = max(float(audio_info.get("duration", 8) or 8), 3.0)
        kw_dur = total_dur / max(len(keywords), 1)
        
        apath = None
        if audio_bytes:
            afd, apath = tempfile.mkstemp(prefix=f"aud_{sec_idx}_", suffix=".mp3")
            os.close(afd)
            with open(apath, "wb") as f:
                f.write(audio_bytes)
            tmp_files.append(apath)
        
        fallback_img = section.get("_image_bytes")
        resolved_images = [
            (kw_images[i] if i < len(kw_images) and kw_images[i] else fallback_img)
            for i in range(len(keywords))
        ]
        
        for kw_idx in range(len(keywords)):
            board_path = _draw_board_slide(
                image_bytes=resolved_images[kw_idx],
                keywords=keywords,
                current_kw_idx=kw_idx,
                is_arabic=is_arabic,
                section_title=section.get("title", ""),
                section_idx=sec_idx,
                total_sections=n_sections,
                revealed_images=resolved_images,
            )
            tmp_files.append(board_path)
            
            segments.append({
                "img": board_path,
                "gentle_zoom": True,
                "motion_idx": kw_idx % 4,
                "audio": apath,
                "audio_start": kw_idx * kw_dur,
                "dur": kw_dur,
            })
            total_secs += kw_dur
    
    # ملخص
    summary_dur = min(_SUMMARY_MAX, max(_SUMMARY_MIN, n_sections * _SUMMARY_SEC_PER_SECTION))
    summary_path = _draw_summary_slide(sections, lecture_data, is_arabic)
    tmp_files.append(summary_path)
    segments.append({"img": summary_path, "audio": None, "audio_start": 0.0, "dur": summary_dur})
    total_secs += summary_dur
    
    return segments, tmp_files, total_secs


def _encode_all_sync(segments: list[dict], output_path: str) -> None:
    """تشفير جميع المقاطع."""
    seg_paths = []
    try:
        for i, seg in enumerate(segments):
            fd, seg_out = tempfile.mkstemp(prefix=f"seg_{i}_", suffix=".mp4")
            os.close(fd)
            seg_paths.append(seg_out)
            
            _ffmpeg_segment(
                seg["img"], seg["dur"], seg["audio"], seg["audio_start"], seg_out,
                gentle_zoom=seg.get("gentle_zoom", False),
                motion_idx=seg.get("motion_idx", 0),
            )
        
        _ffmpeg_concat(seg_paths, output_path)
    finally:
        for p in seg_paths:
            try:
                os.remove(p)
            except:
                pass


# ══════════════════════════════════════════════════════════════════════════════
#  الدالة الرئيسية
# ══════════════════════════════════════════════════════════════════════════════

async def create_video_from_sections(
    sections: list,
    audio_results: list,
    lecture_data: dict,
    output_path: str,
    dialect: str = "msa",
    progress_cb: Callable[[float, float], Awaitable[None]] | None = None,
) -> float:
    """إنشاء الفيديو النهائي."""
    is_arabic = dialect not in ("english", "british")
    loop = asyncio.get_event_loop()
    
    segments, tmp_files, total_video_secs = await loop.run_in_executor(
        None, _build_segment_list, sections, audio_results, lecture_data, is_arabic
    )
    
    if not segments:
        raise RuntimeError("No valid segments generated")
    
    estimated_enc = estimate_encoding_seconds(total_video_secs)
    encode_task = loop.run_in_executor(None, _encode_all_sync, segments, output_path)
    
    start = loop.time()
    try:
        while not encode_task.done():
            await asyncio.sleep(3)
            if encode_task.done():
                break
            elapsed = loop.time() - start
            if progress_cb:
                try:
                    await progress_cb(elapsed, estimated_enc)
                except:
                    pass
        await encode_task
    finally:
        for path in tmp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
    
    return total_video_secs
