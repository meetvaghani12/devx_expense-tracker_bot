"""
Natural Language handler — catches free-text messages and processes them
through the two-agent pipeline (Intent Parser → Operations Executor).
Also handles all NL confirmation/disambiguation callbacks.
"""
import logging
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db import queries
from bot.keyboards.menus import main_menu_keyboard
from bot.notifications import notify_expense_added, notify_settlement
from ai.intent_parser import parse_intent, IntentParseError
from ai.ops_executor import execute_intent, ConfirmationPayload, AmbiguityRequest, ExecutorError
from config import NL_CONFIDENCE_THRESHOLD

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


# ─── User cache (5-minute TTL) ────────────────────────────────────────────────

def _get_cached_users(context) -> list:
    cache = context.bot_data.get("users_cache")
    if cache and (time.time() - cache["ts"]) < 300:
        return cache["data"]
    users = queries.get_all_users()
    context.bot_data["users_cache"] = {"data": users, "ts": time.time()}
    return users


# ─── Main NL text handler ─────────────────────────────────────────────────────

async def handle_natural_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch-all text handler — registered last in main.py so ConversationHandlers take priority."""
    # Skip if user is mid-button flow (belt-and-suspenders)
    if context.user_data.get("adding") or context.user_data.get("settle_payer_id"):
        return

    text = (update.message.text or "").strip()
    if not text or text.startswith("/"):
        return

    try:
        await process_nl_text(text, update, context)
    except Exception as e:
        logger.error(f"NL pipeline failed for text: {e}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ NL error: `{type(e).__name__}: {e}`",
            parse_mode="Markdown",
        )


async def process_nl_text(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Core NL pipeline — called by both text handler and voice handler."""
    try:
        await _process_nl_text_inner(text, update, context)
    except Exception as e:
        logger.error(f"process_nl_text crashed: {e}", exc_info=True)
        await update.message.reply_text(
            f"⚠️ Error: `{type(e).__name__}: {e}`",
            parse_mode="Markdown",
        )


async def _process_nl_text_inner(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = queries.get_user_by_telegram_id(update.effective_user.id)
    if not user:
        await update.message.reply_text("Please /start to register first.")
        return

    all_users = _get_cached_users(context)
    date_iso = datetime.now(IST).date().isoformat()

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        intent_result = await parse_intent(
            raw_text=text,
            sender_name=user["name"],
            known_users=all_users,
            date_iso=date_iso,
        )
    except IntentParseError as e:
        logger.warning(f"NL parse failed: {e}")
        await update.message.reply_text(f"⚠️ Parse error: `{e}`", parse_mode="Markdown")
        return

    intent = intent_result.get("intent", "unknown")
    confidence = intent_result.get("confidence", 0)

    if intent == "check_balance":
        from bot.handlers.balance import my_balance
        await my_balance(update, context)
        return

    if intent == "check_history":
        from bot.handlers.balance import history
        await history(update, context)
        return

    if intent == "unknown" or confidence < NL_CONFIDENCE_THRESHOLD:
        await _fallback_low_confidence(update, intent_result)
        return

    unresolved = intent_result.get("unresolved_names", [])
    if unresolved:
        known = ", ".join(u["name"] for u in all_users)
        await update.message.reply_text(
            f"I don't know: *{', '.join(unresolved)}*\n\n"
            f"Known members: {known}\n\nPlease try again with the correct name.",
            parse_mode="Markdown",
        )
        return

    try:
        result = execute_intent(intent_result, user, all_users)
    except ExecutorError as e:
        await update.message.reply_text(f"❌ {e.user_message}\n\nUse /add for the guided flow.")
        return
    except Exception as e:
        logger.error(f"Unexpected executor error: {e}", exc_info=True)
        await update.message.reply_text(f"⚠️ Error: `{type(e).__name__}: {e}`", parse_mode="Markdown")
        return

    if isinstance(result, AmbiguityRequest):
        await _send_disambiguation(update, context, result)
        return

    await _send_confirmation(update, context, result)


# ─── Confirmation flow ────────────────────────────────────────────────────────

async def _send_confirmation(update_or_query, context, payload: ConfirmationPayload, edit=False):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Confirm", callback_data=payload.confirm_callback),
            InlineKeyboardButton("❌ Cancel", callback_data="nl_cancel"),
        ],
        [InlineKeyboardButton("✏️ Use guided flow instead", callback_data="add_expense")],
    ])
    context.user_data["nl_pending"] = payload

    if edit and hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(
            payload.display_text, parse_mode="Markdown", reply_markup=keyboard
        )
    else:
        msg = update_or_query.message if hasattr(update_or_query, "message") else update_or_query
        await msg.reply_text(payload.display_text, parse_mode="Markdown", reply_markup=keyboard)


