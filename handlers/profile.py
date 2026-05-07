from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import database as db
from keyboards.inline import kb_profile, kb_cancel, kb_main_menu, kb_avatar_skip, kb_back

router = Router()

class ProfileFSM(StatesGroup):
    nickname     = State()
    age          = State()
    avatar       = State()
    edit_nickname = State()
    edit_age      = State()
    edit_avatar   = State()


def kb_edit_choice():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Изменить имя",        callback_data="edit_only_name")],
        [InlineKeyboardButton(text="🎂 Изменить возраст",    callback_data="edit_only_age")],
        [InlineKeyboardButton(text="🖼 Изменить фото",       callback_data="edit_only_avatar")],
        [InlineKeyboardButton(text="✏️ Изменить всё сразу",  callback_data="edit_all")],
        [InlineKeyboardButton(text="◀️ Назад",               callback_data="my_profile")],
    ])


# ─── КНОПКА "РЕДАКТИРОВАТЬ" ───────────────────────────────

@router.callback_query(F.data == "edit_profile")
async def edit_profile_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await call.message.edit_text(
            "✏️ <b>Что хочешь изменить?</b>",
            parse_mode="HTML",
            reply_markup=kb_edit_choice()
        )
    except Exception:
        await call.message.answer(
            "✏️ <b>Что хочешь изменить?</b>",
            parse_mode="HTML",
            reply_markup=kb_edit_choice()
        )


# ─── ТОЛЬКО ИМЯ ───────────────────────────────────────────

@router.callback_query(F.data == "edit_only_name")
async def edit_only_name(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "✏️ Введи новый <b>никнейм</b> (до 30 символов):",
        parse_mode="HTML",
        reply_markup=kb_cancel("edit_profile")
    )
    await state.set_state(ProfileFSM.edit_nickname)

@router.message(ProfileFSM.edit_nickname)
async def save_edit_nickname(message: Message, state: FSMContext):
    nick = message.text.strip() if message.text else ""
    if not nick or len(nick) > 30:
        await message.answer("❌ Никнейм должен быть от 1 до 30 символов:")
        return
    user = await db.get_user(message.from_user.id)
    await db.update_profile(message.from_user.id, nick, user["age"], user["avatar_id"])
    await state.clear()
    await message.answer(f"✅ Никнейм обновлён: <b>{nick}</b>",
                         parse_mode="HTML", reply_markup=kb_main_menu(has_profile=True))


# ─── ТОЛЬКО ВОЗРАСТ ───────────────────────────────────────

@router.callback_query(F.data == "edit_only_age")
async def edit_only_age(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "✏️ Введи новый <b>возраст</b>:",
        parse_mode="HTML",
        reply_markup=kb_cancel("edit_profile")
    )
    await state.set_state(ProfileFSM.edit_age)

