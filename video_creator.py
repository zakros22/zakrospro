#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
إنشاء الفيديو النهائي من الصور والصوت
"""

import os
import tempfile
import subprocess
import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  الإعدادات
# ══════════════════════════════════════════════════════════════════════════════
INTRO_DURATION = 5.0
SUMMARY_DURATION = 6.0


def estimate_encoding_seconds(total_duration: float) -> float:
    """تقدير وقت التشفير."""
    return max(15, total_duration * 0.35)


# ══════════════════════════════════════════════════════════════════════════════
#  إنشاء الفيديو
# ══════════════════════════════════════════════════════════════════════════════
def create_video_segments(
    intro_img: str,
    section_images: list,
    summary_img: str,
    audio_paths: list,
    durations: list,
    output_path: str
) -> float:
    """
    إنشاء الفيديو من الصور والصوتيات.
    
    Args:
        intro_img: صورة المقدمة
        section_images: صور الأقسام
        summary_img: صورة الملخص
        audio_paths: مسارات ملفات الصوت
        durations: مدد كل شريحة
        output_path: مسار حفظ الفيديو
    
    Returns:
        المدة الإجمالية للفيديو
    """
    video_segments = []
    temp_files = []
    total_duration = INTRO_DURATION
    
    try:
        # 1. شريحة المقدمة
        intro_out = tempfile.mktemp(suffix=".mp4")
        temp_files.append(intro_out)
        video_segments.append(intro_out)
        
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-t", str(INTRO_DURATION), "-i", intro_img,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map", "0:v", "-map", "1:a",
            "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10",
            "-c:a", "aac", "-b:a", "64k", "-t", str(INTRO_DURATION), intro_out
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"✅ تم إنشاء شريحة المقدمة ({INTRO_DURATION}s)")
        
        # 2. شرائح الأقسام
        for i, (img, audio, dur) in enumerate(zip(section_images, audio_paths, durations)):
            seg_out = tempfile.mktemp(suffix=".mp4")
            temp_files.append(seg_out)
            video_segments.append(seg_out)
            total_duration += dur
            
            if audio and os.path.exists(audio):
                aud_args = ["-i", audio]
                aud_map = ["-map", "0:v", "-map", "1:a"]
            else:
                aud_args = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
                aud_map = ["-map", "0:v", "-map", "1:a"]
            
            cmd = [
                "ffmpeg", "-y", "-loop", "1", "-t", str(dur), "-i", img,
                *aud_args, *aud_map,
                "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10",
                "-c:a", "aac", "-b:a", "64k", "-t", str(dur), seg_out
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            logger.info(f"✅ تم إنشاء شريحة القسم {i+1} ({dur}s)")
        
        # 3. شريحة الملخص
        total_duration += SUMMARY_DURATION
        summary_out = tempfile.mktemp(suffix=".mp4")
        temp_files.append(summary_out)
        video_segments.append(summary_out)
        
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-t", str(SUMMARY_DURATION), "-i", summary_img,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map", "0:v", "-map", "1:a",
            "-vf", "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-r", "10",
            "-c:a", "aac", "-b:a", "64k", "-t", str(SUMMARY_DURATION), summary_out
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"✅ تم إنشاء شريحة الملخص ({SUMMARY_DURATION}s)")
        
        # 4. دمج المقاطع
        list_file = tempfile.mktemp(suffix=".txt")
        temp_files.append(list_file)
        
        with open(list_file, "w") as f:
            for seg in video_segments:
                f.write(f"file '{seg}'\n")
        
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
            "-c", "copy", output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"✅ تم دمج الفيديو النهائي ({total_duration:.1f}s)")
        
        return total_duration
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ خطأ في FFmpeg: {e.stderr.decode() if e.stderr else str(e)}")
        raise
    finally:
        # تنظيف
        for f in temp_files:
            try:
                os.remove(f)
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
    progress_cb: Callable[[float, float], Awaitable[None]] = None
) -> float:
    """
    إنشاء الفيديو النهائي.
    
    Args:
        sections: الأقسام مع الصور
        audio_results: نتائج الصوت
        lecture_data: بيانات المحاضرة
        output_path: مسار الحفظ
        dialect: اللهجة
        progress_cb: دالة تحديث التقدم
    
    Returns:
        مدة الفيديو بالثواني
    """
    from image_generator import create_educational_card, create_intro_card, create_summary_card
    
    is_arabic = dialect not in ("english", "british")
    subject = lecture_data.get("lecture_type", "other")
    lecture_title = lecture_data.get("title", "المحاضرة")
    
    # تجهيز الصور والصوتيات
    section_images = []
    audio_paths = []
    durations = []
    
    for i, (sec, aud) in enumerate(zip(sections, audio_results)):
        # الحصول على الصورة أو إنشاؤها
        img_path = sec.get("_image_path")
        if not img_path:
            keywords = sec.get("keywords", [])
            title = sec.get("title", f"القسم {i+1}")
            img_path = create_educational_card(
                title, keywords, subject, i+1, len(sections), is_arabic
            )
            sec["_image_path"] = img_path
        
        section_images.append(img_path)
        
        # تجهيز الصوت
        audio_bytes = aud.get("audio")
        if audio_bytes:
            fd, ap = tempfile.mkstemp(suffix=".mp3", dir="/tmp/telegram_bot")
            os.close(fd)
            with open(ap, "wb") as f:
                f.write(audio_bytes)
            audio_paths.append(ap)
        else:
            audio_paths.append(None)
        
        durations.append(max(aud.get("duration", 10), 8))
    
    # إنشاء صورة المقدمة
    intro_img = create_intro_card(lecture_title, sections, subject, is_arabic)
    
    # إنشاء صورة الملخص
    summary_img = create_summary_card(sections, lecture_title, subject, is_arabic)
    
    # حساب المدة الإجمالية المتوقعة
    total_duration = INTRO_DURATION + sum(durations) + SUMMARY_DURATION
    estimated_enc = estimate_encoding_seconds(total_duration)
    
    # إنشاء الفيديو في الخلفية
    loop = asyncio.get_event_loop()
    
    async def run_encode():
        return await loop.run_in_executor(
            None,
            create_video_segments,
            intro_img, section_images, summary_img,
            audio_paths, durations, output_path
        )
    
    encode_task = asyncio.create_task(run_encode())
    
    start = loop.time()
    while not encode_task.done():
        await asyncio.sleep(2)
        if progress_cb:
            elapsed = loop.time() - start
            try:
                await progress_cb(elapsed, estimated_enc)
            except:
                pass
    
    actual_duration = await encode_task
    
    # تنظيف ملفات الصوت
    for ap in audio_paths:
        if ap:
            try:
                os.remove(ap)
            except:
                pass
    
    # تنظيف الصور المؤقتة
    for sec in sections:
        img = sec.get("_image_path")
        if img and os.path.exists(img):
            try:
                os.remove(img)
            except:
                pass
    
    try:
        os.remove(intro_img)
        os.remove(summary_img)
    except:
        pass
    
    return actual_duration
