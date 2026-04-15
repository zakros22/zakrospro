#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
لوحة تحكم المالك - إدارة المستخدمين والإحصائيات
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import OWNER_ID
from database import (
    get_stats, get_all_users, get_user,
    add_attempts, subtract_attempts, set_attempts, ban_user
)

# ══════════════════════════════════════════════════════════════════════════════
#  التحقق من المالك
# ══════════════════════════════════════════════════════════════════════════════
def is_owner(user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم هو المالك."""
    return user_id == OWNER_ID


# ══════════════════════════════════════════════════════════════════════════════
#  أزرار الرجوع
# ══════════════════════════════════════════════════════════════════════════════
def back_button(callback: str = "admin_back") -> list:
    return [InlineKeyboardButton("◀️ رجوع", callback_data=callback)]


# ══════════════════════════════════════════════════════════════════════════════
#  لوحة المفاتيح الرئيسية
# ══════════════════════════════════════════════════════════════════════════════
def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 الإحصاءات", callback_data="admin_stats"),
            InlineKeyboardButton("👥 المستخدمين", callback_data="admin_users_list")
        ],
        [
            InlineKeyboardButton("🔍 بحث عن مستخدم", callback_data="admin_search"),
            InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("🔄 تحديث", callback_data="admin_refresh")
        ]
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  لوحة مفاتيح إدارة مستخدم
# ══════════════════════════════════════════════════════════════════════════════
def user_manage_keyboard(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ 1", callback_data=f"admin_add_1_{user_id}"),
            InlineKeyboardButton("➕ 5", callback_data=f"admin_add_5_{user_id}"),
            InlineKeyboardButton("➕ 10", callback_data=f"admin_add_10_{user_id}")
        ],
        [
            InlineKeyboardButton("➖ 1", callback_data=f"admin_sub_1_{user_id}"),
            InlineKeyboardButton("➖ 5", callback_data=f"admin_sub_5_{user_id}"),
            InlineKeyboardButton("🔢 0", callback_data=f"admin_zero_{user_id}")
        ],
        [
            InlineKeyboardButton(
                "🚫 حظر المستخدم" if not is_banned else "✅ رفع الحظر",
                callback_data=f"admin_{'ban' if not is_banned else 'unban'}_{user_id}"
            )
        ],
        [InlineKeyboardButton("◀️ رجوع للقائمة", callback_data="admin_users_list")]
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  معالج الأمر /admin
# ══════════════════════════════════════════════════════════════════════════════
async def handle_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /admin - فتح لوحة التحكم."""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ غير مصرح لك بالوصول إلى لوحة التحكم.")
        return
    
    stats = get_stats()
    
    text = f"""
🎛️ *لوحة التحكم - المالك*

👥 *المستخدمين:* {stats['total_users']}
🆕 *جدد اليوم:* {stats['new_today']}
🎬 *الفيديوهات:* {stats['total_videos']}
💰 *الإيرادات:* {stats.get('total_revenue', 0):.2f}$
🚫 *محظورين:* {stats['banned_users']}
"""
    
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=admin_main_keyboard()
    )


