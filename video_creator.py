import os
import tempfile
from moviepy.editor import AudioFileClip, CompositeVideoClip, ImageClip, concatenate_videoclips

async def create_video_from_sections(sections: list, audio_results: list, lecture_data: dict, output_path: str):
    """إنشاء فيديو من الصور والصوت"""
    tmp_files = []
    clips = []
    
    try:
        for index, (section, audio_info) in enumerate(zip(sections, audio_results)):
            duration = max(float(audio_info.get("duration", 8)), 3.0)
            image_bytes = section.get("_image_bytes")
            audio_bytes = audio_info.get("audio")
            
            if not image_bytes:
                continue
            
            # حفظ الصورة مؤقتاً
            img_fd, img_path = tempfile.mkstemp(prefix=f"sec_{index}_", suffix=".jpg")
            os.close(img_fd)
            with open(img_path, "wb") as f:
                f.write(image_bytes)
            tmp_files.append(img_path)
            
            image_clip = ImageClip(img_path).set_duration(duration).resize((1280, 720))
            
            if audio_bytes:
                audio_fd, audio_path = tempfile.mkstemp(prefix=f"aud_{index}_", suffix=".mp3")
                os.close(audio_fd)
                with open(audio_path, "wb") as f:
                    f.write(audio_bytes)
                tmp_files.append(audio_path)
                audio_clip = AudioFileClip(audio_path)
                clip = image_clip.set_audio(audio_clip).set_duration(audio_clip.duration)
            else:
                clip = image_clip
            
            clips.append(clip)
        
        if not clips:
            raise RuntimeError("No clips generated")
        
        final_clip = concatenate_videoclips(clips, method="compose")
        final_clip.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            fps=24,
            threads=2,
            preset="ultrafast",
            logger=None,
        )
        final_clip.close()
        
    finally:
        for clip in clips:
            try:
                clip.close()
            except:
                pass
        for path in tmp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except:
                pass
