import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from db import queries
from bot.states import (
    ADD_AMOUNT, ADD_DESCRIPTION, ADD_CATEGORY, ADD_CATEGORY_CUSTOM,
    ADD_PAID_BY, ADD_SPLIT_TYPE, ADD_MEMBERS, ADD_CUSTOM_AMOUNTS,
    ADD_CUSTOM_PERCENT, CONFIRM_EXPENSE,
)
from bot.keyboards.menus import (
    category_keyboard, users_keyboard, split_type_keyboard, confirm_keyboard, back_keyboard
)
from bot.notifications import notify_expense_added
from utils.split_calculator import (
    calculate_equal_split, calculate_custom_amount_split, calculate_percentage_split
)
from utils.report_builder import format_expense_added
from config import CATEGORIES

logger = logging.getLogger(__name__)


def _get_or_require_user(update: Update):
    tg_id = update.effective_user.id
    return queries.get_user_by_telegram_id(tg_id)


async def start_add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _get_or_require_user(update)
    if not user:
        text = "Please /start to register first."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["adding"] = {}

    text = "💰 *Add Expense*\n\nEnter the total amount (e.g. 500 or 1250.50):"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")
    return ADD_AMOUNT


async def got_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        # If it looks like a natural-language sentence, escape the guided flow and
        # run the NL pipeline instead (user probably typed "I paid 500 for dinner…")
        if len(text.split()) > 2:
            context.user_data.clear()
            from bot.handlers.nl import process_nl_text
            try:
                await process_nl_text(update.message.text.strip(), update, context)
            except Exception:
                pass  # process_nl_text already shows the error to the user
            return ConversationHandler.END
        await update.message.reply_text("❌ Please enter a valid positive number (e.g. 500 or 1250.50):")
        return ADD_AMOUNT

    context.user_data["adding"]["amount"] = amount
    await update.message.reply_text("📝 Enter a description for this expense:")
    return ADD_DESCRIPTION


async def got_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    if len(desc) < 2:
        await update.message.reply_text("Please enter a description (at least 2 characters):")
        return ADD_DESCRIPTION

    context.user_data["adding"]["description"] = desc
    await update.message.reply_text(
        "🏷️ Select a category:",
        reply_markup=category_keyboard(),
    )
    return ADD_CATEGORY


async def got_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    if query.data == f"cat_{len(CATEGORIES)-1}":  # "Other"
        await query.edit_message_text("✏️ Enter your custom category name:")
        return ADD_CATEGORY_CUSTOM

    idx = int(query.data.replace("cat_", ""))
    context.user_data["adding"]["category"] = CATEGORIES[idx]
    return await _ask_paid_by(query, context)


async def got_custom_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat = update.message.text.strip()
    context.user_data["adding"]["category"] = cat
    # Need to show users keyboard via message
    users = queries.get_all_users()
    context.user_data["all_users"] = users
    await update.message.reply_text(
        "👤 Who paid?",
        reply_markup=users_keyboard(users, prefix="paid_"),
    )
    return ADD_PAID_BY


async def _ask_paid_by(query_or_msg, context):
    users = queries.get_all_users()
    context.user_data["all_users"] = users
    await query_or_msg.edit_message_text(
        "👤 Who paid for this expense?",
        reply_markup=users_keyboard(users, prefix="paid_"),
    )
    return ADD_PAID_BY


