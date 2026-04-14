#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
لوحة تحكم المالك
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    get_stats, get_all_users, get_pending_payments, approve_payment,
    ban_user, set_attempts, add_attempts, subtract_attempts, get_user
)
from config import OWNER_ID

USERS_PER_PAGE = 8


def is_owner(user_id: int) -> bool:
    """التحقق من المالك."""
    return user_id == OWNER_ID


def _back_btn(target: str = "admin_back") -> list:
    """زر الرجوع."""
    return [InlineKeyboardButton("◀️ رجوع", callback_data=target)]


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """لوحة المفاتيح الرئيسية للوحة التحكم."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 الإحصاءات", callback_data="admin_stats"),
            InlineKeyboardButton("👥 المستخدمين", callback_data="admin_ul_0")
        ],
        [
            InlineKeyboardButton("🔍 بحث بـ ID", callback_data="admin_search"),
            InlineKeyboardButton("💰 المدفوعات", callback_data="admin_payments")
        ],
        [
            InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast"),
            InlineKeyboardButton("🔧 الأوامر", callback_data="admin_commands")
        ],
        [
            InlineKeyboardButton("🔄 تحديث", callback_data="admin_back")
        ],
    ])


def _user_manage_keyboard(uid: int, is_banned: bool, back_offset: int = 0) -> InlineKeyboardMarkup:
    """لوحة مفاتيح إدارة مستخدم محدد."""
    uid_s = str(uid)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕1", callback_data=f"admin_add_1_{uid_s}"),
            InlineKeyboardButton("➕5", callback_data=f"admin_add_5_{uid_s}"),
            InlineKeyboardButton("➕10", callback_data=f"admin_add_10_{uid_s}"),
        ],
        [
            InlineKeyboardButton("➕20", callback_data=f"admin_add_20_{uid_s}"),
            InlineKeyboardButton("➕50", callback_data=f"admin_add_50_{uid_s}"),
            InlineKeyboardButton("➕100", callback_data=f"admin_add_100_{uid_s}"),
        ],
        [
            InlineKeyboardButton("➖1", callback_data=f"admin_sub_1_{uid_s}"),
            InlineKeyboardButton("➖3", callback_data=f"admin_sub_3_{uid_s}"),
            InlineKeyboardButton("➖5", callback_data=f"admin_sub_5_{uid_s}"),
        ],
        [
            InlineKeyboardButton("➖10", callback_data=f"admin_sub_10_{uid_s}"),
            InlineKeyboardButton("🔢 صفر", callback_data=f"admin_zero_{uid_s}"),
        ],
        [
            InlineKeyboardButton("🚫 حظر", callback_data=f"admin_ban_{uid_s}")
            if not is_banned else
            InlineKeyboardButton("✅ رفع الحظر", callback_data=f"admin_unb_{uid_s}"),
        ],
        [InlineKeyboardButton("◀️ للمستخدمين", callback_data=f"admin_ul_{back_offset}")],
    ])


def _users_list_keyboard(users: list, offset: int, total: int) -> InlineKeyboardMarkup:
    """لوحة مفاتيح قائمة المستخدمين."""
    rows = []
    for u in users:
        label = ("🚫 " if u['is_banned'] else "✅ ") + \
                f"{u.get('full_name', 'Unknown')[:18]} [{u['attempts_left']}🎯]"
        rows.append([InlineKeyboardButton(label, callback_data=f"admin_u_{u['user_id']}_{offset}")])
    
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"admin_ul_{offset - USERS_PER_PAGE}"))
    if offset + USERS_PER_PAGE < total:
        nav.append(InlineKeyboardButton("➡️ التالي", callback_data=f"admin_ul_{offset + USERS_PER_PAGE}"))
    if nav:
        rows.append(nav)
    
    rows.append(_back_btn("admin_back"))
    return InlineKeyboardMarkup(rows)


def _user_card(u: dict) -> str:
    """بطاقة معلومات المستخدم."""
    status = "🚫 محظور" if u['is_banned'] else "✅ نشط"
    joined = u['created_at'].strftime('%Y-%m-%d %H:%M') if u.get('created_at') else "—"
    
    return (
        f"👤 *{u.get('full_name', 'Unknown')}*\n"
        f"🆔 `{u['user_id']}`\n"
        f"📱 @{u.get('username') or '—'}\n"
        f"📊 {status}\n"
        f"🎯 محاولات متبقية: *{u['attempts_left']}*\n"
        f"🎬 فيديوهات: *{u['total_videos']}*\n"
        f"🔗 نقاط الإحالة: *{u.get('referral_points', 0):.1f}*\n"
        f"📅 انضم: {joined}"
    )


def _stats_text() -> str:
    """نص الإحصاءات."""
    s = get_stats()
    return (
        f"🎛️ *لوحة التحكم — المالك*\n\n"
        f"👥 المستخدمين: *{s['total_users']}*\n"
        f"🆕 اليوم: *{s['new_today']}*\n"
        f"🎬 الفيديوهات: *{s['total_videos']}*\n"
        f"💰 الإيرادات: *{s.get('total_revenue', 0):.2f}$*\n"
        f"⏳ مدفوعات معلقة: *{s['pending_payments']}*\n"
        f"🚫 محظورون: *{s['banned_users']}*"
    )


async def handle_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأمر /admin"""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ غير مصرح لك بالوصول إلى لوحة التحكم.")
        return
    
    context.user_data.pop("admin_search", None)
    context.user_data.pop("admin_broadcast", None)
    
    await update.message.reply_text(
        _stats_text(),
        parse_mode="Markdown",
        reply_markup=admin_main_keyboard(),
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أزرار لوحة التحكم."""
    query = update.callback_query
    uid = query.from_user.id
    
    if not is_owner(uid):
        await query.answer("❌ غير مصرح لك", show_alert=True)
        return
    
    data = query.data
    await query.answer()
    
    # الرئيسية / رجوع
    if data in ("admin_panel", "admin_back"):
        context.user_data.pop("admin_search", None)
        context.user_data.pop("admin_broadcast", None)
        await query.edit_message_text(
            _stats_text(),
            parse_mode="Markdown",
            reply_markup=admin_main_keyboard(),
        )
    
    # الإحصاءات
    elif data == "admin_stats":
        await query.edit_message_text(
            _stats_text(),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )
    
    # قائمة المستخدمين
    elif data.startswith("admin_ul_"):
        offset = int(data.split("_")[2])
        await _show_users_list(query, offset)
    
    # تفاصيل مستخدم
    elif data.startswith("admin_u_"):
        parts = data.split("_")
        target_id = int(parts[2])
        back_off = int(parts[3]) if len(parts) > 3 else 0
        await _show_user_detail(query, target_id, back_off)
    
    # إضافة محاولات
    elif data.startswith("admin_add_"):
        parts = data.split("_")
        amount = int(parts[2])
        target = int(parts[3])
        new_v = add_attempts(target, amount)
        await query.answer(f"✅ +{amount} محاولة → الرصيد: {new_v}", show_alert=True)
        await _show_user_detail(query, target, 0)
    
    # خصم محاولات
    elif data.startswith("admin_sub_"):
        parts = data.split("_")
        amount = int(parts[2])
        target = int(parts[3])
        new_v = subtract_attempts(target, amount)
        await query.answer(f"✅ -{amount} محاولة → الرصيد: {new_v}", show_alert=True)
        await _show_user_detail(query, target, 0)
    
    # تصفير
    elif data.startswith("admin_zero_"):
        target = int(data[len("admin_zero_"):])
        set_attempts(target, 0)
        await query.answer("✅ تم ضبط المحاولات على صفر", show_alert=True)
        await _show_user_detail(query, target, 0)
    
    # حظر
    elif data.startswith("admin_ban_"):
        target = int(data[len("admin_ban_"):])
        ban_user(target, True)
        await query.answer("🚫 تم حظر المستخدم", show_alert=True)
        try:
            await query.bot.send_message(target, "🚫 تم حظر حسابك من استخدام البوت.")
        except:
            pass
        await _show_user_detail(query, target, 0)
    
    # رفع الحظر
    elif data.startswith("admin_unb_"):
        target = int(data[len("admin_unb_"):])
        ban_user(target, False)
        await query.answer("✅ تم رفع الحظر", show_alert=True)
        try:
            await query.bot.send_message(target, "✅ تم رفع الحظر عن حسابك.")
        except:
            pass
        await _show_user_detail(query, target, 0)
    
    # بحث
    elif data == "admin_search":
        context.user_data["admin_search"] = True
        await query.edit_message_text(
            "🔍 *بحث عن مستخدم*\n\nأرسل الـ ID الخاص بالمستخدم:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )
    
    # المدفوعات
    elif data == "admin_payments":
        await _show_payments(query)
    
    # رسالة جماعية
    elif data == "admin_broadcast":
        context.user_data["admin_broadcast"] = True
        await query.edit_message_text(
            "📢 *إرسال رسالة جماعية*\n\nأرسل الرسالة الآن:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )
    
    # الأوامر
    elif data == "admin_commands":
        msg = (
            "🔧 *أوامر الإدارة:*\n\n"
            "/add `[id]` `[count]` — ➕ إضافة محاولات\n"
            "/set `[id]` `[count]` — 🔢 تعيين العدد\n"
            "/ban `[id]` — 🚫 حظر مستخدم\n"
            "/unban `[id]` — ✅ رفع الحظر\n"
            "/broadcast `[رسالة]` — 📢 رسالة جماعية\n"
            "/approve_`[payment_id]` — 💰 الموافقة على دفع"
        )
        await query.edit_message_text(
            msg,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )


async def _show_users_list(query, offset: int):
    """عرض قائمة المستخدمين."""
    users = get_all_users(limit=USERS_PER_PAGE, offset=offset)
    total = get_stats()['total_users']
    
    if not users:
        await query.edit_message_text(
            "👥 لا يوجد مستخدمون",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )
        return
    
    page = offset // USERS_PER_PAGE + 1
    pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE
    header = f"👥 *المستخدمون* — صفحة {page}/{pages} ({total} إجمالي)\n\n"
    
    lines = []
    for u in users:
        bmark = "🚫" if u['is_banned'] else "✅"
        name = u.get('full_name', 'Unknown')[:20]
        uname = f"@{u['username']}" if u.get('username') else "—"
        lines.append(f"{bmark} `{u['user_id']}` {name} ({uname}) | 🎯{u['attempts_left']}")
    
    await query.edit_message_text(
        header + "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=_users_list_keyboard(users, offset, total),
    )


async def _show_user_detail(query, target_id: int, back_offset: int = 0):
    """عرض تفاصيل مستخدم."""
    u = get_user(target_id)
    if not u:
        await query.edit_message_text(
            f"❌ المستخدم `{target_id}` غير موجود.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn(f"admin_ul_{back_offset}")]),
        )
        return
    
    await query.edit_message_text(
        f"👤 *إدارة المستخدم*\n\n{_user_card(u)}",
        parse_mode="Markdown",
        reply_markup=_user_manage_keyboard(target_id, bool(u['is_banned']), back_offset),
    )


async def _show_payments(query):
    """عرض المدفوعات المعلقة."""
    payments = get_pending_payments()
    
    if not payments:
        msg = "💰 *لا توجد مدفوعات معلقة*"
    else:
        msg = "💰 *المدفوعات المعلقة:*\n\n"
        for p in payments[:8]:
            msg += (
                f"🔢 *#{p['id']}* — {p.get('full_name', 'Unknown')}\n"
                f"   الطريقة: {p['payment_method']} | المبلغ: {p['amount']}\n"
                f"   للموافقة: `/approve_{p['id']}`\n\n"
            )
    
    await query.edit_message_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([_back_btn()]),
    )


async def handle_admin_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """معالجة النصوص المرسلة من المالك (بحث أو رسالة جماعية)."""
    if not is_owner(update.effective_user.id):
        return False
    
    # وضع الرسالة الجماعية
    if context.user_data.get("admin_broadcast"):
        context.user_data.pop("admin_broadcast")
        msg_text = update.message.text or ""
        
        if not msg_text.strip():
            await update.message.reply_text(
                "❌ الرسالة فارغة.",
                reply_markup=InlineKeyboardMarkup([_back_btn()]),
            )
            return True
        
        users = get_all_users(limit=1000)
        sent = 0
        for u in users:
            try:
                await context.bot.send_message(
                    u["user_id"],
                    f"📢 *رسالة من الإدارة:*\n\n{msg_text}",
                    parse_mode="Markdown",
                )
                sent += 1
            except:
                pass
        
        await update.message.reply_text(
            f"✅ *انتهى الإرسال*\n✉️ تم الإرسال: {sent}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )
        return True
    
    # وضع البحث
    if not context.user_data.get("admin_search"):
        return False
    
    text = (update.message.text or "").strip()
    context.user_data.pop("admin_search", None)
    
    try:
        target_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ ID غير صحيح. يجب أن يكون رقماً.")
        return True
    
    u = get_user(target_id)
    if not u:
        await update.message.reply_text(
            f"❌ المستخدم `{target_id}` غير موجود.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 بحث مرة أخرى", callback_data="admin_search")],
                [InlineKeyboardButton("◀️ رجوع", callback_data="admin_back")],
            ]),
        )
        return True
    
    await update.message.reply_text(
        f"👤 *إدارة المستخدم*\n\n{_user_card(u)}",
        parse_mode="Markdown",
        reply_markup=_user_manage_keyboard(target_id, bool(u['is_banned']), 0),
    )
    return True


async def handle_add_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /add [user_id] [count]"""
    if not is_owner(update.effective_user.id):
        return
    
    try:
        target_id = int(context.args[0])
        count = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("الاستخدام: /add [user_id] [count]")
        return
    
    u = get_user(target_id)
    if not u:
        await update.message.reply_text(f"❌ المستخدم {target_id} غير موجود")
        return
    
    new_v = add_attempts(target_id, count)
    await update.message.reply_text(
        f"✅ تم إضافة {count} محاولات للمستخدم {target_id}\n"
        f"الرصيد الجديد: *{new_v}* محاولة",
        parse_mode="Markdown",
    )
    
    try:
        await context.bot.send_message(
            target_id,
            f"🎁 تم إضافة {count} محاولات لحسابك!\nرصيدك الحالي: {new_v} محاولة",
        )
    except:
        pass


async def handle_set_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /set [user_id] [count]"""
    if not is_owner(update.effective_user.id):
        return
    
    try:
        target_id = int(context.args[0])
        count = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("الاستخدام: /set [user_id] [count]")
        return
    
    set_attempts(target_id, count)
    await update.message.reply_text(f"✅ تم تعيين {count} محاولات للمستخدم {target_id}")


async def handle_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /ban [user_id]"""
    if not is_owner(update.effective_user.id):
        return
    
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("الاستخدام: /ban [user_id]")
        return
    
    ban_user(target_id, True)
    await update.message.reply_text(f"🚫 تم حظر المستخدم {target_id}")
    
    try:
        await context.bot.send_message(target_id, "🚫 تم حظر حسابك من استخدام البوت.")
    except:
        pass


async def handle_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /unban [user_id]"""
    if not is_owner(update.effective_user.id):
        return
    
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("الاستخدام: /unban [user_id]")
        return
    
    ban_user(target_id, False)
    await update.message.reply_text(f"✅ تم رفع الحظر عن المستخدم {target_id}")
    
    try:
        await context.bot.send_message(target_id, "✅ تم رفع الحظر عن حسابك.")
    except:
        pass


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الأمر /broadcast [message]"""
    if not is_owner(update.effective_user.id):
        return
    
    if not context.args:
        await update.message.reply_text("الاستخدام: /broadcast [الرسالة]")
        return
    
    message = ' '.join(context.args)
    users = get_all_users(limit=100)
    sent = 0
    
    for u in users:
        try:
            await context.bot.send_message(
                u['user_id'],
                f"📢 *رسالة من الإدارة:*\n\n{message}",
                parse_mode="Markdown",
            )
            sent += 1
        except:
            pass
    
    await update.message.reply_text(f"✅ تم الإرسال إلى {sent} مستخدم")
