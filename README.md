# X-Terminator

Telegram bot that monitors crypto token mentions on X (Twitter). Detects CAs from channels, fetches token info from DexScreener, scrapes X for tweet counts, and sends leaderboards.

## Features

- Multi-channel support
- Leaderboard mode (top 30 tokens every 15 min) or Legacy mode (individual notifications)
- DexScreener API for token info (all chains)
- Sleep/wake and restart commands
- Per-channel leaderboards

## Setup

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/x-terminator.git
cd x-terminator
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_IDS
```

Create `accounts.txt` (format: `username::auth_token:ct0:proxy`):

```
user1::auth_token_here:ct0_here:http://user:pass@proxy:port
user2::auth_token_here:ct0_here:http://user:pass@proxy:port
```

### 3. Run

```bash
python main.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/mode legacy` | Individual tweet notifications |
| `/mode leaderboard` | Top 30 summary every 15 min |
| `/status` | Active monitors |
| `/top` | Show leaderboard now |
| `/sleep [min]` | Pause for N minutes |
| `/wake` | Resume |
| `/restart` | Restart bot process |

## VPS Deployment

```bash
# Run in background
nohup python main.py > bot.log 2>&1 &

# Or with screen
screen -S xterminator
python main.py
# Ctrl+A, D to detach
```