async def got_paid_by(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    paid_by_id = query.data.replace("paid_", "")
    context.user_data["adding"]["paid_by_id"] = paid_by_id

    users = context.user_data.get("all_users", queries.get_all_users())
    payer = next((u for u in users if u["id"] == paid_by_id), None)
    context.user_data["adding"]["paid_by_name"] = payer["name"] if payer else "Unknown"

    await query.edit_message_text(
        "⚖️ How should the expense be split?",
        reply_markup=split_type_keyboard(),
    )
    return ADD_SPLIT_TYPE


async def got_split_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        context.user_data.clear()
        await query.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    split_type = query.data.replace("split_", "")
    context.user_data["adding"]["split_type"] = split_type

    users = context.user_data.get("all_users", queries.get_all_users())
    paid_by_id = context.user_data["adding"]["paid_by_id"]

    if split_type == "equal":
        # Auto include all except payer, but let user deselect
        other_users = [u for u in users if u["id"] != paid_by_id]
        selected = [u["id"] for u in other_users]
        context.user_data["adding"]["selected_members"] = selected
        context.user_data["adding"]["split_type"] = "equal"
        await query.edit_message_text(
            "👥 *Equal Split* — Select who's splitting (toggle to include/exclude):\n\n"
            "✅ = included | Tap to toggle | Tap ✔️ Done when ready",
            parse_mode="Markdown",
            reply_markup=users_keyboard(other_users, prefix="member_", selected_ids=selected, done_button=True),
        )
        context.user_data["adding"]["_member_pool"] = other_users
        return ADD_MEMBERS

    elif split_type in ("custom", "percent", "select"):
        all_except_payer = [u for u in users if u["id"] != paid_by_id]
        selected = []
        context.user_data["adding"]["selected_members"] = selected
        context.user_data["adding"]["_member_pool"] = all_except_payer
        await query.edit_message_text(
            f"👥 Select members for this expense:\n\n"
            f"✅ = selected | Tap to toggle | Tap ✔️ Done when ready",
            reply_markup=users_keyboard(all_except_payer, prefix="member_", selected_ids=selected, done_button=True),
        )
        return ADD_MEMBERS

    return ConversationHandler.END


async def toggle_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = query.data.replace("member_", "")
    selected = context.user_data["adding"].setdefault("selected_members", [])

    if uid in selected:
        selected.remove(uid)
    else:
        selected.append(uid)

    member_pool = context.user_data["adding"]["_member_pool"]
    await query.edit_message_reply_markup(
        reply_markup=users_keyboard(member_pool, prefix="member_", selected_ids=selected, done_button=True)
    )
    return ADD_MEMBERS


async def members_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected = context.user_data["adding"].get("selected_members", [])
    if not selected:
        await query.answer("⚠️ Select at least one member!", show_alert=True)
        return ADD_MEMBERS

    split_type = context.user_data["adding"]["split_type"]
    amount = context.user_data["adding"]["amount"]
    all_users = context.user_data.get("all_users", queries.get_all_users())
    selected_users = [u for u in all_users if u["id"] in selected]
    context.user_data["adding"]["selected_user_objects"] = selected_users

    if split_type == "equal":
        return await _finalize_equal_split(query, context, selected_users, amount)

    elif split_type == "custom":
        names = ", ".join(u["name"] for u in selected_users)
        await query.edit_message_text(
            f"💵 Enter the amount each person owes (comma-separated):\n\n"
            f"*Order:* {names}\n"
            f"*Total:* ₹{amount:.2f}\n\n"
            f"Example: `300, 400, 200`",
            parse_mode="Markdown",
        )
        return ADD_CUSTOM_AMOUNTS

    elif split_type == "percent":
        names = ", ".join(u["name"] for u in selected_users)
        await query.edit_message_text(
            f"📊 Enter percentage for each person (comma-separated, must sum to 100):\n\n"
            f"*Order:* {names}\n"
            f"*Total:* ₹{amount:.2f}\n\n"
            f"Example: `33, 33, 34`",
            parse_mode="Markdown",
        )
        return ADD_CUSTOM_PERCENT

    elif split_type == "select":
        # Equal among selected
        return await _finalize_equal_split(query, context, selected_users, amount)

    return ConversationHandler.END


async def _finalize_equal_split(query_or_update, context, selected_users, amount):
    splits = calculate_equal_split(amount, [u["id"] for u in selected_users])
    context.user_data["adding"]["splits"] = splits
    return await _show_confirm(query_or_update, context)


async def got_custom_amounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    selected_users = context.user_data["adding"]["selected_user_objects"]
    amount = context.user_data["adding"]["amount"]

    try:
        parts = [float(p.strip().replace(",", "")) for p in text.split(",")]
        if len(parts) != len(selected_users):
            raise ValueError(f"Expected {len(selected_users)} values, got {len(parts)}")
        total_split = sum(parts)
        if abs(total_split - amount) > 0.5:
            await update.message.reply_text(
                f"❌ The amounts sum to ₹{total_split:.2f} but the total is ₹{amount:.2f}.\n"
                f"Please re-enter (difference allowed: ₹0.50):"
            )
            return ADD_CUSTOM_AMOUNTS
    except ValueError as e:
        await update.message.reply_text(f"❌ Invalid input: {e}\nPlease try again:")
        return ADD_CUSTOM_AMOUNTS

    amounts_dict = {selected_users[i]["id"]: parts[i] for i in range(len(selected_users))}
    splits = calculate_custom_amount_split(amounts_dict)
    context.user_data["adding"]["splits"] = splits
    return await _show_confirm_message(update, context)


async def got_custom_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    selected_users = context.user_data["adding"]["selected_user_objects"]
    amount = context.user_data["adding"]["amount"]

    try:
        parts = [float(p.strip()) for p in text.split(",")]
        if len(parts) != len(selected_users):
            raise ValueError(f"Expected {len(selected_users)} values, got {len(parts)}")
        total_pct = sum(parts)
        if abs(total_pct - 100) > 0.5:
            await update.message.reply_text(
                f"❌ Percentages sum to {total_pct:.1f}%, must be 100%.\nPlease re-enter:"
            )
            return ADD_CUSTOM_PERCENT
    except ValueError as e:
        await update.message.reply_text(f"❌ Invalid input: {e}\nPlease try again:")
        return ADD_CUSTOM_PERCENT

    percentages = {selected_users[i]["id"]: parts[i] for i in range(len(selected_users))}
    splits = calculate_percentage_split(amount, percentages)
    context.user_data["adding"]["splits"] = splits
    return await _show_confirm_message(update, context)


async def _show_confirm(query, context):
    """Called when we have a callback_query (inline keyboard flow)."""
    data = context.user_data["adding"]
    amount = data["amount"]
    desc = data["description"]
    category = data["category"]
    payer_name = data["paid_by_name"]
    splits = data["splits"]
    all_users = context.user_data.get("all_users", queries.get_all_users())
    users_dict = {u["id"]: u for u in all_users}

    lines = [
        f"📋 *Confirm Expense*\n",
        f"📝 {desc}",
        f"💰 ₹{amount:.2f}",
        f"🏷️ {category}",
        f"👤 Paid by: *{payer_name}*\n",
        "*Split:*",
    ]
    for s in splits:
        name = users_dict.get(s["user_id"], {}).get("name", "Unknown")
        lines.append(f"  • {name}: ₹{s['amount_owed']:.2f}")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=confirm_keyboard(),
    )
    return CONFIRM_EXPENSE


