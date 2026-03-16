from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
)

import database as db
from config import ADMIN_USERS, ALLOWED_USERS, DOMAIN

router = Router()


class AdminStates(StatesGroup):
    waiting_for_user_id = State()


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USERS


# ── Admin panel with buttons ──

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Все проекты", callback_data="admin:projects"),
            InlineKeyboardButton(text="Пользователи", callback_data="admin:users"),
        ],
        [
            InlineKeyboardButton(text="Добавить пользователя", callback_data="admin:adduser"),
        ],
    ])
    await message.answer(
        "<b>Панель администратора</b>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:projects")
async def callback_admin_projects(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.")
        return

    projects = await db.get_all_projects()
    if not projects:
        await callback.message.edit_text("Нет ни одного проекта.")
        await callback.answer()
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
    if len(text) > 4000:
        await callback.message.edit_text(text[:4000], parse_mode="HTML", disable_web_page_preview=True)
    else:
        await callback.message.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()


@router.callback_query(F.data == "admin:users")
async def callback_admin_users(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.")
        return

    lines = [f"<b>Пользователи ({len(ALLOWED_USERS)}):</b>\n"]
    for uid in sorted(ALLOWED_USERS):
        user = await db.get_user(uid)
        name = user["username"] if user else "не зарегистрирован"
        admin_mark = " (admin)" if uid in ADMIN_USERS else ""
        lines.append(f"• <code>{uid}</code> — {name}{admin_mark}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить пользователя", callback_data="admin:adduser")],
    ])
    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:adduser")
async def callback_admin_adduser(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.")
        return

    await callback.message.edit_text(
        "Отправьте Telegram ID пользователя (число).\n\n"
        "Пользователь может узнать свой ID у @userinfobot",
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_for_user_id)
    await callback.answer()


@router.message(AdminStates.waiting_for_user_id)
async def process_adduser_input(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return

    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Введите числовой Telegram ID.")
        return

    user_id = int(text)
    if user_id in ALLOWED_USERS:
        await message.answer(f"Пользователь <code>{user_id}</code> уже в списке.", parse_mode="HTML")
        await state.clear()
        return

    ALLOWED_USERS.add(user_id)
    await db.add_allowed_user(user_id)
    await state.clear()

    await message.answer(
        f"✅ Пользователь <code>{user_id}</code> добавлен.\n"
        f"Всего пользователей: {len(ALLOWED_USERS)}",
        parse_mode="HTML",
    )


# ── Remove user (from user list) ──

@router.callback_query(F.data.startswith("admin:removeuser:"))
async def callback_removeuser(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет прав.")
        return

    user_id = int(callback.data.split(":")[2])

    if user_id in ADMIN_USERS:
        await callback.answer("Нельзя удалить администратора.")
        return

    ALLOWED_USERS.discard(user_id)
    await db.remove_allowed_user(user_id)

    await callback.message.edit_text(
        f"✅ Пользователь <code>{user_id}</code> удалён из списка.",
        parse_mode="HTML",
    )
    await callback.answer()


# ── Command shortcuts ──

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
        await message.answer(f"Пользователь <code>{user_id}</code> уже в списке.", parse_mode="HTML")
        return

    ALLOWED_USERS.add(user_id)
    await db.add_allowed_user(user_id)
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
        await message.answer(f"Пользователь <code>{user_id}</code> не в списке.", parse_mode="HTML")
        return

    if user_id in ADMIN_USERS:
        await message.answer("⛔ Нельзя удалить администратора.")
        return

    ALLOWED_USERS.discard(user_id)
    await db.remove_allowed_user(user_id)
    await message.answer(f"✅ Пользователь <code>{user_id}</code> удалён из списка.", parse_mode="HTML")


@router.message(Command("users"))
async def cmd_users(message: Message):
    if not _is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет прав администратора.")
        return

    lines = [f"<b>Пользователи ({len(ALLOWED_USERS)}):</b>\n"]
    for uid in sorted(ALLOWED_USERS):
        user = await db.get_user(uid)
        name = user["username"] if user else "не зарегистрирован"
        admin_mark = " (admin)" if uid in ADMIN_USERS else ""
        lines.append(f"• <code>{uid}</code> — {name}{admin_mark}")

    await message.answer("\n".join(lines), parse_mode="HTML")
