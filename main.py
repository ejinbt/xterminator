"""
X-Terminator Entry Point
Applies SSL patches and launches the bot.
"""
import os
import ssl
import warnings

# Apply SSL fix before any network imports
warnings.filterwarnings('ignore')
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['PYTHONHTTPSVERIFY'] = '0'

import scraper_utils  # Applies httpx/aiohttp SSL patches

from manager import main

if __name__ == "__main__":
    main()