async def nl_confirm_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    payload: ConfirmationPayload = context.user_data.pop("nl_pending", None)
    if not payload:
        await query.edit_message_text("❌ Session expired. Please try again.")
        return

    db = payload.db_payload
    expense = queries.add_expense(
        description=db["description"],
        amount=db["amount"],
        category=db["category"],
        paid_by_id=db["paid_by_id"],
        splits=db["splits"],
    )

    exp_full, splits_full = queries.get_expense_with_splits(expense["id"])

    await query.edit_message_text(
        f"✅ *Expense saved!*\n\n"
        f"_{db['description']}_ — ₹{db['amount']:.2f}\n\n"
        f"Notifying everyone involved...",
        parse_mode="Markdown",
    )

    await notify_expense_added(
        bot=context.bot,
        expense=expense,
        payer_name=db["paid_by_name"],
        splits=splits_full,
    )


async def nl_confirm_settle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    payload: ConfirmationPayload = context.user_data.pop("nl_pending", None)
    if not payload:
        await query.edit_message_text("❌ Session expired. Please try again.")
        return

    db = payload.db_payload
    queries.settle_between(db["payer_id"], db["receiver_id"], db["amount"], method=db["method"])

    receiver_user = queries.get_user_by_id(db["receiver_id"])
    await query.edit_message_text(
        f"✅ *Settlement recorded!*\n\n"
        f"*{db['payer_name']}* paid ₹{db['amount']:.2f} to *{db['receiver_name']}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")]]),
    )
    await notify_settlement(bot=context.bot, payer_name=db["payer_name"], receiver=receiver_user, amount=db["amount"])


async def nl_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("nl_pending", None)
    context.user_data.pop("nl_disambig", None)
    await query.edit_message_text(
        "Cancelled.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="back_main")]]),
    )


# ─── Disambiguation flow ──────────────────────────────────────────────────────

async def _send_disambiguation(update, context, req: AmbiguityRequest):
    context.user_data["nl_disambig"] = req

    buttons = [
        [InlineKeyboardButton(u["name"], callback_data=f"nl_disambig_{u['id']}")]
        for u in req.candidates
    ]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="nl_cancel")])

    await update.message.reply_text(
        f"I found multiple people matching *{req.ambiguous_name}*. Which one?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def nl_disambiguate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    req: AmbiguityRequest = context.user_data.pop("nl_disambig", None)
    if not req:
        await query.edit_message_text("❌ Session expired. Please try again.")
        return

    chosen_id = query.data.replace("nl_disambig_", "")
    all_users = _get_cached_users(context)
    chosen_user = next((u for u in all_users if u["id"] == chosen_id), None)
    if not chosen_user:
        await query.edit_message_text("❌ User not found. Please try again.")
        return

    # Patch the pending intent: replace the ambiguous name with the chosen user
    intent = req.pending_intent
    data = intent.get("data", {})
    resolving = intent.get("_resolving", "")

    if resolving == "paid_by":
        data["paid_by_name"] = chosen_user["name"]
    elif resolving == "payer":
        data["payer_name"] = chosen_user["name"]
    elif resolving == "receiver":
        data["receiver_name"] = chosen_user["name"]
    elif resolving.startswith("split_"):
        orig_name = resolving[6:]
        for s in data.get("splits", []):
            if s["name"].lower() == orig_name.lower():
                s["name"] = chosen_user["name"]
                break
    intent["data"] = data

    # Re-run executor with patched intent
    acting_user = queries.get_user_by_telegram_id(update.effective_user.id)

    try:
        result = execute_intent(intent, acting_user, all_users)
    except ExecutorError as e:
        await query.edit_message_text(f"❌ {e.user_message}")
        return

    if isinstance(result, AmbiguityRequest):
        # Another ambiguous name — send next disambiguation
        context.user_data["nl_disambig"] = result
        buttons = [
            [InlineKeyboardButton(u["name"], callback_data=f"nl_disambig_{u['id']}")]
            for u in result.candidates
        ]
        buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="nl_cancel")])
        await query.edit_message_text(
            f"Which *{result.ambiguous_name}* do you mean?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    await _send_confirmation(query, context, result, edit=True)


# ─── Fallback helpers ─────────────────────────────────────────────────────────

async def _fallback(update: Update):
    await update.message.reply_text(
        "I didn't understand that. Try something like:\n\n"
        "_'I paid 500 for dinner, split with Meet and Rahul'_\n"
        "_'I paid 900 for groceries for everyone'_\n"
        "_'I settled 300 with Rahul'_\n\n"
        "Or use the menu below.",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def _fallback_low_confidence(update: Update, intent_result: dict):
    data = intent_result.get("data", {})
    desc = data.get("description", "")
    amount = data.get("amount", "")
    hint = ""
    if desc or amount:
        hint = f"\n\nI partially understood: _{desc}_ ₹{amount}" if desc else f"\n\nI partially understood: ₹{amount}"

    await update.message.reply_text(
        f"I'm not sure what you mean.{hint}\n\n"
        f"Try: _'I paid 500 for dinner, split with Meet'_\n"
        f"Or use /add for the guided flow.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Use guided flow", callback_data="add_expense"),
        ]]),
    )
