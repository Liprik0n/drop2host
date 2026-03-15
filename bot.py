import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import database as db
from config import BOT_TOKEN
from handlers import start, upload, manage, admin
from services.scheduler import check_expiring_projects, cleanup_expired_projects

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in .env")
        return

    await db.init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None))
    dp = Dispatcher()

    # Register routers
    dp.include_router(start.router)
    dp.include_router(upload.router)
    dp.include_router(manage.router)
    dp.include_router(admin.router)

    # Scheduler: daily checks at 10:00 UTC
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_expiring_projects,
        CronTrigger(hour=10, minute=0),
        args=[bot],
    )
    scheduler.add_job(
        cleanup_expired_projects,
        CronTrigger(hour=10, minute=30),
        args=[bot],
    )
    scheduler.start()

    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
