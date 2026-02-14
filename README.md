# X-Terminator

Telegram bot that monitors crypto token mentions on X (Twitter). Detects contract addresses from channels, fetches token info from DexScreener, scrapes X for tweet counts, and sends per-channel leaderboards.

## Features

- **Multi-channel support** – Listen to multiple Telegram channels/groups
- **Per-channel leaderboards** – Each channel sees only tokens posted in that channel
- **Two modes** – Leaderboard (top 30 every 15 min) or Legacy (individual notifications)
- **DexScreener integration** – Token name/symbol for all chains (Solana, EVM, etc.)
- **Verified vs regular** – Separate counts for verified and non-verified accounts
- **Sleep/Wake/Restart** – Control bot via Telegram commands

## Requirements

- Python 3.10+
- Twitter accounts with `auth_token` and `ct0` cookies
- Telegram bot token
- (Optional) Proxy for Twitter requests

## Setup

### 1. Install

```bash
git clone https://github.com/YOUR_USERNAME/x-terminator.git
cd x-terminator
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
cp accounts.txt.example accounts.txt
```

Edit `.env`:
- `TELEGRAM_BOT_TOKEN` – From @BotFather
- `TELEGRAM_CHANNEL_IDS` – Comma-separated channel/group IDs (e.g. `-100123,-100456`)

Edit `accounts.txt`:
- Format: `username::auth_token:ct0:proxy`
- Get cookies: Log into X → DevTools → Application → Cookies
- Proxy optional (Bright Data format: `http://user:pass@host:port`)

### 3. Run

```bash
python main.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/mode legacy` | Individual tweet notifications |
| `/mode leaderboard` | Top 30 summary every 15 min (default) |
| `/status` | Show active monitors in this chat |
| `/top` | Show leaderboard now |
| `/sleep [min]` | Pause new token detection (default 60 min) |
| `/wake` | Resume monitoring |
| `/restart` | Restart bot process |
| `/help` | Show help |

## Telegram Setup

1. Create bot via @BotFather
2. Add bot to your group/channel
3. **Disable Group Privacy**: @BotFather → Bot Settings → Group Privacy → Turn OFF
4. Get channel ID (e.g. from @userinfobot or bot logs)

## VPS Deployment

```bash
# Background
nohup python main.py > bot.log 2>&1 &

# Or with screen
screen -S xterminator
python main.py
# Ctrl+A, D to detach
```

## Project Structure

```
x-terminator/
├── main.py          # Entry point
├── manager.py       # Telegram bot, message handling
├── monitor.py       # Token monitoring, X scraping
├── token_tracker.py # Leaderboard, per-channel tracking
├── scraper_utils.py # Account loading, SSL patches
├── scraper.py       # Twitter scraper (twscrape)
├── config.py        # Configuration
├── .env.example     # Env template
├── accounts.txt.example
└── requirements.txt
```

## License

Proprietary – for client use.
