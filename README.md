# drop2host

Telegram bot that instantly hosts your HTML pages on a VPS with HTTPS.

Send an `.html` file or `.zip` archive to the bot — get a live HTTPS link in seconds.

## Features

- **Instant hosting** — send a file, get a link
- **Wildcard subdomains** — each user gets a personal subdomain: `username.drop2host.ru`
- **ZIP support** — upload multi-file sites (HTML + CSS + JS + images)
- **Cyrillic transliteration** — type project names in Russian, auto-converted to Latin
- **Auto-cleanup** — projects expire after 90 days with renewal notifications
- **User isolation** — each user sees only their own projects
- **Admin panel** — `/admin` shows all projects across all users
- **Access control** — whitelist by Telegram ID

## URL Structure

```
https://{username}.drop2host.ru/{project-name}/
```

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Register and choose your subdomain |
| `/list` | View your projects with URLs and expiry |
| `/delete <name>` | Delete a project |
| `/admin` | (Admin only) View all projects |

## Quick Start

### Prerequisites

- Ubuntu 22.04+ VPS
- Domain with DNS on Cloudflare (for wildcard SSL)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### 1. Setup VPS

```bash
sudo bash setup_server.sh drop2host.ru YOUR_CLOUDFLARE_API_TOKEN
```

This installs nginx, obtains wildcard SSL, and creates a systemd service.

### 2. Deploy the bot

```bash
cp -r ./* /opt/html-bot/
cp .env /opt/html-bot/.env
cd /opt/html-bot
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
nano .env
```

Set your `BOT_TOKEN`, `DOMAIN`, `ALLOWED_USERS`, and `ADMIN_USERS`.

### 4. Start

```bash
sudo systemctl start html-bot
sudo systemctl status html-bot
```

## Tech Stack

- Python 3.11+ / [aiogram 3](https://docs.aiogram.dev/)
- SQLite via aiosqlite
- Nginx (wildcard subdomains)
- Let's Encrypt (wildcard SSL via Cloudflare DNS)
- APScheduler (expiry notifications)

## Project Structure

```
├── bot.py              # Entry point
├── config.py           # Environment config
├── database.py         # SQLite models & CRUD
├── handlers/
│   ├── start.py        # Registration & subdomain selection
│   ├── upload.py       # File reception with FSM
│   ├── manage.py       # /list, /delete, extend
│   └── admin.py        # /admin command
├── services/
│   ├── transliterate.py    # Cyrillic → Latin
│   ├── file_manager.py     # File saving, ZIP extraction
│   └── scheduler.py        # 90-day expiry checks
├── setup_server.sh     # VPS setup script
├── requirements.txt
└── .env.example
```

## License

MIT
