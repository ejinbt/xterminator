"""
Token Tracker - Manages all active token monitors and calculates rankings
"""
import asyncio
import datetime
from dataclasses import dataclass
from typing import Dict, Optional, Set
from loguru import logger

@dataclass
class TokenStats:
    """Stats for a single monitored token"""
    token_address: str
    token_name: Optional[str]
    ticker: Optional[str]
    chat_ids: Set[int]  # All channels tracking this token
    start_time: datetime.datetime
    
    # Tweet counts
    initial_tweets: int = 0
    initial_verified: int = 0
    initial_non_verified: int = 0
    
    total_tweets: int = 0
    total_verified: int = 0
    total_non_verified: int = 0
    
    # Last poll stats
    last_poll_tweets: int = 0
    last_poll_verified: int = 0
    last_poll_non_verified: int = 0
    
    # Status
    is_active: bool = True
    
    def get_monitoring_minutes(self) -> int:
        elapsed = datetime.datetime.now() - self.start_time
        return int(elapsed.total_seconds() / 60)
    
    def get_monitoring_time_str(self) -> str:
        minutes = self.get_monitoring_minutes()
        if minutes >= 60:
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours}h {mins}m"
        return f"{minutes}m"
    
    def get_time_factor(self) -> float:
        """
        First hour counts as 1, then adds monitoring time in hours.
        0 min: 1.0, 15 min: 1.25, 1 hour: 2.0, 3 hours: 4.0
        """
        hours_monitored = self.get_monitoring_minutes() / 60
        return 1.0 + hours_monitored
    
    def get_average_tweet_count(self) -> float:
        time_factor = self.get_time_factor()
        return round(self.total_tweets / time_factor, 1)
    
    def get_new_tweets_count(self) -> int:
        return self.total_tweets - self.initial_tweets
    
    def get_display_name(self) -> str:
        return self.ticker or self.token_name or "Unknown"
    
    def get_short_ca(self) -> str:
        if len(self.token_address) > 20:
            return self.token_address[:8] + "..." + self.token_address[-4:]
        return self.token_address


class TokenTracker:
    """Global tracker for all active token monitors"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.tokens: Dict[str, TokenStats] = {}  # token_address -> TokenStats
        self.mode = "leaderboard"  # "legacy" or "leaderboard"
        self.bot = None
        self.chat_id = None
        self._initialized = True
        logger.info("📊 TokenTracker initialized")
    
    def set_bot(self, bot, chat_id):
        self.bot = bot
        self.chat_id = chat_id
    
    def set_mode(self, mode: str):
        if mode in ["legacy", "leaderboard"]:
            self.mode = mode
            logger.info(f"📊 Mode set to: {mode}")
            return True
        return False
    
    def add_token(self, token_address: str, token_name: str, ticker: str, chat_id: int) -> TokenStats:
        """Add a new token or add a channel to an existing token"""
        if token_address in self.tokens:
            # Token already exists, just add this channel
            self.tokens[token_address].chat_ids.add(chat_id)
            return self.tokens[token_address]
        
        stats = TokenStats(
            token_address=token_address,
            token_name=token_name,
            ticker=ticker,
            chat_ids={chat_id},
            start_time=datetime.datetime.now()
        )
        self.tokens[token_address] = stats
        logger.info(f"📊 Tracking token: {stats.get_display_name()} ({token_address[:16]}...)")
        return stats
    
    def add_channel_to_token(self, token_address: str, chat_id: int):
        """Add a channel to an existing token"""
        if token_address in self.tokens:
            self.tokens[token_address].chat_ids.add(chat_id)
    
    def update_initial(self, token_address: str, total: int, verified: int, non_verified: int):
        if token_address in self.tokens:
            stats = self.tokens[token_address]
            stats.initial_tweets = total
            stats.initial_verified = verified
            stats.initial_non_verified = non_verified
            stats.total_tweets = total
            stats.total_verified = verified
            stats.total_non_verified = non_verified
    
    def update_poll(self, token_address: str, new_tweets: int, new_verified: int, new_non_verified: int):
        if token_address in self.tokens:
            stats = self.tokens[token_address]
            stats.last_poll_tweets = new_tweets
            stats.last_poll_verified = new_verified
            stats.last_poll_non_verified = new_non_verified
            stats.total_tweets += new_tweets
            stats.total_verified += new_verified
            stats.total_non_verified += new_non_verified
    
    def mark_complete(self, token_address: str):
        if token_address in self.tokens:
            self.tokens[token_address].is_active = False
    
    def remove_token(self, token_address: str):
        if token_address in self.tokens:
            del self.tokens[token_address]
    
    def get_active_tokens(self, chat_id: int = None) -> list:
        """Get active tokens, optionally filtered by channel"""
        if chat_id:
            return [s for s in self.tokens.values() if s.is_active and chat_id in s.chat_ids]
        return [s for s in self.tokens.values() if s.is_active]
    
    def get_top_tokens(self, limit: int = 30, chat_id: int = None) -> list:
        """Get top tokens sorted by average tweet count, optionally filtered by channel"""
        active = self.get_active_tokens(chat_id)
        sorted_tokens = sorted(active, key=lambda x: x.get_average_tweet_count(), reverse=True)
        return sorted_tokens[:limit]
    
    def get_stats(self, token_address: str) -> Optional[TokenStats]:
        return self.tokens.get(token_address)
    
    async def send_leaderboard(self, bot=None, chat_id=None):
        """Send the top 30 leaderboard for a specific channel"""
        bot = bot or self.bot
        chat_id = chat_id or self.chat_id
        
        if not bot or not chat_id:
            logger.warning("No bot/chat_id set for leaderboard")
            return
        
        # Get top tokens FOR THIS CHANNEL only
        top_tokens = self.get_top_tokens(30, chat_id=chat_id)
        
        if not top_tokens:
            logger.info(f"No active tokens for chat {chat_id}")
            return
        
        # Build message
        msg = f"📊 **TOP {len(top_tokens)} TOKENS**\n\n"
        
        for i, stats in enumerate(top_tokens, 1):
            avg = stats.get_average_tweet_count()
            name = stats.get_display_name()
            ca = stats.token_address
            total = stats.total_tweets
            last_15 = stats.last_poll_tweets
            running = stats.get_new_tweets_count()
            verified = stats.total_verified
            regular = stats.total_non_verified
            mon_time = stats.get_monitoring_time_str()
            
            if i == 1:
                rank = "🥇"
            elif i == 2:
                rank = "🥈"
            elif i == 3:
                rank = "🥉"
            else:
                rank = f"{i}."
            
            msg += (
                f"{rank} **{name}**\n"
                f"`{ca}`\n"
                f"📈 Avg: **{avg}** | Total: **{total}** | +{last_15} (15m)\n"
                f"🆕 New: {running} | ✅ {verified} | 👤 {regular} | ⏱️ {mon_time}\n\n"
            )
        
        msg += f"🔄 _Updates every 15 min_"
        
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode='Markdown'
            )
            logger.info(f"📊 Leaderboard sent to {chat_id} ({len(top_tokens)} tokens)")
        except Exception as e:
            logger.error(f"Failed to send leaderboard to {chat_id}: {e}")


# Global instance
tracker = TokenTracker()
