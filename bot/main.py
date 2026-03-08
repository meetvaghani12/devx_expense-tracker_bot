import logging
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)
from config import TELEGRAM_BOT_TOKEN
from bot.states import (
    REGISTER_NAME, REGISTER_EMAIL,
    ADD_AMOUNT, ADD_DESCRIPTION, ADD_CATEGORY, ADD_CATEGORY_CUSTOM,
    ADD_PAID_BY, ADD_SPLIT_TYPE, ADD_MEMBERS, ADD_CUSTOM_AMOUNTS,
    ADD_CUSTOM_PERCENT, CONFIRM_EXPENSE,
    SETTLE_ENTER_AMOUNT,
)
from bot.handlers.start import start, register_name, register_email, menu, cancel, help_command
from bot.handlers.expense import (
    start_add_expense, got_amount, got_description, got_category, got_custom_category,
    got_paid_by, got_split_type, toggle_member, members_done,
    got_custom_amounts, got_custom_percent, confirm_expense, cancel_expense,
)
from bot.handlers.balance import my_balance, all_balances, history
from bot.handlers.settle import (
    settle_up, do_settle, manual_settle,
    settle_select_receiver, settle_enter_amount, confirm_manual_settle,
)
from bot.handlers.report import report
from scheduler.jobs import setup_jobs

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # ── Registration conversation ─────────────────────────────────────────────
    reg_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            REGISTER_EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_email)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Add Expense conversation ───────────────────────────────────────────────
    expense_conv = ConversationHandler(
        per_message=False,
        entry_points=[
            CommandHandler("add", start_add_expense),
            CallbackQueryHandler(start_add_expense, pattern="^add_expense$"),
        ],
        states={
            ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_amount)],
            ADD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_description)],
            ADD_CATEGORY: [
                CallbackQueryHandler(got_category, pattern="^cat_"),
                CallbackQueryHandler(cancel_expense, pattern="^cancel$"),
            ],
            ADD_CATEGORY_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_custom_category)],
            ADD_PAID_BY: [
                CallbackQueryHandler(got_paid_by, pattern="^paid_"),
                CallbackQueryHandler(cancel_expense, pattern="^cancel$"),
            ],
            ADD_SPLIT_TYPE: [
                CallbackQueryHandler(got_split_type, pattern="^split_"),
                CallbackQueryHandler(cancel_expense, pattern="^cancel$"),
            ],
            ADD_MEMBERS: [
                CallbackQueryHandler(toggle_member, pattern="^member_"),
                CallbackQueryHandler(members_done, pattern="^members_done$"),
                CallbackQueryHandler(cancel_expense, pattern="^cancel$"),
            ],
            ADD_CUSTOM_AMOUNTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_custom_amounts)],
            ADD_CUSTOM_PERCENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, got_custom_percent)],
            CONFIRM_EXPENSE: [
                CallbackQueryHandler(confirm_expense, pattern="^confirm_expense$"),
                CallbackQueryHandler(cancel_expense, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel_expense, pattern="^cancel$"),
        ],
        allow_reentry=True,
    )

    # ── Manual settle amount — only text input step needs ConversationHandler ──
    manual_settle_conv = ConversationHandler(
        per_message=False,
        entry_points=[CallbackQueryHandler(settle_select_receiver, pattern="^settle_recv_")],
        states={
            SETTLE_ENTER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, settle_enter_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    # ── Register all handlers ─────────────────────────────────────────────────
    app.add_handler(reg_conv)
    app.add_handler(expense_conv)
    app.add_handler(manual_settle_conv)

    # Simple commands
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settle", settle_up))
    app.add_handler(CommandHandler("balance", my_balance))
    app.add_handler(CommandHandler("balanceall", all_balances))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("cancel", cancel))

    # ── Settle callbacks — direct handlers, no ConversationHandler ────────────
    app.add_handler(CallbackQueryHandler(settle_up, pattern="^settle_up$"))
    app.add_handler(CallbackQueryHandler(do_settle, pattern="^do_settle_"))
    app.add_handler(CallbackQueryHandler(manual_settle, pattern="^manual_settle$"))
    app.add_handler(CallbackQueryHandler(confirm_manual_settle, pattern="^confirm_manual_settle$"))

    # Callback queries for main menu buttons
    app.add_handler(CallbackQueryHandler(my_balance, pattern="^my_balance$"))
    app.add_handler(CallbackQueryHandler(all_balances, pattern="^all_balances$"))
    app.add_handler(CallbackQueryHandler(history, pattern="^history$"))
    app.add_handler(CallbackQueryHandler(report, pattern="^report$"))
    app.add_handler(CallbackQueryHandler(menu, pattern="^back_main$"))

    # Setup scheduled jobs
    setup_jobs(app)

    return app


def main():
    app = build_application()
    logger.info("SplitBot started. Polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