@router.message(ProfileFSM.edit_age)
async def save_edit_age(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Введи число:")
        return
    age = int(message.text)
    if age < 1 or age > 120:
        await message.answer("❌ Введи реальный возраст:")
        return
    user = await db.get_user(message.from_user.id)
    await db.update_profile(message.from_user.id, user["nickname"], age, user["avatar_id"])
    await state.clear()
    await message.answer(f"✅ Возраст обновлён: <b>{age}</b>",
                         parse_mode="HTML", reply_markup=kb_main_menu(has_profile=True))


# ─── ТОЛЬКО ФОТО ──────────────────────────────────────────

@router.callback_query(F.data == "edit_only_avatar")
async def edit_only_avatar(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "✏️ Отправь новое <b>фото</b> или нажми «Пропустить» (убрать фото):",
        parse_mode="HTML",
        reply_markup=kb_avatar_skip()
    )
    await state.set_state(ProfileFSM.edit_avatar)

@router.message(ProfileFSM.edit_avatar, F.photo)
async def save_edit_avatar(message: Message, state: FSMContext):
    avatar_id = message.photo[-1].file_id
    user = await db.get_user(message.from_user.id)
    await db.update_profile(message.from_user.id, user["nickname"], user["age"], avatar_id)
    await state.clear()
    await message.answer("✅ Фото обновлено!", reply_markup=kb_main_menu(has_profile=True))

@router.callback_query(F.data == "skip_avatar", ProfileFSM.edit_avatar)
async def skip_edit_avatar(call: CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    await db.update_profile(call.from_user.id, user["nickname"], user["age"], None)
    await state.clear()
    await call.message.edit_text("✅ Фото удалено.", reply_markup=kb_main_menu(has_profile=True))


# ─── ВСЁ СРАЗУ / СОЗДАТЬ ПРОФИЛЬ ─────────────────────────

@router.callback_query(F.data.in_({"create_profile", "edit_all"}))
async def start_profile(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "✏️ Шаг 1/3 — Введи свой <b>никнейм</b> (до 30 символов):",
        parse_mode="HTML",
        reply_markup=kb_cancel("main_menu")
    )
    await state.set_state(ProfileFSM.nickname)

@router.message(ProfileFSM.nickname)
async def get_nickname(message: Message, state: FSMContext):
    nick = message.text.strip() if message.text else ""
    if not nick or len(nick) > 30:
        await message.answer("❌ Никнейм должен быть от 1 до 30 символов:")
        return
    await state.update_data(nickname=nick)
    await message.answer("✏️ Шаг 2/3 — Сколько тебе <b>лет</b>? (введи число):",
                         parse_mode="HTML", reply_markup=kb_cancel("main_menu"))
    await state.set_state(ProfileFSM.age)

@router.message(ProfileFSM.age)
async def get_age(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Введи число:")
        return
    age = int(message.text)
    if age < 1 or age > 120:
        await message.answer("❌ Введи реальный возраст:")
        return
    await state.update_data(age=age)
    await message.answer("✏️ Шаг 3/3 — Отправь <b>фото для аватарки</b>\nили нажми «Пропустить»:",
                         parse_mode="HTML", reply_markup=kb_avatar_skip())
    await state.set_state(ProfileFSM.avatar)

@router.message(ProfileFSM.avatar, F.photo)
async def get_avatar_photo(message: Message, state: FSMContext):
    await _save_profile(message, state, message.photo[-1].file_id)

@router.callback_query(F.data == "skip_avatar", ProfileFSM.avatar)
async def skip_avatar(call: CallbackQuery, state: FSMContext):
    await _save_profile_from_call(call, state, None)

async def _save_profile(message: Message, state: FSMContext, avatar_id):
    data = await state.get_data()
    await db.update_profile(message.from_user.id, data["nickname"], data["age"], avatar_id)
    await state.clear()
    await message.answer(
        f"✅ Профиль сохранён!\n\n👤 Ник: <b>{data['nickname']}</b>\n🎂 Возраст: <b>{data['age']}</b>",
        parse_mode="HTML", reply_markup=kb_main_menu(has_profile=True))

async def _save_profile_from_call(call: CallbackQuery, state: FSMContext, avatar_id):
    data = await state.get_data()
    await db.update_profile(call.from_user.id, data["nickname"], data["age"], avatar_id)
    await state.clear()
    await call.message.edit_text(
        f"✅ Профиль сохранён!\n\n👤 Ник: <b>{data['nickname']}</b>\n🎂 Возраст: <b>{data['age']}</b>",
        parse_mode="HTML", reply_markup=kb_main_menu(has_profile=True))


# ─── ПРОСМОТР ПРОФИЛЯ ─────────────────────────────────────

@router.callback_query(F.data == "my_profile")
async def show_profile(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await db.get_user(call.from_user.id)
    if not user or not user["nickname"]:
        await call.message.edit_text("У тебя ещё нет профиля.",
                                     reply_markup=kb_main_menu(has_profile=False))
        return

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Ник: <b>{user['nickname']}</b>\n"
        f"Возраст: <b>{user['age']}</b>\n"
        f"Баланс: <b>{user['balance']:.0f} ₽</b>"
    )
    kb = kb_profile()
    if user["avatar_id"]:
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer_photo(user["avatar_id"], caption=text,
                                        parse_mode="HTML", reply_markup=kb)
    else:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
