#!/bin/bash
# ================================================
# Migration script for the HTML Hosting Telegram Bot
# Restores the database and the published sites from backups
# onto a freshly prepared server (after setup_server.sh has run).
# ================================================
# Usage:
#   sudo bash migrate.sh [HTML_BOT_BACKUP] [SITES_BACKUP]
# Defaults:
#   HTML_BOT_BACKUP = ./html-bot-backup.tar.gz   (contains bot.db + .env)
#   SITES_BACKUP    = ./sites-backup.tar.gz      (contains sites/...)
#
# Safe to re-run. Existing .env is never overwritten silently.

set -euo pipefail

BOT_DIR="/opt/html-bot"
SITES_DIR="/var/www/sites"
BOT_USER="htmlbot"
SERVICE="html-bot"

BOT_BACKUP="${1:-html-bot-backup.tar.gz}"
SITES_BACKUP="${2:-sites-backup.tar.gz}"

# --- Sanity checks ---------------------------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run as root (sudo bash migrate.sh ...)" >&2
    exit 1
fi
if [ ! -d "${BOT_DIR}" ]; then
    echo "ERROR: ${BOT_DIR} not found. Run setup_server.sh first." >&2
    exit 1
fi
if ! id "${BOT_USER}" &>/dev/null; then
    echo "ERROR: user '${BOT_USER}' does not exist. Run setup_server.sh first." >&2
    exit 1
fi
for f in "${BOT_BACKUP}" "${SITES_BACKUP}"; do
    if [ ! -f "$f" ]; then
        echo "ERROR: backup file not found: $f" >&2
        exit 1
    fi
done

# --- Stop the bot so the SQLite DB is not locked during restore ------------
if systemctl is-active --quiet "${SERVICE}"; then
    echo "=== Stopping ${SERVICE} ==="
    systemctl stop "${SERVICE}"
    RESTART_AFTER=1
else
    RESTART_AFTER=0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

# --- Restore the database --------------------------------------------------
echo "=== Restoring database (bot.db) ==="
# The backup stores files at the archive root (bot.db, .env, *.py, ...).
# Extract only the data we need; the code itself comes from git.
tar -xzf "${BOT_BACKUP}" -C "${TMP}" bot.db
if [ -f "${BOT_DIR}/bot.db" ]; then
    BK="${BOT_DIR}/bot.db.bak.$(date +%Y%m%d%H%M%S)"
    echo "    existing bot.db -> ${BK}"
    cp -a "${BOT_DIR}/bot.db" "${BK}"
fi
install -o "${BOT_USER}" -g "${BOT_USER}" -m 644 "${TMP}/bot.db" "${BOT_DIR}/bot.db"

# --- Restore .env (settings: ALLOWED_USERS / ADMIN_USERS / DOMAIN ...) ------
echo "=== Restoring .env ==="
if tar -tzf "${BOT_BACKUP}" | grep -qx '.env'; then
    tar -xzf "${BOT_BACKUP}" -C "${TMP}" .env
    if [ -f "${BOT_DIR}/.env" ]; then
        echo "    ${BOT_DIR}/.env already exists -> saved backup copy as .env.from-backup"
        install -o "${BOT_USER}" -g "${BOT_USER}" -m 600 "${TMP}/.env" "${BOT_DIR}/.env.from-backup"
    else
        install -o "${BOT_USER}" -g "${BOT_USER}" -m 600 "${TMP}/.env" "${BOT_DIR}/.env"
        echo "    .env restored. !!! UPDATE BOT_TOKEN with the newly reissued token !!!"
    fi
else
    echo "    no .env in backup, skipping"
fi

# --- Restore the published sites -------------------------------------------
echo "=== Restoring sites into ${SITES_DIR} ==="
# Archive root is 'sites/...', so extract one level above SITES_DIR.
mkdir -p "${SITES_DIR}"
tar -xzf "${SITES_BACKUP}" -C "$(dirname "${SITES_DIR}")"

# --- Fix ownership & permissions (bot writes, nginx/www-data reads) --------
echo "=== Fixing permissions ==="
chown -R "${BOT_USER}:www-data" "${SITES_DIR}"
find "${SITES_DIR}" -type d -exec chmod 2775 {} \;
find "${SITES_DIR}" -type f -exec chmod 644 {} \;

SITE_COUNT="$(find "${SITES_DIR}" -mindepth 2 -maxdepth 2 -type d | wc -l)"
USER_COUNT="$(find "${SITES_DIR}" -mindepth 1 -maxdepth 1 -type d | wc -l)"

# --- Restart the bot -------------------------------------------------------
if [ "${RESTART_AFTER}" -eq 1 ]; then
    echo "=== Starting ${SERVICE} ==="
    systemctl start "${SERVICE}"
fi

echo ""
echo "========================================="
echo "  Migration complete!"
echo "========================================="
echo "  Restored: ${USER_COUNT} user(s), ${SITE_COUNT} project(s)"
echo ""
echo "Next:"
echo "  1. Make sure ${BOT_DIR}/.env has the NEW reissued BOT_TOKEN"
echo "     (a backed-up .env may be at ${BOT_DIR}/.env.from-backup)"
echo "  2. sudo systemctl restart ${SERVICE}"
echo "  3. sudo systemctl status ${SERVICE}"
echo "  4. journalctl -u ${SERVICE} -f"
