import os
import aiohttp
import asyncio
from typing import Optional
import shutil

async def download_file(file, filename: str) -> str:
    """تحميل ملف من تيليجرام"""
    file_path = f"temp/{filename}"
    await file.download_to_drive(file_path)
    return file_path

def cleanup_temp_files():
    """تنظيف الملفات المؤقتة"""
    temp_dirs = ['temp', 'temp_audio']
    
    for dir_name in temp_dirs:
        if os.path.exists(dir_name):
            for file in os.listdir(dir_name):
                file_path = os.path.join(dir_name, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Error deleting {file_path}: {e}")

def format_duration(seconds: float) -> str:
    """تنسيق المدة الزمنية"""
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes}:{seconds:02d}"

async def download_from_url(url: str, filename: str) -> Optional[str]:
    """تحميل ملف من URL"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    filepath = f"temp/{filename}"
                    with open(filepath, 'wb') as f:
                        f.write(await response.read())
                    return filepath
    except Exception as e:
        print(f"Download error: {e}")
    return None
