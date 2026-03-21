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
# PATCH: Fix twscrape xclid parse_anim_idx
# Twitter moved "ondemand.s" from a chunk map key to a value in a name map.
# This patch handles both old and new formats.
# ============================================
def _rextr(s: str, begin: str, end: str, pos: int) -> str | None:
    end_idx = s.rfind(end, 0, pos)
    if end_idx < 0:
        return None
    begin_idx = s.rfind(begin, 0, end_idx)
    if begin_idx < 0:
        return None
    return s[begin_idx + len(begin):end_idx]


def _fextr(s: str, begin: str, end: str, pos: int = 0) -> str | None:
    start = s.find(begin, pos)
    if start < 0:
        return None
    start += len(begin)
    stop = s.find(end, start)
    if stop < 0:
        return None
    return s[start:stop]


async def _patched_parse_anim_idx(text: str) -> list[int]:
    # New format: "ondemand.s" is a value in a name map, hash lives in a second
    # map under the same key further in the HTML.
    ondemand_pos = text.find('"ondemand.s"')
    if ondemand_pos >= 0:
        ondemand_key = _rextr(text, ",", ':', ondemand_pos)
        if ondemand_key:
            ondemand_s = _fextr(text, ondemand_key + ':"', '"', ondemand_pos)
            if ondemand_s:
                url = xclid.script_url("ondemand.s", f"{ondemand_s}a")
                js_text = await xclid.get_tw_page_text(url)
                items = [int(x.group(2)) for x in xclid.INDICES_REGEX.finditer(js_text)]
                if items:
                    return items

    # Fallback: old format where the chunk map contains ondemand.s as a key.
    scripts = list(xclid.get_scripts_list(text))
    scripts = [u for u in scripts if "/ondemand.s." in u]
    if not scripts:
        raise Exception("Couldn't get XClientTxId scripts")
    js_text = await xclid.get_tw_page_text(scripts[0])
    items = [int(x.group(2)) for x in xclid.INDICES_REGEX.finditer(js_text)]
    if not items:
        raise Exception("Couldn't get XClientTxId indices")
    return items


xclid.parse_anim_idx = _patched_parse_anim_idx
logger.info("Applied twscrape xclid patch (parse_anim_idx)")

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
