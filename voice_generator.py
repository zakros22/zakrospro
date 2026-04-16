from moviepy.editor import *
from PIL import Image
import numpy as np
import os
from typing import List, Dict
import random

class VideoMaker:
    def __init__(self):
        self.fps = 24
        self.resolution = (1080, 1080)
    
    def create_video(self, image_paths: List[str], audio_files: Dict[str, str], 
                     analyzed_content: Dict) -> str:
        """إنشاء الفيديو النهائي"""
        
        clips = []
        
        # مقطع العنوان (مع صوت المقدمة)
        title_clip = self.create_image_clip(image_paths[0], audio_files.get('intro'))
        clips.append(title_clip)
        
        # مقاطع الأقسام
        section_images = image_paths[1:-1]  # كل الصور ما عدا الأولى والأخيرة
        for i, img_path in enumerate(section_images):
            audio_key = f'section_{i}'
            if audio_key in audio_files:
                clip = self.create_image_clip(img_path, audio_files[audio_key])
                clips.append(clip)
            else:
                # إذا لم يوجد صوت، استخدم مدة افتراضية
                clip = ImageClip(img_path).set_duration(5)
                clips.append(clip)
        
        # مقطع الملخص
        summary_clip = self.create_image_clip(image_paths[-1], audio_files.get('summary'))
        clips.append(summary_clip)
        
        # دمج جميع المقاطع
        final_video = concatenate_videoclips(clips, method="compose")
        
        # إضافة موسيقى خلفية هادئة (اختياري)
        final_video = self.add_background_music(final_video)
        
        # حفظ الفيديو
        output_path = f"temp/final_video_{random.randint(1000, 9999)}.mp4"
        final_video.write_videofile(
            output_path,
            fps=self.fps,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile='temp-audio.m4a',
            remove_temp=True
        )
        
        # تنظيف
        for clip in clips:
            clip.close()
        final_video.close()
        
        return output_path
    
    def create_image_clip(self, image_path: str, audio_path: str = None) -> VideoClip:
        """إنشاء مقطع فيديو من صورة وصوت"""
        
        # تحميل الصورة
        img_clip = ImageClip(image_path)
        
        if audio_path and os.path.exists(audio_path):
            # تحميل الصوت
            audio_clip = AudioFileClip(audio_path)
            # ضبط مدة الصورة لتتناسب مع مدة الصوت
            img_clip = img_clip.set_duration(audio_clip.duration)
            # إضافة الصوت
            img_clip = img_clip.set_audio(audio_clip)
        else:
            img_clip = img_clip.set_duration(5)
        
        return img_clip
    
    def add_background_music(self, video: VideoClip) -> VideoClip:
        """إضافة موسيقى خلفية (اختياري)"""
        try:
            # يمكنك إضافة ملف موسيقى هادئة
            # music = AudioFileClip("background_music.mp3").volumex(0.1)
            # music = afx.audio_loop(music, duration=video.duration)
            # return video.set_audio(CompositeAudioClip([video.audio, music]))
            pass
        except:
            pass
        return video
    
    def create_transition_effects(self, clips: List[VideoClip]) -> List[VideoClip]:
        """إضافة تأثيرات انتقالية بين المقاطع"""
        clips_with_transitions = []
        
        for i, clip in enumerate(clips):
            if i > 0:
                # تأثير fade in
                clip = clip.crossfadein(0.5)
            if i < len(clips) - 1:
                # تأثير fade out
                clip = clip.crossfadeout(0.5)
            clips_with_transitions.append(clip)
        
        return clips_with_transitions
