import asyncio
import ssl
import os
import warnings

# ============================================
# APPLY SSL FIX FIRST - BEFORE ANY IMPORTS
# ============================================
warnings.filterwarnings('ignore')
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['PYTHONHTTPSVERIFY'] = '0'

# Apply SSL patch
import scraper_utils

from manager import main

if __name__ == "__main__":
    asyncio.run(main())
