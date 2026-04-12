import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
# ... باقي الاستيرادات
# -*- coding: utf-8 -*-
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from database import (
    create_payment, add_attempts, mark_payment_approved_without_adding
)
from config import (
    MASTERCARD_NUMBER, MASTERCARD_PRICE, TON_WALLET, TRC20_WALLET,
    TELEGRAM_STARS_PRICE, OWNER_ID, PAID_ATTEMPTS, OWNER_USERNAME
)


def get_payment_keyboard(user_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"⭐ نجوم ({TELEGRAM_STARS_PRICE})", callback_data="pay_stars")],
        [InlineKeyboardButton(f"💳 ماستر ({MASTERCARD_PRICE}$)", callback_data="pay_mastercard")],
        [InlineKeyboardButton("💎 TON/USDT", callback_data="pay_crypto")],
        [InlineKeyboardButton("🔗 إحالة مجانية", callback_data="show_referral")],
    ])


async def send_payment_required_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "🔒 *انتهت المحاولات*\n\nاختر طريقة الدفع:"
    await update.effective_message.reply_text(
        msg, parse_mode="Markdown",
        reply_markup=get_payment_keyboard(update.effective_user.id)
    )


async def handle_pay_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title=f"{PAID_ATTEMPTS} محاولات",
            description=f"{PAID_ATTEMPTS} محاولات إضافية",
            payload=f"stars_{query.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(f"{PAID_ATTEMPTS} محاولات", TELEGRAM_STARS_PRICE)],
        )
    except Exception as e:
        await query.message.reply_text(f"❌ خطأ: {e}")


async def handle_pay_mastercard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    msg = (
        f"💳 *ماستر كارد*\n\n"
        f"📱 `{MASTERCARD_NUMBER}`\n"
        f"💰 *{MASTERCARD_PRICE}$*\n\n"
        f"🆔 `{uid}`"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ أرسلت", callback_data=f"sent_mastercard_{uid}")]])
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)


async def handle_pay_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.from_user.id
    msg = (
        f"💎 *TON:* `{TON_WALLET}`\n"
        f"💎 *USDT:* `{TRC20_WALLET}`\n"
        f"💰 *3$*\n"
        f"🆔 `{uid}`"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ أرسلت", callback_data=f"sent_crypto_{uid}")]])
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=kb)


async def handle_payment_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    uid = query.from_user.id

    method = "mastercard" if "mastercard" in data else "crypto"
    amount = MASTERCARD_PRICE if method == "mastercard" else 3.0

    pid = create_payment(uid, method, amount)

    context.bot_data.setdefault('user_states', {})[uid] = {
        'state': 'awaiting_payment_proof',
        'payment_id': pid
    }

    await query.edit_message_text(
        f"✅ *طلب #{pid}*\n📸 أرسل إثبات الدفع",
        parse_mode="Markdown"
    )

    try:
        await context.bot.send_message(
            OWNER_ID,
            f"🔔 *دفع جديد*\n"
            f"👤 {query.from_user.full_name}\n"
            f"🆔 `{uid}`\n"
            f"💳 {method}\n"
            f"💰 {amount}\n"
            f"🔢 #{pid}\n"
            f"/approve_{pid}",
            parse_mode="Markdown"
        )
    except:
        pass


async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    uid = update.effective_user.id

    pid = create_payment(uid, "telegram_stars", TELEGRAM_STARS_PRICE, payment.telegram_payment_charge_id)
    new_attempts = add_attempts(uid, PAID_ATTEMPTS)
    mark_payment_approved_without_adding(pid)

    await update.message.reply_text(
        f"🎉 *تم الدفع!*\n"
        f"⭐ {TELEGRAM_STARS_PRICE} نجمة\n"
        f"🎯 +{PAID_ATTEMPTS} محاولات\n"
        f"📊 {new_attempts}",
        parse_mode="Markdown"
    )
