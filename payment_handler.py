#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from database import add_attempts
from config import MASTERCARD_NUMBER, MASTERCARD_PRICE, TON_WALLET, TRC20_WALLET, TELEGRAM_STARS_PRICE, OWNER_ID, PAID_ATTEMPTS

def get_payment_keyboard(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ نجوم ({TELEGRAM_STARS_PRICE})", callback_data="pay_stars")],
        [InlineKeyboardButton(f"💳 ماستر ({MASTERCARD_PRICE}$)", callback_data="pay_mastercard")],
        [InlineKeyboardButton("💎 TON/USDT", callback_data="pay_crypto")],
        [InlineKeyboardButton("🔗 إحالة مجانية", callback_data="show_referral")],
    ])

async def send_payment_required_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "🔒 *انتهت محاولاتك*\nاختر طريقة الدفع:",
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard(update.effective_user.id)
    )

async def handle_pay_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await context.bot.send_invoice(
        chat_id=q.from_user.id,
        title=f"{PAID_ATTEMPTS} محاولات",
        description=f"شراء {PAID_ATTEMPTS} محاولات",
        payload=f"stars_{q.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(f"{PAID_ATTEMPTS} محاولات", TELEGRAM_STARS_PRICE)]
    )

async def handle_pay_mastercard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        f"💳 *ماستر كارد*\n📱 `{MASTERCARD_NUMBER}`\n💰 *{MASTERCARD_PRICE}$*\n\nأرسل لقطة بعد الدفع",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ أرسلت", callback_data=f"sent_mastercard_{q.from_user.id}")
        ]])
    )

async def handle_pay_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        f"💎 *عملات*\n🔷 TON: `{TON_WALLET}`\n🔵 USDT: `{TRC20_WALLET}`\n💰 *3$*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ أرسلت", callback_data=f"sent_crypto_{q.from_user.id}")
        ]])
    )

async def handle_payment_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("✅ *تم التسجيل*\n📸 أرسل لقطة الإثبات", parse_mode="Markdown")
    await context.bot.send_message(OWNER_ID, f"🔔 طلب دفع من {q.from_user.full_name}")

async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)

async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    add_attempts(uid, PAID_ATTEMPTS)
    await update.message.reply_text(f"🎉 تمت إضافة {PAID_ATTEMPTS} محاولات!")
