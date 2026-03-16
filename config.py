import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DOMAIN = os.getenv("DOMAIN", "drop2host.ru")

ALLOWED_USERS = set(
    int(uid.strip())
    for uid in os.getenv("ALLOWED_USERS", "").split(",")
    if uid.strip().isdigit()
)

ADMIN_USERS = set(
    int(uid.strip())
    for uid in os.getenv("ADMIN_USERS", "").split(",")
    if uid.strip().isdigit()
)

SITES_DIR = Path(os.getenv("SITES_DIR", "/var/www/sites"))
DB_PATH = os.getenv("DB_PATH", "./bot.db")

PROJECT_TTL_DAYS = int(os.getenv("PROJECT_TTL_DAYS", "90"))
NOTIFY_BEFORE_DAYS = int(os.getenv("NOTIFY_BEFORE_DAYS", "7"))

MAX_FILE_SIZE = 30 * 1024 * 1024  # 30 MB
ALLOWED_EXTENSIONS = {".html", ".htm", ".zip"}
SLUG_MIN_LENGTH = 3
SLUG_MAX_LENGTH = 30
