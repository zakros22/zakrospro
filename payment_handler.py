from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ContextTypes
from database import (
    create_payment, add_attempts,
    mark_payment_approved_without_adding
)
from config import (
    MASTERCARD_NUMBER, MASTERCARD_PRICE, TON_WALLET, TRC20_WALLET,
    TELEGRAM_STARS_PRICE, OWNER_ID, PAID_ATTEMPTS, OWNER_USERNAME
)


def get_payment_keyboard(user_id: int):
    keyboard = [
        [
            InlineKeyboardButton(
                f"⭐ نجوم تيليجرام ({TELEGRAM_STARS_PRICE} نجمة)",
                callback_data="pay_stars"
            )
        ],
        [
            InlineKeyboardButton(
                f"💳 ماستر كارد ({MASTERCARD_PRICE}$)",
                callback_data="pay_mastercard"
            )
        ],
        [
            InlineKeyboardButton(
                "💎 TON / USDT",
                callback_data="pay_crypto"
            )
        ],
        [
            InlineKeyboardButton(
                "🔗 احصل على محاولة مجانية بالإحالة",
                callback_data="show_referral"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def send_payment_required_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = (
        f"🔒 *انتهت محاولاتك المجانية*\n\n"
        f"لديك طريقتان للحصول على محاولات إضافية:\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 *الشراء من المالك:*\n"
        f"  ⭐ {TELEGRAM_STARS_PRICE} نجمة تيليجرام\n"
        f"  💳 {MASTERCARD_PRICE}$ ماستر كارد\n"
        f"  💎 ما يعادل 3$ USDT/TON\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔗 *الإحالة المجانية:*\n"
        f"  ادعُ أصدقاءك واحصل على محاولة مجانية\n"
        f"  لكل 10 أصدقاء يسجلون عبر رابطك\n\n"
        f"اختر ما يناسبك:"
    )

    await update.effective_message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=get_payment_keyboard(user.id)
    )


async def handle_pay_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title=f"احصل على {PAID_ATTEMPTS} محاولات",
            description=(
                f"شراء {PAID_ATTEMPTS} محاولات إضافية لتحويل محاضراتك إلى فيديو تعليمي"
            ),
            payload=f"stars_{query.from_user.id}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(f"{PAID_ATTEMPTS} محاولات", TELEGRAM_STARS_PRICE)],
        )
    except Exception as e:
        err = str(e)
        if "CURRENCY_TOTAL_AMOUNT_INVALID" in err:
            msg = (
                "❌ *خطأ في مبلغ النجوم*\n"
                "الحد الأدنى للدفع بالنجوم هو نجمة واحدة.\n"
                f"المبلغ الحالي: {TELEGRAM_STARS_PRICE} نجمة."
            )
        elif "BOT_PAYMENTS_DISABLED" in err or "payments" in err.lower():
            msg = (
                "❌ *دفع النجوم غير مفعّل حالياً*\n\n"
                "تواصل مع المالك لتفعيله أو استخدم طريقة دفع أخرى:\n"
                f"💳 ماستر كارد: {MASTERCARD_PRICE}$\n"
                f"💎 TON / USDT"
            )
        else:
            msg = (
                f"❌ *حدث خطأ أثناء إنشاء الفاتورة*\n\n"
                f"`{err}`\n\n"
                f"جرّب ماستر كارد أو تواصل مع المالك: {OWNER_USERNAME}"
            )
        try:
            await context.bot.send_message(
                chat_id=query.from_user.id,
                text=msg,
                parse_mode="Markdown",
            )
        except Exception:
            pass


async def handle_pay_mastercard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    msg = (
        f"💳 *الدفع بالماستر كارد*\n\n"
        f"📱 الرقم: `{MASTERCARD_NUMBER}`\n"
        f"💰 المبلغ: *{MASTERCARD_PRICE} ماستر*\n\n"
        f"بعد الدفع، أرسل لقطة شاشة لإثبات الدفع هنا في المحادثة، "
        f"وسيتم مراجعتها وتفعيل حسابك خلال دقائق.\n"
        f"أو تواصل مباشرة مع المالك: {OWNER_USERNAME}\n\n"
        f"🆔 ID حسابك: `{user_id}`\n"
        f"_(أرسل هذا الرقم مع لقطة الشاشة)_"
    )
    
    keyboard = [[InlineKeyboardButton("✅ أرسلت الدفع", callback_data=f"sent_mastercard_{user_id}")]]
    
    await query.edit_message_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_pay_crypto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    msg = (
        f"💎 *الدفع بالعملات الرقمية*\n\n"
        f"🔷 *TON Wallet*:\n`{TON_WALLET}`\n\n"
        f"🔵 *USDT (TRC20)*:\n`{TRC20_WALLET}`\n\n"
        f"💰 المبلغ: *3 USDT / TON*\n\n"
        f"بعد الإرسال، أرسل hash العملية هنا مع:\n"
        f"🆔 ID حسابك: `{user_id}`"
    )
    
    keyboard = [[InlineKeyboardButton("✅ أرسلت التحويل", callback_data=f"sent_crypto_{user_id}")]]
    
    await query.edit_message_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_payment_sent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if "mastercard" in data:
        method = "mastercard"
        method_name = "ماستر كارد"
        amount = MASTERCARD_PRICE
    else:
        method = "crypto"
        method_name = "تشفير"
        amount = 3.0
    
    payment_id = create_payment(user_id, method, amount)
    
    context.bot_data.setdefault('user_states', {})[user_id] = {
        'state': 'awaiting_payment_proof',
        'payment_id': payment_id
    }
    
    await query.edit_message_text(
        f"✅ *تم تسجيل طلب الدفع #{payment_id}*\n\n"
        f"الطريقة: {method_name}\n\n"
        f"📸 *الآن أرسل لقطة شاشة* أو رسالة لإثبات الدفع.\n"
        f"سيتم مراجعتها وتفعيل حسابك خلال دقائق.",
        parse_mode="Markdown"
    )
    
    try:
        user = query.from_user
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"🔔 *طلب دفع جديد*\n\n"
                f"👤 المستخدم: {user.full_name} (@{user.username})\n"
                f"🆔 ID: `{user_id}`\n"
                f"💳 الطريقة: {method_name}\n"
                f"💰 المبلغ: {amount}\n"
                f"🔢 رقم الطلب: #{payment_id}\n\n"
                f"للموافقة: /approve\\_{payment_id}\n"
                f"للإضافة المباشرة: /addattempts {user_id} {PAID_ATTEMPTS}"
            ),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Failed to notify owner: {e}")


async def handle_pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    
    payment_id = create_payment(user_id, "telegram_stars", TELEGRAM_STARS_PRICE, payment.telegram_payment_charge_id)
    new_attempts = add_attempts(user_id, PAID_ATTEMPTS)
    mark_payment_approved_without_adding(payment_id)
    
    await update.message.reply_text(
        f"🎉 *تم الدفع بنجاح!*\n\n"
        f"⭐ تم استلام {TELEGRAM_STARS_PRICE} نجمة\n"
        f"🎯 تم إضافة {PAID_ATTEMPTS} محاولات لحسابك\n"
        f"📊 رصيدك الحالي: {new_attempts} محاولة\n\n"
        f"يمكنك الآن إرسال محاضراتك!",
        parse_mode="Markdown"
    )
    
    try:
        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"💫 *دفع بالنجوم ناجح*\n\n"
                f"👤 المستخدم: {update.effective_user.full_name}\n"
                f"🆔 ID: {user_id}\n"
                f"⭐ النجوم: {TELEGRAM_STARS_PRICE}\n"
                f"🎯 المحاولات المضافة: {PAID_ATTEMPTS}"
            ),
            parse_mode="Markdown"
        )
    except Exception:
        pass
