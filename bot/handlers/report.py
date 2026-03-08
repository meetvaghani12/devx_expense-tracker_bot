from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from db import queries
from bot.keyboards.menus import back_keyboard
from utils.report_builder import format_monthly_report


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = queries.get_user_by_telegram_id(update.effective_user.id)
    if not user:
        text = "Please /start to register first."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    now = datetime.utcnow()
    year, month = now.year, now.month

    stats = queries.get_monthly_stats(year, month)
    balances = queries.get_all_balances()
    text = format_monthly_report(stats, balances, month, year)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())
