#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import os
import uuid
import logging
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from config import TELEGRAM_BOT_TOKEN, VOICES, FREE_ATTEMPTS, OWNER_ID, TEMP_DIR, OWNER_USERNAME
from database import (
    init_db, get_user, create_user, decrement_attempts, increment_total_videos,
    is_banned, save_video_request, update_video_request, record_referral, get_referral_stats,
    add_attempts, ban_user, get_all_users, get_stats
)
from ai_analyzer import analyze_lecture, extract_text_from_url, extract_text_from_pdf, fetch_image_for_keyword
from voice_generator import generate_sections_audio, reset_tts_engine
from video_creator import create_video_from_sections
from pdf_generator import create_pdf_summary
from web_server import start_web_server

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# تخزين حالة المستخدمين
user_states = {}

def get_dialect_keyboard():
    """لوحة مفاتيح اختيار اللهجة"""
    keyboard = [
        [
            InlineKeyboardButton("🇮🇶 عراقي", callback_data="dialect_iraq"),
            InlineKeyboardButton("🇪🇬 مصري", callback_data="dialect_egypt"),
        ],
        [
            InlineKeyboardButton("🇸🇾 سوري", callback_data="dialect_syria"),
            InlineKeyboardButton("🇸🇦 خليجي", callback_data="dialect_gulf"),
        ],
        [
            InlineKeyboardButton("📚 فصحى", callback_data="dialect_msa"),
            InlineKeyboardButton("🇺🇸 English", callback_data="dialect_english"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_keyboard(user_id: int, attempts: int):
    """لوحة المفاتيح الرئيسية"""
    keyboard = [
        [InlineKeyboardButton("📊 رصيدي", callback_data="my_balance")],
        [InlineKeyboardButton("🔗 رابط الإحالة", callback_data="my_referral")],
        [InlineKeyboardButton("ℹ️ كيف يعمل البوت", callback_data="how_it_works")],
    ]
    if user_id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("🎛️ لوحة التحكم", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)

# ============== أوامر البوت الأساسية ==============

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start"""
    user = update.effective_user
    is_new = get_user(user.id) is None
    
    # معالجة الإحالة
    referrer_id = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            referrer_id = int(context.args[0][4:])
            if referrer_id == user.id:
                referrer_id = None
        except:
            pass
    
    # إنشاء أو تحديث المستخدم
    if is_new:
        create_user(user.id, user.username or "", user.full_name or "", referrer_id)
    
    # التحقق من الحظر
    if is_banned(user.id):
        await update.message.reply_text("🚫 عذراً، تم حظر حسابك من استخدام البوت.")
        return
    
    # مكافأة الإحالة
    if is_new and referrer_id:
        result = record_referral(referrer_id, user.id)
        if not result['already_referred']:
            if result['attempts_granted'] > 0:
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 *مبروك!*\n\nانضم شخص جديد عبر رابط الإحالة الخاص بك!\n\n🎁 حصلت على *{result['attempts_granted']}* محاولة مجانية!",
                        parse_mode="Markdown"
                    )
                except:
                    pass
    
    db_user = get_user(user.id)
    attempts = db_user.get('attempts_left', FREE_ATTEMPTS)
    
    welcome_msg = (
        f"🎓 *مرحباً {user.first_name}!*\n\n"
        f"أنا بوت تحويل المحاضرات إلى فيديوهات تعليمية 🤖\n\n"
        f"📤 *ما يمكنك إرساله:*\n"
        f"• 📄 ملف PDF\n"
        f"• ✍️ نص مكتوب (50 كلمة على الأقل)\n"
        f"• 🔗 رابط موقع\n\n"
        f"🎯 *المحاولات المتبقية:* {attempts}\n\n"
        f"ابدأ الآن بإرسال محاضرتك! 🚀"
    )
    
    await update.message.reply_text(
        welcome_msg,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(user.id, attempts)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /help"""
    await update.message.reply_text(
        "📖 *المساعدة:*\n\n"
        "أرسل لي:\n"
        "• 📄 ملف PDF\n"
        "• ✍️ نص المحاضرة (50+ كلمة)\n"
        "• 🔗 رابط صفحة ويب\n\n"
        "وسأقوم بـ:\n"
        "1️⃣ تحليل المحاضرة بالذكاء الاصطناعي\n"
        "2️⃣ توليد صور تعليمية لكل قسم\n"
        "3️⃣ تحويل النص إلى صوت باللهجة المختارة\n"
        "4️⃣ إنشاء فيديو احترافي\n"
        "5️⃣ إنشاء ملخص PDF\n\n"
        "*الأوامر المتاحة:*\n"
        "/start - البداية\n"
        "/balance - رصيدك\n"
        "/referral - رابط الإحالة الخاص بك\n"
        "/help - المساعدة",
        parse_mode="Markdown"
    )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /balance - عرض الرصيد"""
    user_id = update.effective_user.id
    db_user = get_user(user_id)
    
    if not db_user:
        db_user = create_user(user_id, update.effective_user.username or "", update.effective_user.full_name or "")
    
    attempts = db_user.get('attempts_left', 0)
    total_videos = db_user.get('total_videos', 0)
    
    await update.message.reply_text(
        f"📊 *رصيدك الحالي:*\n\n"
        f"🎯 المحاولات المتبقية: *{attempts}*\n"
        f"🎬 الفيديوهات المنشأة: *{total_videos}*\n\n"
        f"💡 *كيف تحصل على محاولات إضافية؟*\n"
        f"استخدم /referral للحصول على رابط الإحالة\n"
        f"كل 10 أشخاص يدخلون عبر رابطك = محاولة مجانية!",
        parse_mode="Markdown"
    )

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /referral - عرض رابط الإحالة"""
    user = update.effective_user
    db_user = get_user(user.id)
    
    if not db_user:
        db_user = create_user(user.id, user.username or "", user.full_name or "")
    
    ref_stats = get_referral_stats(user.id)
    bot_info = await context.bot.get_me()
    referral_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    
    invited = ref_stats['total_referrals']
    points = ref_stats['current_points']
    remaining = ref_stats['points_needed']
    remaining_invites = int(remaining / 0.1) if remaining > 0 else 0
    
    msg = (
        f"🔗 *رابط الإحالة الخاص بك:*\n\n"
        f"`{referral_link}`\n\n"
        f"📊 *إحصاءاتك:*\n"
        f"👥 إجمالي المدعوين: *{invited}*\n"
        f"⭐ نقاطك الحالية: *{points:.1f}/1.0*\n"
        f"🎯 تبقى لك *{remaining_invites}* دعوة للحصول على محاولة مجانية\n\n"
        f"💡 *كيف يعمل نظام الإحالة؟*\n"
        f"• كل شخص يدخل عبر رابطك = 0.1 نقطة\n"
        f"• كل 1.0 نقطة (10 أشخاص) = محاولة مجانية\n\n"
        f"📤 شارك الرابط مع أصدقائك الآن!"
    )
    
    await update.message.reply_text(msg, parse_mode="Markdown")

# ============== معالجة الرسائل ==============

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    user = update.effective_user
    
    # التحقق من الحظر
    if is_banned(user.id):
        await update.message.reply_text("🚫 عذراً، تم حظر حسابك.")
        return
    
    # الحصول على المستخدم
    db_user = get_user(user.id)
    if not db_user:
        db_user = create_user(user.id, user.username or "", user.full_name or "")
    
    text = update.message.text.strip()
    
    # التحقق من المحاولات
    if db_user.get('attempts_left', 0) <= 0:
        await update.message.reply_text(
            "⚠️ *نفدت محاولاتك المجانية!*\n\n"
            "للحصول على محاولات إضافية:\n"
            "• ادعُ أصدقاءك عبر رابط الإحالة\n"
            "• استخدم /referral للحصول على رابطك\n\n"
            "🎁 كل 10 أشخاص = محاولة مجانية!",
            parse_mode="Markdown"
        )
        return
    
    # تحديد نوع المدخل
    if text.startswith('http://') or text.startswith('https://'):
        input_type = 'url'
        content_text = None
        url = text
    else:
        # التحقق من طول النص
        if len(text) < 50:
            await update.message.reply_text(
                "⚠️ النص قصير جداً!\n\n"
                "يرجى إرسال:\n"
                "• نص المحاضرة (50 كلمة على الأقل)\n"
                "• رابط موقع\n"
                "• ملف PDF"
            )
            return
        
        input_type = 'text'
        content_text = text
        url = None
    
    # حفظ حالة المستخدم
    user_states[user.id] = {
        'state': 'awaiting_dialect',
        'input_type': input_type,
        'content': content_text,
        'url': url
    }
    
    await update.message.reply_text(
        "🎤 *اختر لهجة الشرح:*\n\n"
        "سيتم تحويل النص إلى صوت باللهجة المختارة",
        parse_mode="Markdown",
        reply_markup=get_dialect_keyboard()
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ملفات PDF"""
    user = update.effective_user
    
    # التحقق من الحظر
    if is_banned(user.id):
        await update.message.reply_text("🚫 عذراً، تم حظر حسابك.")
        return
    
    # الحصول على المستخدم
    db_user = get_user(user.id)
    if not db_user:
        db_user = create_user(user.id, user.username or "", user.full_name or "")
    
    # التحقق من المحاولات
    if db_user.get('attempts_left', 0) <= 0:
        await update.message.reply_text(
            "⚠️ *نفدت محاولاتك المجانية!*\n\n"
            "استخدم /referral للحصول على محاولات مجانية.",
            parse_mode="Markdown"
        )
        return
    
    doc = update.message.document
    
    # التحقق من نوع الملف
    if not doc.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("⚠️ يرجى إرسال ملف PDF فقط.")
        return
    
    # التحقق من حجم الملف (20MB كحد أقصى)
    if doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("❌ حجم الملف كبير جداً (الحد الأقصى 20MB)")
        return
    
    status_msg = await update.message.reply_text("⏳ جاري قراءة الملف...")
    
    try:
        file = await context.bot.get_file(doc.file_id)
        pdf_bytes = await file.download_as_bytearray()
        
        await status_msg.edit_text("📄 تم استلام الملف بنجاح!")
        
        # حفظ حالة المستخدم
        user_states[user.id] = {
            'state': 'awaiting_dialect',
            'input_type': 'pdf',
            'content': bytes(pdf_bytes),
            'url': None
        }
        
        await update.message.reply_text(
            "🎤 *اختر لهجة الشرح:*",
            parse_mode="Markdown",
            reply_markup=get_dialect_keyboard()
        )
    
    except Exception as e:
        await status_msg.edit_text(f"❌ خطأ في قراءة الملف: {str(e)}")

# ============== معالجة Callbacks ==============

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أزرار لوحة المفاتيح"""
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    # معالجة اختيار اللهجة
    if data.startswith("dialect_"):
        await handle_dialect_selection(update, context)
        return
    
    await query.answer()
    
    # عرض الرصيد
    if data == "my_balance":
        db_user = get_user(user_id)
        if not db_user:
            db_user = create_user(user_id, query.from_user.username or "", query.from_user.full_name or "")
        
        attempts = db_user.get('attempts_left', 0)
        total = db_user.get('total_videos', 0)
        
        await query.edit_message_text(
            f"📊 *رصيدك:*\n\n"
            f"🎯 المحاولات: *{attempts}*\n"
            f"🎬 الفيديوهات: *{total}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ رجوع", callback_data="back_main")
            ]])
        )
    
    # عرض رابط الإحالة
    elif data == "my_referral":
        ref_stats = get_referral_stats(user_id)
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        
        await query.edit_message_text(
            f"🔗 *رابط الإحالة:*\n\n"
            f"`{link}`\n\n"
            f"👥 المدعوين: *{ref_stats['total_referrals']}*\n"
            f"⭐ النقاط: *{ref_stats['current_points']:.1f}/1.0*\n"
            f"🎯 تبقى *{int(ref_stats['points_needed']/0.1)}* دعوة للمحاولة القادمة",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ رجوع", callback_data="back_main")
            ]])
        )
    
    # شرح طريقة عمل البوت
    elif data == "how_it_works":
        await query.edit_message_text(
            "ℹ️ *كيف يعمل البوت:*\n\n"
            "1️⃣ أرسل محاضرتك (نص، PDF، أو رابط)\n"
            "2️⃣ اختر لهجة الشرح المفضلة\n"
            "3️⃣ البوت يحلل المحاضرة بالذكاء الاصطناعي\n"
            "4️⃣ يقسمها إلى أقسام ويستخرج الكلمات المفتاحية\n"
            "5️⃣ يولد صوراً تعليمية لكل قسم\n"
            "6️⃣ يحول النص إلى صوت باللهجة المختارة\n"
            "7️⃣ يدمج الصور والصوت في فيديو احترافي\n"
            "8️⃣ ينشئ ملخص PDF كامل\n\n"
            "⏱️ الوقت المطلوب: 1-3 دقائق\n"
            "🎁 *3 محاولات مجانية* + محاولات إضافية عبر الإحالات",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ رجوع", callback_data="back_main")
            ]])
        )
    
    # لوحة تحكم المالك
    elif data == "admin_panel" and user_id == OWNER_ID:
        stats = get_stats()
        msg = (
            f"🎛️ *لوحة تحكم المالك*\n\n"
            f"👥 إجمالي المستخدمين: *{stats['total_users']}*\n"
            f"🆕 مستخدمون اليوم: *{stats['new_today']}*\n"
            f"🎬 إجمالي الفيديوهات: *{stats['total_videos']}*\n"
            f"🚫 المستخدمون المحظورون: *{stats['banned_users']}*\n\n"
            f"*الأوامر الإدارية:*\n"
            f"/add `[user_id] [count]` - إضافة محاولات\n"
            f"/ban `[user_id]` - حظر مستخدم\n"
            f"/unban `[user_id]` - فك الحظر\n"
            f"/broadcast `[message]` - رسالة جماعية\n"
            f"/users - عرض آخر 10 مستخدمين\n"
            f"/stats - إحصاءات سريعة"
        )
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ رجوع", callback_data="back_main")
            ]])
        )
    
    # الرجوع للقائمة الرئيسية
    elif data == "back_main":
        db_user = get_user(user_id)
        attempts = db_user.get('attempts_left', 0) if db_user else 0
        
        await query.edit_message_text(
            f"🎓 *بوت المحاضرات الذكي*\n\n"
            f"🎯 المحاولات المتبقية: *{attempts}*\n\n"
            f"أرسل محاضرتك للبدء!",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id, attempts)
        )

