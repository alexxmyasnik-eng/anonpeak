from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards.inline import kb_profile, kb_cancel, kb_main_menu, kb_avatar_skip, kb_back

router = Router()

class ProfileFSM(StatesGroup):
    nickname = State()
    age      = State()
    avatar   = State()

async def _show_menu(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    has_profile = bool(user["nickname"])
    try:
        await call.message.edit_text(
            "🏠 Главное меню",
            reply_markup=kb_main_menu(has_profile)
        )
    except Exception:
        await call.message.answer(
            "🏠 Главное меню",
            reply_markup=kb_main_menu(has_profile)
        )

@router.callback_query(F.data.in_({"create_profile", "edit_profile"}))
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
    await message.answer(
        "✏️ Шаг 2/3 — Сколько тебе <b>лет</b>? (введи число):",
        parse_mode="HTML",
        reply_markup=kb_cancel("main_menu")
    )
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
    await message.answer(
        "✏️ Шаг 3/3 — Отправь <b>фото для аватарки</b>\nили нажми «Пропустить»:",
        parse_mode="HTML",
        reply_markup=kb_avatar_skip()
    )
    await state.set_state(ProfileFSM.avatar)

@router.message(ProfileFSM.avatar, F.photo)
async def get_avatar_photo(message: Message, state: FSMContext):
    avatar_id = message.photo[-1].file_id
    await _save_profile(message, state, avatar_id)

@router.callback_query(F.data == "skip_avatar", ProfileFSM.avatar)
async def skip_avatar(call: CallbackQuery, state: FSMContext):
    await _save_profile_from_call(call, state, None)

async def _save_profile(message: Message, state: FSMContext, avatar_id):
    data = await state.get_data()
    await db.update_profile(message.from_user.id, data["nickname"], data["age"], avatar_id)
    await state.clear()
    user = await db.get_user(message.from_user.id)
    await message.answer(
        f"✅ Профиль сохранён!\n\n"
        f"👤 Ник: <b>{data['nickname']}</b>\n"
        f"🎂 Возраст: <b>{data['age']}</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(has_profile=True)
    )

async def _save_profile_from_call(call: CallbackQuery, state: FSMContext, avatar_id):
    data = await state.get_data()
    await db.update_profile(call.from_user.id, data["nickname"], data["age"], avatar_id)
    await state.clear()
    await call.message.edit_text(
        f"✅ Профиль сохранён!\n\n"
        f"👤 Ник: <b>{data['nickname']}</b>\n"
        f"🎂 Возраст: <b>{data['age']}</b>",
        parse_mode="HTML",
        reply_markup=kb_main_menu(has_profile=True)
    )

@router.callback_query(F.data == "my_profile")
async def show_profile(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await db.get_user(call.from_user.id)
    if not user or not user["nickname"]:
        await call.message.edit_text(
            "У тебя ещё нет профиля.",
            reply_markup=kb_main_menu(has_profile=False)
        )
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
        await call.message.answer_photo(
            user["avatar_id"], caption=text, parse_mode="HTML", reply_markup=kb
        )
    else:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
