# bot.py
# -*- coding: utf-8 -*-
"""
البوت الرئيسي لتليجرام - بوت المحاضرات الطبية
يتحكم في كل تفاعلات المستخدم وعملية تحويل النص إلى فيديو
"""

import os
import re
import json
import asyncio
import logging
import uuid
import shutil
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

# مكتبة تيليجرام
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InputFile, BotCommand, MenuButtonCommands
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError, RetryAfter

# استيراد وحدات المشروع
from config import config, logger
from database import (
    init_db, get_user, create_or_update_user, is_banned,
    decrement_attempts, add_attempts, get_user_attempts,
    increment_total_videos, save_video_request, update_video_request,
    get_referral_code, get_referral_stats, record_referral,
    create_payment, get_pending_payments, approve_payment,
    get_stats, get_all_users_paginated, ban_user, unban_user
)
from ai_analyzer import analyze_lecture, extract_text_from_message, clean_text
from voice_generator import process_lecture_audio
from video_creator import create_video_from_sections

# حالات المحادثة (لـ ConversationHandler إذا استخدمناه)
(
    SELECTING_SPECIALTY, SELECTING_SUB_SPECIALTY, SELECTING_LEVEL,
    SELECTING_DIALECT, WAITING_FOR_CONTENT, WAITING_FOR_PAYMENT_RECEIPT,
    BROADCAST_MESSAGE,
) = range(7)

# تخزين حالات المستخدمين المؤقتة (في الذاكرة)
user_states: Dict[int, Dict[str, Any]] = {}

# تتبع المهام النشطة لإمكانية الإلغاء
active_tasks: Dict[int, asyncio.Task] = {}
cancel_flags: Dict[int, bool] = {}

# ==================== لوحات المفاتيح ====================

def main_keyboard(language: str = "ar") -> ReplyKeyboardMarkup:
    """لوحة المفاتيح الرئيسية"""
    if language == "ar":
        buttons = [
            [KeyboardButton("📤 رفع محاضرة"), KeyboardButton("📊 رصيدي")],
            [KeyboardButton("🔗 إحالة"), KeyboardButton("❓ مساعدة")],
            [KeyboardButton("💰 الاشتراك")],
        ]
    else:
        buttons = [
            [KeyboardButton("📤 Upload Lecture"), KeyboardButton("📊 My Balance")],
            [KeyboardButton("🔗 Referral"), KeyboardButton("❓ Help")],
            [KeyboardButton("💰 Subscribe")],
        ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def specialty_keyboard() -> InlineKeyboardMarkup:
    """لوحة اختيار التخصص الطبي"""
    specialties = list(config.MEDICAL_SPECIALTIES.items())
    buttons = []
    for i in range(0, len(specialties), 3):
        row = []
        for code, name in specialties[i:i+3]:
            row.append(InlineKeyboardButton(name, callback_data=f"spec_{code}"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main")])
    return InlineKeyboardMarkup(buttons)

def dialect_keyboard() -> InlineKeyboardMarkup:
    """لوحة اختيار اللهجة"""
    buttons = []
    for code, name in config.DIALECTS.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"dialect_{code}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_specialty")])
    return InlineKeyboardMarkup(buttons)

def education_level_keyboard() -> InlineKeyboardMarkup:
    """لوحة اختيار المرحلة الدراسية"""
    buttons = []
    for code, name in config.EDUCATION_LEVELS.items():
        buttons.append([InlineKeyboardButton(name, callback_data=f"level_{code}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_dialect")])
    return InlineKeyboardMarkup(buttons)

