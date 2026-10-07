import asyncio
import hashlib
import io
import json
import logging
import sqlite3
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramMigrateToChat
from aiogram.types import FSInputFile

import database as db
from config import ADMIN_USERS, DB_PATH, SITES_DIR

logger = logging.getLogger(__name__)

# Bot API rejects documents over 50 MB
PART_SIZE = 45 * 1024 * 1024
UPLOAD_TIMEOUT = 600
ENV_PATH = Path(".env")
STATE_PATH = Path("backup_state.json")
# settings key: chat chosen with /backup_here (default: admins' private chats)
BACKUP_CHAT_KEY = "backup_chat_id"

_lock = asyncio.Lock()


def _snapshot_db(dst: Path):
    """Consistent copy of the live SQLite DB, safe while the bot is writing."""
    src = sqlite3.connect(Path(DB_PATH).resolve().as_uri() + "?mode=ro", uri=True)
    out = sqlite3.connect(dst)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()


def _env_without_token() -> bytes:
    """Settings from .env minus BOT_TOKEN: the token never leaves the server."""
    if not ENV_PATH.exists():
        return b""
    kept = [
        line for line in ENV_PATH.read_text(encoding="utf-8").splitlines()
        if line.split("=", 1)[0].strip() != "BOT_TOKEN"
    ]
    return ("\n".join(kept) + "\n").encode()


def _hash_sites(h):
    if not SITES_DIR.exists():
        return
    for path in sorted(SITES_DIR.rglob("*")):
        st = path.lstat()
        h.update(f"{path.relative_to(SITES_DIR)}|{st.st_size}|{st.st_mtime_ns}\n".encode())


def _build(workdir: Path) -> tuple[str, list[Path], str]:
    """Create the archives. Returns (fingerprint, files to send, summary)."""
    db_copy = workdir / "bot.db"
    _snapshot_db(db_copy)
    env = _env_without_token()

    conn = sqlite3.connect(db_copy)
    try:
        dump = "\n".join(conn.iterdump())
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    finally:
        conn.close()

    h = hashlib.sha256()
    h.update(dump.encode())
    h.update(env)
    _hash_sites(h)

    # Same layout restore_server.sh and migrate.sh expect: bot.db and .env at the root
    bot_archive = workdir / "html-bot-backup.tar.gz"
    with tarfile.open(bot_archive, "w:gz") as tar:
        tar.add(db_copy, arcname="bot.db")
        info = tarfile.TarInfo(".env")
        info.size = len(env)
        info.mode = 0o600
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(env))

    # Root is 'sites/...': restore extracts it into /var/www
    sites_archive = workdir / "sites-backup.tar.gz"
    with tarfile.open(sites_archive, "w:gz") as tar:
        if SITES_DIR.exists():
            tar.add(SITES_DIR, arcname="sites")
        else:
            info = tarfile.TarInfo("sites")
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            tar.addfile(info)

    files = [bot_archive]
    if sites_archive.stat().st_size <= PART_SIZE:
        files.append(sites_archive)
    else:
        with sites_archive.open("rb") as f:
            n = 1
            while chunk := f.read(PART_SIZE):
                part = workdir / f"sites-backup.tar.gz.part{n:02d}"
                part.write_bytes(chunk)
                files.append(part)
                n += 1
        sites_archive.unlink()

    size_mb = sum(f.stat().st_size for f in files) / 1024 / 1024
    summary = f"Пользователей: {users}, проектов: {projects}, {size_mb:.1f} МБ"
    return h.hexdigest(), files, summary


def _last_fingerprint() -> str | None:
    try:
        return json.loads(STATE_PATH.read_text())["fingerprint"]
    except (OSError, ValueError, KeyError):
        return None


def _save_fingerprint(fingerprint: str):
    STATE_PATH.write_text(json.dumps({
        "fingerprint": fingerprint,
        "sent_at": datetime.utcnow().isoformat(),
    }))


async def _send_files(bot: Bot, chat_id: int, files: list[Path], caption: str):
    for i, path in enumerate(files):
        await bot.send_document(
            chat_id,
            FSInputFile(path),
            caption=caption if i == 0 else None,
            request_timeout=UPLOAD_TIMEOUT,
        )


async def _send_to_chat(bot: Bot, chat_id: int, files: list[Path], caption: str) -> bool:
    try:
        try:
            await _send_files(bot, chat_id, files, caption)
        except TelegramMigrateToChat as e:
            # A group upgraded to a supergroup gets a new id
            if await db.get_setting(BACKUP_CHAT_KEY) == str(chat_id):
                await db.set_setting(BACKUP_CHAT_KEY, str(e.migrate_to_chat_id))
            chat_id = e.migrate_to_chat_id
            await _send_files(bot, chat_id, files, caption)
        return True
    except Exception:
        logger.exception("Failed to send backup to %s", chat_id)
        return False


async def send_backup(bot: Bot, chat_ids: list[int] | None = None) -> bool:
    """Send the DB and sites archives.

    Scheduled run (chat_ids=None): goes to the /backup_here chat, or to every
    admin if none is set or it fails; skipped if nothing changed since the
    last sent backup. Manual run: always sent to chat_ids.
    """
    scheduled = chat_ids is None
    targets = sorted(ADMIN_USERS) if scheduled else chat_ids
    if not targets:
        logger.warning("Backup skipped: ADMIN_USERS is empty")
        return False
    backup_chat = await db.get_setting(BACKUP_CHAT_KEY) if scheduled else None

    async with _lock:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                fingerprint, files, summary = await asyncio.to_thread(_build, Path(tmp))
            except Exception as e:
                logger.exception("Backup failed")
                for chat_id in targets:
                    try:
                        await bot.send_message(chat_id, f"⚠️ Бэкап не удался: {e}")
                    except Exception:
                        logger.exception("Failed to report backup error to %s", chat_id)
                return False

            if scheduled and fingerprint == _last_fingerprint():
                logger.info("Backup skipped: nothing changed")
                return False

            caption = f"💾 Бэкап {datetime.utcnow():%Y-%m-%d %H:%M} UTC\n{summary}"
            if len(files) > 2:
                caption += (
                    "\n\nСайты разбиты на части, перед восстановлением склейте:\n"
                    "cat sites-backup.tar.gz.part* > sites-backup.tar.gz"
                )

            sent = False
            if backup_chat:
                sent = await _send_to_chat(bot, int(backup_chat), files, caption)
                if not sent:
                    caption = (
                        "⚠️ Не удалось отправить в чат бэкапов — бот всё ещё в нём? "
                        "Новый чат: /backup_here\n\n" + caption
                    )
            if not sent:
                for chat_id in targets:
                    sent = await _send_to_chat(bot, chat_id, files, caption) or sent

            if sent and scheduled:
                _save_fingerprint(fingerprint)
            if sent:
                logger.info("Backup sent: %s", summary)
            return sent
