import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
NL_CONFIDENCE_THRESHOLD = float(os.getenv("NL_CONFIDENCE_THRESHOLD", "0.60"))

CATEGORIES = [
    "Food & Dining",
    "Travel & Transport",
    "Accommodation",
    "Groceries",
    "Entertainment",
    "Utilities & Bills",
    "Rent",
    "Medical",
    "Shopping",
    "Other",
]

# IST timezone
IST_TIMEZONE = "Asia/Kolkata"
# Weekly reminder: Sunday 6 PM IST = 12:30 UTC
WEEKLY_REMINDER_DAY = "sun"
WEEKLY_REMINDER_HOUR = 12
WEEKLY_REMINDER_MINUTE = 30
# Monthly report: 1st of month 9 AM IST = 3:30 UTC
MONTHLY_REPORT_HOUR = 3
MONTHLY_REPORT_MINUTE = 30
