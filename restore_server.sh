#!/bin/bash
# ================================================
# Disaster recovery for the HTML Hosting Telegram Bot
# on a freshly reinstalled server (Ubuntu/Debian).
# ================================================
# One shot: packages -> code -> data -> bot online -> DNS -> SSL -> nginx.
# The bot goes online before SSL, so a certbot problem never blocks it.
#
# Safe next to Amnezia VPN: never enables ufw (only adds 80/443 if it is
# already active) and refuses to continue if 80/443 are taken by
# something other than nginx.
#
# Usage (as root, backups in the same directory as this script):
#   bash restore_server.sh
# Asks for the BOT_TOKEN and the Cloudflare API token (Enter = skip SSL).
# Env overrides: DOMAIN, SERVER_IP, BACKUP_DIR
#
# Safe to re-run: bot.db and sites are restored only if not present yet.

set -euo pipefail

DOMAIN="${DOMAIN:-drop2host.ru}"
SERVER_IP="${SERVER_IP:-193.124.93.158}"
REPO="https://github.com/Liprik0n/drop2host.git"
BOT_DIR="/opt/html-bot"
SITES_DIR="/var/www/sites"
BOT_USER="htmlbot"
SERVICE="html-bot"
PROJECT_TTL_DAYS=90
BACKUP_DIR="${BACKUP_DIR:-$(cd "$(dirname "$0")" && pwd)}"
BOT_BACKUP="${BACKUP_DIR}/html-bot-backup.tar.gz"
SITES_BACKUP="${BACKUP_DIR}/sites-backup.tar.gz"

step() { echo; echo "=== $* ==="; }
warn() { echo "WARNING: $*" >&2; }
die()  { echo "ERROR: $*" >&2; exit 1; }

# --- Sanity checks ---------------------------------------------------------
[ "$(id -u)" -eq 0 ] || die "run as root"
# Large sites backups arrive from the bot split into .partNN files
if [ ! -f "${SITES_BACKUP}" ] && compgen -G "${SITES_BACKUP}.part*" >/dev/null; then
    cat "${SITES_BACKUP}".part* > "${SITES_BACKUP}"
fi
[ -f "${BOT_BACKUP}" ]   || die "backup not found: ${BOT_BACKUP}"
[ -f "${SITES_BACKUP}" ] || die "backup not found: ${SITES_BACKUP}"

export DEBIAN_FRONTEND=noninteractive
APT="apt-get -y -q -o DPkg::Lock::Timeout=300 -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"

# A fresh VPS often has an interrupted dpkg run (apt refuses to work until fixed)
dpkg --force-confdef --force-confold --configure -a

step "Checking ports 80/443"
BUSY="$(ss -ltnpH '( sport = :80 or sport = :443 )' | grep -v nginx || true)"
if [ -n "${BUSY}" ]; then
    echo "${BUSY}"
    die "ports 80/443 are used by another service (Amnezia XRay?). nginx needs them."
fi
echo "    free"

if ! command -v curl >/dev/null; then
    ${APT} update && ${APT} install curl
fi

