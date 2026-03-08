#!/bin/bash
# Run SplitBot
cd "$(dirname "$0")"
source venv/bin/activate
python bot/main.py
