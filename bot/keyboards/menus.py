from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import CATEGORIES


def main_menu_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("➕ Add Expense", callback_data="add_expense"),
            InlineKeyboardButton("💰 My Balance", callback_data="my_balance"),
        ],
        [
            InlineKeyboardButton("👥 All Balances", callback_data="all_balances"),
            InlineKeyboardButton("💸 Settle Up", callback_data="settle_up"),
        ],
        [
            InlineKeyboardButton("📋 History", callback_data="history"),
            InlineKeyboardButton("📊 Report", callback_data="report"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def category_keyboard():
    keyboard = []
    row = []
    for i, cat in enumerate(CATEGORIES):
        short = cat.split(" & ")[0].split(" ")[0]
        row.append(InlineKeyboardButton(cat, callback_data=f"cat_{i}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def users_keyboard(users: list, prefix: str, selected_ids: list = None, done_button: bool = False):
    """Generic user selection keyboard. prefix is callback prefix."""
    selected_ids = selected_ids or []
    keyboard = []
    row = []
    for u in users:
        uid = u["id"]
        name = u["name"]
        mark = "✅ " if uid in selected_ids else ""
        row.append(InlineKeyboardButton(f"{mark}{name}", callback_data=f"{prefix}{uid}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    if done_button:
        keyboard.append([InlineKeyboardButton("✔️ Done", callback_data="members_done")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


def split_type_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("⚖️ Equal Split", callback_data="split_equal"),
            InlineKeyboardButton("💵 Custom ₹", callback_data="split_custom"),
        ],
        [
            InlineKeyboardButton("📊 By Percentage", callback_data="split_percent"),
            InlineKeyboardButton("👥 Select Members", callback_data="split_select"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_keyboard(confirm_data: str = "confirm_expense"):
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm", callback_data=confirm_data),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def settle_actions_keyboard(transactions: list):
    """Show each suggested settlement as a button. No Back button — added by caller."""
    keyboard = []
    for i, t in enumerate(transactions):
        label = f"{t['from_name']} → {t['to_name']}: ₹{t['amount']:.2f}"
        keyboard.append([InlineKeyboardButton(f"✔️ {label}", callback_data=f"do_settle_{i}")])
    return InlineKeyboardMarkup(keyboard)


def back_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")]])
