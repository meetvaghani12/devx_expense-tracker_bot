"""
Agent 2: Operations Executor
Resolves names to DB user records, validates the intent, builds a
ConfirmationPayload ready for the user to approve before writing to DB.
"""
import logging
from utils.split_calculator import calculate_equal_split, calculate_custom_amount_split, calculate_percentage_split

logger = logging.getLogger(__name__)


class ExecutorError(Exception):
    def __init__(self, user_message: str):
        self.user_message = user_message
        super().__init__(user_message)


class AmbiguityRequest:
    def __init__(self, ambiguous_name: str, candidates: list, pending_intent: dict):
        self.ambiguous_name = ambiguous_name
        self.candidates = candidates
        self.pending_intent = pending_intent


class ConfirmationPayload:
    def __init__(self, intent: str, display_text: str, confirm_callback: str, db_payload: dict):
        self.intent = intent
        self.display_text = display_text
        self.confirm_callback = confirm_callback
        self.db_payload = db_payload


def resolve_name(name: str, all_users: list) -> list:
    """
    Returns list of matching user dicts for a given name string.
    Tries: exact → prefix → substring (all case-insensitive).
    """
    name_lower = name.lower().strip()

    # Exact match
    exact = [u for u in all_users if u["name"].lower() == name_lower]
    if exact:
        return exact

    # Prefix match
    prefix = [u for u in all_users if u["name"].lower().startswith(name_lower)]
    if prefix:
        return prefix

    # Substring match
    substr = [u for u in all_users if name_lower in u["name"].lower()]
    if substr:
        return substr

    return []


def _build_expense_display(description, amount, category, paid_by_name, splits_with_names):
    lines = [
        "📋 *Review Expense*\n",
        f"📝 {description}",
        f"💰 ₹{amount:.2f}",
        f"🏷️ {category}",
        f"👤 Paid by: *{paid_by_name}*\n",
        "*Split:*",
    ]
    for s in splits_with_names:
        lines.append(f"  • {s['name']}: ₹{s['amount_owed']:.2f}")
    lines.append("\n_Confirm to save and notify everyone._")
    return "\n".join(lines)


def _build_settle_display(payer_name, receiver_name, amount, method):
    return (
        f"📋 *Review Settlement*\n\n"
        f"💸 *{payer_name}* pays *₹{amount:.2f}* to *{receiver_name}*\n"
        f"💳 Method: {method}\n\n"
        f"_Confirm to record this payment._"
    )


def execute_intent(intent_result: dict, acting_user: dict, all_users: list):
    """
    Synchronous executor (no DB writes here — just validation + payload building).
    Returns ConfirmationPayload, AmbiguityRequest, or raises ExecutorError.
    """
    intent = intent_result.get("intent")
    data = intent_result.get("data", {})

    if intent == "add_expense":
        return _execute_add_expense(data, acting_user, all_users, intent_result)

    elif intent == "settle":
        return _execute_settle(data, acting_user, all_users)

    else:
        raise ExecutorError("I couldn't figure out what you want to do.")


