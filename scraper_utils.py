"""
Scraper Utilities - Account loading and SSL patches for proxy support.
"""
import asyncio
import os
import ssl
import warnings

# SSL fix for Bright Data / intercepting proxies
# This disables SSL verification globally since Bright Data
# uses its own certificate for HTTPS interception

# Disable SSL warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
warnings.filterwarnings('ignore', category=DeprecationWarning)

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Disable SSL verification globally for all Python SSL connections
ssl._create_default_https_context = ssl._create_unverified_context

# Set environment variables
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''

# Patch httpx (used by twscrape)
import httpx
_original_httpx_client = httpx.AsyncClient.__init__
def _patched_httpx_init(self, *args, **kwargs):
    kwargs['verify'] = False
    return _original_httpx_client(self, *args, **kwargs)
httpx.AsyncClient.__init__ = _patched_httpx_init

# Patch httpx sync client too
_original_httpx_sync = httpx.Client.__init__
def _patched_httpx_sync_init(self, *args, **kwargs):
    kwargs['verify'] = False
    return _original_httpx_sync(self, *args, **kwargs)
httpx.Client.__init__ = _patched_httpx_sync_init

# Patch aiohttp (used by telegram bot)
try:
    import aiohttp
    _original_aiohttp_session = aiohttp.ClientSession.__init__
    def _patched_aiohttp_init(self, *args, **kwargs):
        if 'connector' not in kwargs or kwargs['connector'] is None:
            kwargs['connector'] = aiohttp.TCPConnector(ssl=False)
        return _original_aiohttp_session(self, *args, **kwargs)
    aiohttp.ClientSession.__init__ = _patched_aiohttp_init
except ImportError:
    pass

# Now import twscrape
from twscrape import API
from twscrape import xclid
from loguru import logger
import config
import json
import re

# ============================================
# PATCH: Fix twscrape xclid script parsing
# Twitter changes their page structure frequently, breaking the split.
# This patch handles both the old and new formats gracefully.
# ============================================
def _script_url(k: str, v: str):
    return f"https://abs.twimg.com/responsive-web/client-web/{k}.{v}.js"

_original_get_scripts_list = xclid.get_scripts_list

def _patched_get_scripts_list(text: str):
    # Try multiple known split patterns (Twitter changes these)
    split_patterns = [
        ('e=>e+"."+', '[e]+"a.js"'),
        ('e=>e+"."+', '+"a.js"'),
    ]

    scripts_str = None
    for start_pat, end_pat in split_patterns:
        if start_pat in text:
            try:
                scripts_str = text.split(start_pat)[1].split(end_pat)[0]
                break
            except IndexError:
                continue

    if scripts_str is None:
        # Fallback: try to find script URLs directly via regex
        logger.warning("twscrape: Could not parse scripts list with known patterns, trying regex fallback")
        for match in re.finditer(r'https://abs\.twimg\.com/responsive-web/client-web/[^"\']+\.js', text):
            yield match.group(0)
        return

    try:
        for k, v in json.loads(scripts_str).items():
            yield _script_url(k, f"{v}a")
    except json.decoder.JSONDecodeError:
        # Fix unquoted keys
        fixed = re.sub(
            r'([,\{])(\s*)([\w]+_[\w_]+)(\s*):',
            r'\1\2"\3"\4:',
            scripts_str
        )
        try:
            for k, v in json.loads(fixed).items():
                yield _script_url(k, f"{v}a")
        except json.decoder.JSONDecodeError:
            logger.error("twscrape: Failed to parse scripts JSON even after fix")

xclid.get_scripts_list = _patched_get_scripts_list
logger.info("Applied twscrape xclid patch")

async def load_accounts():
    """
    Loads accounts from accounts.txt into the twscrape database.
    Format expected: 
    1. user:pass:email:email_pass:proxy
    2. user:pass:email:email_pass (no proxy)
    3. user::auth_token:ct0:proxy (token login)
    
    Note: Proxy URLs contain colons, so we handle them specially.
    """
    api = API(config.DB_FILE)
    
    if not os.path.exists(config.ACCOUNTS_FILE):
        logger.error(f"{config.ACCOUNTS_FILE} not found. Please create it.")
        return

    count = 0
    with open(config.ACCOUNTS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Handle proxy URLs with colons by splitting carefully
            # Check if line contains http:// or https://
            proxy = None
            if "http://" in line:
                main_part, proxy = line.rsplit("http://", 1)
                proxy = "http://" + proxy
                main_part = main_part.rstrip(":")  # Remove trailing colon
            elif "https://" in line:
                main_part, proxy = line.rsplit("https://", 1)
                proxy = "https://" + proxy
                main_part = main_part.rstrip(":")  # Remove trailing colon
            else:
                main_part = line

            parts = main_part.split(":")
            
            # Basic parsing logic
            try:
                # Token Login detection: Password empty, Email is AuthToken, EmailPass is CT0
                # username::auth_token:ct0[:proxy]
                if len(parts) >= 4 and parts[1] == "":
                    username = parts[0]
                    token = parts[2]
                    ct0 = parts[3]
                    
                    cookies = f"auth_token={token}; ct0={ct0}"
                    logger.info(f"Adding account {username} with proxy: {proxy}")
                    await api.pool.add_account(username, "", "", "", cookies=cookies, proxy=proxy)
                    count += 1
                
                # Standard Login: username:password:email:email_pass[:proxy]
                elif len(parts) >= 4:
                    username = parts[0]
                    password = parts[1]
                    email = parts[2]
                    email_pass = parts[3]
                    
                    logger.info(f"Adding account {username} with proxy: {proxy}")
                    await api.pool.add_account(username, password, email, email_pass, proxy=proxy)
                    count += 1
            except Exception as e:
                logger.error(f"Failed to parse line: {line} - {e}")

    logger.info(f"Loaded {count} accounts into the pool.")
    
    # Reset stale locks so accounts aren't stuck from previous crashes
    logger.info("Resetting account locks...")
    await api.pool.reset_locks()

    # Login check
    logger.info("Verifying accounts...")
    await api.pool.login_all()

def get_api():
    return API(config.DB_FILE)