async def handle_dialect_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اختيار اللهجة وبدء المعالجة"""
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    dialect = query.data.replace("dialect_", "")
    state = user_states.get(user_id, {})
    
    if state.get('state') != 'awaiting_dialect':
        await query.edit_message_text("❌ انتهت الجلسة. يرجى إرسال المحاضرة مرة أخرى.")
        return
    
    state['dialect'] = dialect
    user_states[user_id] = state
    
    dialect_name = VOICES.get(dialect, {}).get('name', dialect)
    
    await query.edit_message_text(
        f"✅ *تم اختيار: {dialect_name}*\n\n"
        f"⏳ جاري معالجة المحاضرة...\n\n"
        f"🔄 *الخطوات:*\n"
        f"1️⃣ تحليل المحاضرة... ⏳\n"
        f"2️⃣ توليد الصور... ⏸️\n"
        f"3️⃣ توليد الصوت... ⏸️\n"
        f"4️⃣ إنشاء الفيديو... ⏸️\n"
        f"5️⃣ إنشاء PDF... ⏸️",
        parse_mode="Markdown"
    )
    
    # بدء المعالجة في الخلفية
    asyncio.create_task(process_lecture(query, context, user_id, state, dialect_name))

# ============== معالجة المحاضرة ==============

async def process_lecture(query, context, user_id, state, dialect_name):
    """المعالجة الكاملة للمحاضرة"""
    dialect = state['dialect']
    input_type = state['input_type']
    
    req_id = save_video_request(user_id, input_type, dialect)
    reset_tts_engine()
    
    try:
        # الخطوة 1: استخراج النص
        if input_type == 'url':
            await context.bot.send_message(chat_id=user_id, text="🌐 جاري تحميل الرابط...")
            content_text = await extract_text_from_url(state['url'])
        elif input_type == 'pdf':
            await context.bot.send_message(chat_id=user_id, text="📄 جاري قراءة الملف...")
            content_text = await extract_text_from_pdf(state['content'])
        else:
            content_text = state['content']
        
        # تحديث حالة المعالجة
        status_msg = await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🔄 *الخطوات:*\n"
                f"1️⃣ تحليل المحاضرة بالذكاء الاصطناعي... ⏳\n"
                f"2️⃣ توليد الصور... ⏸️\n"
                f"3️⃣ توليد الصوت... ⏸️\n"
                f"4️⃣ إنشاء الفيديو... ⏸️\n"
                f"5️⃣ إنشاء PDF... ⏸️"
            ),
            parse_mode="Markdown"
        )
        
        # الخطوة 2: تحليل المحاضرة
        lecture_data = await analyze_lecture(content_text, dialect)
        sections = lecture_data.get('sections', [])
        
        if not sections:
            await context.bot.send_message(chat_id=user_id, text="❌ لم أستطع تحليل المحاضرة. يرجى إرسال نص أوضح.")
            user_states.pop(user_id, None)
            return
        
        await status_msg.edit_text(
            f"🔄 *الخطوات:*\n"
            f"1️⃣ ✅ تحليل المحاضرة ({len(sections)} أقسام)\n"
            f"2️⃣ 🖼️ جاري توليد الصور... ⏳\n"
            f"3️⃣ توليد الصوت... ⏸️\n"
            f"4️⃣ إنشاء الفيديو... ⏸️\n"
            f"5️⃣ إنشاء PDF... ⏸️",
            parse_mode="Markdown"
        )
        
        # الخطوة 3: توليد الصور
        for i, section in enumerate(sections):
            keywords = section.get('keywords', [])
            keyword = keywords[0] if keywords else section.get('title', f'قسم {i+1}')
            section['_image_bytes'] = await fetch_image_for_keyword(keyword)
        
        await status_msg.edit_text(
            f"🔄 *الخطوات:*\n"
            f"1️⃣ ✅ تحليل المحاضرة\n"
            f"2️⃣ ✅ توليد {len(sections)} صورة\n"
            f"3️⃣ 🎙️ جاري توليد الصوت بلهجة {dialect_name}... ⏳\n"
            f"4️⃣ إنشاء الفيديو... ⏸️\n"
            f"5️⃣ إنشاء PDF... ⏸️",
            parse_mode="Markdown"
        )
        
        # الخطوة 4: توليد الصوت
        audio_response = await generate_sections_audio(sections, dialect)
        audio_results = audio_response["results"]
        
        await status_msg.edit_text(
            f"🔄 *الخطوات:*\n"
            f"1️⃣ ✅ تحليل المحاضرة\n"
            f"2️⃣ ✅ توليد الصور\n"
            f"3️⃣ ✅ توليد الصوت\n"
            f"4️⃣ 🎬 جاري إنشاء الفيديو... ⏳\n"
            f"5️⃣ إنشاء PDF... ⏸️",
            parse_mode="Markdown"
        )
        
        # الخطوة 5: إنشاء الفيديو
        video_path = os.path.join(TEMP_DIR, f"video_{user_id}_{uuid.uuid4().hex[:8]}.mp4")
        await create_video_from_sections(sections, audio_results, lecture_data, video_path)
        
        await status_msg.edit_text(
            f"🔄 *الخطوات:*\n"
            f"1️⃣ ✅ تحليل المحاضرة\n"
            f"2️⃣ ✅ توليد الصور\n"
            f"3️⃣ ✅ توليد الصوت\n"
            f"4️⃣ ✅ إنشاء الفيديو\n"
            f"5️⃣ 📄 جاري إنشاء PDF... ⏳",
            parse_mode="Markdown"
        )
        
        # الخطوة 6: إنشاء PDF
        pdf_path = os.path.join(TEMP_DIR, f"summary_{user_id}_{uuid.uuid4().hex[:8]}.pdf")
        create_pdf_summary(lecture_data, sections, pdf_path)
        
        # تحديث قاعدة البيانات
        remaining = decrement_attempts(user_id)
        increment_total_videos(user_id)
        update_video_request(req_id, 'completed', video_path, pdf_path)
        
        await status_msg.edit_text("✅ *اكتملت المعالجة!* جاري إرسال الملفات...", parse_mode="Markdown")
        
        # إرسال الفيديو
        title = lecture_data.get('title', 'المحاضرة')
        lecture_type = lecture_data.get('lecture_type', 'other')
        caption = (
            f"🎓 *{title}*\n\n"
            f"🎤 اللهجة: {dialect_name}\n"
            f"📂 النوع: {lecture_type}\n"
            f"📋 عدد الأقسام: {len(sections)}\n"
            f"🎯 المحاولات المتبقية: {remaining}"
        )
        
        video_size = os.path.getsize(video_path) / (1024 * 1024)
        
        if video_size <= 49:
            with open(video_path, 'rb') as vf:
                await context.bot.send_video(
                    chat_id=user_id,
                    video=vf,
                    caption=caption,
                    parse_mode="Markdown"
                )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ الفيديو كبير جداً ({video_size:.1f}MB).\nسيتم إرسال PDF فقط."
            )
        
        # إرسال PDF
        with open(pdf_path, 'rb') as pf:
            await context.bot.send_document(
                chat_id=user_id,
                document=pf,
                filename=f"{title[:30]}_summary.pdf",
                caption=f"📄 *ملخص المحاضرة*\n_{title}_",
                parse_mode="Markdown"
            )
        
        # تنظيف الملفات المؤقتة
        try:
            os.remove(video_path)
            os.remove(pdf_path)
        except:
            pass
        
        # إشعار عند نفاد المحاولات
        if remaining == 0:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "⚠️ *انتهت محاولاتك المجانية!*\n\n"
                    "للحصول على محاولات إضافية، استخدم:\n"
                    "/referral - رابط الإحالة الخاص بك\n\n"
                    "🎁 كل 10 أشخاص يدخلون عبر رابطك = محاولة مجانية!"
                ),
                parse_mode="Markdown"
            )
        
        user_states.pop(user_id, None)
    
    except Exception as e:
        logger.error(f"Error processing for user {user_id}: {e}", exc_info=True)
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"❌ *حدث خطأ أثناء المعالجة*\n\n`{str(e)[:200]}`\n\nتم حفظ محاولتك، يمكنك المحاولة مرة أخرى.",
            parse_mode="Markdown"
        )
        
        user_states.pop(user_id, None)
        update_video_request(req_id, 'failed')

# ============== أوامر المالك (Admin) ==============

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /admin - لوحة تحكم المالك"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        await update.message.reply_text("❌ غير مصرح لك باستخدام هذا الأمر.")
        return
    
    stats = get_stats()
    msg = (
        f"🎛️ *لوحة تحكم المالك*\n\n"
        f"👥 المستخدمين: *{stats['total_users']}*\n"
        f"🆕 اليوم: *{stats['new_today']}*\n"
        f"🎬 الفيديوهات: *{stats['total_videos']}*\n"
        f"🚫 المحظورين: *{stats['banned_users']}*\n\n"
        f"*الأوامر المتاحة:*\n"
        f"/add `[user_id] [count]` - إضافة محاولات\n"
        f"/ban `[user_id]` - حظر مستخدم\n"
        f"/unban `[user_id]` - فك حظر\n"
        f"/broadcast `[message]` - رسالة جماعية\n"
        f"/users - عرض آخر المستخدمين"
    )
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /add - إضافة محاولات لمستخدم"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
    
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("❌ استخدام: /add [user_id] [count]")
            return
        
        target_id = int(args[0])
        count = int(args[1])
        
        new_attempts = add_attempts(target_id, count)
        
        await update.message.reply_text(
            f"✅ تم إضافة *{count}* محاولة للمستخدم `{target_id}`\n"
            f"الرصيد الحالي: *{new_attempts}*",
            parse_mode="Markdown"
        )
        
        # إشعار المستخدم
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎁 *مبروك!*\n\nتم إضافة *{count}* محاولة لحسابك من قبل الإدارة!\n\nرصيدك الحالي: *{new_attempts}* محاولة",
                parse_mode="Markdown"
            )
        except:
            pass
            
    except (ValueError, IndexError):
        await update.message.reply_text("❌ استخدام: /add [user_id] [count]")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /ban - حظر مستخدم"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
    
    try:
        target_id = int(context.args[0])
        ban_user(target_id, True)
        
        await update.message.reply_text(f"🚫 تم حظر المستخدم `{target_id}`", parse_mode="Markdown")
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="🚫 *تم حظر حسابك*\n\nعذراً، تم حظر حسابك من استخدام البوت.",
                parse_mode="Markdown"
            )
        except:
            pass
            
    except (ValueError, IndexError):
        await update.message.reply_text("❌ استخدام: /ban [user_id]")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /unban - فك حظر مستخدم"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
    
    try:
        target_id = int(context.args[0])
        ban_user(target_id, False)
        
        await update.message.reply_text(f"✅ تم فك حظر المستخدم `{target_id}`", parse_mode="Markdown")
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="✅ *تم فك حظر حسابك*\n\nيمكنك استخدام البوت الآن.",
                parse_mode="Markdown"
            )
        except:
            pass
            
    except (ValueError, IndexError):
        await update.message.reply_text("❌ استخدام: /unban [user_id]")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /broadcast - إرسال رسالة جماعية"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
    
    if not context.args:
        await update.message.reply_text("❌ استخدام: /broadcast [الرسالة]")
        return
    
    message = ' '.join(context.args)
    users = get_all_users(500)
    
    sent = 0
    failed = 0
    
    status_msg = await update.message.reply_text(f"📢 جاري الإرسال... (0/{len(users)})")
    
    for i, user in enumerate(users):
        try:
            await context.bot.send_message(
                chat_id=user['user_id'],
                text=f"📢 *رسالة من الإدارة:*\n\n{message}",
                parse_mode="Markdown"
            )
            sent += 1
        except:
            failed += 1
        
        if (i + 1) % 10 == 0:
            try:
                await status_msg.edit_text(f"📢 جاري الإرسال... ({i+1}/{len(users)})")
            except:
                pass
        
        await asyncio.sleep(0.05)  # تجنب flood
    
    await status_msg.edit_text(
        f"✅ *اكتمل الإرسال*\n\n✉️ تم: {sent}\n❌ فشل: {failed}",
        parse_mode="Markdown"
    )

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /users - عرض آخر المستخدمين"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
    
    users = get_all_users(10)
    
    if not users:
        await update.message.reply_text("لا يوجد مستخدمين بعد.")
        return
    
    msg = "👥 *آخر 10 مستخدمين:*\n\n"
    for u in users:
        status = "🚫" if u['is_banned'] else "✅"
        username = f"@{u['username']}" if u.get('username') else "بدون يوزر"
        msg += (
            f"{status} `{u['user_id']}` - {u.get('full_name', 'N/A')[:20]}\n"
            f"   {username} | محاولات: {u['attempts_left']} | فيديوهات: {u['total_videos']}\n\n"
        )
    
    await update.message.reply_text(msg, parse_mode="Markdown")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /stats - إحصاءات سريعة"""
    user_id = update.effective_user.id
    
    if user_id != OWNER_ID:
        return
    
    stats = get_stats()
    
    msg = (
        f"📊 *إحصاءات البوت*\n\n"
        f"👥 المستخدمين: *{stats['total_users']}*\n"
        f"🆕 اليوم: *{stats['new_today']}*\n"
        f"🎬 الفيديوهات: *{stats['total_videos']}*\n"
        f"🚫 المحظورين: *{stats['banned_users']}*"
    )
    
    await update.message.reply_text(msg, parse_mode="Markdown")

# ============== الدالة الرئيسية ==============

async def main():
    """الدالة الرئيسية لتشغيل البوت"""
    
    # تهيئة قاعدة البيانات
    logger.info("🗄️ جاري تهيئة قاعدة البيانات...")
    init_db()
    
    # تشغيل خادم الويب (مطلوب لـ Heroku)
    logger.info("🌐 جاري تشغيل خادم الويب...")
    await start_web_server()
    
    # إنشاء تطبيق البوت
    logger.info("🤖 جاري تهيئة البوت...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # أوامر المستخدمين العاديين
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("referral", referral_command))
    
    # أوامر المالك
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    # معالجة الملفات والنصوص
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # معالجة الأزرار
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("✅ البوت جاهز للعمل!")
    logger.info(f"👑 معرف المالك: {OWNER_ID}")
    
    # تشغيل البوت
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        # إبقاء البوت يعمل للأبد
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 تم إيقاف البوت يدوياً")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}")
        sys.exit(1)
