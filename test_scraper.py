import asyncio
from scraper import TwitterScraper
import config
from loguru import logger

async def main():
    logger.info("Starting Twitter Search Scraper...")
    
    scraper = TwitterScraper()
    
    # 1. Initialize (Add account if needed, Login)
    await scraper.initialize()
    
    # 2. Validate Session (Check cookies)
    is_valid = await scraper.validate_session()
    
    if is_valid:
        # 3. Perform Search
        query = getattr(config, 'SEARCH_QUERY', 'crypto')
        limit = getattr(config, 'LIMIT', 50)
        
        logger.info(f"Executing search: {query}")
        results = await scraper.search(query, limit=limit)
        
        # 4. Output Results
        scraper.save_results(results, "results.csv")
        scraper.save_results(results, "results.json")
    else:
        logger.error("Session validation failed. Aborting scrape.")

if __name__ == "__main__":
    asyncio.run(main())
