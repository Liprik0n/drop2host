import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import NOTIFY_BEFORE_DAYS, DOMAIN
from services.file_manager import delete_project_files

logger = logging.getLogger(__name__)


async def check_expiring_projects(bot: Bot):
    """Notify users about projects expiring soon."""
    projects = await db.get_expiring_projects(NOTIFY_BEFORE_DAYS)

    for p in projects:
        try:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Продлить на 90 дней",
                        callback_data=f"extend:{p['user_id']}:{p['slug']}",
                    ),
                    InlineKeyboardButton(
                        text="Удалить сейчас",
                        callback_data=f"delete_now:{p['user_id']}:{p['slug']}",
                    ),
                ]
            ])

            url = f"https://{p['username']}.{DOMAIN}/{p['slug']}/"
            await bot.send_message(
                p["user_id"],
                f"⏰ Проект <b>{p['slug']}</b> истекает скоро!\n"
                f"🔗 {url}\n\n"
                f"Продлить или удалить?",
                reply_markup=keyboard,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            await db.mark_notified(p["id"])
            logger.info("Notified user %s about expiring project %s", p["user_id"], p["slug"])
        except Exception:
            logger.exception("Failed to notify user %s", p["user_id"])


async def cleanup_expired_projects(bot: Bot):
    """Delete projects that have passed their expiry date."""
    projects = await db.get_expired_projects()

    for p in projects:
        try:
            delete_project_files(p["username"], p["slug"])
            await db.delete_project(p["user_id"], p["slug"])

            await bot.send_message(
                p["user_id"],
                f"🗑 Проект <b>{p['slug']}</b> удалён (срок хранения истёк).",
                parse_mode="HTML",
            )
            logger.info("Deleted expired project %s/%s", p["username"], p["slug"])
        except Exception:
            logger.exception("Failed to cleanup project %s/%s", p["username"], p["slug"])
