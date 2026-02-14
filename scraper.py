"""
Twitter Scraper - twscrape wrapper with SSL and JSON parsing patches.
"""
import asyncio
import json
import random
import re
import ssl

import httpx
import pandas as pd
from twscrape import API
from twscrape.logger import set_log_level

# SSL patch for proxy support
# Create SSL context that doesn't verify certificates
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Store original AsyncClient
_original_async_client = httpx.AsyncClient

# Create patched AsyncClient that disables SSL verification
class PatchedAsyncClient(_original_async_client):
    def __init__(self, *args, **kwargs):
        # Force disable SSL verification
        kwargs['verify'] = False
        super().__init__(*args, **kwargs)

# Apply the patch
httpx.AsyncClient = PatchedAsyncClient

# ============================================
# PATCH 2: Fix JSON parsing for malformed keys
# ============================================
from twscrape import xclid

def script_url(k: str, v: str):
    return f"https://abs.twimg.com/responsive-web/client-web/{k}.{v}.js"

def patched_get_scripts_list(text: str):
    scripts = text.split('e=>e+"."+')[1].split('[e]+"a.js"')[0]
    
    try:
        for k, v in json.loads(scripts).items():
            yield script_url(k, f"{v}a")
    except json.decoder.JSONDecodeError:
        # Fix unquoted keys like: node_modules_pnpm_ws_8_18_0_node_modules_ws_browser_js
        fixed_scripts = re.sub(
            r'([,\{])(\s*)([\w]+_[\w_]+)(\s*):',
            r'\1\2"\3"\4:',
            scripts
        )
        for k, v in json.loads(fixed_scripts).items():
            yield script_url(k, f"{v}a")

# Apply the patch
xclid.get_scripts_list = patched_get_scripts_list

from loguru import logger
import config

class TwitterScraper:
    def __init__(self):
        self.api = API(config.DB_FILE)
        set_log_level("INFO")

    async def initialize(self):
        """
        Initialize the scraper: add account and log in.
        """
        logger.info("Initializing Twitter Scraper...")
        
        # Check if we have single-account config available
        username = getattr(config, 'USERNAME', None)
        if not username:
             logger.warning("No single account configured in config.py. Skipping single-account init.")
             # We assume accounts are managed via accounts.txt or CLI
             await self.api.pool.login_all()
             return

        # Check if account exists, add if not
        accounts = await self.api.pool.accounts_info()
        found = False
        for acc in accounts:
            if acc['username'] == username:
                found = True
                break
        
        # Check if proxy is configured
        proxy = None
        if hasattr(config, 'PROXY_URL') and config.PROXY_URL:
            proxy = config.PROXY_URL

        if not found:
            logger.info(f"Adding account {username} with Auth Tokens...")
            # Construct cookie string from tokens
            auth_token = getattr(config, 'AUTH_TOKEN', '')
            ct0 = getattr(config, 'CT0', '')
            cookies = f"auth_token={auth_token}; ct0={ct0}"
            await self.api.pool.add_account(
                username, 
                "", # No password needed
                "", # No email needed
                "", # No email password needed
                cookies=cookies,
                proxy=proxy
            )
        
        # We ensure the proxy is in the pool. In a single-account setup, 
        # twscrape will use available proxies.
        # if config.PROXY_URL and config.PROXY_URL != "http://user:pass@host:port":
        #    logger.info("Configuring proxy...")
        #    await self.api.pool.add_proxy(config.PROXY_URL)
        
        logger.info("Logging in...")
        try:
            # force_login will use the proxy if we set it up correctly, 
            # but twscrape manages proxies in the DB.
            # Let's verify login status.
            await self.api.pool.login_all()
            logger.info("Login successful.")
        except Exception as e:
            logger.error(f"Login failed: {e}")
            raise

    async def validate_session(self):
        """
        Validate that the cookies/session are active.
        """
        logger.info("Validating session...")
        try:
            username = getattr(config, 'USERNAME', None)
            if not username:
                 # If no specific user, we just check if ANY account is active
                 accounts = await self.api.pool.accounts_info()
                 active_count = sum(1 for acc in accounts if acc['active'])
                 if active_count > 0:
                     logger.info(f"Found {active_count} active accounts in pool.")
                     return True
                 else:
                     logger.warning("No active accounts found in pool.")
                     return False

            # A simple way to validate is to fetch a user profile or similar lightweight call
            # using the specific account credentials managed by the pool
            # The pool automatically handles token rotation and validation on requests.
            # We can check account status from the pool.
            accounts = await self.api.pool.accounts_info()
            for acc in accounts:
                if acc['username'] == username:
                    if acc['active']:
                        logger.info(f"Session for {username} is valid.")
                        return True
                    else:
                        logger.warning(f"Session for {username} is inactive/locked.")
                        return False
            logger.warning("Account not found in pool.")
            return False
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return False

    async def search(self, query: str, limit: int = 50):
        """
        Perform the search with rate limit handling and random delays.
        """
        logger.info(f"Starting search for: '{query}' (Limit: {limit})")
        results = []
        
        try:
            # gather(self.api.search(...)) is the standard way, 
            # but using the generator allows us to handle items one by one and sleep
            async for tweet in self.api.search(query, limit=limit):
                data = {
                    "id": tweet.id,
                    "username": tweet.user.username,
                    "text": tweet.rawContent,
                    "date": tweet.date,
                    "likes": tweet.likeCount,
                    "retweets": tweet.retweetCount,
                    "replies": tweet.replyCount,
                    "url": tweet.url
                }
                results.append(data)
                
                # "Stealth" delay: Random sleep between 0.5s and 2s
                # Note: twscrape is fast and async, adding delay here slows it down 
                # but mimics human reading speed slightly better if processing stream.
                # However, the internal API is robust. We'll add a small jitter.
                await asyncio.sleep(random.uniform(0.1, 0.5))

            logger.info(f"Search complete. Found {len(results)} tweets.")
            return results

        except Exception as e:
            logger.error(f"An error occurred during search: {e}")
            # In a real scenario, you'd check for specific rate limit exceptions here
            # twscrape handles 429 retries internally to some extent, 
            # but if it propagates, we should catch it.
            if "429" in str(e):
                logger.warning("Rate limit hit (429). Sleeping for 15 minutes...")
                await asyncio.sleep(15 * 60)
                # Retry strategy could be implemented here
            return results

    def save_results(self, results, filename="tweets.csv"):
        """
        Save results to a CSV/JSON file.
        """
        if not results:
            logger.warning("No results to save.")
            return

        df = pd.DataFrame(results)
        if filename.endswith(".json"):
            df.to_json(filename, orient="records", lines=True, date_format="iso")
        else:
            df.to_csv(filename, index=False)
        
        logger.info(f"Results saved to {filename}")

if __name__ == "__main__":
    # This block is for testing scraper.py directly
    async def main():
        scraper = TwitterScraper()
        await scraper.initialize()
        valid = await scraper.validate_session()
        if valid:
            data = await scraper.search(config.SEARCH_QUERY, config.LIMIT)
            scraper.save_results(data)
    
    asyncio.run(main())
