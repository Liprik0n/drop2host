from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import ALLOWED_USERS, DOMAIN
from services.file_manager import delete_project_files

router = Router()


@router.message(Command("list"))
async def cmd_list(message: Message):
    user_id = message.from_user.id
    if user_id not in ALLOWED_USERS:
        return

    user = await db.get_user(user_id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    projects = await db.get_user_projects(user_id)
    if not projects:
        await message.answer("У вас пока нет проектов. Отправьте HTML или ZIP файл.")
        return

    for p in projects:
        url = f"https://{user['username']}.{DOMAIN}/{p['slug']}/"
        expires = datetime.fromisoformat(p["expires_at"])
        days_left = (expires - datetime.utcnow()).days

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Открыть", url=url),
                InlineKeyboardButton(text="Удалить", callback_data=f"ask_delete:{p['slug']}"),
            ]
        ])

        desc_line = f"\n📝 {p['description']}" if p.get('description') else ""
        await message.answer(
            f"<b>{p['slug']}</b>{desc_line}\n"
            f"🔗 {url}\n"
            f"⏳ Осталось: {days_left} дн.",
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )


@router.message(Command("delete"))
async def cmd_delete(message: Message):
    user_id = message.from_user.id
    if user_id not in ALLOWED_USERS:
        return

    user = await db.get_user(user_id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /delete <имя-проекта>\n\nИли нажмите «Мои проекты» и используйте кнопку «Удалить».")
        return

    slug = parts[1].strip()
    project = await db.get_project(user_id, slug)
    if not project:
        await message.answer(f"Проект <b>{slug}</b> не найден.", parse_mode="HTML")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, удалить", callback_data=f"confirm_delete:{slug}"),
            InlineKeyboardButton(text="Отмена", callback_data="cancel_delete"),
        ]
    ])
    await message.answer(
        f"Удалить проект <b>{slug}</b>? Это действие необратимо.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("ask_delete:"))
async def callback_ask_delete(callback: CallbackQuery):
    slug = callback.data.split(":", 1)[1]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да, удалить", callback_data=f"confirm_delete:{slug}"),
            InlineKeyboardButton(text="Отмена", callback_data="cancel_delete"),
        ]
    ])
    await callback.message.edit_text(
        f"Удалить проект <b>{slug}</b>? Это действие необратимо.",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_delete:"))
async def callback_confirm_delete(callback: CallbackQuery):
    slug = callback.data.split(":", 1)[1]
    user_id = callback.from_user.id

    user = await db.get_user(user_id)
    if not user:
        await callback.answer("Ошибка")
        return

    project = await db.get_project(user_id, slug)
    if not project:
        await callback.message.edit_text(f"Проект <b>{slug}</b> не найден.", parse_mode="HTML")
        await callback.answer()
        return

    delete_project_files(user["username"], slug)
    await db.delete_project(user_id, slug)

    await callback.message.edit_text(
        f"🗑 Проект <b>{slug}</b> удалён.", parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_delete")
async def callback_cancel_delete(callback: CallbackQuery):
    await callback.message.edit_text("Удаление отменено.")
    await callback.answer()


# ── Extend project (from scheduler notifications) ──

@router.callback_query(F.data.startswith("extend:"))
async def callback_extend(callback: CallbackQuery):
    parts = callback.data.split(":")
    user_id = int(parts[1])
    slug = parts[2]

    if callback.from_user.id != user_id:
        await callback.answer("Это не ваш проект.")
        return

    await db.extend_project(user_id, slug)
    await callback.message.edit_text(
        f"✅ Проект <b>{slug}</b> продлён на 90 дней.", parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_now:"))
async def callback_delete_now(callback: CallbackQuery):
    parts = callback.data.split(":")
    user_id = int(parts[1])
    slug = parts[2]

    if callback.from_user.id != user_id:
        await callback.answer("Это не ваш проект.")
        return

    user = await db.get_user(user_id)
    if user:
        delete_project_files(user["username"], slug)
    await db.delete_project(user_id, slug)

    await callback.message.edit_text(
        f"🗑 Проект <b>{slug}</b> удалён.", parse_mode="HTML"
    )
    await callback.answer()
