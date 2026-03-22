"""
X-Terminator Telegram Bot
Handles message processing, commands, and token monitoring orchestration.
"""
import asyncio
import datetime
import os
import re
import sys
from typing import Optional

import aiohttp

# Import scraper_utils FIRST to apply SSL patch
from scraper_utils import load_accounts

import config
from loguru import logger
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler, filters
from monitor import TokenMonitor
from token_tracker import tracker

# Token info APIs (order: GeckoTerminal → DexScreener fallback)
GECKOTERMINAL_API = "https://api.geckoterminal.com/api/v2/search/pools?query={token}&page=1"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/search?q={token}"

# Per-chat leaderboard last-send times (chat_id -> datetime)
CHAT_LEADERBOARD_LAST_SENT = {}

# TOKEN CACHE
TOKEN_INFO_CACHE = {}  # token_address -> (name, ticker, chain)

# Per-chat poll interval overrides (chat_id -> seconds)
CHAT_POLL_INTERVAL = {}
# Running monitors per chat (chat_id -> set[TokenMonitor])
CHAT_MONITORS = {}

# Sleep control
SLEEP_UNTIL: Optional[datetime.datetime] = None
BOT_START_TIME: Optional[datetime.datetime] = None

def extract_token(text):
    """
    Extracts a token address from the message.
    Supports:
    - Pump.fun Solana Addresses (ending with 'pump')
    - General Solana Addresses (Base58, 32-44 chars)
    - EVM Addresses (Hex, 42 chars starting with 0x)
    """
    if not text: return None

    # 1. Pump.fun Address (priority - ends with 'pump')
    pump_match = re.search(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}pump\b', text)
    if pump_match:
        return pump_match.group(0)

    # 2. General Solana Address (Base58, 32-44 chars)
    sol_match = re.search(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b', text)
    if sol_match:
        return sol_match.group(0)

    # 3. EVM Address (0x...)
    evm_match = re.search(r'\b0x[a-fA-F0-9]{40}\b', text)
    if evm_match:
        return evm_match.group(0)
    
    return None

async def get_token_info(token_address: str):
    """
    Fetch token info. Tries GeckoTerminal first (no Cloudflare), 
    falls back to DexScreener.
    Returns (name, ticker, chain) or (None, None, None).
    """
    # Check cache first
    if token_address in TOKEN_INFO_CACHE:
        logger.info(f"📦 Cache hit for {token_address[:16]}...")
        return TOKEN_INFO_CACHE[token_address]
    
    # Try GeckoTerminal first (no Cloudflare blocking from VPS)
    result = await _fetch_from_geckoterminal(token_address)
    if result[0] or result[1]:  # Got a name or ticker
        TOKEN_INFO_CACHE[token_address] = result
        return result
    
    # Fallback: DexScreener (may be blocked by Cloudflare on VPS)
    logger.info(f"🔄 GeckoTerminal missed, trying DexScreener fallback...")
    result = await _fetch_from_dexscreener(token_address)
    if result[0] or result[1]:
        TOKEN_INFO_CACHE[token_address] = result
        return result
    
    return None, None, None

async def _fetch_from_geckoterminal(token_address: str):
    """GeckoTerminal pool search - free, no Cloudflare blocking from VPS"""
    url = GECKOTERMINAL_API.format(token=token_address)
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                if response.status == 200:
                    data = await response.json()
                    pools = data.get('data', [])
                    
                    if pools:
                        pool = pools[0]
                        attrs = pool.get('attributes', {})
                        
                        # Pool name format: "TOKEN / SOL" or "TOKEN / USDT"
                        pool_name = attrs.get('name', '')
                        name = pool_name.split(' / ')[0].strip() if ' / ' in pool_name else pool_name
                        
                        # Chain from base_token ID: "solana_xxx" or "eth_xxx"
                        base_token_id = (pool.get('relationships', {})
                                         .get('base_token', {})
                                         .get('data', {})
                                         .get('id', ''))
                        chain = base_token_id.split('_')[0] if '_' in base_token_id else 'unknown'
                        
                        ticker = f"${name}" if name else None
                        
                        logger.info(f"✅ GeckoTerminal: {name} ({ticker}) on {chain}")
                        return name, ticker, chain
                    else:
                        logger.warning(f"⚠️ Token not found on GeckoTerminal")
                        return None, None, None
                
                elif response.status == 429:
                    logger.warning(f"⚠️ GeckoTerminal rate limited (429)")
                    return None, None, None
                else:
                    logger.warning(f"⚠️ GeckoTerminal HTTP {response.status}")
                    return None, None, None
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ GeckoTerminal timeout")
        return None, None, None
    except Exception as e:
        logger.error(f"❌ GeckoTerminal error: {e}")
        return None, None, None

async def _fetch_from_dexscreener(token_address: str):
    """DexScreener fallback with retry + backoff (may be blocked by Cloudflare on VPS)"""
    url = DEXSCREENER_API.format(token=token_address)
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            try:
                logger.info(f"🔍 DexScreener attempt {attempt + 1}/3...")
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get('pairs', [])
                        
                        if pairs and len(pairs) > 0:
                            pair = pairs[0]
                            base_token = pair.get('baseToken', {})
                            name = base_token.get('name') or None
                            symbol = base_token.get('symbol') or None
                            chain = pair.get('chainId', 'unknown')
                            ticker = f"${symbol}" if symbol else None
                            
                            logger.info(f"✅ DexScreener: {name} ({ticker}) on {chain}")
                            return name, ticker, chain
                        else:
                            logger.warning(f"⚠️ Token not found on DexScreener")
                            return None, None, None
                    
                    elif response.status == 429 or response.status == 1015:
                        wait = 30 * (attempt + 1)
                        logger.warning(f"⚠️ DexScreener {response.status} rate limit. Waiting {wait}s...")
                        await asyncio.sleep(wait)
                        continue
                    
                    else:
                        logger.warning(f"⚠️ DexScreener HTTP {response.status}")
                        if attempt < 2:
                            await asyncio.sleep(5)
                            continue
                        return None, None, None
            
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ DexScreener timeout (attempt {attempt + 1})")
                if attempt < 2:
                    await asyncio.sleep(5)
                    continue
            except Exception as e:
                logger.error(f"❌ DexScreener error: {e}")
                if attempt < 2:
                    await asyncio.sleep(5)
                    continue
    
    return None, None, None



# Store channel IDs as set globally after parsing
CHANNEL_IDS = set()  # Empty set = listen to all chats

# Track processed CAs per channel: {token_address: set(chat_ids)}
PROCESSED_CAS = {}  # token -> set of chat_ids that already got notified

# Helpers
def is_sleeping():
    if not SLEEP_UNTIL:
        return False
    return datetime.datetime.utcnow() < SLEEP_UNTIL

def sleep_until_str():
    if not SLEEP_UNTIL:
        return "not sleeping"
    return SLEEP_UNTIL.strftime("%H:%M UTC")

async def send_initial_notification(bot, chat_id: int, token: str, name: str, ticker: str, 
                                     count: int, verified: int, non_verified: int):
    """Send the initial token notification (both modes)"""
    display = ticker or name or "Unknown"
    
    msg = (
        f"🆕 **NEW TOKEN DETECTED**\n\n"
        f"🪙 **{display}**\n"
        f"📍 `{token}`\n\n"
        f"📊 Existing: **{count}**\n"
        f"✅ Verified: **{verified}** | 👤 Regular: **{non_verified}**\n\n"
        f"⏳ Monitoring: {config.MONITOR_DURATION_HOURS}h | 🔔 Updates: {CHAT_POLL_INTERVAL.get(chat_id, config.POLL_INTERVAL_MIN) // 60}m"
    )
    
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=msg,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Failed to send initial notification: {e}")

async def start_monitoring(token: str, token_name: str, ticker: str, bot, chat_id: int):
    """Start monitoring a token with the gathered info - fully non-blocking"""

    # Format display name (prefer ticker, fallback to name)
    display = ticker or token_name or None
    token_short = token[:16] + "..." if len(token) > 16 else token
    interval = CHAT_POLL_INTERVAL.get(chat_id, config.POLL_INTERVAL_MIN)

    logger.info(f"🚀 Starting monitor for {display or 'Unknown'} ({token_short})")

    # Initialize Monitor
    monitor = TokenMonitor(token, bot=bot, chat_id=chat_id, token_name=display, poll_interval_seconds=interval)
    CHAT_MONITORS.setdefault(chat_id, set()).add(monitor)

    # Run initial count + monitoring in background so Telegram listener stays responsive
    async def _run_monitor():
        try:
            count, verified, non_verified = await monitor.initial_count()
            await send_initial_notification(bot, chat_id, token, token_name, ticker, count, verified, non_verified)
            await monitor.start()
        except Exception as e:
            logger.error(f"[{token_short}] Monitor task crashed: {e}")

    asyncio.create_task(_run_monitor())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHANNEL_IDS, PROCESSED_CAS, BOT_START_TIME
    
    # Ignore messages sent before bot started
    msg_date = None
    if update.message:
        msg_date = update.message.date
    elif update.channel_post:
        msg_date = update.channel_post.date
    
    if BOT_START_TIME and msg_date:
        if msg_date.replace(tzinfo=None) < BOT_START_TIME:
            return
    
    chat_id = update.effective_chat.id
    
    # Check if this is from one of our target chats (empty set = allow all)
    if CHANNEL_IDS and chat_id not in CHANNEL_IDS:
        return

    # Get text from message or channel_post
    text = None
    if update.message:
        text = update.message.text or update.message.caption
    elif update.channel_post:
        text = update.channel_post.text or update.channel_post.caption
    
    if not text:
        return
    
    # Skip new tokens while sleeping
    if is_sleeping():
        logger.info(f"😴 Sleeping until {sleep_until_str()} - skipping CA detection")
        return

    # Extract CA from message
    token = extract_token(text)
    
    if token:
        token_short = token[:16] + "..."
        
        # Check if this channel already got notified for this token
        if token in PROCESSED_CAS and chat_id in PROCESSED_CAS[token]:
            logger.debug(f"🔄 Duplicate CA in same chat ignored: {token_short}")
            return
        
        # Mark this channel as notified for this token
        if token not in PROCESSED_CAS:
            PROCESSED_CAS[token] = set()
        PROCESSED_CAS[token].add(chat_id)
        
        # Check if token was already scraped (seen in another channel)
        existing_stats = tracker.get_stats(token)
        
        if existing_stats:
            # Already scraped - add this channel and send existing results
            logger.info(f"📤 Sending existing results for {token_short} to chat {chat_id}")
            tracker.add_channel_to_token(token, chat_id)
            
            await send_initial_notification(
                bot=context.bot,
                chat_id=chat_id,
                token=token,
                name=existing_stats.token_name,
                ticker=existing_stats.ticker,
                count=existing_stats.total_tweets,
                verified=existing_stats.total_verified,
                non_verified=existing_stats.total_non_verified
            )
        else:
            # New token - fetch info & start monitoring in background
            logger.info(f"📝 New CA detected: {token_short}")

            async def _handle_new_token(tok, tok_short, bot, cid):
                try:
                    name, ticker, chain = await get_token_info(tok)
                    if chain:
                        logger.info(f"🔗 Chain: {chain}")
                    await start_monitoring(token=tok, token_name=name, ticker=ticker, bot=bot, chat_id=cid)
                except Exception as e:
                    logger.error(f"[{tok_short}] New token handling failed: {e}")

            asyncio.create_task(_handle_new_token(token, token_short, context.bot, chat_id))

# ==================== COMMAND HANDLERS ====================

async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mode command to switch notification modes"""
    chat_id = update.effective_chat.id
    
    if not context.args:
        # Show current mode
        current = tracker.mode
        msg = (
            f"📊 Current: **{current}**\n\n"
            f"Commands:\n"
            f"`/mode legacy` - Individual notifications\n"
            f"`/mode leaderboard` - Top 30 summary"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        return
    
    new_mode = context.args[0].lower()
    
    # Accept 'leaderboards' as alias for 'leaderboard'
    if new_mode == "leaderboards":
        new_mode = "leaderboard"
    
    if new_mode in ["legacy", "leaderboard"]:
        tracker.set_mode(new_mode)
        
        if new_mode == "legacy":
            msg = (
                f"✅ **Legacy Mode**\n\n"
                f"• Individual notifications per token\n"
                f"• Tweet content + engagement\n"
                f"• ⚠️ Can be spammy!"
            )
        else:
            msg = (
                f"✅ **Leaderboard Mode**\n\n"
                f"• Top 30 tokens at your set interval\n"
                f"• Ranked by avg tweet count\n"
                f"• 🎯 Clean & organized"
            )
        
        await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            f"❌ Invalid: `{new_mode}`\n\nUse `legacy` or `leaderboard`",
            parse_mode='Markdown'
        )


async def cmd_sleep(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sleep command to pause monitoring"""
    global SLEEP_UNTIL

    minutes = 60
    if context.args:
        try:
            minutes = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⌛ Invalid number of minutes.", parse_mode='Markdown')
            return

    SLEEP_UNTIL = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
    await update.message.reply_text(
        f"😴 Sleeping for {minutes} minutes (until {sleep_until_str()}). Use /wake to resume early.",
        parse_mode='Markdown'
    )


async def cmd_wake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /wake command to resume monitoring"""
    global SLEEP_UNTIL
    if not is_sleeping():
        await update.message.reply_text("👍 Already awake.", parse_mode='Markdown')
        return

    SLEEP_UNTIL = None
    await update.message.reply_text("☀️ Resuming monitoring now.", parse_mode='Markdown')

async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /restart command to restart the bot process"""
    await update.message.reply_text("🔄 Restarting bot...", parse_mode='Markdown')
    await asyncio.sleep(1)
    os.execl(sys.executable, sys.executable, *sys.argv)

async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /reset command to clear all data and start fresh"""
    global PROCESSED_CAS, TOKEN_INFO_CACHE
    import glob
    
    # Count what we're clearing
    token_count = len(tracker.tokens)
    csv_files = glob.glob("monitor_*.csv")
    csv_count = len(csv_files)
    cache_count = len(TOKEN_INFO_CACHE)
    
    # Clear tracker (all tokens)
    tracker.tokens.clear()
    
    # Clear processed CAs
    PROCESSED_CAS.clear()
    
    # Clear token info cache
    TOKEN_INFO_CACHE.clear()
    
    # Delete CSV files
    for f in csv_files:
        try:
            os.remove(f)
        except Exception as e:
            logger.warning(f"Could not delete {f}: {e}")
    
    msg = (
        f"🗑️ **Reset Complete**\n\n"
        f"• Tokens cleared: {token_count}\n"
        f"• CSVs deleted: {csv_count}\n"
        f"• Cache cleared: {cache_count}\n\n"
        f"_Ready for fresh monitoring_"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')
    logger.info(f"🗑️ Reset: {token_count} tokens, {csv_count} CSVs, {cache_count} cached")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command to show current tracking status for this channel"""
    chat_id = update.effective_chat.id
    active = tracker.get_active_tokens(chat_id=chat_id)
    all_active = tracker.get_active_tokens()
    
    if not active:
        await update.message.reply_text("📊 No active monitors in this chat")
        return
    
    msg = f"📊 **{len(active)} Active** (this chat)\n"
    if len(all_active) != len(active):
        msg += f"🌐 {len(all_active)} total across all chats\n"
    msg += "\n"
    
    for stats in active[:10]:
        name = stats.get_display_name()
        total = stats.total_tweets
        avg = stats.get_average_tweet_count()
        mon_time = stats.get_monitoring_time_str()
        msg += f"• {name}\n  {total} tweets | avg {avg} | {mon_time}\n"
    
    if len(active) > 10:
        msg += f"\n_+{len(active) - 10} more_"
    
    sleep_note = "Sleeping" if is_sleeping() else "Awake"
    msg += f"\n\nMode: `{tracker.mode}` | {sleep_note}"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /top command to show current leaderboard for this channel"""
    chat_id = update.effective_chat.id
    await tracker.send_leaderboard(context.bot, chat_id)  # Filtered to this channel

async def cmd_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /interval command to set/show poll interval for this chat."""
    chat_id = update.effective_chat.id

    if not context.args:
        current_seconds = CHAT_POLL_INTERVAL.get(chat_id, config.POLL_INTERVAL_MIN)
        await update.message.reply_text(
            f"⏱️ Current poll interval: **{current_seconds // 60} min**\n"
            f"Use `/interval <minutes>` or `/interval reset`.",
            parse_mode='Markdown'
        )
        return

    arg = context.args[0].lower().strip()

    if arg == "reset":
        CHAT_POLL_INTERVAL.pop(chat_id, None)
        CHAT_LEADERBOARD_LAST_SENT.pop(chat_id, None)
        default_seconds = config.POLL_INTERVAL_MIN
        updated = 0
        for m in list(CHAT_MONITORS.get(chat_id, set())):
            if datetime.datetime.now() < m.end_time:
                m.set_poll_interval(default_seconds)
                updated += 1
            else:
                CHAT_MONITORS.get(chat_id, set()).discard(m)
        logger.info(f"⏱️ Interval reset in chat {chat_id}: {default_seconds}s ({updated} monitors updated)")
        await update.message.reply_text(
            f"✅ Poll interval reset to default (**{config.POLL_INTERVAL_MIN // 60} min**).",
            parse_mode='Markdown'
        )
        return

    try:
        minutes = int(arg)
        if minutes < 1:
            await update.message.reply_text("❌ Minimum is 1 minute.", parse_mode='Markdown')
            return

        seconds = minutes * 60
        CHAT_POLL_INTERVAL[chat_id] = seconds
        CHAT_LEADERBOARD_LAST_SENT.pop(chat_id, None)  # Reset so next leaderboard uses new interval
        updated = 0
        for m in list(CHAT_MONITORS.get(chat_id, set())):
            if datetime.datetime.now() < m.end_time:
                m.set_poll_interval(seconds)
                updated += 1
            else:
                CHAT_MONITORS.get(chat_id, set()).discard(m)
        logger.info(f"⏱️ Interval set in chat {chat_id}: {seconds}s ({updated} monitors updated)")
        await update.message.reply_text(
            f"✅ Poll interval set to **{minutes} min** for this chat.",
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid interval.\nUse `/interval <minutes>` or `/interval reset`.",
            parse_mode='Markdown'
        )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    msg = (
        f"🤖 **X-Terminator**\n\n"
        f"📌 **Commands**\n"
        f"`/mode` - Switch notification mode\n"
        f"`/status` - Active monitors (this chat)\n"
        f"`/top` - Show leaderboard now\n"
        f"`/interval [min|reset]` - Set poll interval\n"
        f"`/sleep [min]` - Pause for N minutes\n"
        f"`/wake` - Resume monitoring\n"
        f"`/reset` - Clear all data & CSVs\n"
        f"`/restart` - Restart bot process\n\n"
        f"📌 **Modes**\n"
        f"• Leaderboard - Top 30 at your set interval (default 15 min)\n"
        f"• Legacy - Individual tweet notifications\n\n"
        f"📌 **Usage**\n"
        f"Post token CA → Bot scans X → 3h monitoring\n\n"
        f"⚠️ Run `/reset` periodically to clear old data and prevent VPS storage from filling up."
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

# ==================== PERIODIC TASKS ====================

async def leaderboard_loop(app):
    """Background task to send leaderboard based on per-channel interval"""
    logger.info("⏰ Leaderboard loop started")

    while True:
        await asyncio.sleep(30)  # Check every 30s for due channels

        try:
            if tracker.mode != "leaderboard":
                continue
            if is_sleeping():
                continue

            if not tracker.get_active_tokens():
                continue

            now = datetime.datetime.now()

            # Build list of channels to check
            channels = list(CHANNEL_IDS) if CHANNEL_IDS else ([tracker.chat_id] if tracker.chat_id else [])

            for chat_id in channels:
                interval_sec = CHAT_POLL_INTERVAL.get(chat_id, config.POLL_INTERVAL_MIN)
                last_sent = CHAT_LEADERBOARD_LAST_SENT.get(chat_id)

                if last_sent and (now - last_sent).total_seconds() < interval_sec:
                    continue

                logger.info(f"📊 Sending leaderboard to {chat_id} (interval: {interval_sec // 60}m)...")
                await tracker.send_leaderboard(app.bot, chat_id, interval_sec=interval_sec)
                CHAT_LEADERBOARD_LAST_SENT[chat_id] = now
        except Exception as e:
            logger.error(f"Leaderboard loop error: {e}")

# ==================== MAIN ====================

def main():
    global CHANNEL_IDS, BOT_START_TIME
    BOT_START_TIME = datetime.datetime.utcnow()
    logger.info("=" * 50)
    logger.info("🚀 X-TERMINATOR BOT STARTING")
    logger.info("=" * 50)

    # Parse Channel IDs (comma-separated)
    raw_ids = config.TELEGRAM_CHANNEL_IDS
    if raw_ids:
        for raw_id in raw_ids.split(","):
            raw_id = raw_id.strip()
            if not raw_id:
                continue
            try:
                cid = int(raw_id)
                CHANNEL_IDS.add(cid)
                logger.info(f"📡 Listening to chat: {cid}")
            except ValueError:
                logger.warning(f"⚠️ Skipping invalid ID: '{raw_id}'")
        
        if CHANNEL_IDS:
            # Use first channel as default for leaderboard
            tracker.chat_id = next(iter(CHANNEL_IDS))
        else:
            logger.warning("⚠️ No valid IDs parsed. Listening to ALL chats.")
    else:
        logger.warning("⚠️ No TELEGRAM_CHANNEL_IDS set. Listening to ALL chats.")

    # Load Twitter Accounts
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    logger.info("🐦 Loading Twitter Accounts...")
    loop.run_until_complete(load_accounts())
    
    # Start Telegram Listener
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN is missing!")
        return

    # Post-init callback to start background tasks
    async def post_init(application):
        # Drop old pending updates by calling getUpdates with offset -1
        try:
            await application.bot.get_updates(offset=-1, timeout=1)
            logger.info("🗑️ Dropped pending old messages")
        except Exception:
            pass
        asyncio.create_task(leaderboard_loop(application))
        logger.info(f"⏰ Leaderboard loop started (every {LEADERBOARD_INTERVAL//60} min)")
    
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # Store bot reference in tracker
    tracker.bot = app.bot
    
    # Add command handlers FIRST
    app.add_handler(CommandHandler("mode", cmd_mode))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("sleep", cmd_sleep))
    app.add_handler(CommandHandler("wake", cmd_wake))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("interval", cmd_interval))

    # Listen for messages (exclude commands with ~filters.COMMAND)
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST & ~filters.COMMAND, handle_message))
    
    logger.info(f"👂 Listening for messages...")
    logger.info(f"🔍 Token info: GeckoTerminal → DexScreener fallback")
    logger.info(f"📊 Default mode: {tracker.mode}")
    logger.info("=" * 50)
    logger.info("**COMMANDS:**")
    logger.info("/mode legacy     - Individual notifications")
    logger.info("/mode leaderboard - Top 30 summary (default)")
    logger.info("/status          - Show active monitors")
    logger.info("/top             - Show current leaderboard")
    logger.info("=" * 50)
    logger.info("⚠️  IMPORTANT FOR GROUPS:")
    logger.info("1. Go to @BotFather")
    logger.info("2. /mybots -> Bot Settings -> Group Privacy -> Turn OFF")
    logger.info("3. Remove & re-add the bot to the group")
    logger.info("=" * 50)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
