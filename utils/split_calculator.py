def calculate_equal_split(total: float, members: list, total_people: int = None) -> list:
    """
    members: list of user_ids who OWE money (excludes payer).
    total_people: total headcount INCLUDING payer. Defaults to len(members).
    Each member owes total / total_people.
    Returns: list of {"user_id": str, "amount_owed": float}
    """
    if not members:
        return []
    n = total_people if total_people else len(members)
    per_person = round(total / n, 2)
    splits = [{"user_id": uid, "amount_owed": per_person} for uid in members]
    # Rounding adjustment goes to the last debtor
    diff = round(total - per_person * n, 2)
    if diff != 0:
        splits[-1]["amount_owed"] = round(splits[-1]["amount_owed"] + diff, 2)
    return splits


def calculate_custom_amount_split(amounts: dict) -> list:
    """
    amounts: {user_id: amount_owed}
    Returns: list of {"user_id": str, "amount_owed": float}
    """
    return [{"user_id": uid, "amount_owed": round(float(amt), 2)} for uid, amt in amounts.items()]


def calculate_percentage_split(total: float, percentages: dict) -> list:
    """
    percentages: {user_id: percentage (0-100)}
    Returns: list of {"user_id": str, "amount_owed": float}
    """
    result = []
    total_so_far = 0.0
    items = list(percentages.items())
    for i, (uid, pct) in enumerate(items):
        if i == len(items) - 1:
            amt = round(total - total_so_far, 2)
        else:
            amt = round(total * pct / 100, 2)
        total_so_far += amt
        result.append({"user_id": uid, "amount_owed": amt})
    return result


def simplify_debts(pairwise_debts: list, users: dict) -> list:
    """
    pairwise_debts: list of {"from": user_id, "to": user_id, "amount": float}
    users: {user_id: {"name": str, ...}}
    Returns: list of {"from": user_id, "from_name": str, "to": user_id, "to_name": str, "amount": float}
    Minimizes number of transactions using net balance approach.
    """
    # Compute net balance for each person in the debt graph
    net = {}
    for d in pairwise_debts:
        net[d["from"]] = net.get(d["from"], 0.0) - d["amount"]
        net[d["to"]] = net.get(d["to"], 0.0) + d["amount"]

    creditors = sorted([(uid, bal) for uid, bal in net.items() if bal > 0.01], key=lambda x: -x[1])
    debtors = sorted([(uid, -bal) for uid, bal in net.items() if bal < -0.01], key=lambda x: -x[1])

    creditors = list(creditors)
    debtors = list(debtors)

    transactions = []
    i, j = 0, 0
    while i < len(creditors) and j < len(debtors):
        cred_id, credit = creditors[i]
        debt_id, debt = debtors[j]
        amount = round(min(credit, debt), 2)

        transactions.append({
            "from": debt_id,
            "from_name": users.get(debt_id, {}).get("name", "Unknown"),
            "to": cred_id,
            "to_name": users.get(cred_id, {}).get("name", "Unknown"),
            "amount": amount,
        })

        creditors[i] = (cred_id, round(credit - amount, 2))
        debtors[j] = (debt_id, round(debt - amount, 2))

        if creditors[i][1] < 0.01:
            i += 1
        if debtors[j][1] < 0.01:
            j += 1

    return transactions
