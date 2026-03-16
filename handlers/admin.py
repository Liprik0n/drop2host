from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from config import ADMIN_USERS, ALLOWED_USERS, DOMAIN

router = Router()


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USERS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
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


@router.message(Command("adduser"))
async def cmd_adduser(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Использование: /adduser <telegram_id>\n\n"
            "Пользователь может узнать свой ID у @userinfobot",
            parse_mode="HTML",
        )
        return

    user_id = int(parts[1])
    if user_id in ALLOWED_USERS:
        await message.answer(f"Пользователь {user_id} уже в списке.")
        return

    ALLOWED_USERS.add(user_id)
    await message.answer(
        f"✅ Пользователь <code>{user_id}</code> добавлен.\n"
        f"Всего пользователей: {len(ALLOWED_USERS)}",
        parse_mode="HTML",
    )


@router.message(Command("removeuser"))
async def cmd_removeuser(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return

    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Использование: /removeuser <telegram_id>")
        return

    user_id = int(parts[1])
    if user_id not in ALLOWED_USERS:
        await message.answer(f"Пользователь {user_id} не в списке.")
        return

    if user_id in ADMIN_USERS:
        await message.answer("⛔ Нельзя удалить администратора.")
        return

    ALLOWED_USERS.discard(user_id)
    await message.answer(f"✅ Пользователь <code>{user_id}</code> удалён из списка.", parse_mode="HTML")


@router.message(Command("users"))
async def cmd_users(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return

    lines = [f"<b>Разрешённые пользователи ({len(ALLOWED_USERS)}):</b>\n"]
    for uid in sorted(ALLOWED_USERS):
        user = await db.get_user(uid)
        name = user["username"] if user else "не зарегистрирован"
        admin_mark = " (admin)" if uid in ADMIN_USERS else ""
        lines.append(f"• <code>{uid}</code> — {name}{admin_mark}")

    await message.answer("\n".join(lines), parse_mode="HTML")
