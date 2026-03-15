from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from config import ADMIN_USERS, DOMAIN

router = Router()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_USERS:
        await message.answer("⛔ У вас нет прав администратора.")
        return

    projects = await db.get_all_projects()
    if not projects:
        await message.answer("Нет ни одного проекта.")
        return

    lines = [f"<b>Все проекты ({len(projects)}):</b>\n"]
    for p in projects:
        url = f"https://{p['username']}.{DOMAIN}/{p['slug']}/"
        expires = datetime.fromisoformat(p["expires_at"])
        days_left = (expires - datetime.utcnow()).days
        lines.append(
            f"• <b>{p['username']}/{p['slug']}</b> (user: {p['user_id']})\n"
            f"  🔗 {url}\n"
            f"  ⏳ {days_left} дн."
        )

    text = "\n".join(lines)
    # Telegram message limit: 4096 chars
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await message.answer(text[i:i + 4000], parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)