def payment_methods_keyboard() -> InlineKeyboardMarkup:
    """لوحة اختيار طريقة الدفع"""
    buttons = [
        [InlineKeyboardButton("⭐ نجوم تيليجرام", callback_data="pay_stars_1m")],
        [InlineKeyboardButton("💳 ماستر كارد", callback_data="pay_card")],
        [InlineKeyboardButton("💰 TON/USDT", callback_data="pay_crypto")],
        [InlineKeyboardButton("🔗 رابط الإحالة (مجاني)", callback_data="pay_referral")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main_menu")],
    ]
    return InlineKeyboardMarkup(buttons)

# ==================== دوال مساعدة ====================

async def get_user_language(user_id: int) -> str:
    """استرجاع لغة المستخدم المفضلة من قاعدة البيانات"""
    user = get_user(user_id)
    return user.get('language', 'ar') if user else 'ar'

async def check_user_access(update: Update, user_id: int) -> Tuple[bool, str]:
    """التحقق من إمكانية استخدام المستخدم للبوت (غير محظور ولديه محاولات)"""
    banned, reason = is_banned(user_id)
    if banned:
        return False, f"⛔ عذراً، حسابك محظور.\nالسبب: {reason or 'غير محدد'}"

    attempts = get_user_attempts(user_id)
    if attempts <= 0:
        # التحقق من وجود اشتراك غير محدود
        user = get_user(user_id)
        if user and user.get('subscription_type') == 'unlimited':
            return True, ""
        return False, "❌ رصيد المحاولات لديك غير كافٍ. يرجى شراء محاولات جديدة أو استخدام رابط الإحالة."

    return True, ""

async def send_progress_update(chat_id: int, message_id: int, text: str, progress: int = None):
    """تحديث رسالة التقدم مع شريط تقدم بصري"""
    bar_length = 10
    if progress is not None:
        filled = int(bar_length * progress / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        full_text = f"{text}\n\n[{bar}] {progress}%"
    else:
        full_text = text

    try:
        # استخدام application.bot مباشرة (سيتم تعيينه لاحقاً)
        from bot import application
        if application and application.bot:
            await application.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=full_text
            )
    except Exception as e:
        logger.debug(f"فشل تحديث رسالة التقدم: {e}")

# ==================== معالجات الأوامر الأساسية ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start - ترحيب وتسجيل المستخدم"""
    user = update.effective_user
    args = context.args  # للتعامل مع روابط الإحالة

    # استخراج معرف المُحيل إذا وجد (من رابط start)
    referrer_id = None
    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0].replace("ref_", ""))
        except:
            pass

    # إنشاء أو تحديث المستخدم
    user_data = create_or_update_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        referred_by=referrer_id
    )

    # تسجيل الإحالة تلقائياً تم في create_or_update_user

    # رسالة ترحيبية
    lang = user_data.get('language', 'ar')
    attempts = user_data.get('attempts', config.FREE_ATTEMPTS)

    welcome_text = f"""
🩺 *مرحباً بك في {config.BOT_NAME}* 🩺

أهلاً {user.first_name or 'بك'}!

يمكنك تحويل المحاضرات الطبية (PDF أو TXT أو نص) إلى فيديوهات تعليمية احترافية بأسلوب Osmosis.

📊 *رصيدك الحالي:* {attempts} محاولات
🔗 *رابط الإحالة الخاص بك:* `{user_data.get('referral_code', '')}`

استخدم الأزرار أدناه للبدء:
    """

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_keyboard(lang)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /help - شرح استخدام البوت"""
    help_text = """
📚 *دليل استخدام البوت* 📚

1️⃣ اضغط على *رفع محاضرة* وأرسل ملف PDF أو TXT أو انسخ النص مباشرة.
2️⃣ اختر التخصص الطبي (أو اتركه للبوت ليحدده تلقائياً).
3️⃣ اختر اللهجة المفضلة للشرح (عراقي، مصري، فصحى...).
4️⃣ انتظر قليلاً... سنقوم بتحليل المحاضرة وإنتاج فيديو تعليمي مميز!

🎥 *مميزات الفيديو:*
- شخصية كرتونية طبية تشرح المحتوى.
- صور توضيحية طبية.
- كلمات مفتاحية تظهر تدريجياً.
- ملخص في نهاية الفيديو.

💰 *الأسعار:*
- لديك {free} محاولات مجانية.
- يمكنك الحصول على محاولات إضافية عبر الإحالات أو الاشتراك.

