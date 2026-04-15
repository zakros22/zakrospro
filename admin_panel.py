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


# ══════════════════════════════════════════════════════════════════════════════
# Keyboards
# ══════════════════════════════════════════════════════════════════════════════

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
        [InlineKeyboardButton("🔑 حالة ElevenLabs", callback_data="admin_elstatus"),
         InlineKeyboardButton("🖼️ حالة الصور", callback_data="admin_imgstatus")],
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


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _user_card(u: dict) -> str:
    status = "🚫 محظور" if u['is_banned'] else "✅ نشط"
    joined = u['created_at'].strftime('%Y-%m-%d') if u.get('created_at') else "—"
    return (
        f"👤 *{u.get('full_name', 'Unknown')}*\n"
        f"🆔 `{u['user_id']}`\n"
        f"📱 @{u.get('username') or '—'}\n"
        f"📊 {status}\n"
        f"🎯 محاولات متبقية: *{u['attempts_left']}*\n"
        f"🎬 فيديوهات: *{u.get('total_videos', 0)}*\n"
        f"📅 انضم: {joined}"
    )


def _stats_text() -> str:
    s = get_stats()
    
    el_line = "🔑 ElevenLabs: —"
    try:
        from voice_generator import keys_status
        el = keys_status()
        el_line = f"🔑 ElevenLabs: {el['active']}/{el['total']} مفاتيح نشطة" if el['total'] else "🔑 ElevenLabs: لا توجد مفاتيح"
    except:
        pass
    
    img_line = "🖼️ الصور: —"
    try:
        from image_generator import get_image_keys_status
        img = get_image_keys_status()
        stability = img.get('stability', {})
        img_line = f"🖼️ Stability: {stability.get('active', 0)}/{stability.get('total', 0)} نشط"
    except:
        pass
    
    return (
        f"🎛️ *لوحة التحكم — المالك*\n\n"
        f"👥 المستخدمين: *{s['total_users']}*\n"
        f"🆕 اليوم: *{s.get('new_today', 0)}*\n"
        f"📊 نشط (24س): *{s.get('active_users', 0)}*\n"
        f"🎬 الفيديوهات: *{s.get('total_videos', 0)}*\n"
        f"💰 الإيرادات: *{s.get('total_revenue', 0):.2f}*\n"
        f"⏳ مدفوعات معلقة: *{s.get('pending_payments', 0)}*\n"
        f"🚫 محظورون: *{s.get('banned_users', 0)}*\n"
        f"{el_line}\n"
        f"{img_line}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# Entry command
# ══════════════════════════════════════════════════════════════════════════════

async def handle_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    context.user_data.pop("admin_search", None)
    await update.message.reply_text(
        _stats_text(),
        parse_mode="Markdown",
        reply_markup=admin_main_keyboard(),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Main callback router
# ══════════════════════════════════════════════════════════════════════════════

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id

    if not is_owner(uid):
        await query.answer("❌ غير مصرح لك", show_alert=True)
        return

    data = query.data

    # ── Main / back ──────────────────────────────────────────────────────────
    if data in ("admin_panel", "admin_back"):
        await query.answer()
        context.user_data.pop("admin_search", None)
        context.user_data.pop("admin_broadcast", None)
        await query.edit_message_text(
            _stats_text(), parse_mode="Markdown",
            reply_markup=admin_main_keyboard(),
        )

    # ── Stats ────────────────────────────────────────────────────────────────
    elif data == "admin_stats":
        await query.answer()
        await query.edit_message_text(
            _stats_text(), parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )

    # ── ElevenLabs status ────────────────────────────────────────────────────
    elif data == "admin_elstatus":
        await query.answer()
        try:
            from voice_generator import keys_status
            el = keys_status()
            msg = (
                f"🔑 *حالة مفاتيح ElevenLabs*\n\n"
                f"إجمالي المفاتيح: *{el['total']}*\n"
                f"المفاتيح النشطة: *{el['active']}*\n"
                f"المفاتيح المنتهية: *{el['exhausted']}*\n\n"
                + ("✅ جميع المفاتيح تعمل" if not el['all_gone'] else "⚠️ كل المفاتيح نفدت — يعمل بـ gTTS")
            )
        except Exception as e:
            msg = f"❌ خطأ في قراءة حالة ElevenLabs: {e}"
        
        await query.edit_message_text(
            msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )

    # ── Image status ─────────────────────────────────────────────────────────
    elif data == "admin_imgstatus":
        await query.answer()
        try:
            from image_generator import get_image_keys_status
            img = get_image_keys_status()
            stability = img.get('stability', {})
            replicate = img.get('replicate', {})
            pollinations = img.get('pollinations', {})
            
            msg = (
                f"🖼️ *حالة خدمات الصور*\n\n"
                f"🎨 *Stability AI:*\n"
                f"   إجمالي: {stability.get('total', 0)} | نشط: {stability.get('active', 0)}\n\n"
                f"🌟 *Replicate (Flux):*\n"
                f"   متاح: {'✅ نعم' if replicate.get('available') else '❌ لا'}\n\n"
                f"🆓 *Pollinations:*\n"
                f"   متاح: {'✅ نعم (مجاني)' if pollinations.get('available') else '❌ لا'}\n\n"
                f"📌 *الأولوية:* Pollinations → Stability → Replicate → صورة احتياطية"
            )
        except Exception as e:
            msg = f"❌ خطأ في قراءة حالة الصور: {e}"
        
        await query.edit_message_text(
            msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )

    # ── Users list ───────────────────────────────────────────────────────────
    elif data.startswith("admin_ul_"):
        await query.answer()
        offset = int(data.split("_")[2])
        await _show_users_list(query, offset)

    # ── Single user detail ───────────────────────────────────────────────────
    elif data.startswith("admin_u_"):
        await query.answer()
        parts = data.split("_")
        target_id = int(parts[2])
        back_off = int(parts[3]) if len(parts) > 3 else 0
        await _show_user_detail(query, target_id, back_off)

    # ── Add attempts ─────────────────────────────────────────────────────────
    elif data.startswith("admin_add_"):
        parts = data.split("_")
        amount = int(parts[2])
        target = int(parts[3])
        new_v = add_attempts(target, amount)
        await query.answer(f"✅ +{amount} محاولة → الرصيد: {new_v}", show_alert=True)
        await _show_user_detail(query, target, 0)

    # ── Subtract attempts ────────────────────────────────────────────────────
    elif data.startswith("admin_sub_"):
        parts = data.split("_")
        amount = int(parts[2])
        target = int(parts[3])
        new_v = subtract_attempts(target, amount)
        await query.answer(f"✅ -{amount} محاولة → الرصيد: {new_v}", show_alert=True)
        await _show_user_detail(query, target, 0)

    # ── Set to zero ──────────────────────────────────────────────────────────
    elif data.startswith("admin_zero_"):
        target = int(data[len("admin_zero_"):])
        set_attempts(target, 0)
        await query.answer("✅ تم ضبط المحاولات على صفر", show_alert=True)
        await _show_user_detail(query, target, 0)

    # ── Ban ──────────────────────────────────────────────────────────────────
    elif data.startswith("admin_ban_"):
        target = int(data[len("admin_ban_"):])
        ban_user(target, True)
        await query.answer("🚫 تم حظر المستخدم", show_alert=True)
        try:
            await query.bot.send_message(target, "🚫 تم حظر حسابك من استخدام البوت.")
        except:
            pass
        await _show_user_detail(query, target, 0)

    # ── Unban ────────────────────────────────────────────────────────────────
    elif data.startswith("admin_unb_"):
        target = int(data[len("admin_unb_"):])
        ban_user(target, False)
        await query.answer("✅ تم رفع الحظر", show_alert=True)
        try:
            await query.bot.send_message(target, "✅ تم رفع الحظر عن حسابك.")
        except:
            pass
        await _show_user_detail(query, target, 0)

    # ── Search by ID ─────────────────────────────────────────────────────────
    elif data == "admin_search":
        await query.answer()
        context.user_data["admin_search"] = True
        await query.edit_message_text(
            "🔍 *بحث عن مستخدم*\n\n"
            "أرسل الـ ID الخاص بالمستخدم كرسالة نصية الآن:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )

    # ── Payments ─────────────────────────────────────────────────────────────
    elif data == "admin_payments":
        await query.answer()
        await _show_payments(query)

    # ── Broadcast ────────────────────────────────────────────────────────────
    elif data == "admin_broadcast":
        await query.answer()
        context.user_data["admin_broadcast"] = True
        context.user_data.pop("admin_search", None)
        await query.edit_message_text(
            "📢 *إرسال رسالة جماعية*\n\n"
            "✏️ اكتب رسالتك الآن وسيتم إرسالها لجميع المستخدمين\n"
            "_(سواء كانوا نشطين أو لا)_\n\n"
            "يمكنك تضمين الإيموجي وأي تنسيق Markdown.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )

    # ── Commands ─────────────────────────────────────────────────────────────
    elif data == "admin_commands":
        await query.answer()
        msg = (
            "🔧 *أوامر الإدارة:*\n\n"
            "/addattempts `[id]` `[count]` — ➕ إضافة محاولات\n"
            "/setattempts `[id]` `[count]` — 🔢 تعيين العدد\n"
            "/ban `[id]` — 🚫 حظر مستخدم\n"
            "/unban `[id]` — ✅ رفع الحظر\n"
            "/userinfo `[id]` — ℹ️ معلومات مستخدم\n"
            "/approve\\_`[payment_id]` — 💰 الموافقة على دفع\n"
            "/broadcast `[رسالة]` — 📢 رسالة جماعية"
        )
        await query.edit_message_text(
            msg, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )

    else:
        await query.answer()


# ══════════════════════════════════════════════════════════════════════════════
# Page renderers
# ══════════════════════════════════════════════════════════════════════════════

async def _show_users_list(query, offset: int):
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
    u = get_user(target_id)
    if not u:
        await query.edit_message_text(
            f"❌ المستخدم `{target_id}` غير موجود في قاعدة البيانات.",
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
        msg, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([_back_btn()]),
    )


# ══════════════════════════════════════════════════════════════════════════════
# Handle owner text (search + broadcast)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_admin_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Call this from the main message handler.
    Returns True if the message was consumed as an admin action.
    """
    if not is_owner(update.effective_user.id):
        return False

    # ── Broadcast mode ───────────────────────────────────────────────────────
    if context.user_data.get("admin_broadcast"):
        context.user_data.pop("admin_broadcast", None)
        msg_text = update.message.text or ""
        if not msg_text.strip():
            await update.message.reply_text(
                "❌ الرسالة فارغة.",
                reply_markup=InlineKeyboardMarkup([_back_btn()]),
            )
            return True

        users = get_all_users(limit=100000)
        total = len(users)
        sent = 0
        failed = 0

        status_msg = await update.message.reply_text(
            f"📢 *جاري الإرسال الجماعي...*\n⏳ 0 / {total}",
            parse_mode="Markdown",
        )

        for u in users:
            try:
                await context.bot.send_message(
                    u["user_id"],
                    f"📢 *رسالة من الإدارة:*\n\n{msg_text}",
                    parse_mode="Markdown",
                )
                sent += 1
            except:
                failed += 1
            progress = sent + failed
            if progress % 20 == 0 or progress == total:
                try:
                    await status_msg.edit_text(
                        f"📢 *جاري الإرسال الجماعي...*\n⏳ {progress} / {total}",
                        parse_mode="Markdown",
                    )
                except:
                    pass

        await status_msg.edit_text(
            f"✅ *انتهى الإرسال الجماعي*\n\n"
            f"📤 إجمالي المستخدمين: *{total}*\n"
            f"✉️ تم الإرسال بنجاح: *{sent}*\n"
            f"❌ فشل: *{failed}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([_back_btn()]),
        )
        return True

    # ── Search mode ──────────────────────────────────────────────────────────
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
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔍 بحث مرة أخرى", callback_data="admin_search"),
                InlineKeyboardButton("◀️ رجوع", callback_data="admin_back"),
            ]]),
        )
        return True

    await update.message.reply_text(
        f"👤 *إدارة المستخدم*\n\n{_user_card(u)}",
        parse_mode="Markdown",
        reply_markup=_user_manage_keyboard(target_id, bool(u['is_banned']), 0),
    )
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Command handlers (text commands)
# ══════════════════════════════════════════════════════════════════════════════

async def handle_add_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    try:
        target_id = int(context.args[0])
        count = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("الاستخدام: /addattempts [user_id] [count]")
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
    if not is_owner(update.effective_user.id):
        return
    try:
        target_id = int(context.args[0])
        count = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("الاستخدام: /setattempts [user_id] [count]")
        return

    set_attempts(target_id, count)
    await update.message.reply_text(f"✅ تم تعيين {count} محاولات للمستخدم {target_id}")


async def handle_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


async def handle_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("الاستخدام: /userinfo [user_id]")
        return

    u = get_user(target_id)
    if not u:
        await update.message.reply_text(f"❌ المستخدم {target_id} غير موجود")
        return

    await update.message.reply_text(
        f"ℹ️ *معلومات المستخدم*\n\n{_user_card(u)}",
        parse_mode="Markdown",
        reply_markup=_user_manage_keyboard(target_id, bool(u['is_banned']), 0),
    )


async def handle_approve_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    try:
        payment_id = int(update.message.text.split("_")[1])
        result = approve_payment(payment_id)
    except (ValueError, IndexError):
        await update.message.reply_text("❌ خطأ في رقم الدفع")
        return

    if result:
        await update.message.reply_text(
            f"✅ تمت الموافقة على الدفع #{payment_id}\n"
            f"تم إضافة 4 محاولات للمستخدم {result['user_id']}"
        )
        try:
            await context.bot.send_message(
                result['user_id'],
                "🎉 تم الموافقة على دفعتك!\nتم إضافة 4 محاولات لحسابك.",
            )
        except:
            pass
    else:
        await update.message.reply_text(f"❌ لم يتم العثور على الدفع #{payment_id}")


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("الاستخدام: /broadcast [الرسالة]")
        return

    message = ' '.join(context.args)
    users = get_all_users(limit=5000)
    sent = failed = 0

    status_msg = await update.message.reply_text(f"📢 جاري الإرسال... (0/{len(users)})")

    for u in users:
        try:
            await context.bot.send_message(
                u['user_id'],
                f"📢 *رسالة من الإدارة:*\n\n{message}",
                parse_mode="Markdown",
            )
            sent += 1
        except:
            failed += 1
        if (sent + failed) % 10 == 0:
            try:
                await status_msg.edit_text(f"📢 جاري الإرسال... ({sent + failed}/{len(users)})")
            except:
                pass

    await status_msg.edit_text(
        f"✅ *انتهى الإرسال الجماعي*\n\n"
        f"✉️ تم الإرسال: {sent}\n❌ فشل: {failed}",
        parse_mode="Markdown",
    )
