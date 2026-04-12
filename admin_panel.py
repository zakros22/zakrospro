import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# ... باقي الاستيرادات
# -*- coding: utf-8 -*-
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import (
    get_stats, get_all_users, get_pending_payments, approve_payment,
    ban_user, set_attempts, add_attempts, subtract_attempts, get_user
)
from config import OWNER_ID

USERS_PER_PAGE = 8


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def _back_btn(target: str = "admin_back") -> list:
    return [InlineKeyboardButton("◀️ رجوع", callback_data=target)]


def admin_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصاءات", callback_data="admin_stats"),
         InlineKeyboardButton("👥 المستخدمين", callback_data="admin_ul_0")],
        [InlineKeyboardButton("🔍 بحث بـ ID", callback_data="admin_search"),
         InlineKeyboardButton("💰 المدفوعات", callback_data="admin_payments")],
        [InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast"),
         InlineKeyboardButton("🔧 الأوامر", callback_data="admin_commands")],
    ])


def _user_manage_keyboard(uid: int, is_banned: bool, back_offset: int = 0) -> InlineKeyboardMarkup:
    uid_s = str(uid)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕1", callback_data=f"admin_add_1_{uid_s}"),
            InlineKeyboardButton("➕5", callback_data=f"admin_add_5_{uid_s}"),
            InlineKeyboardButton("➕10", callback_data=f"admin_add_10_{uid_s}"),
            InlineKeyboardButton("➕20", callback_data=f"admin_add_20_{uid_s}"),
            InlineKeyboardButton("➕50", callback_data=f"admin_add_50_{uid_s}"),
        ],
        [
            InlineKeyboardButton("➖1", callback_data=f"admin_sub_1_{uid_s}"),
            InlineKeyboardButton("➖3", callback_data=f"admin_sub_3_{uid_s}"),
            InlineKeyboardButton("➖5", callback_data=f"admin_sub_5_{uid_s}"),
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
    status = "🚫 محظور" if u['is_banned'] else "✅ نشط"
    joined = u['created_at'].strftime('%Y-%m-%d') if u.get('created_at') else "—"
    return (
        f"👤 *{u.get('full_name', 'Unknown')}*\n"
        f"🆔 `{u['user_id']}`\n"
        f"📱 @{u.get('username') or '—'}\n"
        f"📊 {status}\n"
        f"🎯 محاولات: *{u['attempts_left']}*\n"
        f"🎬 فيديوهات: *{u['total_videos']}*\n"
        f"📅 انضم: {joined}"
    )


def _stats_text() -> str:
    s = get_stats()
    return (
        f"🎛️ *لوحة التحكم*\n\n"
        f"👥 المستخدمين: *{s['total_users']}*\n"
        f"🆕 اليوم: *{s['new_today']}*\n"
        f"🎬 الفيديوهات: *{s['total_videos']}*\n"
        f"💰 الإيرادات: *{s.get('total_revenue', 0):.2f}*\n"
        f"⏳ معلقة: *{s['pending_payments']}*\n"
        f"🚫 محظورون: *{s['banned_users']}*"
    )


async def handle_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    context.user_data.pop("admin_search", None)
    await update.message.reply_text(
        _stats_text(), parse_mode="Markdown", reply_markup=admin_main_keyboard()
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id

    if not is_owner(uid):
        await query.answer("❌ غير مصرح", show_alert=True)
        return

    data = query.data

    if data in ("admin_panel", "admin_back"):
        await query.answer()
        context.user_data.pop("admin_search", None)
        await query.edit_message_text(
            _stats_text(), parse_mode="Markdown", reply_markup=admin_main_keyboard()
        )

    elif data == "admin_stats":
        await query.answer()
        await query.edit_message_text(
            _stats_text(), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()])
        )

    elif data.startswith("admin_ul_"):
        await query.answer()
        offset = int(data.split("_")[2])
        await _show_users_list(query, offset)

    elif data.startswith("admin_u_"):
        await query.answer()
        parts = data.split("_")
        target_id = int(parts[2])
        back_off = int(parts[3]) if len(parts) > 3 else 0
        await _show_user_detail(query, target_id, back_off)

    elif data.startswith("admin_add_"):
        parts = data.split("_")
        amount = int(parts[2])
        target = int(parts[3])
        new_v = add_attempts(target, amount)
        await query.answer(f"✅ +{amount} → {new_v}", show_alert=True)
        await _show_user_detail(query, target, 0)

    elif data.startswith("admin_sub_"):
        parts = data.split("_")
        amount = int(parts[2])
        target = int(parts[3])
        new_v = subtract_attempts(target, amount)
        await query.answer(f"✅ -{amount} → {new_v}", show_alert=True)
        await _show_user_detail(query, target, 0)

    elif data.startswith("admin_zero_"):
        target = int(data[len("admin_zero_"):])
        set_attempts(target, 0)
        await query.answer("✅ صفر", show_alert=True)
        await _show_user_detail(query, target, 0)

    elif data.startswith("admin_ban_"):
        target = int(data[len("admin_ban_"):])
        ban_user(target, True)
        await query.answer("🚫 تم الحظر", show_alert=True)
        await _show_user_detail(query, target, 0)

    elif data.startswith("admin_unb_"):
        target = int(data[len("admin_unb_"):])
        ban_user(target, False)
        await query.answer("✅ رفع الحظر", show_alert=True)
        await _show_user_detail(query, target, 0)

    elif data == "admin_search":
        await query.answer()
        context.user_data["admin_search"] = True
        await query.edit_message_text(
            "🔍 أرسل ID المستخدم:", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()])
        )

    elif data == "admin_payments":
        await query.answer()
        await _show_payments(query)

    elif data == "admin_broadcast":
        await query.answer()
        context.user_data["admin_broadcast"] = True
        await query.edit_message_text(
            "📢 أرسل الرسالة:", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()])
        )

    elif data == "admin_commands":
        await query.answer()
        msg = (
            "🔧 *أوامر:*\n"
            "/add `id` `count` - إضافة محاولات\n"
            "/set `id` `count` - تعيين المحاولات\n"
            "/ban `id` - حظر\n"
            "/unban `id` - رفع حظر\n"
            "/broadcast `msg` - رسالة جماعية\n"
            "/approve_`id` - موافقة دفع"
        )
        await query.edit_message_text(
            msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([_back_btn()])
        )

    else:
        await query.answer()