للاستفسار أو الدعم: @MedicalBotSupport
""".format(free=config.FREE_ATTEMPTS)

    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض رصيد المستخدم"""
    user = update.effective_user
    user_data = get_user(user.id)
    if not user_data:
        await update.message.reply_text("حدث خطأ، الرجاء إعادة التشغيل /start")
        return

    attempts = user_data['attempts']
    total_videos = user_data['total_videos']
    ref_stats = get_referral_stats(user.id)
    sub_type = user_data.get('subscription_type', 'free')
    expiry = user_data.get('subscription_expiry')

    balance_text = f"""
📊 *رصيدك الحالي* 📊

🎬 المحاولات المتبقية: *{attempts}*
📹 عدد الفيديوهات المنتجة: *{total_videos}*
💎 الاشتراك: *{sub_type}*
{f"⏳ ينتهي في: {expiry.strftime('%Y-%m-%d')}" if expiry else ""}

🔗 *الإحالات:*
👥 عدد من دعوتهم: *{ref_stats['total_referrals']}*
🎁 نقاط الإحالة: *{ref_stats['current_points']}* (تحتاج {ref_stats['points_needed_for_reward']} نقطة لمحاولة مجانية)

رابط الإحالة الخاص بك:
`https://t.me/{context.bot.username}?start=ref_{user.id}`
"""
    await update.message.reply_text(balance_text, parse_mode=ParseMode.MARKDOWN)

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات الإحالة"""
    await balance_command(update, context)

# ==================== استقبال المحتوى (ملف أو نص) ====================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال ملف PDF أو TXT"""
    user = update.effective_user
    document = update.message.document

    # التحقق من الحظر والمحاولات
    has_access, error_msg = await check_user_access(update, user.id)
    if not has_access:
        await update.message.reply_text(error_msg)
        return

    # التحقق من نوع الملف وحجمه
    file_name = document.file_name.lower()
    if not (file_name.endswith('.pdf') or file_name.endswith('.txt')):
        await update.message.reply_text("❌ نوع الملف غير مدعوم. الرجاء إرسال PDF أو TXT.")
        return

    file_size_mb = document.file_size / (1024 * 1024)
    if file_size_mb > config.MAX_PDF_SIZE_MB:
        await update.message.reply_text(f"❌ حجم الملف كبير جداً ({file_size_mb:.1f} MB). الحد الأقصى {config.MAX_PDF_SIZE_MB} MB.")
        return

    # تنزيل الملف
    processing_msg = await update.message.reply_text("📥 جاري تنزيل الملف...")
    file = await context.bot.get_file(document.file_id)

    # حفظ مؤقت
    tmp_path = config.PDF_TMP / f"{user.id}_{uuid.uuid4().hex}.{file_name.split('.')[-1]}"
    await file.download_to_drive(tmp_path)

    # استخراج النص
    try:
        from ai_analyzer import extract_full_text_from_pdf, clean_text
        if file_name.endswith('.pdf'):
            text, pages = extract_full_text_from_pdf(tmp_path)
            await processing_msg.edit_text(f"📄 تم استخراج النص من {pages} صفحة. جاري التحليل...")
        else:
            with open(tmp_path, 'r', encoding='utf-8') as f:
                text = f.read()
            text = clean_text(text)
    except Exception as e:
        await processing_msg.edit_text(f"❌ فشل قراءة الملف: {e}")
        tmp_path.unlink(missing_ok=True)
        return

    tmp_path.unlink(missing_ok=True)

    # تخزين النص في حالة المستخدم والانتقال لاختيار التخصص
    user_states[user.id] = {
        'text': text,
        'file_name': file_name,
        'step': 'specialty',
        'message_id': processing_msg.message_id,
        'chat_id': update.effective_chat.id
    }

    await processing_msg.edit_text(
        "✅ تم استلام المحتوى!\nالرجاء اختيار التخصص الطبي (أو تخطي للاكتشاف التلقائي):",
        reply_markup=specialty_keyboard()
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال نص مباشر (بدلاً من ملف)"""
    user = update.effective_user
    text = update.message.text

    # تجاهل أوامر البوت
    if text.startswith('/'):
        return

    # التحقق من الحظر والمحاولات
    has_access, error_msg = await check_user_access(update, user.id)
    if not has_access:
        await update.message.reply_text(error_msg)
        return

    # التحقق من طول النص
    if len(text) < config.MIN_TEXT_LENGTH:
        await update.message.reply_text(f"❌ النص قصير جداً ({len(text)} حرف). الحد الأدنى {config.MIN_TEXT_LENGTH} حرف.")
        return

    # تنظيف النص
    text = clean_text(text)

    # تخزين النص
    processing_msg = await update.message.reply_text("📝 جاري معالجة النص...")
    user_states[user.id] = {
        'text': text,
        'file_name': None,
        'step': 'specialty',
        'message_id': processing_msg.message_id,
        'chat_id': update.effective_chat.id
    }

    await processing_msg.edit_text(
        "✅ تم استلام النص!\nالرجاء اختيار التخصص الطبي:",
        reply_markup=specialty_keyboard()
    )

# ==================== معالجات الأزرار (Callbacks) ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج عام لأزرار Inline"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = query.data

    # الرجوع للقائمة الرئيسية
    if data == "back_to_main" or data == "back_to_main_menu":
        await query.edit_message_text("العودة للقائمة الرئيسية. استخدم الأزرار أدناه.")
        await query.message.reply_text("اختر من القائمة:", reply_markup=main_keyboard())
        if user.id in user_states:
            del user_states[user.id]
        return

    # اختيار تخصص
    if data.startswith("spec_"):
        specialty = data.replace("spec_", "")
        if user.id in user_states:
            user_states[user.id]['specialty'] = specialty
            user_states[user.id]['step'] = 'dialect'
        else:
            # إذا لم تكن هناك حالة، ربما بدأ من جديد
            await query.edit_message_text("لم يتم العثور على محتوى. الرجاء إرسال محاضرة أولاً.")
            return

        await query.edit_message_text(
            f"التخصص المختار: {config.MEDICAL_SPECIALTIES.get(specialty, specialty)}\n\nاختر اللهجة المفضلة للشرح:",
            reply_markup=dialect_keyboard()
        )
        return

    # اختيار لهجة
    if data.startswith("dialect_"):
        dialect = data.replace("dialect_", "")
        if user.id in user_states:
            user_states[user.id]['dialect'] = dialect
            user_states[user.id]['step'] = 'level'
        else:
            await query.edit_message_text("انتهت الجلسة. الرجاء البدء من جديد.")
            return

        await query.edit_message_text(
            f"اللهجة المختارة: {config.DIALECTS.get(dialect, dialect)}\n\nاختر المرحلة الدراسية (اختياري):",
            reply_markup=education_level_keyboard()
        )
        return

    # اختيار مستوى تعليمي (يمكن تخطيه)
    if data.startswith("level_"):
        level = data.replace("level_", "")
        if user.id in user_states:
            user_states[user.id]['level'] = level

        # بدء المعالجة
        await query.edit_message_text("🚀 جاري بدء معالجة المحاضرة... يرجى الانتظار.")
        await start_processing(update, context, user.id)
        return

    # معالجة الدفع (سيتم تفصيلها لاحقاً)
    if data.startswith("pay_"):
        await handle_payment_callback(update, context)
        return

    await query.edit_message_text("عذراً، هذا الزر غير متاح حالياً.")

async def start_processing(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """بدء مهمة معالجة المحاضرة في الخلفية"""
    state = user_states.get(user_id)
    if not state:
        await update.effective_message.edit_text("❌ انتهت الجلسة. الرجاء إرسال المحاضرة مرة أخرى.")
        return

    # إنشاء مهمة غير متزامنة
    task = asyncio.create_task(process_lecture_task(
        user_id=user_id,
        chat_id=state['chat_id'],
        message_id=state['message_id'],
        text=state['text'],
        file_name=state.get('file_name'),
        specialty=state.get('specialty'),
        dialect=state.get('dialect', 'fusha'),
        level=state.get('level')
    ))
    active_tasks[user_id] = task

    # تنظيف الحالة (سنحتفظ بها حتى تنتهي المهمة أو نفشل)
    # user_states.pop(user_id, None)

async def process_lecture_task(user_id: int, chat_id: int, message_id: int,
                               text: str, file_name: str = None,
                               specialty: str = None, dialect: str = 'fusha',
                               level: str = None):
    """
    المهمة الرئيسية لمعالجة المحاضرة: تحليل، صوت، فيديو، إرسال.
    تعمل في الخلفية وتقوم بتحديث رسالة التقدم.
    """
    from bot import application  # استيراد متأخر لتجنب circular import
    bot = application.bot

    progress_msg_id = message_id
    request_id = None

    try:
        # خصم محاولة مبدئياً (سنعيدها إذا فشلت)
        user = get_user(user_id)
        if user and user.get('subscription_type') != 'unlimited':
            if not decrement_attempts(user_id, 1):
                await bot.edit_message_text("❌ رصيد المحاولات غير كافٍ.", chat_id=chat_id, message_id=progress_msg_id)
                return

        # حفظ طلب الفيديو في قاعدة البيانات
        request_id = save_video_request(user_id, text, file_name, specialty, None, dialect, level)

        # تحديثات التقدم حسب النسب المطلوبة
        async def update_status(percent: int, message: str):
            await send_progress_update(chat_id, progress_msg_id, message, percent)

        await update_status(5, "🔍 جاري قراءة النص وتنظيفه...")
        # التحليل باستخدام الذكاء الاصطناعي
        await update_status(8, "📊 تحليل نوع المحاضرة وتحديد التخصص...")
        await update_status(12, "🔑 استخراج المصطلحات الطبية من النص...")
        await update_status(15, "🧠 جاري الاتصال بالذكاء الاصطناعي لتحليل المحاضرة...")

        # استدعاء ai_analyzer
        language = 'ar'  # يمكن اكتشافها تلقائياً
        analysis_result = analyze_lecture(text, language=language, dialect=dialect, force_specialty=specialty)

        await update_status(25, "✅ تم تحليل المحاضرة بنجاح!")
        sections = analysis_result['sections']
        title = analysis_result['title']
        await update_status(28, f"📚 تم تقسيم المحاضرة إلى {len(sections)} أقسام تعليمية")
        await update_status(30, f"📝 العنوان: {title}")

        # جلب الصور (تم ضمن analyze_lecture)
        for i, sec in enumerate(sections):
            percent = 33 + int((i+1)/len(sections)*22)
            await update_status(percent, f"🖼️ جاري جلب الصورة للقسم {i+1}/{len(sections)}: {sec.get('heading', '')[:20]}...")
            # الصورة موجودة في sec['image_path']

        # توليد الصوت
        await update_status(58, "🎤 جاري الاتصال بخدمة تحويل النص إلى صوت...")
        await update_status(62, "🎙️ جاري توليد الصوت للقسم الأول...")
        audio_result = await process_lecture_audio(sections, language, dialect)
        if not audio_result['success']:
            raise Exception("فشل توليد الصوت")
        sections_with_audio = audio_result['sections']
        total_audio_duration = audio_result['total_duration']
        await update_status(72, "✅ تم توليد الصوت لجميع الأقسام!")
        await update_status(75, f"⏱️ المدة الإجمالية للصوت: {int(total_audio_duration//60)}:{int(total_audio_duration%60):02d}")

        # إنشاء الفيديو
        await update_status(78, "🎬 جاري إنتاج الفيديو...")
        await update_status(82, "🎨 إنشاء شرائح المقدمة والعنوان...")
        await update_status(86, "📝 بناء شرائح الأقسام وإضافة الصور...")
        await update_status(90, "🎬 جاري تشفير الفيديو (قد يستغرق دقيقة)...")

        video_data = {
            'title': title,
            'specialty_code': specialty or analysis_result.get('specialty_code', 'general'),
            'language': language,
            'dialect': dialect,
            'sections': sections_with_audio,
        }
        video_path, video_duration = create_video_from_sections(video_data)

        await update_status(95, f"✅ اكتمل الفيديو! المدة: {int(video_duration//60)}:{int(video_duration%60):02d}")
        await update_status(97, "📤 جاري إرسال الفيديو...")

        # إرسال الفيديو
        caption = f"""
🎬 *{title}*

📊 عدد الأقسام: {len(sections)}
⏱ المدة: {int(video_duration//60)}:{int(video_duration%60):02d}
🏥 التخصص: {analysis_result.get('specialty', 'عام')}
🤖 النموذج: {analysis_result.get('ai_model_used', 'AI')}

📌 لإنتاج فيديوهات أخرى، اضغط على "رفع محاضرة"
"""
        with open(video_path, 'rb') as f:
            await bot.send_video(
                chat_id=chat_id,
                video=InputFile(f),
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                supports_streaming=True
            )

        await update_status(100, "✅ تم الإرسال بنجاح!")

        # تحديث قاعدة البيانات
        increment_total_videos(user_id)
        update_video_request(
            request_id,
            status='completed',
            title=title,
            sections_count=len(sections),
            total_duration=int(video_duration),
            video_file_path=str(video_path),
            ai_model_used=analysis_result.get('ai_model_used')
        )

        # تنظيف
        if user_id in user_states:
            del user_states[user_id]
        # حذف الملفات المؤقتة بعد فترة أو فوراً

    except Exception as e:
        logger.error(f"فشل معالجة المحاضرة للمستخدم {user_id}: {e}", exc_info=True)
        error_msg = f"❌ عذراً، حدث خطأ أثناء المعالجة:\n`{str(e)[:200]}`\n\nتم إعادة المحاولة إلى رصيدك."
        try:
            await bot.edit_message_text(error_msg, chat_id=chat_id, message_id=progress_msg_id, parse_mode=ParseMode.MARKDOWN)
        except:
            await bot.send_message(chat_id, error_msg, parse_mode=ParseMode.MARKDOWN)

        # إعادة المحاولة
        add_attempts(user_id, 1, "فشل المعالجة")
        if request_id:
            update_video_request(request_id, status='failed', error_message=str(e))

        if user_id in user_states:
            del user_states[user_id]
    finally:
        if user_id in active_tasks:
            del active_tasks[user_id]
        # إعادة لوحة المفاتيح الرئيسية
        await bot.send_message(chat_id, "يمكنك متابعة استخدام البوت:", reply_markup=main_keyboard())

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أزرار الدفع - سيتم تفصيلها لاحقاً"""
    query = update.callback_query

    # ... تابع bot.py

# ==================== معالجات الدفع والإحالات ====================

async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض خطط الاشتراك وخيارات الدفع"""
    user = update.effective_user
    lang = await get_user_language(user.id)
    
    plans_text = f"""
💰 *خطط الاشتراك* 💰

اختر الخطة المناسبة لك:

1️⃣ *شهر واحد* - {config.SUBSCRIPTION_PRICES['1_month']} $ (أو {config.STARS_PRICE_1M} ⭐ نجوم)
   🎬 {config.ATTEMPTS_PER_PLAN['1_month']} محاولة

3️⃣ *3 شهور* - {config.SUBSCRIPTION_PRICES['3_months']} $ (أو {config.STARS_PRICE_3M} ⭐)
   🎬 {config.ATTEMPTS_PER_PLAN['3_months']} محاولة

1️⃣2️⃣ *12 شهر* - {config.SUBSCRIPTION_PRICES['12_months']} $ (أو {config.STARS_PRICE_12M} ⭐)
   🎬 {config.ATTEMPTS_PER_PLAN['12_months']} محاولة

♾️ *غير محدود* - {config.SUBSCRIPTION_PRICES['unlimited']} $ (أو {config.STARS_PRICE_UNLIMITED} ⭐)
   🎬 محاولات لا نهائية

طرق الدفع المتاحة:
- ⭐ نجوم تيليجرام
- 💳 ماستر كارد (تحويل)
- 💰 TON / USDT

اختر الخطة وطريقة الدفع:
"""
    await update.message.reply_text(
        plans_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=payment_plans_keyboard()
    )

def payment_plans_keyboard() -> InlineKeyboardMarkup:
    """لوحة خطط الدفع"""
    buttons = [
        [InlineKeyboardButton("⭐ شهر - نجوم", callback_data="pay_stars_1m")],
        [InlineKeyboardButton("⭐ 3 شهور - نجوم", callback_data="pay_stars_3m")],
        [InlineKeyboardButton("⭐ 12 شهر - نجوم", callback_data="pay_stars_12m")],
        [InlineKeyboardButton("⭐ غير محدود - نجوم", callback_data="pay_stars_unlim")],
        [InlineKeyboardButton("💳 ماستر كارد", callback_data="pay_card_menu")],
        [InlineKeyboardButton("💰 TON/USDT", callback_data="pay_crypto_menu")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_main_menu")],
    ]
    return InlineKeyboardMarkup(buttons)

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع أزرار الدفع"""
    query = update.callback_query
    user = update.effective_user
    data = query.data
    
    if data.startswith("pay_stars_"):
        plan = data.replace("pay_stars_", "")
        plan_name = {"1m": "شهر", "3m": "3 شهور", "12m": "12 شهر", "unlim": "غير محدود"}.get(plan, plan)
        stars_price = config.get_subscription_price_stars(
            "1_month" if plan == "1m" else 
            "3_months" if plan == "3m" else 
            "12_months" if plan == "12m" else 
            "unlimited"
        )
        # إنشاء فاتورة نجوم تيليجرام
        try:
            # ملاحظة: نجوم تيليجرام تحتاج إعداد خاص في BotFather وواجهة خاصة
            await query.edit_message_text(
                f"⭐ للاشتراك بـ *{plan_name}* بواسطة نجوم تيليجرام:\n\n"
                f"السعر: *{stars_price}* نجمة\n\n"
                f"⚠️ حالياً الدفع بالنجوم قيد التفعيل. يمكنك استخدام طرق الدفع الأخرى.",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            await query.edit_message_text("حدث خطأ في إنشاء الفاتورة.")
    
    elif data == "pay_card_menu":
        await query.edit_message_text(
            "💳 *الدفع عن طريق ماستر كارد*\n\n"
            "قم بتحويل المبلغ إلى الحساب التالي:\n\n"
            f"`{config.PAYMENT_METHODS.get('mastercard', 'غير متوفر')}`\n\n"
            "بعد التحويل، أرسل صورة الإيصال هنا.\n"
            "سنقوم بتفعيل اشتراكك خلال 24 ساعة.",
            parse_mode=ParseMode.MARKDOWN
        )
        user_states[user.id] = {'step': 'waiting_receipt', 'method': 'card'}
    
    elif data == "pay_crypto_menu":
        await query.edit_message_text(
            "💰 *الدفع عن طريق العملات الرقمية*\n\n"
            "عنوان USDT (TON):\n"
            f"`{config.PAYMENT_METHODS.get('ton_usdt', 'غير متوفر')}`\n\n"
            "بعد التحويل، أرسل صورة الإيصال أو رابط المعاملة.\n"
            "سنقوم بتفعيل اشتراكك خلال 24 ساعة.",
            parse_mode=ParseMode.MARKDOWN
        )
        user_states[user.id] = {'step': 'waiting_receipt', 'method': 'crypto'}

async def handle_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال صورة إيصال الدفع"""
    user = update.effective_user
    state = user_states.get(user.id, {})
    
    if state.get('step') != 'waiting_receipt':
        return  # ليس في وضع انتظار إيصال
    
    photo = update.message.photo[-1]  # أعلى جودة
    file_id = photo.file_id
    
    # إنشاء طلب دفع في قاعدة البيانات
    payment_id = create_payment(
        user_id=user.id,
        amount=0,  # سيتم تحديده لاحقاً من قبل المالك
        payment_method=state.get('method', 'manual'),
        receipt_file_id=file_id
    )
    
    await update.message.reply_text(
        "✅ *تم استلام إيصالك بنجاح!*\n\n"
        "رقم الطلب: `{payment_id}`\n"
        "سيقوم فريق الدعم بمراجعة طلبك وتفعيل الاشتراك خلال 24 ساعة.\n"
        "شكراً لصبرك!".format(payment_id=str(payment_id)[:8]),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # إشعار المالك
    owner_id = config.OWNER_ID
    if owner_id:
        try:
            await context.bot.send_message(
                owner_id,
                f"🆕 *طلب دفع جديد*\n\n"
                f"المستخدم: {user.full_name} (@{user.username})\n"
                f"ID: `{user.id}`\n"
                f"طريقة الدفع: {state.get('method')}\n"
                f"رقم الطلب: `{payment_id}`\n\n"
                f"استخدم /admin للمراجعة.",
                parse_mode=ParseMode.MARKDOWN
            )
            # إعادة توجيه الإيصال
            await context.bot.forward_message(owner_id, user.id, update.message.message_id)
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمالك: {e}")
    
    # تنظيف الحالة
    del user_states[user.id]

# ==================== لوحة تحكم المالك ====================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لوحة تحكم المالك - تعرض الإحصائيات وخيارات الإدارة"""
    user = update.effective_user
    if user.id != config.OWNER_ID:
        await update.message.reply_text("⛔ غير مصرح لك.")
        return
    
    stats = get_stats()
    
    admin_text = f"""
🔐 *لوحة تحكم المالك* 🔐

📊 *إحصائيات عامة:*
👥 إجمالي المستخدمين: *{stats['total_users']}*
🆕 مستخدمين جدد اليوم: *{stats['new_users_today']}*
🎬 إجمالي الفيديوهات: *{stats['total_videos']}*
💰 إجمالي الإيرادات: *${stats['total_revenue']:.2f}*
⏳ طلبات دفع معلقة: *{stats['pending_payments']}*
🚫 محظورين: *{stats['banned_users']}*
🔗 إجمالي الإحالات: *{stats['total_referrals']}*

استخدم الأزرار أدناه:
"""
    keyboard = [
        [InlineKeyboardButton("👥 عرض المستخدمين", callback_data="admin_users_1")],
        [InlineKeyboardButton("💰 طلبات الدفع المعلقة", callback_data="admin_payments")],
        [InlineKeyboardButton("📨 إرسال رسالة جماعية", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔄 تحديث الإحصائيات", callback_data="admin_refresh")],
    ]
    await update.message.reply_text(admin_text, parse_mode=ParseMode.MARKDOWN,
                                   reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أزرار لوحة التحكم"""
    query = update.callback_query
    user = update.effective_user
    if user.id != config.OWNER_ID:
        await query.answer("غير مصرح", show_alert=True)
        return
    
    data = query.data
    await query.answer()
    
    if data.startswith("admin_users_"):
        page = int(data.split("_")[-1])
        users, total = get_all_users_paginated(page, 10)
        total_pages = (total + 9) // 10
        
        text = f"👥 *قائمة المستخدمين* (صفحة {page}/{total_pages}):\n\n"
        for u in users:
            banned_icon = "🚫" if u['is_banned'] else "✅"
            text += f"{banned_icon} `{u['user_id']}` - {u.get('full_name', '---')} | محاولات: {u['attempts']}\n"
        
        buttons = []
        row = []
        if page > 1:
            row.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin_users_{page-1}"))
        if page < total_pages:
            row.append(InlineKeyboardButton("التالي ➡️", callback_data=f"admin_users_{page+1}"))
        if row:
            buttons.append(row)
        buttons.append([InlineKeyboardButton("🔙 رجوع للوحة التحكم", callback_data="admin_back")])
        
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN,
                                      reply_markup=InlineKeyboardMarkup(buttons))
    
    elif data == "admin_payments":
        pending = get_pending_payments()
        if not pending:
            await query.edit_message_text("✅ لا توجد طلبات دفع معلقة حالياً.")
            return
        text = "💰 *طلبات الدفع المعلقة:*\n\n"
        for p in pending[:10]:
            text += f"🔹 `{p['payment_id']}` - {p.get('full_name', '---')} - {p['payment_method']} - ${p['amount']}\n"
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    
    elif data == "admin_broadcast":
        user_states[user.id] = {'step': 'broadcast'}
        await query.edit_message_text(
            "📨 *إرسال رسالة جماعية*\n\n"
            "أرسل النص الذي تريد إرساله لجميع المستخدمين.\n"
            "يمكنك إرفاق صورة أو فيديو (اختياري).\n"
            "اكتب /cancel للإلغاء.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data == "admin_refresh":
        await admin_command(update, context)
        await query.message.delete()
    
    elif data == "admin_back":
        await admin_command(update, context)
        await query.message.delete()

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال رسالة البث من المالك وإرسالها للجميع"""
    user = update.effective_user
    if user.id != config.OWNER_ID:
        return
    state = user_states.get(user.id, {})
    if state.get('step') != 'broadcast':
        return
    
    # تنظيف الحالة
    del user_states[user.id]
    
    # جلب جميع المستخدمين (بشكل تدريجي لتجنب التهيئة الزائدة)
    users, _ = get_all_users_paginated(1, 1000)  # تبسيط، يمكن عمل تكرار للجميع
    
    success = 0
    failed = 0
    
    progress_msg = await update.message.reply_text(f"📤 جاري الإرسال إلى {len(users)} مستخدم...")
    
    for u in users:
        try:
            if update.message.text:
                await context.bot.send_message(u['user_id'], update.message.text)
            elif update.message.photo:
                await context.bot.send_photo(u['user_id'], update.message.photo[-1].file_id,
                                           caption=update.message.caption)
            elif update.message.video:
                await context.bot.send_video(u['user_id'], update.message.video.file_id,
                                           caption=update.message.caption)
            success += 1
        except Exception as e:
            logger.warning(f"فشل إرسال البث إلى {u['user_id']}: {e}")
            failed += 1
        await asyncio.sleep(0.05)  # تجنب flood limits
    
    await progress_msg.edit_text(
        f"✅ *اكتمل البث!*\n\n"
        f"✅ تم الإرسال: {success}\n"
        f"❌ فشل: {failed}",
        parse_mode=ParseMode.MARKDOWN
    )

# ==================== معالجات إضافية ====================

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء العملية الحالية"""
    user = update.effective_user
    if user.id in user_states:
        del user_states[user.id]
    if user.id in cancel_flags:
        cancel_flags[user.id] = True
    await update.message.reply_text("✅ تم إلغاء العملية.", reply_markup=main_keyboard())

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأخطاء العام"""
    logger.error(f"حدث خطأ: {context.error}", exc_info=context.error)
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ حدث خطأ غير متوقع. الرجاء المحاولة لاحقاً أو التواصل مع الدعم."
            )
    except:
        pass

# ==================== دالة التشغيل الرئيسية ====================

# متغير عام للتطبيق (لتتمكن الدوال الأخرى من الوصول إليه)
application = None

async def setup_bot_commands(app: Application):
    """إعداد أوامر البوت في القائمة"""
    commands = [
        BotCommand("start", "بدء البوت والترحيب"),
        BotCommand("help", "شرح طريقة الاستخدام"),
        BotCommand("balance", "عرض رصيد المحاولات"),
        BotCommand("subscribe", "الاشتراك المدفوع"),
        BotCommand("referral", "رابط الإحالة"),
        BotCommand("cancel", "إلغاء العملية الحالية"),
    ]
    await app.bot.set_my_commands(commands)
    
    # لقائمة خاصة للمالك
    if config.OWNER_ID:
        admin_commands = [
            BotCommand("admin", "لوحة تحكم المالك"),
        ]
        await app.bot.set_my_commands(commands + admin_commands, scope={"type": "chat", "chat_id": config.OWNER_ID})

async def post_init(app: Application):
    """بعد تهيئة التطبيق"""
    await setup_bot_commands(app)
    logger.info("✅ تم تهيئة البوت وتعيين الأوامر")

def main() -> None:
    """نقطة بدء تشغيل البوت"""
    global application
    
    # تهيئة قاعدة البيانات
    try:
        init_db()
        logger.info("✅ تم الاتصال بقاعدة البيانات")
    except Exception as e:
        logger.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
        # استمرار التشغيل بوظائف محدودة
    
    # إنشاء التطبيق
    builder = Application.builder()
    builder.token(config.BOT_TOKEN)
    builder.post_init(post_init)
    application = builder.build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("referral", referral_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # استقبال الملفات والنصوص
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_receipt_photo))
    
    # حالة البث (للمالك فقط)
    application.add_handler(MessageHandler(
        filters.User(user_id=config.OWNER_ID) & (filters.TEXT | filters.PHOTO | filters.VIDEO),
        handle_broadcast_message
    ), group=1)
    
    # أزرار الكول باك
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^(spec_|dialect_|level_|back_)"))
    application.add_handler(CallbackQueryHandler(handle_payment_callback, pattern="^pay_"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    
    # معالج الأخطاء
    application.add_error_handler(error_handler)
    
    # بدء البوت (webhook أو polling)
    webhook_url = config.WEBHOOK_URL
    if webhook_url:
        # وضع Webhook لـ Heroku
        app_name = webhook_url.rstrip('/')
        webhook_path = f"/webhook/{config.BOT_TOKEN}"
        full_url = f"{app_name}{webhook_path}"
        application.run_webhook(
            listen="0.0.0.0",
            port=config.PORT,
            url_path=webhook_path,
            webhook_url=full_url
        )
        logger.info(f"🚀 البوت يعمل عبر Webhook: {full_url}")
    else:
        # وضع Polling للتطوير المحلي
        logger.info("🚀 البوت يعمل عبر Polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
    await query.edit_message_text("نظام الدفع قيد التطوير حالياً.")
