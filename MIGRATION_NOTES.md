# Перенос drop2host на новый сервер — разбор проблем и решений

Заметки по миграции бота на новый VPS (Ubuntu 24.04, nginx 1.24, certbot cloudflare 2.11).
Здесь собраны все грабли, на которые мы наступили, их причины и как не повторить.

---

## 0. Что нужно для переноса (короткий чек-лист)

- VPS Ubuntu 22.04/24.04, root-доступ.
- Домен с DNS-зоной на Cloudflare + **scoped API-токен** (Zone:DNS:Edit + Zone:Zone:Read на нужную зону).
- Перевыпущенный токен бота от @BotFather.
- Бэкапы: `html-bot-backup.tar.gz` (bot.db + .env) и `sites-backup.tar.gz` (/var/www/sites).
- Скрипты `setup_server.sh` и `migrate.sh` (должны быть **в репозитории**, см. проблему №1).

Порядок: `setup_server.sh` → `pip install` → `migrate.sh` → задать токен в `.env` → `systemctl start`.
DNS: A `@` и A `*` → IP нового сервера. SSL/TLS в Cloudflare → **Full (strict)**.

---

## Проблема 1. На сервере не оказалось migrate.sh, бэкапов и фикса setup_server.sh

**Симптом:** `bash migrate.sh: No such file or directory`; сервис стартовал под `root` (старый юнит).

**Причина:** сервер берёт код через `git clone`, а `migrate.sh`, оба `*.tar.gz` и правки `setup_server.sh`
существовали только в локальной папке и **не были закоммичены/запушены**. Бэкапы в git и не должны попадать
(внутри токен и данные пользователей).

**Решение:** перекинули нужные файлы по `scp` напрямую с рабочей машины:
```
scp html-bot-backup.tar.gz sites-backup.tar.gz migrate.sh setup_server.sh root@IP:/opt/html-bot/
```

**Как не повторить:**
- `migrate.sh` и исправленный `setup_server.sh` — **закоммитить в репозиторий** (в них нет секретов).
- Бэкапы (`*.tar.gz`) — **никогда в git**; переносить по scp/sftp. Держать их вне рабочей папки (мы убрали в `/root/migration-backups`).

---

## Проблема 2. Cloudflare: «6003 Invalid request headers» при выпуске SSL

**Симптом:** `certbot ... Error determining zone_id: 6003 Invalid request headers`.

**Причина:** в `/etc/letsencrypt/cloudflare.ini` оказался невалидный/битый токен (а не проблема прав —
у прав была бы 9109/403). Проверка токена напрямую подтвердила, валиден он или нет:
```
curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer $TOKEN"
```
(`"success":true` → токен ок; иначе — пересоздать).

**Как не повторить:** использовать **scoped-токен** (шаблон «Edit zone DNS», права Zone:DNS:Edit + Zone:Zone:Read
на конкретную зону), копировать целиком, проверять через `/tokens/verify` до запуска certbot.

---

## Проблема 3. UnicodeEncodeError при certbot — кириллица в credential-файле

**Симптом:** `UnicodeEncodeError: 'latin-1' codec can't encode characters...`.

**Причина:** команду выполнили буквально с плейсхолдером `'СЮДА_ТОКЕН'` (кириллица) — она попала в `cloudflare.ini`.

**Как не повторить:** все плейсхолдеры заменять реальными значениями латиницей. Проверять файл `cat -A`
(маркеры пробелов/`^M`).

---

## Проблема 4. SSL-проверка: «Incorrect TXT record found at _acme-challenge»

**Симптом:** certbot создал TXT через API, но LE нашёл чужое значение и проверка не прошла.

**Причина:** в зоне Cloudflare висела **старая запись `_acme-challenge`** с прошлого выпуска (на старом сервере).

**Решение:** удалить все старые TXT `_acme-challenge` в Cloudflare DNS и перевыпустить с увеличенным ожиданием:
```
certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  -d drop2host.ru -d '*.drop2host.ru' \
  --dns-cloudflare-propagation-seconds 60 \
  --non-interactive --agree-tos --email admin@drop2host.ru
```

