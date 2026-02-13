import os
from dotenv import load_dotenv

load_dotenv()

# Twitter Configuration
# accounts.txt format: username:password:email:email_password:proxy
# OR for token login: username::token:ct0:proxy (we will parse this logic)
ACCOUNTS_FILE = "accounts.txt"
DB_FILE = "accounts.db"

# Telegram Configuration
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_CHANNEL_IDS = os.getenv("TELEGRAM_CHANNEL_IDS", "") # Comma-separated: -100123,-100456,-100789
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Monitoring Configuration
MONITOR_DURATION_HOURS = 3
POLL_INTERVAL_MIN = 900  # 15 minutes in seconds
POLL_INTERVAL_MAX = 900  # 15 minutes in seconds

# Default Search Configuration
SEARCH_QUERY = "crypto" # Default fallback query
LIMIT = 50
