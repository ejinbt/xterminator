"""
X-Terminator Configuration
Loads settings from environment variables (.env)
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Twitter / X Scraping
ACCOUNTS_FILE = "accounts.txt"
DB_FILE = "accounts.db"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_IDS = os.getenv("TELEGRAM_CHANNEL_IDS", "")  # Comma-separated channel IDs

# Monitoring
MONITOR_DURATION_HOURS = 3
POLL_INTERVAL_MIN = 900   # 15 minutes
POLL_INTERVAL_MAX = 900   # 15 minutes