# ══════════════════════════════════════════════════════════════════════════════
#  معالج أزرار لوحة التحكم
# ══════════════════════════════════════════════════════════════════════════════
async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أزرار لوحة التحكم."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ غير مصرح", show_alert=True)
        return
    
    data = query.data
    
    # ═════════════════════════════════════════════════════════════════════════
    # تحديث / رجوع للرئيسية
    # ═════════════════════════════════════════════════════════════════════════
    if data in ("admin_refresh", "admin_back"):
        stats = get_stats()
        text = f"""
🎛️ *لوحة التحكم*

👥 *المستخدمين:* {stats['total_users']}
🆕 *جدد اليوم:* {stats['new_today']}
🎬 *الفيديوهات:* {stats['total_videos']}
💰 *الإيرادات:* {stats.get('total_revenue', 0):.2f}$
🚫 *محظورين:* {stats['banned_users']}
"""
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=admin_main_keyboard()
        )
    
    # ═════════════════════════════════════════════════════════════════════════
    # الإحصاءات
    # ═════════════════════════════════════════════════════════════════════════
    elif data == "admin_stats":
        stats = get_stats()
        text = f"""
📊 *إحصاءات تفصيلية*

👥 إجمالي المستخدمين: *{stats['total_users']}*
🆕 مستخدمين جدد اليوم: *{stats['new_today']}*
🎬 إجمالي الفيديوهات: *{stats['total_videos']}*
💰 إجمالي الإيرادات: *{stats.get('total_revenue', 0):.2f}$*
🚫 مستخدمين محظورين: *{stats['banned_users']}*
"""
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([back_button()])
        )
    
    # ═════════════════════════════════════════════════════════════════════════
    # قائمة المستخدمين
    # ═════════════════════════════════════════════════════════════════════════
    elif data == "admin_users_list":
        users = get_all_users(limit=20)
        
        if not users:
            await query.edit_message_text(
                "👥 *لا يوجد مستخدمين بعد*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([back_button()])
            )
            return
        
        # إنشاء أزرار للمستخدمين
        keyboard = []
        for u in users:
            status = "🚫" if u.get('is_banned') else "✅"
            name = u.get('full_name', 'غير معروف')[:15]
            btn_text = f"{status} {name} | 🎯{u['attempts_left']}"
            keyboard.append([
                InlineKeyboardButton(
                    btn_text,
                    callback_data=f"admin_user_{u['user_id']}"
                )
            ])
        
        keyboard.append(back_button())
        
        await query.edit_message_text(
            f"👥 *قائمة المستخدمين* ({len(users)} مستخدم)\n\n"
            "اختر مستخدماً لإدارته:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # ═════════════════════════════════════════════════════════════════════════
    # عرض تفاصيل مستخدم
    # ═════════════════════════════════════════════════════════════════════════
    elif data.startswith("admin_user_"):
        target_id = int(data.replace("admin_user_", ""))
        user = get_user(target_id)
        
        if not user:
            await query.answer("❌ المستخدم غير موجود", show_alert=True)
            return
        
        status = "🚫 محظور" if user['is_banned'] else "✅ نشط"
        joined = user.get('created_at', '—')
        if hasattr(joined, 'strftime'):
            joined = joined.strftime('%Y-%m-%d')
        
        text = f"""
👤 *معلومات المستخدم*

🆔 *ID:* `{user['user_id']}`
👤 *الاسم:* {user.get('full_name', '—')}
📱 *اليوزر:* @{user.get('username', '—')}
📊 *الحالة:* {status}
🎯 *المحاولات:* {user['attempts_left']}
🎬 *الفيديوهات:* {user['total_videos']}
🔗 *نقاط الإحالة:* {user.get('referral_points', 0):.1f}
📅 *تاريخ التسجيل:* {joined}
"""
        
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=user_manage_keyboard(target_id, user['is_banned'])
        )
    
    # ═════════════════════════════════════════════════════════════════════════
    # إضافة محاولات
    # ═════════════════════════════════════════════════════════════════════════
    elif data.startswith("admin_add_"):
        parts = data.split("_")
        amount = int(parts[2])
        target_id = int(parts[3])
        
        new_amount = add_attempts(target_id, amount)
        await query.answer(f"✅ تمت إضافة {amount} محاولة. الرصيد: {new_amount}", show_alert=True)
        
        # تحديث العرض
        user = get_user(target_id)
        if user:
            status = "🚫 محظور" if user['is_banned'] else "✅ نشط"
            text = f"""
👤 *معلومات المستخدم*

🆔 *ID:* `{user['user_id']}`
🎯 *المحاولات:* {user['attempts_left']}
📊 *الحالة:* {status}
"""
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=user_manage_keyboard(target_id, user['is_banned'])
            )
    
    # ═════════════════════════════════════════════════════════════════════════
    # خصم محاولات
    # ═════════════════════════════════════════════════════════════════════════
    elif data.startswith("admin_sub_"):
        parts = data.split("_")
        amount = int(parts[2])
        target_id = int(parts[3])
        
        new_amount = subtract_attempts(target_id, amount)
        await query.answer(f"✅ تم خصم {amount} محاولة. الرصيد: {new_amount}", show_alert=True)
        
        # تحديث العرض
        user = get_user(target_id)
        if user:
            status = "🚫 محظور" if user['is_banned'] else "✅ نشط"
            text = f"""
👤 *معلومات المستخدم*

🆔 *ID:* `{user['user_id']}`
🎯 *المحاولات:* {user['attempts_left']}
📊 *الحالة:* {status}
"""
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=user_manage_keyboard(target_id, user['is_banned'])
            )
    
    # ═════════════════════════════════════════════════════════════════════════
    # تصفير المحاولات
    # ═════════════════════════════════════════════════════════════════════════
    elif data.startswith("admin_zero_"):
        target_id = int(data.replace("admin_zero_", ""))
        set_attempts(target_id, 0)
        await query.answer("✅ تم تصفير المحاولات", show_alert=True)
        
        user = get_user(target_id)
        if user:
            status = "🚫 محظور" if user['is_banned'] else "✅ نشط"
            text = f"""
👤 *معلومات المستخدم*

🆔 *ID:* `{user['user_id']}`
🎯 *المحاولات:* 0
📊 *الحالة:* {status}
"""
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=user_manage_keyboard(target_id, user['is_banned'])
            )
    
    # ═════════════════════════════════════════════════════════════════════════
    # حظر مستخدم
    # ═════════════════════════════════════════════════════════════════════════
    elif data.startswith("admin_ban_"):
        target_id = int(data.replace("admin_ban_", ""))
        ban_user(target_id, True)
        await query.answer("🚫 تم حظر المستخدم", show_alert=True)
        
        # محاولة إرسال إشعار للمستخدم
        try:
            await context.bot.send_message(
                target_id,
                "🚫 *تم حظر حسابك من استخدام البوت.*\n"
                "إذا كنت تعتقد أن هذا خطأ، تواصل مع المالك.",
                parse_mode="Markdown"
            )
        except:
            pass
        
        user = get_user(target_id)
        if user:
            text = f"""
👤 *معلومات المستخدم*

🆔 *ID:* `{user['user_id']}`
🎯 *المحاولات:* {user['attempts_left']}
📊 *الحالة:* 🚫 محظور
"""
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=user_manage_keyboard(target_id, True)
            )
    
    # ═════════════════════════════════════════════════════════════════════════
    # رفع الحظر
    # ═════════════════════════════════════════════════════════════════════════
    elif data.startswith("admin_unban_"):
        target_id = int(data.replace("admin_unban_", ""))
        ban_user(target_id, False)
        await query.answer("✅ تم رفع الحظر", show_alert=True)
        
        # محاولة إرسال إشعار للمستخدم
        try:
            await context.bot.send_message(
                target_id,
                "✅ *تم رفع الحظر عن حسابك.*\n"
                "يمكنك الآن استخدام البوت مرة أخرى.",
                parse_mode="Markdown"
            )
        except:
            pass
        
        user = get_user(target_id)
        if user:
            text = f"""
👤 *معلومات المستخدم*

🆔 *ID:* `{user['user_id']}`
🎯 *المحاولات:* {user['attempts_left']}
📊 *الحالة:* ✅ نشط
"""
            await query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=user_manage_keyboard(target_id, False)
            )
    
    # ═════════════════════════════════════════════════════════════════════════
    # بحث عن مستخدم
    # ═════════════════════════════════════════════════════════════════════════
    elif data == "admin_search":
        context.user_data['admin_search_mode'] = True
        await query.edit_message_text(
            "🔍 *بحث عن مستخدم*\n\n"
            "أرسل ID المستخدم في رسالة نصية:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([back_button()])
        )
    
    # ═════════════════════════════════════════════════════════════════════════
    # رسالة جماعية
    # ═════════════════════════════════════════════════════════════════════════
    elif data == "admin_broadcast":
        context.user_data['admin_broadcast_mode'] = True
        await query.edit_message_text(
            "📢 *رسالة جماعية*\n\n"
            "أرسل الرسالة التي تريد إرسالها لجميع المستخدمين:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([back_button()])
        )