async def _show_confirm_message(update, context):
    """Called when we have a message (text input flow)."""
    data = context.user_data["adding"]
    amount = data["amount"]
    desc = data["description"]
    category = data["category"]
    payer_name = data["paid_by_name"]
    splits = data["splits"]
    all_users = context.user_data.get("all_users", queries.get_all_users())
    users_dict = {u["id"]: u for u in all_users}

    lines = [
        f"📋 *Confirm Expense*\n",
        f"📝 {desc}",
        f"💰 ₹{amount:.2f}",
        f"🏷️ {category}",
        f"👤 Paid by: *{payer_name}*\n",
        "*Split:*",
    ]
    for s in splits:
        name = users_dict.get(s["user_id"], {}).get("name", "Unknown")
        lines.append(f"  • {name}: ₹{s['amount_owed']:.2f}")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=confirm_keyboard(),
    )
    return CONFIRM_EXPENSE


async def confirm_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = context.user_data["adding"]
    expense = queries.add_expense(
        description=data["description"],
        amount=data["amount"],
        category=data["category"],
        paid_by_id=data["paid_by_id"],
        splits=data["splits"],
        note=data.get("note"),
    )

    # Fetch full expense with splits for notification
    exp_full, splits_full = queries.get_expense_with_splits(expense["id"])

    await query.edit_message_text(
        f"✅ *Expense saved!*\n\n"
        f"_{data['description']}_ — ₹{data['amount']:.2f}\n\n"
        f"Notifying all involved members...",
        parse_mode="Markdown",
    )

    # Notify all debtors
    await notify_expense_added(
        bot=context.bot,
        expense=expense,
        payer_name=data["paid_by_name"],
        splits=splits_full,
    )

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("❌ Expense cancelled.")
    return ConversationHandler.END
