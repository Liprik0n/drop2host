from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import database as db
from config import ALLOWED_USERS, DOMAIN, ALLOWED_EXTENSIONS, SLUG_MIN_LENGTH, SLUG_MAX_LENGTH, MAX_FILE_SIZE
from services.transliterate import transliterate, validate_slug
from services.file_manager import (
    save_html_file,
    save_zip_archive,
    generate_random_slug,
)

router = Router()


class Upload(StatesGroup):
    waiting_for_project_name = State()
    waiting_for_overwrite_confirm = State()


def _get_file_ext(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


@router.message(F.document)
async def handle_document(message: Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    if user_id not in ALLOWED_USERS:
        return

    user = await db.get_user(user_id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь: /start")
        return

    doc = message.document
    ext = _get_file_ext(doc.file_name or "")

    if ext not in ALLOWED_EXTENSIONS:
        await message.answer(
            f"❌ Неподдерживаемый формат: {ext}\n"
            f"Допустимые: {', '.join(ALLOWED_EXTENSIONS)}"
        )
        return

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        size_mb = doc.file_size / (1024 * 1024)
        limit_mb = MAX_FILE_SIZE / (1024 * 1024)
        await message.answer(
            f"❌ Файл слишком большой: {size_mb:.1f} МБ\n"
            f"Максимальный размер: {limit_mb:.0f} МБ"
        )
        return

    # Download file
    file = await bot.get_file(doc.file_id)
    file_data = await bot.download_file(file.file_path)
    content = file_data.read()

    # Store file data and type in FSM
    await state.update_data(
        file_content=content,
        file_ext=ext,
        original_filename=doc.file_name,
        username=user["username"],
    )

    # Check if caption has project name
    if message.caption and message.caption.strip():
        raw_name = message.caption.strip()
        if raw_name.lower() == "auto":
            slug = generate_random_slug()
            await _save_project(message, state, slug, raw_name)
            return
        slug = transliterate(raw_name)
        error = validate_slug(slug, SLUG_MIN_LENGTH, SLUG_MAX_LENGTH)
        if not error:
            await state.update_data(pending_slug=slug, pending_original=raw_name)
            existing = await db.get_project(user_id, slug)
            if existing:
                await _ask_overwrite(message, slug)
                await state.set_state(Upload.waiting_for_overwrite_confirm)
                return
            await _save_project(message, state, slug, raw_name)
            return

    await message.answer(
        "Введите имя для проекта (станет частью URL).\n"
        "Или отправьте <b>auto</b> для случайного имени.",
        parse_mode="HTML",
    )
    await state.set_state(Upload.waiting_for_project_name)


@router.message(Upload.waiting_for_project_name)
async def process_project_name(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("file_content"):
        await message.answer("Сначала отправьте файл.")
        await state.clear()
        return

    raw_name = message.text.strip()

    if raw_name.lower() == "auto":
        slug = generate_random_slug()
        await _save_project(message, state, slug, raw_name)
        return

    slug = transliterate(raw_name)
    error = validate_slug(slug, SLUG_MIN_LENGTH, SLUG_MAX_LENGTH)
    if error:
        await message.answer(
            f"❌ {error}\n"
            f"Транслитерация: <b>{slug}</b>\n"
            f"Попробуйте другое имя или отправьте <b>auto</b>.",
            parse_mode="HTML",
        )
        return

    user_id = message.from_user.id
    existing = await db.get_project(user_id, slug)
    if existing:
        await state.update_data(pending_slug=slug, pending_original=raw_name)
        await _ask_overwrite(message, slug)
        await state.set_state(Upload.waiting_for_overwrite_confirm)
        return

    await _save_project(message, state, slug, raw_name)


async def _ask_overwrite(message: Message, slug: str):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Перезаписать", callback_data=f"overwrite:{slug}"),
            InlineKeyboardButton(text="Новое имя", callback_data="new_name"),
        ]
    ])
    await message.answer(
        f"Проект <b>{slug}</b> уже существует. Перезаписать?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("overwrite:"))
async def callback_overwrite(callback: CallbackQuery, state: FSMContext):
    slug = callback.data.split(":", 1)[1]
    data = await state.get_data()
    if not data.get("file_content"):
        await callback.answer("Файл не найден, отправьте заново.")
        await state.clear()
        return

    username = data["username"]
    original = data.get("pending_original", slug)

    # Save files
    if data["file_ext"] == ".zip":
        save_zip_archive(username, slug, data["file_content"])
    else:
        save_html_file(username, slug, data["file_content"])

    await db.update_project(callback.from_user.id, slug, original)
    await state.clear()

    url = f"https://{username}.{DOMAIN}/{slug}/"
    await callback.message.edit_text(
        f"✅ Проект <b>{slug}</b> перезаписан!\n\n🔗 {url}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "new_name")
async def callback_new_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите другое имя для проекта или отправьте <b>auto</b>.",
        parse_mode="HTML",
    )
    await state.set_state(Upload.waiting_for_project_name)
    await callback.answer()


async def _save_project(message: Message, state: FSMContext, slug: str, original_name: str):
    data = await state.get_data()
    username = data["username"]

    if data["file_ext"] == ".zip":
        try:
            save_zip_archive(username, slug, data["file_content"])
        except ValueError as e:
            await message.answer(f"❌ Ошибка архива: {e}")
            await state.clear()
            return
    else:
        save_html_file(username, slug, data["file_content"])

    await db.create_project(message.from_user.id, slug, original_name)
    await state.clear()

    url = f"https://{username}.{DOMAIN}/{slug}/"
    await message.answer(
        f"✅ Проект <b>{slug}</b> размещён!\n\n🔗 {url}",
        parse_mode="HTML",
    )
