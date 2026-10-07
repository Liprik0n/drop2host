# drop2host

Telegram-бот для мгновенного хостинга HTML-страниц на вашем VPS с HTTPS.

Отправьте `.html` файл или `.zip` архив боту — получите рабочую HTTPS-ссылку за секунды. Идеально для учителей: быстро поделиться тестом, викториной или интерактивной страницей с учениками.

## Возможности

- **Мгновенный хостинг** — отправил файл, получил ссылку
- **Поддомены** — каждый пользователь получает свой поддомен: `username.yourdomain.com`
- **ZIP-архивы** — загружайте многостраничные сайты (HTML + CSS + JS + картинки)
- **Описание проектов** — добавляйте описание при загрузке для удобства
- **Транслитерация** — вводите названия на русском, автоматически переводятся в латиницу
- **Автоочистка** — проекты удаляются через 90 дней с уведомлением и возможностью продлить
- **Кнопочный интерфейс** — удобное меню и inline-кнопки, не нужно запоминать команды
- **Управление пользователями** — добавление/удаление пользователей прямо из Telegram
- **Админ-панель** — все проекты и пользователи в одном месте
- **Бэкапы в Telegram** — база и сайты каждый день приходят админу (только при изменениях)
- **Лимит 30 МБ** — достаточно для любого статического сайта
- **CORS и gzip** — поддержка современных веб-технологий из коробки

## Быстрый старт

### Требования

- VPS с Ubuntu 22.04+
- Домен с DNS на Cloudflare (для wildcard SSL)
- Токен бота от [@BotFather](https://t.me/BotFather)

### 1. Настройка VPS

```bash
git clone https://github.com/Liprik0n/drop2host.git /opt/html-bot
cd /opt/html-bot
sudo bash setup_server.sh yourdomain.com YOUR_CLOUDFLARE_API_TOKEN
```

Скрипт установит nginx, получит wildcard SSL-сертификат и создаст systemd-сервис.

### 2. Настройка бота

```bash
cp .env.example .env
nano .env
```

Заполните: `BOT_TOKEN`, `DOMAIN`, `ALLOWED_USERS`, `ADMIN_USERS`.

### 3. Запуск

```bash
sudo systemctl start html-bot
sudo systemctl status html-bot
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Регистрация и выбор поддомена |
| `/list` | Список ваших проектов |
| `/delete <имя>` | Удалить проект |
| `/admin` | Панель администратора |
| `/adduser <id>` | Добавить пользователя |
| `/removeuser <id>` | Удалить пользователя |
| `/users` | Список пользователей |
| `/backup` | Прислать бэкап прямо сейчас |
| `/backup_here` | Присылать ежедневные бэкапы в этот чат (например, отдельную группу) |

## Бэкапы и восстановление

Каждый день в 03:00 UTC (и при запуске) бот присылает администраторам `html-bot-backup.tar.gz` (база + настройки, **без токена**) и `sites-backup.tar.gz` (все сайты). Если с прошлого бэкапа ничего не изменилось, отправка пропускается. Архивы больше 45 МБ приходят частями `.partNN`.

Отдельный чат для бэкапов: создайте закрытую группу, добавьте в неё бота и отправьте там `/backup_here`. Если бот не сможет отправить в группу, бэкап придёт админам в личку с предупреждением.

Восстановление на чистом сервере: положите оба архива (или все части) и `restore_server.sh` в `/root/` и выполните `bash /root/restore_server.sh` — скрипт спросит токен бота и Cloudflare-токен.

## URL Structure

```
https://{username}.yourdomain.com/{project-name}/
```

---

## EN | English

Telegram bot that instantly hosts your HTML pages on a VPS with HTTPS.

Send an `.html` file or `.zip` archive to the bot — get a live HTTPS link in seconds.

### Features

- **Instant hosting** — send a file, get a link
- **Wildcard subdomains** — each user gets a personal subdomain
- **ZIP support** — upload multi-file sites (HTML + CSS + JS + images)
- **Project descriptions** — optional description field for each project
- **Cyrillic transliteration** — type project names in Russian, auto-converted to Latin
- **Auto-cleanup** — projects expire after 90 days with renewal notifications
- **Button interface** — menu buttons and inline keyboards, no commands to memorize
- **User management** — add/remove users directly from Telegram
- **Admin panel** — manage all projects and users in one place
- **30 MB limit** — enough for any static site
- **CORS & gzip** — modern web technologies supported out of the box

## Tech Stack

- Python 3.11+ / [aiogram 3](https://docs.aiogram.dev/)
- SQLite via aiosqlite
- Nginx (wildcard subdomains, gzip, CORS)
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
│   └── admin.py        # Admin panel & user management
├── services/
│   ├── transliterate.py    # Cyrillic → Latin
│   ├── file_manager.py     # File saving, ZIP extraction
│   ├── scheduler.py        # 90-day expiry checks
│   └── backup.py           # Daily backups to admins in Telegram
├── setup_server.sh     # VPS setup script
├── restore_server.sh   # One-shot recovery on a clean server
├── requirements.txt
└── .env.example
```

## License

MIT
