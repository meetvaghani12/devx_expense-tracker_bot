"""
Minimal HTTP server to keep Azure App Service happy.
Azure requires an HTTP server listening on port 8000.
The actual Telegram bot runs as a background process.
"""
from flask import Flask, jsonify
import subprocess
import os

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "running", "service": "SplitBot"})

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200
