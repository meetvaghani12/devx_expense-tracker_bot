# SplitBot — Full Project Report

> Date: March 8, 2026
> Status: Production — Live on Azure
> Bot: Telegram-based expense splitting bot for internal group use (10–12 people)

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Requirements Gathered](#2-requirements-gathered)
3. [Architecture & Design](#3-architecture--design)
4. [Tech Stack](#4-tech-stack)
5. [Database Design](#5-database-design)
6. [Codebase Breakdown](#6-codebase-breakdown)
7. [Feature Implementation](#7-feature-implementation)
8. [Azure Deployment (Deep Dive)](#8-azure-deployment-deep-dive)
9. [Notifications System](#9-notifications-system)
10. [Scheduling System](#10-scheduling-system)
11. [Security Decisions](#11-security-decisions)
12. [What's Live Right Now](#12-whats-live-right-now)

---

## 1. Project Overview

SplitBot is a Telegram-based expense splitting and tracking system built for a small internal group of 10–12 people. It is the equivalent of Splitwise — but runs entirely through a Telegram bot with no separate app to install. Every member of the group gets notified via Telegram and Email when expenses are added or settlements are made. Monthly reports are sent automatically on the 1st of every month.

**Core problem it solves:**
- Track who paid for what
- Know who owes whom and how much
- Settle debts with minimum number of transactions
- Never manually chase people — bot sends reminders automatically

---

## 2. Requirements Gathered

Before writing a single line of code, requirements were gathered through a structured Q&A session. Here is what was confirmed:

| Requirement | Decision |
|---|---|
| Platform | Telegram Bot (free, no app install needed) |
| Group size | 10–12 people (internal use) |
| Currency | INR (₹) only |
| Split types | Equal, Custom ₹, Percentage, Select members |
| Categories | 9 predefined + free-text fallback |
| Notifications | Telegram + Email (Gmail) |
| Settlement | Auto-suggest minimum transactions + manual mark |
| Reports | Monthly auto (1st of month) + on-demand |
| Weekly reminder | Sunday 6 PM IST to anyone with pending dues |
| Hosting | Free / lowest cost possible |
| Language | Python (developer is comfortable with any) |
| Access control | Equal rights for all members |

---

## 3. Architecture & Design

### System Flow

```
User sends message / taps button on Telegram
          │
          ▼
  python-telegram-bot (v22.6)
  ConversationHandler / CommandHandler
          │
          ▼
  Handler Layer (bot/handlers/)
  ├── start.py        → Registration flow
  ├── expense.py      → Add expense (multi-step conversation)
  ├── balance.py      → View balances and history
  ├── settle.py       → Debt settlement flow
  └── report.py       → Monthly/on-demand reports
          │
          ▼
  DB Layer (db/queries.py)
  Supabase PostgreSQL (cloud hosted, free tier)
          │
          ▼
  Utils Layer
  ├── split_calculator.py  → Equal / Custom / % / Simplify debts
  └── report_builder.py    → Format text messages for reports
          │
          ▼
  Notifications (bot/notifications.py)
  ├── Telegram → bot.send_message()
  └── Email    → Gmail SMTP (smtplib, SSL port 465)
          │
          ▼
  Scheduler (scheduler/jobs.py)
  ├── Weekly reminder   → Every Sunday 12:30 UTC (6 PM IST)
  └── Monthly report    → 1st of month, 03:30 UTC (9 AM IST)
```

### Conversation State Machine (Add Expense)

```
/add or [Add Expense button]
    │
    ▼
ASK_AMOUNT       ← user types ₹ amount
    │
    ▼
ASK_DESCRIPTION  ← user types description
    │
    ▼
ASK_CATEGORY     ← inline keyboard: 9 categories + Other
    │
    ├── (Other selected)
    │       ▼
    │   ASK_CATEGORY_CUSTOM  ← user types custom category
    │
    ▼
ASK_PAID_BY      ← inline keyboard: all registered users
    │
    ▼
ASK_SPLIT_TYPE   ← Equal / Custom ₹ / Percentage / Select Members
    │
    ▼
ASK_MEMBERS      ← multi-select toggle keyboard (✅/☐)
    │
    ├── (Custom ₹ selected)
    │       ▼
    │   ASK_CUSTOM_AMOUNTS  ← user types comma-separated amounts
    │
    ├── (Percentage selected)
    │       ▼
    │   ASK_CUSTOM_PERCENT  ← user types comma-separated percentages
    │
    ▼
CONFIRM_EXPENSE  ← full summary shown → [Confirm] [Cancel]
    │
    ▼
  Saved to DB + Telegram + Email notifications sent to all involved
```

---

## 4. Tech Stack

| Layer | Technology | Version | Why |
|---|---|---|---|
| Language | Python | 3.11 (Azure) / 3.14 (local) | Best Telegram bot ecosystem |
| Bot framework | python-telegram-bot | 22.6 | Async, ConversationHandler, built-in job queue |
| Database client | supabase-py | 2.4.3 | Official Python client for Supabase |
| Database | PostgreSQL (via Supabase) | 17 | Free tier, 500MB, no expiry |
| Scheduler | APScheduler (via PTB job queue) | built-in | Weekly + monthly jobs |
| Email | smtplib + Gmail SMTP | stdlib | Free, no third-party service needed |
| HTTP server | Flask + Gunicorn | 3.1.0 / 23.0.0 | Required for Azure App Service health checks |
| Cloud | Azure App Service | Linux B1 | Existing plan, zero extra cost |
| Hosting DB | Supabase cloud | Free tier | 500MB, always-on |

---

## 5. Database Design

Four tables, designed for clarity and minimal joins.

### `users`
Stores all registered group members.
```sql
id               UUID  PRIMARY KEY
telegram_id      BIGINT UNIQUE        -- used to identify user from Telegram
telegram_username TEXT
name             TEXT
email            TEXT                 -- for email notifications
joined_at        TIMESTAMPTZ
```

### `expenses`
Each expense record. Stores who paid, how much, what category.
```sql
id          UUID  PRIMARY KEY
description TEXT
amount      DECIMAL(10,2)            -- INR
category    TEXT DEFAULT 'Other'
paid_by     UUID → users(id)         -- who actually paid the bill
note        TEXT                     -- optional note
created_at  TIMESTAMPTZ
```

### `expense_splits`
Who owes how much for each expense. Only debtors are recorded (not the payer — payer owes nothing to themselves).
```sql
id          UUID  PRIMARY KEY
expense_id  UUID → expenses(id) ON DELETE CASCADE
user_id     UUID → users(id)          -- the debtor
amount_owed DECIMAL(10,2)
is_settled  BOOLEAN DEFAULT FALSE
settled_at  TIMESTAMPTZ
UNIQUE(expense_id, user_id)
```

### `settlements`
Audit log of every payment made to settle debts.
```sql
id          UUID  PRIMARY KEY
payer_id    UUID → users(id)
receiver_id UUID → users(id)
amount      DECIMAL(10,2)
settled_at  TIMESTAMPTZ
method      TEXT   -- 'manual' or 'auto'
note        TEXT
```

### Balance Calculation Logic

```
Net balance for user A =
    SUM(amount) of expenses where paid_by = A and split is_settled = false
  - SUM(amount_owed) of expense_splits where user_id = A and is_settled = false

Positive net → others owe A money
Negative net → A owes others money
```

### Debt Simplification Algorithm

Instead of showing every individual debt, the bot computes the minimum number of transactions to settle all debts using a greedy algorithm:

```
1. Compute net balance for every user
2. Separate into creditors (net > 0) and debtors (net < 0)
3. Sort both lists descending by amount
4. Greedily match largest debtor with largest creditor
5. Record transaction, reduce both balances, move to next if zero

Example:
  Raw debts: A owes B ₹200, B owes C ₹300, C owes A ₹100
  After simplification: A pays C ₹100, A pays B ₹100
  Reduced from 3 transactions to 2.
```

---

## 6. Codebase Breakdown

### Project Structure
```
splitbot/
├── run.py                        ← entry point (fixes Python path)
├── config.py                     ← all env vars loaded from .env
├── health.py                     ← Flask app for Azure health checks
├── startup.sh                    ← Azure startup script
├── setup_db.py                   ← one-time DB verification tool
├── requirements.txt              ← all dependencies
├── .env                          ← secrets (never deployed to Azure)
│
├── bot/
│   ├── main.py                   ← builds Application, registers all handlers
│   ├── states.py                 ← 15 conversation state constants
│   ├── notifications.py          ← Telegram + Email sender
│   ├── handlers/
│   │   ├── start.py              ← /start, registration, /help, /menu
│   │   ├── expense.py            ← full add-expense conversation (415 lines)
│   │   ├── balance.py            ← /balance, /balanceall, /history
│   │   ├── settle.py             ← /settle, auto + manual settlement (225 lines)
│   │   └── report.py             ← /report on-demand
│   └── keyboards/
│       └── menus.py              ← all InlineKeyboardMarkup builders
│
├── db/
│   ├── client.py                 ← Supabase singleton client
│   ├── queries.py                ← all DB operations (257 lines)
│   └── schema.sql                ← SQL to create all 4 tables
│
├── utils/
│   ├── split_calculator.py       ← split logic + debt simplification
│   └── report_builder.py         ← text formatters for all messages
│
└── scheduler/
    └── jobs.py                   ← weekly + monthly scheduled jobs
```

### Lines of Code by Module
| File | Lines |
|---|---|
| bot/handlers/expense.py | 415 |
| db/queries.py | 257 |
| bot/handlers/settle.py | 225 |
| bot/main.py | 157 |
| bot/handlers/start.py | 109 |
| bot/handlers/balance.py | 99 |
| scheduler/jobs.py | 85 |
| utils/split_calculator.py | 85 |
| **Total (core files)** | **~1,432** |

---

## 7. Feature Implementation

### Commands Available
| Command | Description |
|---|---|
| `/start` | Register name + email. If already registered, shows main menu |
| `/menu` | Show main menu with all buttons |
| `/add` | Start add-expense guided flow |
| `/balance` | Your personal net balance + who owes you / you owe |
| `/balanceall` | Full group balance summary |
| `/history` | Last 10 expenses with date, description, amount, payer |
| `/settle` | See simplified debt suggestions, settle with one tap |
| `/report` | Current month stats: total spent, by person, by category |
| `/cancel` | Cancel any active conversation |
| `/help` | Full command reference |

### Split Types
| Type | How it works |
|---|---|
| Equal | Total ÷ number of selected members. Rounding remainder goes to last person |
| Custom ₹ | User enters comma-separated amounts. Validated to sum within ₹0.50 of total |
| Percentage | User enters comma-separated percentages. Must sum to 100% (±0.5%) |
| Select Members | Choose specific people then splits equally among them |

### Predefined Categories
Food & Dining · Travel & Transport · Accommodation · Groceries · Entertainment · Utilities & Bills · Rent · Medical · Shopping · **Other** (free-text fallback)

### Notification Triggers
| Event | Telegram | Email |
|---|---|---|
| Expense added | All debtors notified with their share | Same |
| Settlement recorded | Receiver notified | Same |
| Weekly reminder (Sunday 6 PM IST) | Anyone with pending dues | Same |
| Monthly report (1st of month, 9 AM IST) | All members | Same |

---

## 8. Azure Deployment (Deep Dive)

### Why Azure App Service

The user already had a Medusa-based e-commerce backend (`perfume-staging-api`) running on Azure App Service under the `perfume-staging-plan` (B1, Linux). Since Azure App Service pricing is **per plan, not per app**, adding a second Web App to the same plan costs nothing extra. This was the decisive reason for choosing Azure App Service over alternatives like Azure Container Instances or a new VM.

### Infrastructure Used

| Resource | Name | Details |
|---|---|---|
| Subscription | Azure subscription 1 | ID: `ebf6665c-32f1-477b-8ed2-6d5a1f1a4f9a` |
| Resource Group | `perfume-staging-rg` | Central India region |
| App Service Plan | `perfume-staging-plan` | B1 tier, Linux OS, 1 worker |
| Web App (existing) | `perfume-staging-api` | Node.js — Medusa backend |
| Web App (new) | `splitbot-app` | **Python 3.11 — Telegram Bot** |

### The Azure App Service Challenge

Azure App Service is designed for **HTTP web applications** — it expects your process to:
1. Listen on port 8000 (or the PORT env variable)
2. Respond to HTTP health checks from the Azure load balancer
3. Return HTTP 200 or risk being killed and restarted

A Telegram bot running in polling mode is a **pure background process** — it makes outbound HTTP calls to Telegram's API, never listens for inbound HTTP. If deployed naively, Azure would immediately kill it thinking the app crashed because nothing is listening on port 8000.

### How This Was Solved

Two separate processes run inside the same container via `startup.sh`:

```bash
# startup.sh — Azure startup script
python run.py >> "$LOG" 2>&1 &        # Telegram bot (background)
gunicorn health:app --bind 0.0.0.0:8000   # HTTP server (foreground, keeps Azure alive)
```

- **Foreground**: `gunicorn` serves the Flask `health.py` app on port 8000. Azure's health checker hits `/health`, gets `{"status":"ok"}`, stays happy.
- **Background**: `run.py` starts the Telegram bot which polls `api.telegram.org` for updates.

```python
# health.py — minimal Flask app
@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200
```

When `gunicorn` is the foreground process, Azure sees a "healthy" HTTP app and never kills the container. The bot runs indefinitely in the background.

### Environment Variables on Azure

Secrets are **never deployed in code or zip files**. They are configured directly on the Azure Web App as Application Settings, which Azure injects as environment variables at runtime:

```bash
az webapp config appsettings set \
  --resource-group perfume-staging-rg \
  --name splitbot-app \
  --settings \
    TELEGRAM_BOT_TOKEN="..." \
    SUPABASE_URL="..." \
    SUPABASE_SERVICE_KEY="..." \
    GMAIL_ADDRESS="..." \
    GMAIL_APP_PASSWORD="..." \
    SCM_DO_BUILD_DURING_DEPLOYMENT="true"
```

`SCM_DO_BUILD_DURING_DEPLOYMENT=true` tells Azure's Kudu build system to automatically run `pip install -r requirements.txt` during every deployment — no manual dependency installation needed.

### Deployment Method: Zip Deploy

Zip Deploy was chosen over Git Deploy or FTP because:
- Single command: `az webapp deploy --src-path file.zip --type zip`
- Fast (28KB zip, deployed in ~140 seconds including pip install)
- No need to push code to a remote git repo
- Works identically to the existing Medusa backend's deployment method

**What is excluded from the zip:**
- `venv/` — Azure builds its own virtualenv via `pip install`
- `.env` — secrets are in Azure App Settings, not files
- `__pycache__/`, `*.pyc` — compiled bytecode not needed
- `*.log` — local logs not relevant

### Build Process on Azure (Kudu)

When the zip is deployed, Azure's Kudu build system runs automatically:

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

Total deployment time: **~138 seconds** (most of it is pip install).

### Startup Command Configuration

```bash
az webapp config set \
  --resource-group perfume-staging-rg \
  --name splitbot-app \
  --startup-file "bash startup.sh"
```

This overrides Azure's default startup behavior (which would try to run `gunicorn` on a WSGI file) with our custom script that handles both processes.

### Logging

Azure App Service writes all stdout/stderr to `/home/LogFiles/`. The `startup.sh` additionally writes to `/home/LogFiles/splitbot.log` for bot-specific logs. Logs can be downloaded anytime:

```bash
az webapp log download \
  --resource-group perfume-staging-rg \
  --name splitbot-app \
  --log-file logs.zip
```

### Conflict Resolution

After Azure deployment, the **local bot instance was still running** on the Mac (PID 85082). Telegram only allows **one active polling connection per bot token**. When both were running simultaneously, Azure threw:

```
telegram.error.Conflict: terminated by other getUpdates request;
make sure that only one bot instance is running
```

The local instance was killed (`kill -9 85082`), and Azure continued polling cleanly without interruption.

### Verified Live State

```bash
$ curl https://splitbot-app.azurewebsites.net/health
{"status":"ok"}

$ curl -o /dev/null -w "HTTP %{http_code} | %{time_total}s"
  https://splitbot-app.azurewebsites.net/
HTTP 200 | 0.589s
```

Bot state in Azure logs (confirmed polling):
```
2026-03-08 15:19:09 - HTTP Request: POST api.telegram.org/getUpdates "HTTP/1.1 200 OK"
```

### Redeployment Process (for future updates)

```bash
cd /Users/vaghani/Desktop/splitbot

# 1. Make code changes

# 2. Rebuild zip
zip -r ../splitbot-deploy.zip . \
  --exclude "*.pyc" --exclude "__pycache__/*" \
  --exclude ".env" --exclude "venv/*" --exclude "*.log"

# 3. Deploy
az webapp deploy \
  --resource-group perfume-staging-rg \
  --name splitbot-app \
  --src-path ../splitbot-deploy.zip \
  --type zip

# 4. Monitor
az webapp log download \
  --resource-group perfume-staging-rg \
  --name splitbot-app \
  --log-file logs.zip
```

---

## 9. Notifications System

All notifications are sent through `bot/notifications.py` which handles both channels.

### Telegram Notifications
Uses `bot.send_message(chat_id=telegram_id, text=..., parse_mode="Markdown")` to push messages directly to each user's DM. No group chat required — each person gets a private message.

### Email Notifications
Uses Python's built-in `smtplib` over SSL (port 465) with a Gmail App Password (not the account password — a 16-character app-specific password that can be revoked independently):

```python
with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
    server.sendmail(GMAIL_ADDRESS, to, msg.as_string())
```

All errors are caught and logged — a failed email never crashes the bot.

---

## 10. Scheduling System

Scheduling uses the built-in job queue from `python-telegram-bot` (powered by APScheduler underneath). Jobs are registered in `scheduler/jobs.py` and attached to the bot's `Application` object at startup.

### Weekly Reminder — Every Sunday 6 PM IST
- Calculated as **Sunday 12:30 UTC** (IST = UTC+5:30)
- `job_queue.run_repeating()` with interval of 604,800 seconds (7 days)
- First run: dynamically calculated to be the next Sunday at 12:30 UTC
- Only sends to users whose net balance is negative (they owe money)

### Monthly Report — 1st of Every Month, 9 AM IST
- `job_queue.run_monthly()` with `when=time(3, 30)` (03:30 UTC = 9:00 AM IST)
- Reports on the **previous** month's data
- Sent to all registered users via Telegram + Email
- Includes: total spent, per-person breakdown, top categories, current balances

---

## 11. Security Decisions

| Decision | Reason |
|---|---|
| `.env` excluded from deployment zip | Secrets never travel to Azure in code |
| Azure App Settings for secrets | Encrypted at rest, injected at runtime |
| Gmail App Password (not account password) | Can be revoked without changing Gmail password |
| Supabase service_role key | Bypasses RLS for admin-level DB access from trusted backend |
| No RLS on Supabase tables | All users are trusted internal members — no public access |
| HTTPS only on Azure | Azure enforces HTTPS for all App Service endpoints by default |

---

## 12. What's Live Right Now

| Component | Status | URL / Location |
|---|---|---|
| Telegram Bot | ✅ Running | Azure — polling `api.telegram.org` |
| Health Endpoint | ✅ Live | `https://splitbot-app.azurewebsites.net/health` |
| Supabase DB | ✅ Connected | `aumzmlejfefeofpswcjb.supabase.co` |
| Weekly Reminder | ✅ Scheduled | Every Sunday 6 PM IST |
| Monthly Report | ✅ Scheduled | 1st of every month, 9 AM IST |
| Email Notifications | ✅ Working | via Gmail SMTP (metvaghani1239@gmail.com) |
| Local bot instance | ⛔ Stopped | Azure is the only active instance |

### Cost Summary
| Resource | Cost |
|---|---|
| Azure App Service Plan (B1) | Already paid (shared with perfume backend) |
| splitbot-app Web App | ₹0 extra (same plan) |
| Supabase (free tier) | ₹0 (500MB, always-on) |
| Gmail SMTP | ₹0 |
| **Total additional cost** | **₹0** |

---

*Report generated: March 8, 2026*
*Project location: `/Users/vaghani/Desktop/splitbot/`*