**Как не повторить:** перед выпуском чистить старые `_acme-challenge`; ставить `--dns-cloudflare-propagation-seconds 60`.

**Доп. нюанс:** на этом VPS заблокирован исходящий DNS к внешним резолверам
(`dig @1.1.1.1` → connection refused). Это не мешает certbot (он ходит в Cloudflare по HTTPS, проверяет сам LE).
Для `dig` использовать системный резолвер (без `@`).

---

## Проблема 5. Бот падает в цикле: «BOT_TOKEN is not set in .env»

**Симптом:** сервис `active`, но каждые ~5 c крэшится с `BOT_TOKEN is not set`.

**Причина:** в `.env` строка токена была записана криво — вероятно с пробелами вокруг `=`
(`BOT_TOKEN = ...`). `python-dotenv` и `grep '^BOT_TOKEN='` такую строку не подхватывают → токен пустой.
Маскировка `sed 's/\(BOT_TOKEN=\).*/\1***/'` это скрывала (печатала `***` даже при пустом значении).

**Решение:** задать токен начисто, без пробелов вокруг `=` и без кавычек, и проверить так же, как читает бот:
```
sudo sed -i -E '/^[[:space:]]*BOT_TOKEN[[:space:]]*=/d' /opt/html-bot/.env
printf 'BOT_TOKEN=%s\n' 'РЕАЛЬНЫЙ_ТОКЕН' | sudo tee -a /opt/html-bot/.env >/dev/null
cd /opt/html-bot
sudo -u htmlbot ./venv/bin/python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(len(os.getenv('BOT_TOKEN','')))"
# должно быть ~46
```

**Как не повторить:**
- Формат `.env`: `KEY=value`, **без пробелов** вокруг `=`, без кавычек.
- Проверять переменную тем же механизмом (`load_dotenv` от имени сервисного юзера), а не «на глаз».
- При маскировке для проверки длины использовать что-то, что не маскирует пустоту
  (например выводить длину значения).

---

## Проблема 6. Восстановленный .env затёрся минимальным (только токен)

**Симптом:** при ручном создании `.env` остались только `BOT_TOKEN`, пропали `ALLOWED_USERS`/`ADMIN_USERS`.
`ADMIN_USERS` читается **только из .env** (в БД не мёржится) → админка не работала бы.

**Причина:** `migrate.sh` не перезаписывает существующий `.env` (кладёт бэкап как `.env.from-backup`).
Минимальный `.env` уже лежал, поэтому полные настройки не применились.

**Решение:** взять `.env.from-backup` за основу и заменить в нём только токен.

**Как не повторить:** после `migrate.sh` сверять `.env` с `.env.from-backup` — должны быть
`DOMAIN`, `ALLOWED_USERS`, `ADMIN_USERS`, `BOT_TOKEN`.

---

## Не-проблема: nginx 404 на голом поддомене

`https://user.drop2host.ru/` (без `/slug/`) → 404 — это **нормально**: сайты лежат по пути
`/{username}/{slug}/`, у корня поддомена индекса нет. Рабочая ссылка — с проектом:
`https://user.drop2host.ru/slug/`.

---

## Безопасность

- **Токен светился в открытом виде** в терминале/переписке при настройке. Если лог куда-то попадёт —
  перевыпустить токен ещё раз.
- Старый токен лежит в `html-bot-backup.tar.gz` и `.env.from-backup` — после переезда они в `/root/migration-backups`
  (старый токен уже мёртв, но хранить осторожно).
- Сервис теперь работает под непривилегированным `htmlbot` (не root) + systemd-харднинг
  (`NoNewPrivileges`, `ProtectSystem=full`, `PrivateTmp`, `ReadWritePaths`).

---

## Модель прав (итог)

- `/opt/html-bot` → `htmlbot:htmlbot` (бот пишет `bot.db`), `.env` → `chmod 600`.
- `/var/www/sites` → `htmlbot:www-data`, каталоги `2775` (setgid), файлы `644`.
  Бот (`htmlbot`) пишет, nginx (`www-data`) читает; новые сайты наследуют группу `www-data`.
- systemd: `User=htmlbot`, `Group=htmlbot`, `UMask=0022`.
