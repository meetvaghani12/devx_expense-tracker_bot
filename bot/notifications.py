import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import GMAIL_ADDRESS, GMAIL_APP_PASSWORD

logger = logging.getLogger(__name__)


async def send_telegram_message(bot, telegram_id: int, text: str, parse_mode: str = "Markdown"):
    try:
        await bot.send_message(chat_id=telegram_id, text=text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {telegram_id}: {e}")


async def notify_expense_added(bot, expense: dict, payer_name: str, splits: list):
    """Notify all people involved in an expense."""
    desc = expense["description"]
    amount = float(expense["amount"])
    category = expense["category"]

    logger.info(f"notify_expense_added: {len(splits)} splits to notify for '{desc}'")

    for s in splits:
        user = s.get("users", {})
        logger.info(f"  Split row: amount={s.get('amount_owed')}, user={user}")
        if not user:
            logger.warning(f"  Skipping split — no user data found: {s}")
            continue
        tg_id = user.get("telegram_id")
        name = user.get("name", "Unknown")
        owed = float(s["amount_owed"])
        if tg_id:
            msg = (
                f"💸 *New Expense Added*\n\n"
                f"📝 {desc}\n"
                f"💰 Total: ₹{amount:.2f}\n"
                f"🏷️ Category: {category}\n"
                f"👤 Paid by: *{payer_name}*\n\n"
                f"You owe: *₹{owed:.2f}*"
            )
            await send_telegram_message(bot, tg_id, msg)
            logger.info(f"  Telegram sent to {name} (tg_id={tg_id})")
            email = user.get("email")
            if email:
                send_email(
                    to=email,
                    subject=f"[SplitBot] New expense: {desc}",
                    body=f"Hi {name},\n\n{payer_name} added an expense:\n\nDescription: {desc}\nTotal: ₹{amount:.2f}\nCategory: {category}\n\nYour share: ₹{owed:.2f}\n\nOpen your Telegram bot to settle up.\n\n— SplitBot",
                )
                logger.info(f"  Email sent to {email}")


async def notify_settlement(bot, payer_name: str, receiver: dict, amount: float):
    """Notify receiver that they've been paid."""
    tg_id = receiver.get("telegram_id")
    name = receiver.get("name", "Unknown")
    email = receiver.get("email")

    msg = (
        f"✅ *Payment Received*\n\n"
        f"*{payer_name}* has settled ₹{amount:.2f} with you."
    )
    if tg_id:
        await send_telegram_message(bot, tg_id, msg)
    if email:
        send_email(
            to=email,
            subject=f"[SplitBot] {payer_name} settled ₹{amount:.2f} with you",
            body=f"Hi {name},\n\n{payer_name} has marked a payment of ₹{amount:.2f} to you as settled.\n\n— SplitBot",
        )


async def send_weekly_reminder(bot, users_with_dues: list):
    """Send Sunday evening reminder to people with pending dues."""
    for user in users_with_dues:
        tg_id = user.get("telegram_id")
        name = user.get("name", "Unknown")
        amount = abs(user["net"])
        email = user.get("email")
        msg = (
            f"⏰ *Weekly Reminder*\n\n"
            f"Hi {name}! You have ₹{amount:.2f} in pending dues.\n"
            f"Use /settle to settle up."
        )
        if tg_id:
            await send_telegram_message(bot, tg_id, msg)
        if email:
            send_email(
                to=email,
                subject="[SplitBot] Weekly Reminder — Pending Dues",
                body=f"Hi {name},\n\nYou have ₹{amount:.2f} in pending dues.\n\nOpen the Telegram bot and use /settle to settle up.\n\n— SplitBot",
            )


async def send_monthly_report_to_all(bot, users: list, report_text: str, month_label: str):
    """Send monthly report to all users."""
    plain = report_text.replace("*", "").replace("_", "")
    for user in users:
        tg_id = user.get("telegram_id")
        email = user.get("email")
        name = user.get("name", "")
        if tg_id:
            await send_telegram_message(bot, tg_id, report_text)
        if email:
            send_email(
                to=email,
                subject=f"[SplitBot] Monthly Report — {month_label}",
                body=f"Hi {name},\n\n{plain}\n\n— SplitBot",
            )


def send_email(to: str, subject: str, body: str):
    try:
        msg = MIMEMultipart()
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, to, msg.as_string())
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
