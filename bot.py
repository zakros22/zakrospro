import asyncio
import os
import uuid
import logging
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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

user_states = {}

def get_dialect_keyboard():
    keyboard = [
        [InlineKeyboardButton("🇮🇶 عراقي", callback_data="dialect_iraq"),
         InlineKeyboardButton("🇪🇬 مصري", callback_data="dialect_egypt")],
        [InlineKeyboardButton("🇸🇾 سوري", callback_data="dialect_syria"),
         InlineKeyboardButton("🇸🇦 خليجي", callback_data="dialect_gulf")],
        [InlineKeyboardButton("📚 فصحى", callback_data="dialect_msa"),
         InlineKeyboardButton("🇺🇸 English", callback_data="dialect_english")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    if is_new:
        create_user(user.id, user.username or "", user.full_name or "", referrer_id)
    
    if is_banned(user.id):
        await update.message.reply_text("🚫 عذراً، تم حظر حسابك.")
        return
    
    # مكافأة الإحالة
    if is_new and referrer_id:
        result = record_referral(referrer_id, user.id)
        if not result['already_referred'] and result['attempts_granted'] > 0:
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 حصلت على {result['attempts_granted']} محاولة مجانية من الإحالات!"
                )
            except:
                pass
    
    db_user = get_user(user.id)
    attempts = db_user.get('attempts_left', FREE_ATTEMPTS)
    
    welcome = (
        f"🎓 *مرحباً {user.first_name}!*\n\n"
        f"أنا بوت تحويل المحاضرات إلى فيديوهات تعليمية 🤖\n\n"
        f"📤 *أرسل لي:*\n"
        f"• 📄 ملف PDF\n"
        f"• ✍️ نص مكتوب\n"
        f"• 🔗 رابط موقع\n\n"
        f"🎯 *المحاولات المتبقية:* {attempts}\n\n"
        f"ابدأ الآن! 🚀"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 رصيدي", callback_data="my_balance")],
        [InlineKeyboardButton("🔗 رابط الإحالة", callback_data="my_referral")],
    ]
    
    if user.id == OWNER_ID:
        keyboard.append([InlineKeyboardButton("🎛️ لوحة التحكم", callback_data="admin_panel")])
    
    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text("🚫 عذراً، تم حظر حسابك.")
        return
    
    db_user = get_user(user.id)
    if not db_user:
        db_user = create_user(user.id, user.username or "", user.full_name or "")
    
    text = update.message.text.strip()
    
    # أوامر المالك
    if user.id == OWNER_ID and text.startswith('/'):
        await handle_admin_commands(update, context)
        return
    
    if db_user.get('attempts_left', 0) <= 0:
        await update.message.reply_text(
            "⚠️ *نفدت محاولاتك المجانية!*\n\n"
            "ادعُ أصدقاءك عبر رابط الإحالة لتحصل على محاولات مجانية.\n"
            "استخدم /referral للحصول على رابطك.",
            parse_mode="Markdown"
        )
        return
    
    if text.startswith('http://') or text.startswith('https://'):
        input_type = 'url'
        content_text = None
    elif len(text) < 50:
        await update.message.reply_text("⚠️ النص قصير جداً! أرسل 50 حرفاً على الأقل.")
        return
    else:
        input_type = 'text'
        content_text = text
    
    user_states[user.id] = {
        'state': 'awaiting_dialect',
        'input_type': input_type,
        'content': content_text,
        'url': text if input_type == 'url' else None
    }
    
    await update.message.reply_text(
        "🎤 *اختر لهجة الشرح:*",
        parse_mode="Markdown",
        reply_markup=get_dialect_keyboard()
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text("🚫 عذراً، تم حظر حسابك.")
        return
    
    db_user = get_user(user.id)
    if not db_user:
        db_user = create_user(user.id, user.username or "", user.full_name or "")
    
    if db_user.get('attempts_left', 0) <= 0:
        await update.message.reply_text("⚠️ نفدت محاولاتك المجانية!")
        return
    
    doc = update.message.document
    if not doc.file_name.endswith('.pdf'):
        await update.message.reply_text("⚠️ يرجى إرسال ملف PDF فقط.")
        return
    
    status = await update.message.reply_text("⏳ جاري قراءة الملف...")
    
    try:
        file = await context.bot.get_file(doc.file_id)
        pdf_bytes = await file.download_as_bytearray()
        await status.edit_text("📄 تم استلام الملف!")
        
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
        await status.edit_text(f"❌ خطأ: {str(e)}")

async def handle_dialect_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    dialect = query.data.replace("dialect_", "")
    state = user_states.get(user_id, {})
    
    if state.get('state') != 'awaiting_dialect':
        await query.edit_message_text("❌ انتهت الجلسة. أرسل المحاضرة مرة أخرى.")
        return
    
    state['dialect'] = dialect
    user_states[user_id] = state
    
    dialect_name = VOICES.get(dialect, {}).get('name', dialect)
    
    await query.edit_message_text(
        f"✅ *تم اختيار: {dialect_name}*\n\n"
        f"⏳ جاري المعالجة... (قد يستغرق 1-3 دقائق)",
        parse_mode="Markdown"
    )
    
    asyncio.create_task(process_lecture(query, context, user_id, state, dialect_name))

async def process_lecture(query, context, user_id, state, dialect_name):
    dialect = state['dialect']
    input_type = state['input_type']
    
    req_id = save_video_request(user_id, input_type, dialect)
    reset_tts_engine()
    
    try:
        # استخراج النص
        if input_type == 'url':
            await context.bot.send_message(chat_id=user_id, text="🌐 جاري تحميل الرابط...")
            content_text = await extract_text_from_url(state['url'])
        elif input_type == 'pdf':
            await context.bot.send_message(chat_id=user_id, text="📄 جاري قراءة الملف...")
            content_text = await extract_text_from_pdf(state['content'])
        else:
            content_text = state['content']
        
        status_msg = await context.bot.send_message(
            chat_id=user_id,
            text="🔄 1️⃣ تحليل المحاضرة... ⏳"
        )
        
        # تحليل المحاضرة
        lecture_data = await analyze_lecture(content_text, dialect)
        sections = lecture_data.get('sections', [])
        
        if not sections:
            await context.bot.send_message(chat_id=user_id, text="❌ لم أستطع تحليل المحاضرة.")
            user_states.pop(user_id, None)
            return
        
        await status_msg.edit_text(f"🔄 1️⃣ ✅ التحليل | 2️⃣ 🖼️ جاري توليد {len(sections)} صورة...")
        
        # توليد الصور
        for i, section in enumerate(sections):
            keyword = section.get('keywords', [section.get('title', '')])[0]
            section['_image_bytes'] = await fetch_image_for_keyword(keyword)
        
        await status_msg.edit_text(f"🔄 1️⃣✅ 2️⃣✅ | 3️⃣ 🎙️ جاري توليد الصوت...")
        
        # توليد الصوت
        audio_response = await generate_sections_audio(sections, dialect)
        audio_results = audio_response["results"]
        
        await status_msg.edit_text(f"🔄 1️⃣✅ 2️⃣✅ 3️⃣✅ | 4️⃣ 🎬 جاري إنشاء الفيديو...")
        
        # إنشاء الفيديو
        video_path = os.path.join(TEMP_DIR, f"video_{user_id}_{uuid.uuid4().hex[:8]}.mp4")
        await create_video_from_sections(sections, audio_results, lecture_data, video_path)
        
        await status_msg.edit_text(f"🔄 1️⃣✅ 2️⃣✅ 3️⃣✅ 4️⃣✅ | 5️⃣ 📄 جاري إنشاء PDF...")
        
        # إنشاء PDF
        pdf_path = os.path.join(TEMP_DIR, f"summary_{user_id}_{uuid.uuid4().hex[:8]}.pdf")
        create_pdf_summary(lecture_data, sections, pdf_path)
        
        # تحديث قاعدة البيانات
        remaining = decrement_attempts(user_id)
        increment_total_videos(user_id)
        update_video_request(req_id, 'completed', video_path, pdf_path)
        
        await status_msg.edit_text("✅ اكتملت المعالجة! جاري إرسال الملفات...")
        
        # إرسال الفيديو
        title = lecture_data.get('title', 'المحاضرة')
        caption = f"🎓 *{title}*\n\n🎤 اللهجة: {dialect_name}\n🎯 المحاولات المتبقية: {remaining}"
        
        video_size = os.path.getsize(video_path) / (1024*1024)
        
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
                text=f"⚠️ الفيديو كبير جداً ({video_size:.1f}MB).\nتم إرسال PDF فقط."
            )
        
        # إرسال PDF
        with open(pdf_path, 'rb') as pf:
            await context.bot.send_document(
                chat_id=user_id,
                document=pf,
                filename=f"{title[:30]}_summary.pdf",
                caption=f"📄 ملخص: {title}"
            )
        
        # تنظيف
        try:
            os.remove(video_path)
            os.remove(pdf_path)
        except:
            pass
        
        user_states.pop(user_id, None)
        
    except Exception as e:
        logger.error(f"Error for user {user_id}: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"❌ خطأ: {str(e)[:200]}")
        user_states.pop(user_id, None)
        update_video_request(req_id, 'failed')

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("dialect_"):
        await handle_dialect_selection(update, context)
        return
    
    await query.answer()
    
    if data == "my_balance":
        db_user = get_user(user_id) or create_user(user_id, query.from_user.username or "", query.from_user.full_name or "")
        attempts = db_user.get('attempts_left', 0)
        total = db_user.get('total_videos', 0)
        
        await query.edit_message_text(
            f"📊 *رصيدك:*\n\n🎯 المحاولات: *{attempts}*\n🎬 الفيديوهات: *{total}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ رجوع", callback_data="back_main")
            ]])
        )
    
    elif data == "my_referral":
        ref_stats = get_referral_stats(user_id)
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        
        await query.edit_message_text(
            f"🔗 *رابط الإحالة:*\n`{link}`\n\n"
            f"👥 المدعوين: *{ref_stats['total_referrals']}*\n"
            f"⭐ النقاط: *{ref_stats['current_points']:.1f}/1.0*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ رجوع", callback_data="back_main")
            ]])
        )
    
    elif data == "admin_panel" and user_id == OWNER_ID:
        stats = get_stats()
        await query.edit_message_text(
            f"🎛️ *لوحة التحكم*\n\n"
            f"👥 المستخدمين: *{stats['total_users']}*\n"
            f"🆕 اليوم: *{stats['new_today']}*\n"
            f"🎬 الفيديوهات: *{stats['total_videos']}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 عرض المستخدمين", callback_data="admin_users")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="back_main")]
            ])
        )
    
    elif data == "admin_users" and user_id == OWNER_ID:
        users = get_all_users(10)
        msg = "👥 *آخر 10 مستخدمين:*\n\n"
        for u in users:
            status = "🚫" if u['is_banned'] else "✅"
            msg += f"{status} `{u['user_id']}` - {u['full_name'][:20]}\n   محاولات: {u['attempts_left']} | فيديوهات: {u['total_videos']}\n\n"
        
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ رجوع", callback_data="admin_panel")
            ]])
        )
    
    elif data == "back_main":
        db_user = get_user(user_id)
        attempts = db_user.get('attempts_left', 0) if db_user else 0
        keyboard = [
            [InlineKeyboardButton("📊 رصيدي", callback_data="my_balance")],
            [InlineKeyboardButton("🔗 رابط الإحالة", callback_data="my_referral")],
        ]
        if user_id == OWNER_ID:
            keyboard.append([InlineKeyboardButton("🎛️ لوحة التحكم", callback_data="admin_panel")])
        
        await query.edit_message_text(
            f"🎓 *بوت المحاضرات الذكي*\n\n🎯 المحاولات: {attempts}\n\nأرسل محاضرتك للبدء!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return
    
    text = update.message.text
    parts = text.split()
    cmd = parts[0].lower()
    
    if cmd == "/add" and len(parts) >= 3:
        try:
            target = int(parts[1])
            count = int(parts[2])
            new_bal = add_attempts(target, count)
            await update.message.reply_text(f"✅ تم إضافة {count} محاولة للمستخدم {target}\nالرصيد: {new_bal}")
        except:
            await update.message.reply_text("❌ استخدام: /add [user_id] [count]")
    
    elif cmd == "/ban" and len(parts) >= 2:
        try:
            target = int(parts[1])
            ban_user(target, True)
            await update.message.reply_text(f"🚫 تم حظر {target}")
        except:
            await update.message.reply_text("❌ استخدام: /ban [user_id]")
    
    elif cmd == "/unban" and len(parts) >= 2:
        try:
            target = int(parts[1])
            ban_user(target, False)
            await update.message.reply_text(f"✅ تم فك حظر {target}")
        except:
            await update.message.reply_text("❌ استخدام: /unban [user_id]")
    
    elif cmd == "/broadcast" and len(parts) >= 2:
        msg = ' '.join(parts[1:])
        users = get_all_users(100)
        sent = 0
        for u in users:
            try:
                await context.bot.send_message(chat_id=u['user_id'], text=f"📢 {msg}")
                sent += 1
            except:
                pass
        await update.message.reply_text(f"✅ تم الإرسال إلى {sent} مستخدم")

async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref_stats = get_referral_stats(user.id)
    bot_info = await context.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"
    
    await update.message.reply_text(
        f"🔗 *رابط الإحالة الخاص بك:*\n`{link}`\n\n"
        f"👥 المدعوين: *{ref_stats['total_referrals']}*\n"
        f"⭐ النقاط: *{ref_stats['current_points']:.1f}/1.0*\n\n"
        f"💡 كل 10 أشخاص = محاولة مجانية!",
        parse_mode="Markdown"
    )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_user = get_user(user_id) or create_user(user_id, update.effective_user.username or "", update.effective_user.full_name or "")
    await update.message.reply_text(
        f"📊 *رصيدك:*\n🎯 المحاولات: *{db_user.get('attempts_left', 0)}*\n🎬 الفيديوهات: *{db_user.get('total_videos', 0)}*",
        parse_mode="Markdown"
    )

async def main():
    init_db()
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("referral", referral_command))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    logger.info("🤖 Bot started!")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())
