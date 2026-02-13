import asyncio
import datetime
import os
import random
import pandas as pd
from loguru import logger

# Import scraper_utils FIRST to apply SSL patch before twscrape loads
from scraper_utils import get_api
import scraper  # This imports the patched scraper.py to apply the monkey patch

from twscrape import API, gather
import config
from token_tracker import tracker


class TokenMonitor:
    def __init__(self, token_keyword, bot=None, chat_id=None, token_name=None):
        self.token = token_keyword
        self.token_name = token_name  # e.g., "$ELON" or "Elon Coin"
        self.api = get_api()
        self.start_time = datetime.datetime.now()
        self.end_time = self.start_time + datetime.timedelta(hours=config.MONITOR_DURATION_HOURS)
        self.results = []
        self.seen_ids = set()  # Track seen tweet IDs
        self.filename = f"monitor_{self.token}_{int(self.start_time.timestamp())}.csv"
        
        # Telegram bot reference for sending updates
        self.bot = bot
        self.chat_id = chat_id
        
        # Counters - Total
        self.initial_count_value = 0
        self.new_mentions_count = 0
        
        # Counters - Verified vs Non-Verified
        self.initial_verified = 0
        self.initial_non_verified = 0
        self.new_verified = 0
        self.new_non_verified = 0
        
        # Register with tracker
        self.stats = tracker.add_token(
            token_address=self.token,
            token_name=self.token_name,
            ticker=self.token_name,  # We use token_name as ticker
            chat_id=chat_id
        )
    
    def get_display_name(self):
        """Get formatted display name with token name and CA"""
        token_short = self.token[:16] + "..." if len(self.token) > 16 else self.token
        if self.token_name:
            return f"**{self.token_name}** (`{token_short}`)"
        return f"`{token_short}`"
    
    def get_elapsed_time(self):
        """Get elapsed monitoring time as formatted string"""
        elapsed = datetime.datetime.now() - self.start_time
        total_seconds = int(elapsed.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"
        
    async def start(self):
        logger.info(f"[{self.token}] Starting monitor task. Duration: {config.MONITOR_DURATION_HOURS} hours.")
        
        # Monitoring Loop (initial_count is called separately before start())
        while datetime.datetime.now() < self.end_time:
            # Wait for next poll
            sleep_time = random.randint(config.POLL_INTERVAL_MIN, config.POLL_INTERVAL_MAX)
            logger.info(f"[{self.token}] Sleeping for {sleep_time}s...")
            await asyncio.sleep(sleep_time)
            
            await self.poll_new_mentions()
            
        # Mark complete
        tracker.mark_complete(self.token)
        
        # Send final summary (only in legacy mode)
        if tracker.mode == "legacy":
            await self.send_final_summary()
        
        logger.info(f"[{self.token}] Monitoring finished.")

    async def initial_count(self):
        logger.info(f"[{self.token}] Checking existing mentions on X...")
        count = 0
        verified = 0
        non_verified = 0
        try:
            query = f"{self.token}"
            logger.info(f"[{self.token}] Running search query: '{query}'")
            
            try:
                async for tweet in self.api.search(query, limit=500):
                    count += 1
                    self.seen_ids.add(tweet.id)
                    
                    # Check if user is verified (blue = Twitter Blue, verified = legacy)
                    is_verified = getattr(tweet.user, 'verified', False) or getattr(tweet.user, 'blue', False)
                    if is_verified:
                        verified += 1
                    else:
                        non_verified += 1
                    
                    if count % 50 == 0:
                        logger.info(f"[{self.token}] Found {count} tweets so far (✓{verified} / ○{non_verified})...")
            except asyncio.TimeoutError:
                logger.warning(f"[{self.token}] Search timed out after finding {count} tweets")
            
            logger.info(f"[{self.token}] Search complete. Found {count} tweets (✓{verified} verified / ○{non_verified} non-verified).")
            self.initial_count_value = count
            self.initial_verified = verified
            self.initial_non_verified = non_verified
            
            # Update tracker
            tracker.update_initial(self.token, count, verified, non_verified)
            
            return count, verified, non_verified
            
        except Exception as e:
            logger.error(f"[{self.token}] Initial count failed: {e}")
            import traceback
            traceback.print_exc()
            return 0, 0, 0

    async def poll_new_mentions(self):
        logger.info(f"[{self.token}] Polling for new mentions...")
        try:
            query = f"{self.token} -filter:retweets"
            new_tweets = []
            new_verified = 0
            new_non_verified = 0
            
            async for tweet in self.api.search(query, limit=50):
                # Skip if already seen
                if tweet.id in self.seen_ids:
                    continue
                
                self.seen_ids.add(tweet.id)
                
                # Check if user is verified (blue = Twitter Blue, verified = legacy)
                is_verified = getattr(tweet.user, 'verified', False) or getattr(tweet.user, 'blue', False)
                if is_verified:
                    new_verified += 1
                else:
                    new_non_verified += 1
                
                data = {
                    "id": tweet.id,
                    "username": tweet.user.username,
                    "text": tweet.rawContent,
                    "date": tweet.date,
                    "likes": tweet.likeCount,
                    "replies": tweet.replyCount,
                    "retweets": tweet.retweetCount,
                    "url": tweet.url,
                    "verified": is_verified
                }
                new_tweets.append(data)
                self.results.append(data)
            
            if new_tweets:
                self.new_mentions_count += len(new_tweets)
                self.new_verified += new_verified
                self.new_non_verified += new_non_verified
                logger.info(f"[{self.token}] Found {len(new_tweets)} new mentions (✓{new_verified} / ○{new_non_verified}). Total new: {self.new_mentions_count}")
                self.save_batch(new_tweets)
                
                # Update tracker
                tracker.update_poll(self.token, len(new_tweets), new_verified, new_non_verified)
                
                # Only send individual notifications in legacy mode
                if tracker.mode == "legacy":
                    await self.notify_new_mentions(new_tweets)
            else:
                # Still update tracker with 0 new tweets
                tracker.update_poll(self.token, 0, 0, 0)
                logger.info(f"[{self.token}] No new mentions.")

        except Exception as e:
            logger.error(f"[{self.token}] Polling failed: {e}")

    async def notify_new_mentions(self, new_tweets):
        """Send new mentions to Telegram group - LEGACY MODE ONLY"""
        if not self.bot or not self.chat_id:
            return
        
        try:
            display_name = self.get_display_name()
            elapsed_time = self.get_elapsed_time()
            total_count = self.initial_count_value + self.new_mentions_count
            total_verified = self.initial_verified + self.new_verified
            total_non_verified = self.initial_non_verified + self.new_non_verified
            
            # Count verified in this batch
            batch_verified = sum(1 for t in new_tweets if t.get('verified'))
            batch_non_verified = len(new_tweets) - batch_verified
            
            # Sort tweets by engagement (likes + retweets) in descending order
            sorted_tweets = sorted(
                new_tweets, 
                key=lambda t: (t.get('likes', 0) + t.get('retweets', 0)), 
                reverse=True
            )
            
            # Build message
            msg = (
                f"🆕 **{len(new_tweets)} New Mentions**\n"
                f"🪙 {display_name}\n\n"
                f"📊 Total: **{total_count}** | ✅ {total_verified} | 👤 {total_non_verified}\n"
                f"⏱️ {elapsed_time} | 🔸 Batch: +{len(new_tweets)}\n\n"
                f"🔥 **Top Tweets:**\n"
            )
            
            # Show tweets sorted by engagement
            for i, tweet in enumerate(sorted_tweets[:5]):
                username = tweet['username']
                text = tweet['text'].replace('\n', ' ')
                text = text[:100] + "..." if len(text) > 100 else text
                likes = tweet['likes']
                retweets = tweet['retweets']
                url = tweet['url']
                verified_badge = "✅" if tweet.get('verified') else ""
                
                msg += f"\n{verified_badge}@{username} | ❤️{likes} 🔄{retweets}\n"
                msg += f"_{text}_\n"
                msg += f"[View]({url})\n"
            
            if len(sorted_tweets) > 5:
                msg += f"\n_+{len(sorted_tweets) - 5} more_"
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=msg,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"[{self.token}] Failed to send Telegram notification: {e}")

    async def send_final_summary(self):
        """Send final summary when monitoring ends - LEGACY MODE ONLY"""
        if not self.bot or not self.chat_id:
            return
        
        try:
            display_name = self.get_display_name()
            total_count = self.initial_count_value + self.new_mentions_count
            total_verified = self.initial_verified + self.new_verified
            total_non_verified = self.initial_non_verified + self.new_non_verified
            
            # Determine sentiment emoji based on growth
            if self.new_mentions_count > 50:
                sentiment = "🚀 Explosive"
            elif self.new_mentions_count > 20:
                sentiment = "🔥 High"
            elif self.new_mentions_count > 5:
                sentiment = "📈 Moderate"
            else:
                sentiment = "📊 Low"
            
            msg = (
                f"🏁 **MONITORING COMPLETE**\n\n"
                f"🪙 {display_name}\n\n"
                f"📋 Initial: **{self.initial_count_value}** (✅{self.initial_verified} 👤{self.initial_non_verified})\n"
                f"🆕 New: **{self.new_mentions_count}** (✅{self.new_verified} 👤{self.new_non_verified})\n\n"
                f"📈 **Total: {total_count}**\n"
                f"✅ Verified: {total_verified} | 👤 Regular: {total_non_verified}\n\n"
                f"📊 Activity: {sentiment}\n"
                f"⏱️ Duration: {config.MONITOR_DURATION_HOURS}h\n\n"
                f"_Post token again to rescan_"
            )
            
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=msg,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"[{self.token}] Failed to send final summary: {e}")

    def save_batch(self, new_data):
        df = pd.DataFrame(new_data)
        # Append to CSV
        hdr = not os.path.exists(self.filename)
        df.to_csv(self.filename, mode='a', header=hdr, index=False)
        logger.info(f"[{self.token}] Saved batch to {self.filename}")
