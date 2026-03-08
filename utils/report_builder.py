from datetime import datetime


def format_balance_summary(balances: dict) -> str:
    """balances: {user_id: {name, net, ...}}"""
    lines = ["📊 *Current Balances*\n"]
    for uid, data in sorted(balances.items(), key=lambda x: -x[1]["net"]):
        net = data["net"]
        name = data["name"]
        if abs(net) < 0.01:
            lines.append(f"  ✅ {name}: All settled up")
        elif net > 0:
            lines.append(f"  🟢 {name}: is owed ₹{net:.2f}")
        else:
            lines.append(f"  🔴 {name}: owes ₹{abs(net):.2f}")
    return "\n".join(lines)


def format_settle_suggestions(transactions: list) -> str:
    if not transactions:
        return "✅ Everyone is settled up! No pending dues."
    lines = ["💸 *Suggested Settlements*\n", "_Minimum transactions to settle all debts:_\n"]
    for t in transactions:
        lines.append(f"  • {t['from_name']} → {t['to_name']}: ₹{t['amount']:.2f}")
    return "\n".join(lines)


def format_expense_history(expenses: list) -> str:
    if not expenses:
        return "No expenses found."
    lines = ["📋 *Recent Expenses*\n"]
    for e in expenses:
        payer = e.get("users", {})
        payer_name = payer.get("name", "Unknown") if payer else "Unknown"
        date = e["created_at"][:10]
        lines.append(
            f"  • [{date}] {e['description']} — ₹{float(e['amount']):.2f}\n"
            f"    Paid by *{payer_name}* | {e['category']}"
        )
    return "\n".join(lines)


def format_monthly_report(stats: dict, balances: dict, month: int, year: int) -> str:
    month_name = datetime(year, month, 1).strftime("%B %Y")
    lines = [
        f"📅 *Monthly Report — {month_name}*\n",
        f"Total Spent: ₹{stats['total']:.2f}",
        f"Total Expenses: {stats['expense_count']}\n",
        "*Paid By:*",
    ]
    for name, amt in stats["paid_by"].items():
        lines.append(f"  • {name}: ₹{amt:.2f}")

    lines.append("\n*Top Categories:*")
    for cat, amt in list(stats["categories"].items())[:5]:
        lines.append(f"  • {cat}: ₹{amt:.2f}")

    lines.append("\n*Current Balances:*")
    for uid, data in sorted(balances.items(), key=lambda x: -x[1]["net"]):
        net = data["net"]
        if abs(net) < 0.01:
            lines.append(f"  ✅ {data['name']}: Settled")
        elif net > 0:
            lines.append(f"  🟢 {data['name']}: owed ₹{net:.2f}")
        else:
            lines.append(f"  🔴 {data['name']}: owes ₹{abs(net):.2f}")

    return "\n".join(lines)


def format_expense_added(expense: dict, payer_name: str, splits: list) -> str:
    desc = expense["description"]
    amount = float(expense["amount"])
    category = expense["category"]
    lines = [
        f"✅ *Expense Added*\n",
        f"📝 {desc}",
        f"💰 ₹{amount:.2f}",
        f"🏷️ {category}",
        f"👤 Paid by *{payer_name}*\n",
        "*Split:*",
    ]
    for s in splits:
        user = s.get("users", {})
        name = user.get("name", "Unknown") if user else "Unknown"
        lines.append(f"  • {name}: owes ₹{float(s['amount_owed']):.2f}")
    return "\n".join(lines)