# ══════════════════════════════════════════════════════════════════════════════
#  معالج النصوص (بحث ورسائل جماعية)
# ══════════════════════════════════════════════════════════════════════════════
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    معالجة النصوص المرسلة من المالك.
    ترجع True إذا تم استهلاك الرسالة.
    """
    if not is_owner(update.effective_user.id):
        return False
    
    # ═════════════════════════════════════════════════════════════════════════
    # وضع البحث
    # ═════════════════════════════════════════════════════════════════════════
    if context.user_data.get('admin_search_mode'):
        context.user_data.pop('admin_search_mode')
        text = update.message.text.strip()
        
        try:
            target_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ ID غير صالح. يجب أن يكون رقماً.")
            return True
        
        user = get_user(target_id)
        if not user:
            await update.message.reply_text(f"❌ المستخدم `{target_id}` غير موجود.", parse_mode="Markdown")
            return True
        
        status = "🚫 محظور" if user['is_banned'] else "✅ نشط"
        joined = user.get('created_at', '—')
        if hasattr(joined, 'strftime'):
            joined = joined.strftime('%Y-%m-%d')
        
        text = f"""
👤 *نتيجة البحث*

🆔 *ID:* `{user['user_id']}`
👤 *الاسم:* {user.get('full_name', '—')}
📱 *اليوزر:* @{user.get('username', '—')}
📊 *الحالة:* {status}
🎯 *المحاولات:* {user['attempts_left']}
🎬 *الفيديوهات:* {user['total_videos']}
📅 *تاريخ التسجيل:* {joined}
"""
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=user_manage_keyboard(target_id, user['is_banned'])
        )
        return True
    
    # ═════════════════════════════════════════════════════════════════════════
    # وضع الرسالة الجماعية
    # ═════════════════════════════════════════════════════════════════════════
    if context.user_data.get('admin_broadcast_mode'):
        context.user_data.pop('admin_broadcast_mode')
        message = update.message.text
        
        if not message:
            await update.message.reply_text("❌ الرسالة فارغة.")
            return True
        
        users = get_all_users(limit=500)
        sent = 0
        failed = 0
        
        status_msg = await update.message.reply_text(f"📢 جاري الإرسال... 0/{len(users)}")
        
        for i, u in enumerate(users):
            try:
                await context.bot.send_message(
                    u['user_id'],
                    f"📢 *رسالة من الإدارة:*\n\n{message}",
                    parse_mode="Markdown"
                )
                sent += 1
            except:
                failed += 1
            
            if (i + 1) % 20 == 0:
                try:
                    await status_msg.edit_text(f"📢 جاري الإرسال... {i+1}/{len(users)}")
                except:
                    pass
        
        await status_msg.edit_text(
            f"✅ *تم الإرسال الجماعي*\n\n"
            f"✉️ تم الإرسال: {sent}\n"
            f"❌ فشل: {failed}",
            parse_mode="Markdown"
        )
        return True
    
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  أوامر الأدمن النصية
# ══════════════════════════════════════════════════════════════════════════════
async def handle_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /add [user_id] [amount]"""
    if not is_owner(update.effective_user.id):
        return
    
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ الاستخدام: `/add 123456 5`", parse_mode="Markdown")
        return
    
    new_amount = add_attempts(target_id, amount)
    await update.message.reply_text(
        f"✅ تمت إضافة *{amount}* محاولة للمستخدم `{target_id}`\n"
        f"الرصيد الحالي: *{new_amount}*",
        parse_mode="Markdown"
    )