# --- Tokens (asked first, so everything below runs unattended) ------------
step "Tokens"
echo "Input is hidden (nothing is shown while typing)."
echo "Paste with RIGHT-CLICK or Shift+Insert (Ctrl+V usually does not work), then press Enter."
mask() { printf '%s chars: %s...%s' "${#1}" "${1:0:4}" "${1: -4}"; }
while :; do
    read -rsp "Telegram BOT_TOKEN (from @BotFather): " RAW </dev/tty; echo
    # Pull the token out of whatever was pasted (stray ^V, quotes, BotFather text)
    BOT_TOKEN="$(printf '%s' "${RAW}" | grep -oE '[0-9]{5,}:[A-Za-z0-9_-]{30,}' | head -1 || true)"
    if [ -z "${BOT_TOKEN}" ]; then
        echo "    no token found in the input (${#RAW} chars received), try again"
        continue
    fi
    echo "    got $(mask "${BOT_TOKEN}")"
    RESP="$(curl -sS -m 20 "https://api.telegram.org/bot${BOT_TOKEN}/getMe")" \
        || die "server cannot reach api.telegram.org"
    case "${RESP}" in
        *'"ok":true'*) echo "    OK: $(printf '%s' "${RESP}" | grep -o '"username":"[^"]*"')"; break ;;
        *) echo "    Telegram rejected it: $(printf '%s' "${RESP}" | grep -o '"description":"[^"]*"' || printf '%.200s' "${RESP}")" ;;
    esac
done

while :; do
    read -rsp "Cloudflare API token (Enter = skip DNS/SSL): " RAW </dev/tty; echo
    CF_TOKEN="$(printf '%s' "${RAW}" | tr -cd 'A-Za-z0-9_-')"
    [ -n "${CF_TOKEN}" ] || { warn "Cloudflare skipped: sites will not open until SSL is set up"; break; }
    echo "    got $(mask "${CF_TOKEN}")"
    RESP="$(curl -sS -m 20 "https://api.cloudflare.com/client/v4/user/tokens/verify" \
        -H "Authorization: Bearer ${CF_TOKEN}")" || die "server cannot reach api.cloudflare.com"
    case "${RESP}" in
        *'"success":true'*) echo "    OK"; break ;;
        *) echo "    Cloudflare rejected it: $(printf '%s' "${RESP}" | grep -o '"message":"[^"]*"' | head -1 || true)" ;;
    esac
done

# --- Packages --------------------------------------------------------------
step "Installing packages"
${APT} update
${APT} install nginx certbot python3-certbot-dns-cloudflare python3-venv python3-pip git

# --- Code ------------------------------------------------------------------
step "Bot user and code"
id "${BOT_USER}" &>/dev/null || useradd -r -s /bin/false "${BOT_USER}"
if [ -d "${BOT_DIR}/.git" ]; then
    git -c safe.directory="${BOT_DIR}" -C "${BOT_DIR}" pull --ff-only
else
    if [ -d "${BOT_DIR}" ] && [ -n "$(ls -A "${BOT_DIR}")" ]; then
        mv "${BOT_DIR}" "${BOT_DIR}.old.$(date +%Y%m%d%H%M%S)"
    fi
    git clone "${REPO}" "${BOT_DIR}"
fi

step "Python venv"
[ -x "${BOT_DIR}/venv/bin/python" ] || python3 -m venv "${BOT_DIR}/venv"
"${BOT_DIR}/venv/bin/pip" install -q --upgrade pip
"${BOT_DIR}/venv/bin/pip" install -q -r "${BOT_DIR}/requirements.txt"

# --- Data ------------------------------------------------------------------
step "Restoring data"
systemctl stop "${SERVICE}" 2>/dev/null || true
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
tar -xzf "${BOT_BACKUP}" -C "${TMP}" bot.db .env

if [ -f "${BOT_DIR}/bot.db" ]; then
    echo "    bot.db already present, keeping it"
else
    install -m 644 "${TMP}/bot.db" "${BOT_DIR}/bot.db"
    # Projects in an old backup are usually past their expiry date: without
    # this the daily cleanup job would delete all of them on the first run.
    python3 - "${BOT_DIR}/bot.db" "${PROJECT_TTL_DAYS}" <<'PY'
import sqlite3, sys
from datetime import datetime, timedelta, timezone
now = datetime.now(timezone.utc).replace(tzinfo=None)
ttl = int(sys.argv[2])
c = sqlite3.connect(sys.argv[1])
n = c.execute(
    "UPDATE projects SET expires_at = ?, notified = 0 WHERE expires_at <= ?",
    ((now + timedelta(days=ttl)).isoformat(), (now + timedelta(days=7)).isoformat()),
).rowcount
c.commit()
users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
projects = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
print(f"    bot.db restored: {users} user(s), {projects} project(s); extended {n} by {ttl} days")
PY
fi

if [ ! -f "${BOT_DIR}/.env" ]; then
    install -m 600 "${TMP}/.env" "${BOT_DIR}/.env"
fi
sed -i -e '$a\' "${BOT_DIR}/.env"
sed -i -E '/^[[:space:]]*BOT_TOKEN[[:space:]]*=/d' "${BOT_DIR}/.env"
printf 'BOT_TOKEN=%s\n' "${BOT_TOKEN}" >> "${BOT_DIR}/.env"

mkdir -p "${SITES_DIR}"
if [ -z "$(ls -A "${SITES_DIR}")" ]; then
    # Archive root is 'sites/...'
    tar -xzf "${SITES_BACKUP}" -C "$(dirname "${SITES_DIR}")"
    echo "    sites restored: $(find "${SITES_DIR}" -mindepth 2 -maxdepth 2 -type d | wc -l) project dir(s)"
else
    echo "    ${SITES_DIR} not empty, keeping it"
fi

step "Permissions"
chown -R "${BOT_USER}:${BOT_USER}" "${BOT_DIR}"
chmod 600 "${BOT_DIR}/.env"
chown -R "${BOT_USER}:www-data" "${SITES_DIR}"
find "${SITES_DIR}" -type d -exec chmod 2775 {} \;
find "${SITES_DIR}" -type f -exec chmod 644 {} \;

# Read the token exactly the way the bot does (see MIGRATION_NOTES, problem 5)
TOKEN_LEN="$(cd "${BOT_DIR}" && runuser -u "${BOT_USER}" -- ./venv/bin/python -c \
    "from dotenv import load_dotenv; load_dotenv(); import os; print(len(os.getenv('BOT_TOKEN','')))")"
[ "${TOKEN_LEN}" -gt 20 ] || die "bot cannot read BOT_TOKEN from ${BOT_DIR}/.env"

# --- Bot online ------------------------------------------------------------
step "Starting the bot"
cat > "/etc/systemd/system/${SERVICE}.service" <<SERVICE
[Unit]
Description=HTML Hosting Telegram Bot
After=network.target

[Service]
Type=simple
User=${BOT_USER}
Group=${BOT_USER}
WorkingDirectory=${BOT_DIR}
ExecStart=${BOT_DIR}/venv/bin/python ${BOT_DIR}/bot.py
Restart=always
RestartSec=5
# New files (bot.db, extracted sites) get mode 644 so nginx (www-data) can read them
UMask=0022
Environment=PYTHONUNBUFFERED=1

# --- Hardening ---
NoNewPrivileges=true
ProtectSystem=full
PrivateTmp=true
ReadWritePaths=${BOT_DIR} ${SITES_DIR}

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable "${SERVICE}" >/dev/null
systemctl restart "${SERVICE}"
sleep 8
if systemctl is-active --quiet "${SERVICE}"; then
    echo "    bot is running"
    BOT_OK=1
else
    journalctl -u "${SERVICE}" -n 30 --no-pager
    warn "bot is not running, see the log above"
    BOT_OK=0
fi

# --- DNS + SSL -------------------------------------------------------------
CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
if [ -n "${CF_TOKEN}" ]; then
    step "Cloudflare DNS: ${DOMAIN}, *.${DOMAIN} -> ${SERVER_IP}"
    CF_TOKEN="${CF_TOKEN}" python3 - "${DOMAIN}" "${SERVER_IP}" <<'PY' \
        || warn "set DNS manually in Cloudflare: A @ and A * -> ${SERVER_IP}"
import json, os, sys, urllib.error, urllib.parse, urllib.request
domain, ip = sys.argv[1], sys.argv[2]
API = "https://api.cloudflare.com/client/v4"

def call(method, path, params=None, body=None):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + os.environ["CF_TOKEN"],
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["result"]
    except urllib.error.HTTPError as e:
        sys.exit(f"    Cloudflare API {method} {path}: {e.code} {e.read().decode()[:300]}")

zones = call("GET", "/zones", {"name": domain})
if not zones:
    sys.exit(f"    zone {domain} is not visible for this token")
zid = zones[0]["id"]
for name in (domain, "*." + domain):
    recs = call("GET", f"/zones/{zid}/dns_records", {"type": "A", "name": name})
    if not recs:
        call("POST", f"/zones/{zid}/dns_records",
             body={"type": "A", "name": name, "content": ip, "ttl": 1, "proxied": False})
        print(f"    {name}: created -> {ip}")
    for r in recs:
        if r["content"] == ip:
            print(f"    {name}: already {ip}")
        else:
            call("PATCH", f"/zones/{zid}/dns_records/{r['id']}", body={"content": ip})
            print(f"    {name}: {r['content']} -> {ip}")
# Stale challenge records break the next issuance (MIGRATION_NOTES, problem 4)
for r in call("GET", f"/zones/{zid}/dns_records", {"type": "TXT", "name": "_acme-challenge." + domain}):
    call("DELETE", f"/zones/{zid}/dns_records/{r['id']}")
    print("    removed stale TXT _acme-challenge")
PY

    step "SSL certificate"
    mkdir -p /etc/letsencrypt
    (umask 077; printf 'dns_cloudflare_api_token = %s\n' "${CF_TOKEN}" > /etc/letsencrypt/cloudflare.ini)
    certbot certonly \
        --dns-cloudflare \
        --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
        --dns-cloudflare-propagation-seconds 60 \
        -d "${DOMAIN}" \
        -d "*.${DOMAIN}" \
        --keep-until-expiring \
        --non-interactive \
        --agree-tos \
        --email "admin@${DOMAIN}" \
        || warn "certbot failed, see the output above"
    # Renewed certificates are only picked up after an nginx reload
    mkdir -p /etc/letsencrypt/renewal-hooks/deploy
    printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
    chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
    systemctl enable --now certbot.timer 2>/dev/null || true
fi

# --- nginx -----------------------------------------------------------------
if [ -f "${CERT}" ]; then
    step "Configuring nginx"
    rm -f /etc/nginx/conf.d/gzip.conf
    cat > /etc/nginx/conf.d/gzip-extra.conf <<GZIP
gzip_vary on;
gzip_proxied any;
gzip_min_length 256;
gzip_types text/plain text/css application/json application/javascript
           text/xml application/xml application/xml+rss text/javascript
           application/wasm image/svg+xml font/woff2;
GZIP

    cat > /etc/nginx/sites-available/html-hosting <<NGINX
# HTTP → HTTPS redirect
server {
    listen 80;
    server_name ${DOMAIN} *.${DOMAIN};
    return 301 https://\$host\$request_uri;
}

# Main domain
server {
    listen 443 ssl;
    server_name ${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    location / {
        return 200 'HTML Hosting Bot is running.';
        add_header Content-Type text/plain;
    }
}

# Wildcard subdomains
server {
    listen 443 ssl;
    server_name *.${DOMAIN};

    ssl_certificate /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;

    set \$subdomain "";
    if (\$host ~* ^(.+)\.${DOMAIN//./\\.}\$) {
        set \$subdomain \$1;
    }

    root ${SITES_DIR}/\$subdomain;
    index index.html;
    autoindex off;

    location / {
        try_files \$uri \$uri/ =404;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # CORS headers
    add_header Access-Control-Allow-Origin "*" always;
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
    add_header Access-Control-Allow-Headers "DNT, User-Agent, X-Requested-With, If-Modified-Since, Cache-Control, Content-Type, Range, Authorization" always;

    # Cache static assets
    location ~* \.(css|js|jpg|jpeg|png|gif|ico|svg|woff|woff2|ttf|eot|otf|webp|avif|mp4|webm|ogg|mp3|wav|json|xml|wasm|map|mjs)$ {
        expires 7d;
        add_header Cache-Control "public, immutable";
        add_header Access-Control-Allow-Origin "*";
    }
}
NGINX

    ln -sf /etc/nginx/sites-available/html-hosting /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    nginx -t && systemctl reload nginx
    NGINX_OK=1
else
    warn "no certificate at ${CERT}: nginx not configured, sites will not open yet"
    NGINX_OK=0
fi

# --- Firewall: do not touch Amnezia's rules -------------------------------
step "Firewall"
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
    ufw allow 80/tcp
    ufw allow 443/tcp
else
    echo "    ufw inactive, left untouched (Amnezia VPN keeps working)"
fi

# --- Summary ---------------------------------------------------------------
step "Check"
if [ "${NGINX_OK}" -eq 1 ]; then
    curl -sk -m 10 --resolve "${DOMAIN}:443:127.0.0.1" "https://${DOMAIN}/" && echo
fi
echo
echo "========================================="
[ "${BOT_OK}" -eq 1 ]   && echo "  Bot:   RUNNING" || echo "  Bot:   NOT RUNNING (journalctl -u ${SERVICE} -n 50)"
[ "${NGINX_OK}" -eq 1 ] && echo "  Sites: https://<user>.${DOMAIN}/<project>/" || echo "  Sites: NOT CONFIGURED (needs Cloudflare token + certificate)"
echo "========================================="
echo "Logs: journalctl -u ${SERVICE} -f"