async def _show_users_list(query, offset: int):
    users = get_all_users(limit=USERS_PER_PAGE, offset=offset)
    total = get_stats()['total_users']

    if not users:
        await query.edit_message_text(
            "👥 لا يوجد", reply_markup=InlineKeyboardMarkup([_back_btn()])
        )
        return

    page = offset // USERS_PER_PAGE + 1
    pages = (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE
    header = f"👥 *المستخدمون* - {page}/{pages} ({total})\n\n"
    lines = []
    for u in users:
        bmark = "🚫" if u['is_banned'] else "✅"
        name = u.get('full_name', 'Unknown')[:20]
        lines.append(f"{bmark} `{u['user_id']}` {name} | 🎯{u['attempts_left']}")

    await query.edit_message_text(
        header + "\n".join(lines), parse_mode="Markdown",
        reply_markup=_users_list_keyboard(users, offset, total)
    )


async def _show_user_detail(query, target_id: int, back_offset: int = 0):
    u = get_user(target_id)
    if not u:
        await query.edit_message_text(
            f"❌ `{target_id}` غير موجود", parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn(f"admin_ul_{back_offset}")])
        )
        return
    await query.edit_message_text(
        f"👤 *إدارة*\n\n{_user_card(u)}", parse_mode="Markdown",
        reply_markup=_user_manage_keyboard(target_id, bool(u['is_banned']), back_offset)
    )


async def _show_payments(query):
    payments = get_pending_payments()
    if not payments:
        msg = "💰 لا توجد مدفوعات"
    else:
        msg = "💰 *معلقة:*\n\n"
        for p in payments[:8]:
            msg += (
                f"🔢 #{p['id']} - {p.get('full_name', 'Unknown')}\n"
                f"   {p['payment_method']} | {p['amount']}\n"
                f"   `/approve_{p['id']}`\n\n"
            )
    await query.edit_message_text(
        msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([_back_btn()])
    )


async def handle_admin_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not is_owner(update.effective_user.id):
        return False

    if context.user_data.get("admin_broadcast"):
        context.user_data.pop("admin_broadcast", None)
        msg_text = update.message.text or ""
        if not msg_text.strip():
            await update.message.reply_text("❌ فارغة", reply_markup=InlineKeyboardMarkup([_back_btn()]))
            return True

        users = get_all_users(limit=100000)
        sent = failed = 0
        status_msg = await update.message.reply_text(f"📢 جاري... 0/{len(users)}")

        for u in users:
            try:
                await context.bot.send_message(u["user_id"], f"📢 {msg_text}", parse_mode="Markdown")
                sent += 1
            except:
                failed += 1

        await status_msg.edit_text(f"✅ تم: {sent}\n❌ فشل: {failed}")
        return True

    if not context.user_data.get("admin_search"):
        return False

    text = update.message.text.strip()
    context.user_data.pop("admin_search", None)

    try:
        target_id = int(text)
    except:
        await update.message.reply_text("❌ رقم غير صحيح")
        return True

    u = get_user(target_id)
    if not u:
        await update.message.reply_text(f"❌ `{target_id}` غير موجود", parse_mode="Markdown")
        return True

    await update.message.reply_text(
        f"👤 *إدارة*\n\n{_user_card(u)}", parse_mode="Markdown",
        reply_markup=_user_manage_keyboard(target_id, bool(u['is_banned']), 0)
    )
    return True


async def handle_add_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    try:
        target = int(context.args[0])
        count = int(context.args[1])
    except:
        await update.message.reply_text("/add `id` `count`")
        return
    new_v = add_attempts(target, count)
    await update.message.reply_text(f"✅ +{count} → {new_v}")


async def handle_set_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    try:
        target = int(context.args[0])
        count = int(context.args[1])
    except:
        await update.message.reply_text("/set `id` `count`")
        return
    set_attempts(target, count)
    await update.message.reply_text(f"✅ = {count}")


async def handle_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    try:
        target = int(context.args[0])
    except:
        await update.message.reply_text("/ban `id`")
        return
    ban_user(target, True)
    await update.message.reply_text(f"🚫 {target}")


async def handle_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    try:
        target = int(context.args[0])
    except:
        await update.message.reply_text("/unban `id`")
        return
    ban_user(target, False)
    await update.message.reply_text(f"✅ {target}")


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("/broadcast `msg`")
        return

    msg = ' '.join(context.args)
    users = get_all_users(limit=5000)
    sent = failed = 0

    for u in users:
        try:
            await context.bot.send_message(u['user_id'], f"📢 {msg}", parse_mode="Markdown")
            sent += 1
        except:
            failed += 1

    await update.message.reply_text(f"✅ {sent} | ❌ {failed}")


async def handle_approve_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    try:
        pid = int(update.message.text.split("_")[1])
        res = approve_payment(pid)
    except:
        await update.message.reply_text("❌ خطأ")
        return
    if res:
        await update.message.reply_text(f"✅ #{pid}")
    else:
        await update.message.reply_text(f"❌ #{pid}")
