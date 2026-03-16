from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import database as db
from config import ALLOWED_USERS, ADMIN_USERS, DOMAIN, SLUG_MIN_LENGTH, SLUG_MAX_LENGTH
from services.transliterate import transliterate, validate_slug

router = Router()

MENU_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мои проекты"), KeyboardButton(text="Помощь")],
    ],
    resize_keyboard=True,
)


class Registration(StatesGroup):
    waiting_for_subdomain = State()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if user_id not in ALLOWED_USERS:
        await message.answer("⛔ Доступ запрещён. Ваш ID не в списке разрешённых.")
        return

    user = await db.get_user(user_id)
    if user:
        await message.answer(
            f"Привет! Ваш поддомен: <b>{user['username']}.{DOMAIN}</b>\n\n"
            "Отправьте HTML-файл или ZIP-архив — я размещу его и дам ссылку.",
            parse_mode="HTML",
            reply_markup=MENU_KEYBOARD,
        )
        return

    await message.answer(
        f"Добро пожаловать! Придумайте имя для вашего поддомена.\n"
        f"Оно станет частью URL: <b>ваше-имя.{DOMAIN}</b>\n\n"
        f"Можно вводить на русском — будет транслитерировано.\n"
        f"Длина: {SLUG_MIN_LENGTH}-{SLUG_MAX_LENGTH} символов.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Registration.waiting_for_subdomain)


@router.message(Registration.waiting_for_subdomain)
async def process_subdomain(message: Message, state: FSMContext):
    raw_name = message.text.strip()
    slug = transliterate(raw_name)

    error = validate_slug(slug, SLUG_MIN_LENGTH, SLUG_MAX_LENGTH)
    if error:
        await message.answer(
            f"❌ {error}\n"
            f"Результат транслитерации: <b>{slug}</b>\n"
            f"Попробуйте другое имя.",
            parse_mode="HTML",
        )
        return

    existing = await db.get_user_by_username(slug)
    if existing:
        await message.answer(
            f"❌ Имя <b>{slug}</b> уже занято. Выберите другое.",
            parse_mode="HTML",
        )
        return

    is_admin = message.from_user.id in ADMIN_USERS
    await db.create_user(message.from_user.id, slug, is_admin)
    await state.clear()

    await message.answer(
        f"✅ Ваш поддомен: <b>{slug}.{DOMAIN}</b>\n\n"
        "Теперь отправьте HTML-файл или ZIP-архив для размещения.",
        parse_mode="HTML",
        reply_markup=MENU_KEYBOARD,
    )


@router.message(F.text == "Мои проекты")
async def btn_my_projects(message: Message):
    from handlers.manage import cmd_list
    await cmd_list(message)


@router.message(F.text == "Помощь")
async def btn_help(message: Message):
    user_id = message.from_user.id
    if user_id not in ALLOWED_USERS:
        return

    await message.answer(
        "<b>Как пользоваться ботом:</b>\n\n"
        "1. Отправьте <b>.html</b> файл или <b>.zip</b> архив\n"
        "2. Введите имя проекта (или <b>auto</b> для случайного)\n"
        "3. Получите готовую ссылку\n\n"
        "<b>Кнопки:</b>\n"
        "• <b>Мои проекты</b> — список ваших страниц со ссылками\n\n"
        "<b>Команды:</b>\n"
        "/delete <i>имя</i> — удалить проект\n"
        "/admin — панель администратора\n\n"
        "Максимальный размер файла: <b>30 МБ</b>\n"
        "Проекты хранятся <b>90 дней</b>, за неделю до удаления придёт напоминание.",
        parse_mode="HTML",
    )
