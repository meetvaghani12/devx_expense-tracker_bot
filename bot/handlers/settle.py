import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from db import queries
from bot.states import SETTLE_ENTER_AMOUNT
from bot.keyboards.menus import back_keyboard, settle_actions_keyboard
from bot.notifications import notify_settlement
from utils.split_calculator import simplify_debts
from utils.report_builder import format_settle_suggestions

logger = logging.getLogger(__name__)


async def settle_up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point — show simplified debt suggestions."""
    tg_id = update.effective_user.id
    user = queries.get_user_by_telegram_id(tg_id)

    if not user:
        text = "Please /start to register first."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    debts = queries.get_pairwise_debts()
    all_users = queries.get_all_users()

    transactions = simplify_debts(debts, {u["id"]: u for u in all_users})
    # Store in user_data so do_settle can access them via index
    context.user_data["settle_transactions"] = transactions

    summary_text = format_settle_suggestions(transactions)

    if not transactions:
        kb = back_keyboard()
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(summary_text, reply_markup=kb)
        else:
            await update.message.reply_text(summary_text, reply_markup=kb)
        return

    keyboard = settle_actions_keyboard(transactions)
    full_keyboard = InlineKeyboardMarkup(
        list(keyboard.inline_keyboard)
        + [[InlineKeyboardButton("✏️ Manual Settle", callback_data="manual_settle")]]
        + [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
    )
    text = summary_text + "\n\n_Tap a settlement to mark it as done, or use Manual Settle._"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=full_keyboard)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=full_keyboard)


async def do_settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mark a suggested settlement as done, then show remaining ones."""
    query = update.callback_query
    await query.answer()

    idx = int(query.data.replace("do_settle_", ""))

    # Always re-fetch fresh transactions — never rely on stale user_data
    debts = queries.get_pairwise_debts()
    all_users = queries.get_all_users()
    transactions = simplify_debts(debts, {u["id"]: u for u in all_users})

    if idx >= len(transactions):
        await query.edit_message_text("❌ Settlement not found. Use /settle to refresh.")
        return

    t = transactions[idx]
    payer_id = t["from"]
    receiver_id = t["to"]
    amount = t["amount"]

    receiver_user = queries.get_user_by_id(receiver_id)
    if not receiver_user:
        await query.edit_message_text("❌ User not found.")
        return

    queries.settle_between(payer_id, receiver_id, amount, method="auto")
    logger.info(f"Settlement recorded: {t['from_name']} → {t['to_name']} ₹{amount}")

    # Notify receiver
    await notify_settlement(bot=context.bot, payer_name=t["from_name"], receiver=receiver_user, amount=amount)

    # Re-fetch remaining debts and show them immediately
    remaining_debts = queries.get_pairwise_debts()
    remaining = simplify_debts(remaining_debts, {u["id"]: u for u in all_users})
    context.user_data["settle_transactions"] = remaining

    if not remaining:
        await query.edit_message_text(
            f"✅ *Settlement Recorded!*\n\n"
            f"*{t['from_name']}* paid *₹{amount:.2f}* to *{t['to_name']}*\n\n"
            f"🎉 All debts are settled!",
            parse_mode="Markdown",
            reply_markup=back_keyboard(),
        )
    else:
        # Show next settlements without making user press Settle Up again
        summary = format_settle_suggestions(remaining)
        kb = settle_actions_keyboard(remaining)
        full_keyboard = InlineKeyboardMarkup(
            list(kb.inline_keyboard)
            + [[InlineKeyboardButton("✏️ Manual Settle", callback_data="manual_settle")]]
            + [[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]
        )
        await query.edit_message_text(
            f"✅ *Settled:* {t['from_name']} → {t['to_name']} ₹{amount:.2f}\n\n"
            f"📋 *Remaining:*\n{summary}\n\n"
            f"_Tap to settle next or go back._",
            parse_mode="Markdown",
            reply_markup=full_keyboard,
        )


async def manual_settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show list of users to pay."""
    query = update.callback_query
    await query.answer()

    tg_id = update.effective_user.id
    current_user = queries.get_user_by_telegram_id(tg_id)
    if not current_user:
        await query.edit_message_text("Please /start first.")
        return

    all_users = queries.get_all_users()
    others = [u for u in all_users if u["id"] != current_user["id"]]
    context.user_data["settle_payer_id"] = current_user["id"]
    context.user_data["settle_payer_name"] = current_user["name"]

    keyboard = []
    row = []
    for u in others:
        row.append(InlineKeyboardButton(u["name"], callback_data=f"settle_recv_{u['id']}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="back_main")])

    await query.edit_message_text(
        f"✏️ *Manual Settle*\n\n{current_user['name']}, who are you paying?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def settle_select_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User picked who they're paying — ask for amount via text."""
    query = update.callback_query
    await query.answer()

    receiver_id = query.data.replace("settle_recv_", "")
    receiver = queries.get_user_by_id(receiver_id)
    context.user_data["settle_receiver_id"] = receiver_id
    context.user_data["settle_receiver_name"] = receiver["name"] if receiver else "Unknown"

    await query.edit_message_text(
        f"💵 How much are you paying *{context.user_data['settle_receiver_name']}*?\n\nEnter amount:",
        parse_mode="Markdown",
    )
    return SETTLE_ENTER_AMOUNT


async def settle_enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive text amount and show confirmation."""
    text = update.message.text.strip().replace(",", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Enter a valid positive amount:")
        return SETTLE_ENTER_AMOUNT

    payer_name = context.user_data.get("settle_payer_name", "")
    receiver_name = context.user_data.get("settle_receiver_name", "")
    context.user_data["settle_amount"] = amount

    await update.message.reply_text(
        f"📋 *Confirm Settlement*\n\n"
        f"*{payer_name}* pays *₹{amount:.2f}* to *{receiver_name}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Confirm", callback_data="confirm_manual_settle"),
            InlineKeyboardButton("❌ Cancel", callback_data="back_main"),
        ]]),
    )
    return ConversationHandler.END


async def confirm_manual_settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Final confirmation — record the manual settlement."""
    query = update.callback_query
    await query.answer()

    payer_id = context.user_data.get("settle_payer_id")
    receiver_id = context.user_data.get("settle_receiver_id")
    amount = context.user_data.get("settle_amount")
    payer_name = context.user_data.get("settle_payer_name", "")
    receiver_name = context.user_data.get("settle_receiver_name", "")

    if not all([payer_id, receiver_id, amount]):
        await query.edit_message_text("❌ Session expired. Please use /settle again.")
        return

    queries.settle_between(payer_id, receiver_id, amount, method="manual")
    receiver_user = queries.get_user_by_id(receiver_id)
    logger.info(f"Manual settlement: {payer_name} → {receiver_name} ₹{amount}")

    await query.edit_message_text(
        f"✅ *Settlement Recorded!*\n\n"
        f"*{payer_name}* paid *₹{amount:.2f}* to *{receiver_name}*",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )
    await notify_settlement(bot=context.bot, payer_name=payer_name, receiver=receiver_user, amount=amount)

    for key in ["settle_payer_id", "settle_payer_name", "settle_receiver_id", "settle_receiver_name", "settle_amount"]:
        context.user_data.pop(key, None)
