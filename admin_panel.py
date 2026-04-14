#!/usr/bin/env python3
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

def _back_btn(target: str = "admin_back"):
    return [InlineKeyboardButton("◀️ رجوع", callback_data=target)]

def admin_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصاءات", callback_data="admin_stats"),
         InlineKeyboardButton("👥 المستخدمين", callback_data="admin_ul_0")],
        [InlineKeyboardButton("🔍 بحث بـ ID", callback_data="admin_search"),
         InlineKeyboardButton("💰 المدفوعات", callback_data="admin_payments")],
        [InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔄 تحديث", callback_data="admin_back")],
    ])

async def handle_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        return
    s = get_stats()
    text = f"🎛️ *لوحة التحكم*\n\n👥 المستخدمين: *{s['total_users']}*\n🎬 الفيديوهات: *{s['total_videos']}*\n💰 الإيرادات: *{s['total_revenue']:.2f}$*\n⏳ معلقة: *{s['pending_payments']}*"
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=admin_main_keyboard())

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    
    if not is_owner(q.from_user.id):
        await q.answer("❌ غير مصرح", show_alert=True)
        return
    
    await q.answer()
    
    if data in ("admin_panel", "admin_back"):
        s = get_stats()
        text = f"🎛️ *لوحة التحكم*\n\n👥 *{s['total_users']}* | 🎬 *{s['total_videos']}* | 💰 *{s['total_revenue']:.2f}$*"
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=admin_main_keyboard())
    
    elif data == "admin_stats":
        s = get_stats()
        await q.edit_message_text(f"📊 *إحصاءات*\n👥 {s['total_users']}\n🆕 {s['new_today']}\n🎬 {s['total_videos']}\n💰 {s['total_revenue']:.2f}$", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([_back_btn()]))
    
    elif data == "admin_payments":
        payments = get_pending_payments()
        if not payments:
            text = "💰 لا توجد مدفوعات معلقة"
        else:
            text = "💰 *مدفوعات معلقة:*\n\n"
            for p in payments[:5]:
                text += f"#{p['id']} - {p.get('full_name', '')} - {p['amount']}$\nللموافقة: `/approve_{p['id']}`\n\n"
        await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([_back_btn()]))
    
    elif data == "admin_broadcast":
        context.user_data["admin_broadcast"] = True
        await q.edit_message_text("📢 أرسل الرسالة الجماعية:", reply_markup=InlineKeyboardMarkup([_back_btn()]))
    
    elif data.startswith("admin_add_"):
        parts = data.split("_")
        amount = int(parts[2])
        target = int(parts[3])
        add_attempts(target, amount)
        await q.answer(f"✅ +{amount}", show_alert=True)
    
    elif data.startswith("admin_sub_"):
        parts = data.split("_")
        amount = int(parts[2])
        target = int(parts[3])
        subtract_attempts(target, amount)
        await q.answer(f"✅ -{amount}", show_alert=True)
    
    elif data.startswith("admin_zero_"):
        target = int(data.split("_")[2])
        set_attempts(target, 0)
        await q.answer("✅ صفر", show_alert=True)
    
    elif data.startswith("admin_ban_"):
        target = int(data.split("_")[2])
        ban_user(target, True)
        await q.answer("🚫 حظر", show_alert=True)
    
    elif data.startswith("admin_unb_"):
        target = int(data.split("_")[2])
        ban_user(target, False)
        await q.answer("✅ رفع", show_alert=True)

async def handle_admin_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not is_owner(update.effective_user.id):
        return False
    
    if context.user_data.get("admin_broadcast"):
        context.user_data.pop("admin_broadcast")
        msg = update.message.text
        users = get_all_users(limit=1000)
        sent = 0
        for u in users:
            try:
                await context.bot.send_message(u['user_id'], f"📢 *رسالة من الإدارة:*\n\n{msg}", parse_mode="Markdown")
                sent += 1
            except:
                pass
        await update.message.reply_text(f"✅ تم الإرسال لـ {sent} مستخدم")
        return True
    
    return False

async def handle_add_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        target = int(context.args[0])
        count = int(context.args[1])
        add_attempts(target, count)
        await update.message.reply_text(f"✅ +{count} للمستخدم {target}")
    except:
        await update.message.reply_text("/add [id] [count]")

async def handle_set_attempts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        target = int(context.args[0])
        count = int(context.args[1])
        set_attempts(target, count)
        await update.message.reply_text(f"✅ تعيين {count} للمستخدم {target}")
    except:
        await update.message.reply_text("/set [id] [count]")

async def handle_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        target = int(context.args[0])
        ban_user(target, True)
        await update.message.reply_text(f"🚫 حظر {target}")
    except:
        await update.message.reply_text("/ban [id]")

async def handle_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        target = int(context.args[0])
        ban_user(target, False)
        await update.message.reply_text(f"✅ رفع الحظر عن {target}")
    except:
        await update.message.reply_text("/unban [id]")

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("/broadcast [رسالة]")
        return
    msg = ' '.join(context.args)
    users = get_all_users(limit=100)
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(u['user_id'], f"📢 {msg}")
            sent += 1
        except:
            pass
    await update.message.reply_text(f"✅ تم الإرسال لـ {sent}")

async def handle_approve_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    try:
        payment_id = int(update.message.text.split("_")[1])
        result = approve_payment(payment_id)
        if result:
            await update.message.reply_text(f"✅ تمت الموافقة على #{payment_id}")
        else:
            await update.message.reply_text(f"❌ لم يتم العثور على #{payment_id}")
    except:
        await update.message.reply_text("/approve_123")