async def handle_ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /ban [user_id]"""
    if not is_owner(update.effective_user.id):
        return
    
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ الاستخدام: `/ban 123456`", parse_mode="Markdown")
        return
    
    ban_user(target_id, True)
    await update.message.reply_text(f"🚫 تم حظر المستخدم `{target_id}`", parse_mode="Markdown")


async def handle_unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /unban [user_id]"""
    if not is_owner(update.effective_user.id):
        return
    
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ الاستخدام: `/unban 123456`", parse_mode="Markdown")
        return
    
    ban_user(target_id, False)
    await update.message.reply_text(f"✅ تم رفع الحظر عن المستخدم `{target_id}`", parse_mode="Markdown")


async def handle_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /broadcast [message]"""
    if not is_owner(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("❌ الاستخدام: `/broadcast رسالتك هنا`", parse_mode="Markdown")
        return
    
    message = ' '.join(context.args)
    users = get_all_users(limit=100)
    sent = 0
    
    for u in users:
        try:
            await context.bot.send_message(
                u['user_id'],
                f"📢 *رسالة من الإدارة:*\n\n{message}",
                parse_mode="Markdown"
            )
            sent += 1
        except:
            pass
    
    await update.message.reply_text(f"✅ تم الإرسال إلى *{sent}* مستخدم", parse_mode="Markdown")