def _execute_add_expense(data, acting_user, all_users, full_intent):
    amount = data.get("amount", 0)
    if not amount or float(amount) <= 0:
        raise ExecutorError("Amount must be a positive number.")

    amount = float(amount)
    description = data.get("description", "").strip()
    if not description:
        raise ExecutorError("I couldn't understand the description of this expense.")

    category = data.get("category", "Other")
    split_type = data.get("split_type", "equal")
    include_all = data.get("include_all_members", False)

    # Resolve payer
    paid_by_name = data.get("paid_by_name", acting_user["name"])
    payer_matches = resolve_name(paid_by_name, all_users)

    if len(payer_matches) == 0:
        raise ExecutorError(f"I don't know who '{paid_by_name}' is. Known members: {', '.join(u['name'] for u in all_users)}")
    if len(payer_matches) > 1:
        return AmbiguityRequest(
            ambiguous_name=paid_by_name,
            candidates=payer_matches,
            pending_intent={**full_intent, "_resolving": "paid_by"},
        )
    payer = payer_matches[0]

    # If include_all_members → all users except payer
    if include_all or (split_type == "equal" and not data.get("splits")):
        debtors = [u for u in all_users if u["id"] != payer["id"]]
        splits_db = calculate_equal_split(amount, [u["id"] for u in debtors])
        splits_display = [
            {"name": u["name"], "amount_owed": s["amount_owed"]}
            for u, s in zip(debtors, splits_db)
        ]
        display = _build_expense_display(description, amount, category, payer["name"], splits_display)
        return ConfirmationPayload(
            intent="add_expense",
            display_text=display,
            confirm_callback="nl_confirm_expense",
            db_payload={
                "description": description,
                "amount": amount,
                "category": category,
                "paid_by_id": payer["id"],
                "paid_by_name": payer["name"],
                "splits": splits_db,
            },
        )

    # Resolve each split person
    raw_splits = data.get("splits", [])
    if not raw_splits:
        raise ExecutorError("I couldn't figure out who should split this expense.")

    resolved_splits = []
    for s in raw_splits:
        name = s.get("name", "")
        matches = resolve_name(name, all_users)
        if len(matches) == 0:
            raise ExecutorError(f"I don't know '{name}'. Known members: {', '.join(u['name'] for u in all_users)}")
        if len(matches) > 1:
            return AmbiguityRequest(
                ambiguous_name=name,
                candidates=matches,
                pending_intent={**full_intent, "_resolving": f"split_{name}"},
            )
        resolved_splits.append({"user": matches[0], "amount_owed": s.get("amount_owed", 0)})

    # Build DB splits
    if split_type == "equal":
        member_ids = [s["user"]["id"] for s in resolved_splits]
        splits_db = calculate_equal_split(amount, member_ids)
        splits_display = [
            {"name": s["user"]["name"], "amount_owed": db_s["amount_owed"]}
            for s, db_s in zip(resolved_splits, splits_db)
        ]
    elif split_type == "custom":
        amounts_dict = {s["user"]["id"]: s["amount_owed"] for s in resolved_splits}
        splits_db = calculate_custom_amount_split(amounts_dict)
        splits_display = [
            {"name": s["user"]["name"], "amount_owed": s["amount_owed"]}
            for s in resolved_splits
        ]
    elif split_type == "percent":
        pct_dict = {s["user"]["id"]: s["amount_owed"] for s in resolved_splits}
        splits_db = calculate_percentage_split(amount, pct_dict)
        user_map = {s["user"]["id"]: s["user"]["name"] for s in resolved_splits}
        splits_display = [
            {"name": user_map[db_s["user_id"]], "amount_owed": db_s["amount_owed"]}
            for db_s in splits_db
        ]
    else:
        member_ids = [s["user"]["id"] for s in resolved_splits]
        splits_db = calculate_equal_split(amount, member_ids)
        splits_display = [
            {"name": s["user"]["name"], "amount_owed": db_s["amount_owed"]}
            for s, db_s in zip(resolved_splits, splits_db)
        ]

    display = _build_expense_display(description, amount, category, payer["name"], splits_display)
    return ConfirmationPayload(
        intent="add_expense",
        display_text=display,
        confirm_callback="nl_confirm_expense",
        db_payload={
            "description": description,
            "amount": amount,
            "category": category,
            "paid_by_id": payer["id"],
            "paid_by_name": payer["name"],
            "splits": splits_db,
        },
    )


def _execute_settle(data, acting_user, all_users):
    payer_name = data.get("payer_name", acting_user["name"])
    receiver_name = data.get("receiver_name", "")
    amount = data.get("amount", 0)
    method = data.get("method", "manual")

    if not amount or float(amount) <= 0:
        raise ExecutorError("Settlement amount must be a positive number.")
    amount = float(amount)

    if not receiver_name:
        raise ExecutorError("I couldn't figure out who you're paying. Please specify the receiver's name.")

    payer_matches = resolve_name(payer_name, all_users)
    if len(payer_matches) == 0:
        raise ExecutorError(f"I don't know '{payer_name}'. Known members: {', '.join(u['name'] for u in all_users)}")
    if len(payer_matches) > 1:
        return AmbiguityRequest(ambiguous_name=payer_name, candidates=payer_matches, pending_intent={"intent": "settle", "data": data, "_resolving": "payer"})
    payer = payer_matches[0]

    receiver_matches = resolve_name(receiver_name, all_users)
    if len(receiver_matches) == 0:
        raise ExecutorError(f"I don't know '{receiver_name}'. Known members: {', '.join(u['name'] for u in all_users)}")
    if len(receiver_matches) > 1:
        return AmbiguityRequest(ambiguous_name=receiver_name, candidates=receiver_matches, pending_intent={"intent": "settle", "data": data, "_resolving": "receiver"})
    receiver = receiver_matches[0]

    if payer["id"] == receiver["id"]:
        raise ExecutorError("Payer and receiver can't be the same person.")

    display = _build_settle_display(payer["name"], receiver["name"], amount, method)
    return ConfirmationPayload(
        intent="settle",
        display_text=display,
        confirm_callback="nl_confirm_settle",
        db_payload={
            "payer_id": payer["id"],
            "payer_name": payer["name"],
            "receiver_id": receiver["id"],
            "receiver_name": receiver["name"],
            "amount": amount,
            "method": method,
        },
    )
