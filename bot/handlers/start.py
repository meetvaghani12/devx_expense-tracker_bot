from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from db import queries
from bot.states import REGISTER_NAME, REGISTER_EMAIL
from bot.keyboards.menus import main_menu_keyboard


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = queries.get_user_by_telegram_id(user.id)

    if existing:
        await update.message.reply_text(
            f"👋 Welcome back, *{existing['name']}*!\n\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 Welcome to *SplitBot*!\n\nI help your group track shared expenses.\n\nWhat's your name?",
        parse_mode="Markdown",
    )
    return REGISTER_NAME


async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Please enter a valid name (at least 2 characters).")
        return REGISTER_NAME
    context.user_data["reg_name"] = name
    await update.message.reply_text(f"Nice to meet you, *{name}*! 😊\n\nWhat's your email address? (for notifications)", parse_mode="Markdown")
    return REGISTER_EMAIL


async def register_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip().lower()
    if "@" not in email or "." not in email:
        await update.message.reply_text("Please enter a valid email address.")
        return REGISTER_EMAIL

    user = update.effective_user
    name = context.user_data.pop("reg_name", user.first_name)

    new_user = queries.create_user(
        telegram_id=user.id,
        username=user.username or "",
        name=name,
        email=email,
    )

    await update.message.reply_text(
        f"✅ You're registered, *{name}*!\n\nUse the menu below to get started.",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu — /menu command or callback."""
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            "🏠 *Main Menu*\n\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update.message.reply_text(
            "🏠 *Main Menu*\n\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=main_menu_keyboard(),
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer("Cancelled.")
        await update.callback_query.edit_message_text(
            "❌ Action cancelled.\n\nUse /menu to return to the main menu.",
        )
    else:
        await update.message.reply_text("❌ Action cancelled. Use /menu to return to the main menu.")
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 *SplitBot Help*\n\n"
        "*Commands:*\n"
        "/start — Register / Welcome\n"
        "/menu — Show main menu\n"
        "/add — Add a new expense\n"
        "/balance — Your current balance\n"
        "/balanceall — Everyone's balance\n"
        "/history — Recent transactions\n"
        "/settle — Settle up debts\n"
        "/report — Monthly report\n"
        "/cancel — Cancel current action\n"
        "/help — This message\n\n"
        "*Tips:*\n"
        "• Use buttons for guided flow\n"
        "• Equal split is fastest\n"
        "• Custom split: enter amounts as comma-separated values"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
