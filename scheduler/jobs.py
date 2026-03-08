import logging
from datetime import datetime, time
from db import queries
from bot.notifications import send_weekly_reminder, send_monthly_report_to_all
from utils.report_builder import format_monthly_report

logger = logging.getLogger(__name__)


async def weekly_reminder_job(context):
    """Send Sunday evening reminder to anyone with pending dues."""
    logger.info("Running weekly reminder job...")
    try:
        balances = queries.get_all_balances()
        users_with_dues = [
            data for uid, data in balances.items()
            if data["net"] < -0.01
        ]
        if users_with_dues:
            await send_weekly_reminder(context.bot, users_with_dues)
            logger.info(f"Sent weekly reminders to {len(users_with_dues)} users.")
        else:
            logger.info("No pending dues — no reminders sent.")
    except Exception as e:
        logger.error(f"Weekly reminder job failed: {e}")


async def monthly_report_job(context):
    """Send monthly report on the 1st of each month."""
    logger.info("Running monthly report job...")
    try:
        now = datetime.utcnow()
        # Report is for previous month
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1

        stats = queries.get_monthly_stats(year, month)
        balances = queries.get_all_balances()
        report_text = format_monthly_report(stats, balances, month, year)
        month_label = datetime(year, month, 1).strftime("%B %Y")

        all_users = queries.get_all_users()
        await send_monthly_report_to_all(context.bot, all_users, report_text, month_label)
        logger.info(f"Monthly report for {month_label} sent to {len(all_users)} users.")
    except Exception as e:
        logger.error(f"Monthly report job failed: {e}")


def setup_jobs(application):
    """Register scheduled jobs with the bot's job queue."""
    job_queue = application.job_queue

    # Weekly reminder: Sunday 6 PM IST = Sunday 12:30 PM UTC
    # APScheduler day_of_week: 0=Monday, 6=Sunday
    job_queue.run_repeating(
        weekly_reminder_job,
        interval=604800,  # 7 days in seconds
        first=_next_sunday_utc(),
        name="weekly_reminder",
    )

    # Monthly report: 1st of month at 3:30 AM UTC (9 AM IST)
    job_queue.run_monthly(
        monthly_report_job,
        when=time(3, 30, tzinfo=None),
        day=1,
        name="monthly_report",
    )

    logger.info("Scheduled jobs registered: weekly_reminder, monthly_report")


def _next_sunday_utc():
    """Calculate seconds until next Sunday 12:30 UTC."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    # Sunday = weekday 6
    days_ahead = (6 - now.weekday()) % 7
    if days_ahead == 0 and (now.hour > 12 or (now.hour == 12 and now.minute >= 30)):
        days_ahead = 7
    next_sunday = now.replace(hour=12, minute=30, second=0, microsecond=0) + timedelta(days=days_ahead)
    delta = (next_sunday - now).total_seconds()
    return delta if delta > 0 else delta + 604800
