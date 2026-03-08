#!/bin/bash
# Azure App Service startup script for SplitBot

LOG="/home/LogFiles/splitbot.log"
mkdir -p /home/LogFiles

echo "=== SplitBot Startup $(date) ===" | tee -a "$LOG"
echo "Python: $(python --version)" | tee -a "$LOG"

# Start the Telegram bot in background
echo "Starting Telegram bot..." | tee -a "$LOG"
python run.py >> "$LOG" 2>&1 &
BOT_PID=$!
echo "Bot PID: $BOT_PID" | tee -a "$LOG"

# Start the HTTP health server (required by Azure App Service)
echo "Starting health server on port 8000..." | tee -a "$LOG"
gunicorn health:app --bind 0.0.0.0:8000 --workers 1 --timeout 120 2>&1 | tee -a "$LOG"
