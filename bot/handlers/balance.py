from telegram import Update
from telegram.ext import ContextTypes
from db import queries
from bot.keyboards.menus import back_keyboard
from utils.report_builder import format_balance_summary, format_expense_history


async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    balances = queries.get_all_balances()
    my = balances.get(user["id"])

    if not my:
        text = "No expense data found yet."
    else:
        net = my["net"]
        if abs(net) < 0.01:
            text = f"✅ *{user['name']}*, you're all settled up! Nothing owed."
        elif net > 0:
            text = f"🟢 *{user['name']}*, you are owed *₹{net:.2f}*"
        else:
            text = f"🔴 *{user['name']}*, you owe *₹{abs(net):.2f}*"

        # Show who owes what to this user
        debts = queries.get_pairwise_debts()
        uid = user["id"]
        all_users = queries.get_all_users()
        users_dict = {u["id"]: u["name"] for u in all_users}

        owed_by = [(d["from"], d["amount"]) for d in debts if d["to"] == uid]
        owe_to = [(d["to"], d["amount"]) for d in debts if d["from"] == uid]

        if owed_by:
            text += "\n\n*People who owe you:*"
            for from_id, amt in owed_by:
                text += f"\n  • {users_dict.get(from_id, '?')}: ₹{amt:.2f}"
        if owe_to:
            text += "\n\n*You owe:*"
            for to_id, amt in owe_to:
                text += f"\n  • {users_dict.get(to_id, '?')}: ₹{amt:.2f}"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())


async def all_balances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = queries.get_user_by_telegram_id(update.effective_user.id)
    if not user:
        text = "Please /start to register first."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    balances = queries.get_all_balances()
    text = format_balance_summary(balances)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = queries.get_user_by_telegram_id(update.effective_user.id)
    if not user:
        text = "Please /start to register first."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    expenses = queries.get_recent_expenses(limit=10)
    text = format_expense_history(expenses)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=back_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=back_keyboard())
