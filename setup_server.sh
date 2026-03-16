#!/bin/bash
# ================================================
# VPS Setup Script for HTML Hosting Telegram Bot
# Ubuntu 22.04 / 24.04
# ================================================
# Usage: sudo bash setup_server.sh YOUR_DOMAIN CLOUDFLARE_API_TOKEN
# Example: sudo bash setup_server.sh example.com your-cf-token-here

set -euo pipefail

DOMAIN="${1:?Usage: $0 DOMAIN CLOUDFLARE_API_TOKEN}"
CF_TOKEN="${2:?Usage: $0 DOMAIN CLOUDFLARE_API_TOKEN}"
SITES_DIR="/var/www/sites"
BOT_DIR="/opt/html-bot"
BOT_USER="htmlbot"

echo "=== Installing packages ==="
apt update
apt install -y nginx certbot python3-certbot-dns-cloudflare python3-venv python3-pip ufw

echo "=== Setting up Cloudflare credentials ==="
mkdir -p /etc/letsencrypt
cat > /etc/letsencrypt/cloudflare.ini <<EOF
dns_cloudflare_api_token = ${CF_TOKEN}
EOF
chmod 600 /etc/letsencrypt/cloudflare.ini

echo "=== Obtaining wildcard SSL certificate ==="
certbot certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
    -d "${DOMAIN}" \
    -d "*.${DOMAIN}" \
    --non-interactive \
    --agree-tos \
    --email "admin@${DOMAIN}"

echo "=== Creating sites directory ==="
mkdir -p "${SITES_DIR}"

echo "=== Configuring Nginx gzip compression ==="
cat > /etc/nginx/conf.d/gzip.conf <<GZIP
gzip on;
gzip_vary on;
gzip_proxied any;
gzip_min_length 256;
gzip_types text/plain text/css application/json application/javascript
           text/xml application/xml application/xml+rss text/javascript
           application/wasm image/svg+xml font/woff2;
GZIP

echo "=== Configuring Nginx ==="
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

echo "=== Creating bot user and directory ==="
useradd -r -s /bin/false "${BOT_USER}" 2>/dev/null || true
mkdir -p "${BOT_DIR}"

echo "=== Setting up Python virtual environment ==="
python3 -m venv "${BOT_DIR}/venv"
"${BOT_DIR}/venv/bin/pip" install --upgrade pip

echo "=== Copy your bot files to ${BOT_DIR} and run: ==="
echo "  cp -r /path/to/bot/* ${BOT_DIR}/"
echo "  cp .env ${BOT_DIR}/.env"
echo "  ${BOT_DIR}/venv/bin/pip install -r ${BOT_DIR}/requirements.txt"

echo "=== Creating systemd service ==="
cat > /etc/systemd/system/html-bot.service <<SERVICE
[Unit]
Description=HTML Hosting Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${BOT_DIR}
ExecStart=${BOT_DIR}/venv/bin/python ${BOT_DIR}/bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable html-bot

echo "=== Configuring firewall ==="
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "=== Setting up SSL auto-renewal ==="
systemctl enable certbot.timer
systemctl start certbot.timer

echo "=== Setting permissions ==="
chown -R root:root "${SITES_DIR}"
chmod -R 755 "${SITES_DIR}"

echo ""
echo "========================================="
echo "  Setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Copy bot files to ${BOT_DIR}/"
echo "2. Create ${BOT_DIR}/.env with your settings"
echo "3. Install dependencies: ${BOT_DIR}/venv/bin/pip install -r ${BOT_DIR}/requirements.txt"
echo "4. Start the bot: systemctl start html-bot"
echo "5. Check status: systemctl status html-bot"
echo "6. View logs: journalctl -u html-bot -f"
echo ""
echo "DNS: Make sure Cloudflare has:"
echo "  A record: @ -> your server IP"
echo "  A record: * -> your server IP"
