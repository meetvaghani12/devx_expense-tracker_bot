from datetime import datetime, timezone
from db.client import get_client


# ─── Users ────────────────────────────────────────────────────────────────────

def get_user_by_telegram_id(telegram_id: int):
    db = get_client()
    res = db.table("users").select("*").eq("telegram_id", telegram_id).execute()
    return res.data[0] if res.data else None


def create_user(telegram_id: int, username: str, name: str, email: str):
    db = get_client()
    res = db.table("users").insert({
        "telegram_id": telegram_id,
        "telegram_username": username,
        "name": name,
        "email": email,
    }).execute()
    return res.data[0] if res.data else None


def update_user_email(telegram_id: int, email: str):
    db = get_client()
    res = db.table("users").update({"email": email}).eq("telegram_id", telegram_id).execute()
    return res.data[0] if res.data else None


def get_all_users():
    db = get_client()
    res = db.table("users").select("*").order("name").execute()
    return res.data or []


def get_user_by_id(user_id: str):
    db = get_client()
    res = db.table("users").select("*").eq("id", user_id).execute()
    return res.data[0] if res.data else None


# ─── Expenses ─────────────────────────────────────────────────────────────────

def add_expense(description: str, amount: float, category: str, paid_by_id: str, splits: list, note: str = None):
    """
    splits: list of {"user_id": str, "amount_owed": float}
    The payer is NOT included in splits (they owe nothing to themselves).
    """
    db = get_client()

    # Insert expense
    exp_res = db.table("expenses").insert({
        "description": description,
        "amount": amount,
        "category": category,
        "paid_by": paid_by_id,
        "note": note,
    }).execute()
    expense = exp_res.data[0]

    # Insert splits for each debtor
    split_rows = [
        {
            "expense_id": expense["id"],
            "user_id": s["user_id"],
            "amount_owed": s["amount_owed"],
            "is_settled": False,
        }
        for s in splits
    ]
    if split_rows:
        db.table("expense_splits").insert(split_rows).execute()

    return expense


def get_expense_with_splits(expense_id: str):
    db = get_client()
    exp = db.table("expenses").select("*, users!expenses_paid_by_fkey(name, telegram_id)").eq("id", expense_id).execute()
    splits_raw = db.table("expense_splits").select("id, user_id, amount_owed, is_settled").eq("expense_id", expense_id).execute()

    # Explicitly fetch user data for each split to avoid PostgREST join issues
    splits = []
    for s in (splits_raw.data or []):
        user_res = db.table("users").select("name, telegram_id, email").eq("id", s["user_id"]).execute()
        s["users"] = user_res.data[0] if user_res.data else None
        splits.append(s)

    return exp.data[0] if exp.data else None, splits


def get_recent_expenses(limit: int = 10):
    db = get_client()
    res = db.table("expenses").select(
        "*, users!expenses_paid_by_fkey(name)"
    ).order("created_at", desc=True).limit(limit).execute()
    return res.data or []


def get_expenses_for_month(year: int, month: int):
    db = get_client()
    start = f"{year}-{month:02d}-01T00:00:00+00:00"
    if month == 12:
        end = f"{year+1}-01-01T00:00:00+00:00"
    else:
        end = f"{year}-{month+1:02d}-01T00:00:00+00:00"
    res = db.table("expenses").select(
        "*, users!expenses_paid_by_fkey(name), expense_splits(user_id, amount_owed, is_settled, users(name))"
    ).gte("created_at", start).lt("created_at", end).order("created_at", desc=True).execute()
    return res.data or []


# ─── Balances ─────────────────────────────────────────────────────────────────

def get_all_balances():
    """
    Returns a dict: {user_id: {"name": str, "email": str, "telegram_id": int, "net": float}}
    Positive net = others owe this person.
    Negative net = this person owes others.
    """
    db = get_client()
    users = get_all_users()
    balances = {u["id"]: {"name": u["name"], "email": u["email"], "telegram_id": u["telegram_id"], "net": 0.0} for u in users}

    # What each person is owed (they paid for others)
    expenses = db.table("expenses").select("paid_by, id").execute().data or []
    expense_ids = [e["id"] for e in expenses]
    payer_map = {e["id"]: e["paid_by"] for e in expenses}

    if expense_ids:
        splits = db.table("expense_splits").select("expense_id, user_id, amount_owed, is_settled").eq("is_settled", False).execute().data or []
        for s in splits:
            payer_id = payer_map.get(s["expense_id"])
            debtor_id = s["user_id"]
            amount = float(s["amount_owed"])
            if payer_id and payer_id in balances:
                balances[payer_id]["net"] += amount   # payer is owed
            if debtor_id in balances:
                balances[debtor_id]["net"] -= amount  # debtor owes

    return balances


