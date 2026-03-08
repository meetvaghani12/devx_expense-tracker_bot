# SplitBot 🤖💸

> A Telegram bot that tracks shared expenses, splits bills, and notifies everyone — just like Splitwise, but built for small private groups and running entirely on your own infrastructure.

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-2CA5E0?logo=telegram)](https://core.telegram.org/bots)
[![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?logo=supabase)](https://supabase.com)
[![Azure](https://img.shields.io/badge/Azure-App%20Service-0078D4?logo=microsoftazure)](https://azure.microsoft.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What It Does

SplitBot lets a group of 10–12 people track shared expenses over Telegram. No app to install — just a bot in your Telegram DMs.

- Add an expense in seconds with guided button flow or commands
- Choose how to split: **equal**, **custom amount**, **percentage**, or **select members**
- Bot automatically notifies everyone who owes money via **Telegram + Email**
- See who owes whom with one command — debts are simplified to minimum transactions
- Settle up with a single tap
- Monthly reports sent automatically on the 1st of every month
- Weekly Sunday reminders for anyone with pending dues

---

## Demo Flow

```
You: /add
Bot: Enter the total amount:
You: 900

Bot: Enter a description:
You: Dinner at Zomato

Bot: Select a category:
     [Food & Dining] [Travel] [Rent] [Other...]

Bot: Who paid?
     [Meet] [Rahul] [Priya] [Karan]

Bot: How to split?
     [Equal] [Custom ₹] [Percentage] [Select Members]

Bot: Select members (toggle):
     [✅ Meet] [✅ Rahul] [☐ Priya] [✅ Karan]  → Done ✔️

Bot: Confirm?
     Dinner at Zomato — ₹900
     Paid by: Meet
     • Rahul: ₹300
     • Karan: ₹300
     [✅ Confirm]  [❌ Cancel]

→ Saved. Rahul and Karan get a Telegram DM + Email instantly.
```

---

## Features

| Feature | Details |
|---|---|
| **Add Expense** | Guided button flow + `/add` command |
| **Split Types** | Equal / Custom ₹ / Percentage / Select specific members |
| **Categories** | 9 preset (Food, Travel, Rent…) + free-text fallback |
| **Notifications** | Telegram DM + Email on every expense added |
| **Balance Check** | Personal balance + group overview |
| **Settle Up** | Simplified debt suggestions (minimum transactions) |
| **Settlement** | Auto-suggested or manual, marks all splits cleared |
| **Monthly Report** | Auto-sent on 1st of every month (Telegram + Email) |
| **Weekly Reminder** | Every Sunday 6 PM IST to anyone with pending dues |
| **On-demand Report** | `/report` shows current month stats anytime |
| **History** | `/history` shows last 10 expenses |

---

## Commands

| Command | Description |
|---|---|
| `/start` | Register yourself (name + email) |
| `/menu` | Show main menu |
| `/add` | Add a new expense |
| `/balance` | Your personal net balance |
| `/balanceall` | Full group balance summary |
| `/history` | Last 10 transactions |
| `/settle` | See who owes whom + settle with one tap |
| `/report` | Current month report on demand |
| `/cancel` | Cancel any active flow |
| `/help` | All commands reference |

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Language | Python | 3.11 |
| Bot Framework | python-telegram-bot | 22.6 |
| Database | PostgreSQL via Supabase | Free tier |
| DB Client | supabase-py | 2.4.3 |
| Scheduler | APScheduler (via PTB job queue) | built-in |
| Email | Gmail SMTP (smtplib) | stdlib |
| HTTP Health Server | Flask + Gunicorn | 3.1.0 / 23.0.0 |
| Cloud Hosting | Azure App Service (Linux) | B1 tier |

---

## Project Structure

```
splitbot/
├── run.py                        # Entry point
├── config.py                     # Env var loader
├── health.py                     # Flask app for Azure health checks
├── startup.sh                    # Azure startup script
├── setup_db.py                   # One-time DB setup verifier
├── requirements.txt
│
├── bot/
│   ├── main.py                   # Application builder, handler registration
│   ├── states.py                 # Conversation state constants
│   ├── notifications.py          # Telegram + Email sender
│   ├── handlers/
│   │   ├── start.py              # /start, registration, /menu, /help
│   │   ├── expense.py            # Full add-expense conversation flow
│   │   ├── balance.py            # /balance, /balanceall, /history
│   │   ├── settle.py             # Settlement flow
│   │   └── report.py             # /report
│   └── keyboards/
│       └── menus.py              # All InlineKeyboardMarkup builders
│
├── db/
│   ├── client.py                 # Supabase singleton client
│   ├── queries.py                # All database operations
│   └── schema.sql                # SQL to create all tables (run once)
│
├── utils/
│   ├── split_calculator.py       # Split logic + debt simplification algorithm
│   └── report_builder.py        # Message formatters
│
└── scheduler/
    └── jobs.py                   # Weekly + monthly scheduled jobs
```

---

## Database Schema

```sql
users             -- registered members (telegram_id, name, email)
expenses          -- each expense (amount, category, paid_by)
expense_splits    -- who owes how much per expense (is_settled flag)
settlements       -- audit log of every payment made
```

### Balance Calculation
```
Net balance = SUM(expenses paid by user) - SUM(unsettled splits owed by user)

Positive → others owe you
Negative → you owe others
```

### Debt Simplification Algorithm
Reduces N pairwise debts to the minimum number of transactions using a greedy creditor/debtor approach — same as Splitwise's "Simplify Debts" feature.

---

## Local Setup

### Prerequisites
- Python 3.11+
- A Telegram Bot token from [@BotFather](https://t.me/BotFather)
- A [Supabase](https://supabase.com) project (free tier)
- A Gmail account with [App Password](https://myaccount.google.com/apppasswords) enabled

### 1. Clone and install

```bash
git clone https://github.com/yourname/splitbot.git
cd splitbot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
SUPABASE_URL=https://yourproject.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key
GMAIL_ADDRESS=yourbot@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

> ⚠️ Never commit `.env` to git. It's already in `.gitignore`.

### 3. Set up the database

Run the SQL from `db/schema.sql` in your Supabase SQL Editor:

```
https://supabase.com/dashboard/project/<your-project-ref>/sql/new
```

Then verify:
```bash
python setup_db.py
# Should show: ✅ users  ✅ expenses  ✅ expense_splits  ✅ settlements
```

### 4. Run locally

```bash
python run.py
```

The bot will start polling. Open Telegram, find your bot, and send `/start`.

---

## Azure Deployment

This project is deployed on **Azure App Service (Linux, Python 3.11)**. Here is the complete deployment guide.

### Architecture on Azure

Azure App Service expects an HTTP server listening on port 8000. A Telegram polling bot makes only outbound calls and never listens for HTTP — so naively deploying it would cause Azure to kill the process thinking the app crashed.

The solution: run **two processes** from one `startup.sh`:

```
startup.sh
├── python run.py &          → Telegram bot (background, polls api.telegram.org)
└── gunicorn health:app      → Flask health server (foreground, port 8000)
```

Azure's health checker hits `/health`, gets `{"status":"ok"}`, stays satisfied. The bot runs indefinitely in the background.

```python
# health.py — keeps Azure happy
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200
```

---

### Prerequisites

- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
- Logged in: `az login`
- An Azure subscription with an existing Resource Group and App Service Plan (Linux)

---

### Step 1 — Create the Web App

```bash
az webapp create \
  --resource-group your-resource-group \
  --plan your-app-service-plan \
  --name splitbot-app \
  --runtime "PYTHON:3.11"
```

> If you already have an App Service Plan (e.g. for another backend), you can add this web app to the **same plan at no extra cost** — Azure charges per plan, not per app.

---

### Step 2 — Set Environment Variables

Secrets are never deployed in code. They are set directly on the Azure Web App as Application Settings:

```bash
az webapp config appsettings set \
  --resource-group your-resource-group \
  --name splitbot-app \
  --settings \
    TELEGRAM_BOT_TOKEN="your_bot_token" \
    SUPABASE_URL="https://yourproject.supabase.co" \
    SUPABASE_SERVICE_KEY="your_service_role_key" \
    GMAIL_ADDRESS="yourbot@gmail.com" \
    GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx" \
    SCM_DO_BUILD_DURING_DEPLOYMENT="true"
```

`SCM_DO_BUILD_DURING_DEPLOYMENT=true` tells Azure's Kudu build system to automatically run `pip install -r requirements.txt` on every deploy — no manual steps needed.

---

### Step 3 — Set Startup Command

```bash
az webapp config set \
  --resource-group your-resource-group \
  --name splitbot-app \
  --startup-file "bash startup.sh"
```

This overrides Azure's default WSGI startup with our custom script that handles both the bot and health server.

---

### Step 4 — Deploy via Zip Deploy

```bash
# Create the zip (exclude secrets and build artifacts)
zip -r splitbot-deploy.zip . \
  --exclude "*.pyc" \
  --exclude "__pycache__/*" \
  --exclude ".env" \
  --exclude "venv/*" \
  --exclude "*.log" \
  --exclude ".git/*"

# Deploy
az webapp deploy \
  --resource-group your-resource-group \
  --name splitbot-app \
  --src-path splitbot-deploy.zip \
  --type zip
```

Deployment takes ~60–90 seconds (most of it is `pip install`).

#### What happens during deployment (Kudu build system)

```
1. Zip extracted to /home/site/wwwroot/
2. Kudu detects Python project (requirements.txt present)
3. Creates virtualenv at /tmp/.../antenv/
4. Runs: pip install -r requirements.txt
5. Applies startup command: bash startup.sh
6. startup.sh forks bot process + starts gunicorn
7. Azure health check hits /health → 200 OK
8. Deployment marked: RuntimeSuccessful
```

---

### Step 5 — Verify

```bash
# Check health endpoint
curl https://splitbot-app.azurewebsites.net/health
# → {"status":"ok"}

# Check bot state
az webapp show \
  --resource-group your-resource-group \
  --name splitbot-app \
  --query state -o tsv
# → Running
```

---

### Redeployment (after code changes)

```bash
# 1. Rebuild zip
zip -r splitbot-deploy.zip . \
  --exclude "*.pyc" --exclude "__pycache__/*" \
  --exclude ".env" --exclude "venv/*" \
  --exclude "*.log" --exclude ".git/*"

# 2. Deploy
az webapp deploy \
  --resource-group your-resource-group \
  --name splitbot-app \
  --src-path splitbot-deploy.zip \
  --type zip

# 3. If only env vars changed (no code changes), just restart
az webapp restart \
  --resource-group your-resource-group \
  --name splitbot-app
```

---

### Logs

```bash
# Download logs
az webapp log download \
  --resource-group your-resource-group \
  --name splitbot-app \
  --log-file logs.zip

# Bot-specific log inside the zip
unzip -p logs.zip "LogFiles/splitbot.log" | tail -50
```

---

### Important: Only One Bot Instance

Telegram only allows **one active polling connection per bot token**. If you run the bot locally while it's also running on Azure, you'll get:

```
telegram.error.Conflict: terminated by other getUpdates request
```

Always stop your local instance before deploying, or vice versa.

```bash
# Stop local bot
pkill -f "run.py"
```

---

### Azure Resource Summary

| Resource | Name | Details |
|---|---|---|
| Resource Group | `your-resource-group` | Your existing group |
| App Service Plan | `your-plan` | Linux, B1 (can share with other apps) |
| Web App | `splitbot-app` | Python 3.11, Central India |
| Database | Supabase (external) | Free tier, 500MB |
| Email | Gmail SMTP (external) | Free |
| **Extra monthly cost** | **₹0** | Shares existing plan |

---

## Scheduling

| Job | Schedule | Description |
|---|---|---|
| Weekly Reminder | Every Sunday 6 PM IST | Sends Telegram + Email to anyone with pending dues |
| Monthly Report | 1st of every month, 9 AM IST | Full group report with totals, per-person, top categories |

Schedules are configured in `scheduler/jobs.py` using python-telegram-bot's built-in APScheduler job queue.

---

## Notification Events

| Trigger | Telegram | Email |
|---|---|---|
| Expense added | All debtors notified with their share | ✅ |
| Settlement recorded | Receiver notified | ✅ |
| Weekly reminder | Anyone with pending dues | ✅ |
| Monthly report | All members | ✅ |

---

## Security

- `.env` is excluded from git (`.gitignore`) and from deployment zip
- All secrets stored as Azure App Settings (encrypted at rest)
- Gmail App Password used — not the main account password (can be revoked independently)
- Supabase `service_role` key used server-side only — never exposed to clients
- HTTPS enforced by Azure App Service by default

---

## Contributing

This is an internal tool but PRs are welcome. To add a feature:

1. Fork and clone
2. Create a branch: `git checkout -b feature/your-feature`
3. Make changes and test locally with `python run.py`
4. Deploy to Azure using the Zip Deploy steps above
5. Open a PR

---

## License

MIT — do whatever you want with it.

---

<div align="center">
  Built with Python 🐍 · Deployed on Azure ☁️ · Powered by Supabase 🗄️
</div>
