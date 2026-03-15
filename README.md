# drop2host

Telegram bot that instantly hosts your HTML pages on a VPS with HTTPS.

Send an `.html` file or `.zip` archive to the bot — get a live HTTPS link in seconds.

## Features

- **Instant hosting** — send a file, get a link
- **Wildcard subdomains** — each user gets a personal subdomain: `username.yourdomain.com`
- **ZIP support** — upload multi-file sites (HTML + CSS + JS + images)
- **Cyrillic transliteration** — type project names in Russian, auto-converted to Latin
- **Auto-cleanup** — projects expire after 90 days with renewal notifications
- **User isolation** — each user sees only their own projects
- **Admin panel** — `/admin` shows all projects across all users
- **Access control** — whitelist by Telegram ID

## URL Structure

```
https://{username}.yourdomain.com/{project-name}/
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
sudo bash setup_server.sh yourdomain.com YOUR_CLOUDFLARE_API_TOKEN
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

---

## RU | Описание на русском

Telegram-бот для мгновенного хостинга HTML-страниц на вашем VPS с HTTPS.

Отправьте `.html` файл или `.zip` архив боту — получите рабочую HTTPS-ссылку за секунды.

### Возможности

- **Мгновенный хостинг** — отправил файл, получил ссылку
- **Поддомены** — каждый пользователь получает свой поддомен: `username.yourdomain.com`
- **ZIP-архивы** — загружайте многостраничные сайты (HTML + CSS + JS + картинки)
- **Транслитерация** — вводите названия на русском, автоматически переводятся в латиницу
- **Автоочистка** — проекты удаляются через 90 дней с уведомлением и возможностью продлить
- **Изоляция** — каждый пользователь видит только свои проекты
- **Админ-панель** — `/admin` показывает все проекты всех пользователей
- **Контроль доступа** — whitelist по Telegram ID

### Быстрый старт

1. Подготовьте VPS (Ubuntu 22.04+) и домен с DNS на Cloudflare
2. Получите токен бота у [@BotFather](https://t.me/BotFather)
3. Запустите скрипт настройки:
   ```bash
   sudo bash setup_server.sh yourdomain.com CLOUDFLARE_API_TOKEN
   ```
4. Скопируйте файлы бота в `/opt/html-bot/`, создайте `.env`
5. Запустите: `sudo systemctl start html-bot`

### Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Регистрация и выбор поддомена |
| `/list` | Список ваших проектов с URL и сроком |
| `/delete <имя>` | Удалить проект |
| `/admin` | (Только админ) Все проекты всех пользователей |

## License

MIT