def get_pairwise_debts():
    """
    Returns list of {"from": user_id, "to": user_id, "amount": float}
    Only positive (net) debts between pairs.
    """
    db = get_client()
    expenses = db.table("expenses").select("id, paid_by").execute().data or []
    payer_map = {e["id"]: e["paid_by"] for e in expenses}

    splits = db.table("expense_splits").select("expense_id, user_id, amount_owed").eq("is_settled", False).execute().data or []

    # pairwise: debt[debtor][creditor] = amount
    debt = {}
    for s in splits:
        payer_id = payer_map.get(s["expense_id"])
        debtor_id = s["user_id"]
        if not payer_id or payer_id == debtor_id:
            continue
        debt.setdefault(debtor_id, {})
        debt[debtor_id][payer_id] = debt[debtor_id].get(payer_id, 0.0) + float(s["amount_owed"])

    # Net out mutual debts
    pairs_done = set()
    result = []
    for debtor, creditors in debt.items():
        for creditor, amount in creditors.items():
            pair = tuple(sorted([debtor, creditor]))
            if pair in pairs_done:
                continue
            pairs_done.add(pair)
            reverse = debt.get(creditor, {}).get(debtor, 0.0)
            net = amount - reverse
            if net > 0.01:
                result.append({"from": debtor, "to": creditor, "amount": round(net, 2)})
            elif net < -0.01:
                result.append({"from": creditor, "to": debtor, "amount": round(-net, 2)})

    return result


def get_user_splits(user_id: str):
    """Get all unsettled splits where user owes money."""
    db = get_client()
    res = db.table("expense_splits").select(
        "*, expenses(description, amount, category, paid_by, created_at, users!expenses_paid_by_fkey(name))"
    ).eq("user_id", user_id).eq("is_settled", False).order("expenses(created_at)", desc=True).execute()
    return res.data or []


# ─── Settlements ──────────────────────────────────────────────────────────────

def settle_between(payer_id: str, receiver_id: str, amount: float, method: str = "manual"):
    """
    Mark ALL unsettled splits between payer and receiver as settled.
    The `amount` is the net payment (from simplify_debts) — it clears the whole
    relationship between the two people, so all splits are marked settled.
    """
    db = get_client()
    now = datetime.now(timezone.utc).isoformat()

    # Mark all splits where payer owes receiver (payer's splits in receiver's expenses)
    expenses_by_receiver = db.table("expenses").select("id").eq("paid_by", receiver_id).execute().data or []
    exp_ids_receiver = [e["id"] for e in expenses_by_receiver]
    if exp_ids_receiver:
        splits_payer_owes = db.table("expense_splits").select("id").eq("user_id", payer_id).eq("is_settled", False).in_("expense_id", exp_ids_receiver).execute().data or []
        ids = [s["id"] for s in splits_payer_owes]
        if ids:
            db.table("expense_splits").update({"is_settled": True, "settled_at": now}).in_("id", ids).execute()

    # Also mark splits where receiver owes payer (receiver's splits in payer's expenses)
    expenses_by_payer = db.table("expenses").select("id").eq("paid_by", payer_id).execute().data or []
    exp_ids_payer = [e["id"] for e in expenses_by_payer]
    if exp_ids_payer:
        splits_receiver_owes = db.table("expense_splits").select("id").eq("user_id", receiver_id).eq("is_settled", False).in_("expense_id", exp_ids_payer).execute().data or []
        ids = [s["id"] for s in splits_receiver_owes]
        if ids:
            db.table("expense_splits").update({"is_settled": True, "settled_at": now}).in_("id", ids).execute()

    # Record settlement
    res = db.table("settlements").insert({
        "payer_id": payer_id,
        "receiver_id": receiver_id,
        "amount": amount,
        "method": method,
    }).execute()

    return res.data[0] if res.data else None


def get_recent_settlements(limit: int = 10):
    db = get_client()
    res = db.table("settlements").select(
        "*, payer:users!settlements_payer_id_fkey(name), receiver:users!settlements_receiver_id_fkey(name)"
    ).order("settled_at", desc=True).limit(limit).execute()
    return res.data or []


def get_monthly_stats(year: int, month: int):
    expenses = get_expenses_for_month(year, month)
    total = sum(float(e["amount"]) for e in expenses)

    # Per category
    categories = {}
    for e in expenses:
        cat = e.get("category", "Other")
        categories[cat] = categories.get(cat, 0.0) + float(e["amount"])

    # Per person paid
    paid_by = {}
    for e in expenses:
        payer = e.get("users", {})
        name = payer.get("name", "Unknown") if payer else "Unknown"
        paid_by[name] = paid_by.get(name, 0.0) + float(e["amount"])

    return {
        "total": total,
        "expense_count": len(expenses),
        "categories": dict(sorted(categories.items(), key=lambda x: x[1], reverse=True)),
        "paid_by": dict(sorted(paid_by.items(), key=lambda x: x[1], reverse=True)),
    }
