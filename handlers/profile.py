from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards.inline import kb_profile, kb_cancel, kb_main_menu

router = Router()

class ProfileFSM(StatesGroup):
    nickname = State()
    age      = State()
    avatar   = State()

@router.callback_query(F.data.in_({"create_profile", "edit_profile"}))
async def start_profile(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "✏️ Введи свой никнейм (до 30 символов):",
        reply_markup=kb_cancel()
    )
    await state.set_state(ProfileFSM.nickname)

@router.message(ProfileFSM.nickname)
async def get_nickname(message: Message, state: FSMContext):
    nick = message.text.strip()
    if len(nick) > 30:
        await message.answer("❌ Слишком длинный никнейм, попробуй короче:")
        return
    await state.update_data(nickname=nick)
    await message.answer("📅 Сколько тебе лет? (введи число):", reply_markup=kb_cancel())
    await state.set_state(ProfileFSM.age)

@router.message(ProfileFSM.age)
async def get_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введи число:")
        return
    age = int(message.text)
    if age < 18 or age > 99:
        await message.answer("❌ Возраст должен быть от 18 до 99:")
        return
    await state.update_data(age=age)
    await message.answer(
        "🖼 Отправь фото для аватарки профиля\n"
        "(или напиши <b>пропустить</b>):",
        parse_mode="HTML",
        reply_markup=kb_cancel()
    )
    await state.set_state(ProfileFSM.avatar)

@router.message(ProfileFSM.avatar)
async def get_avatar(message: Message, state: FSMContext):
    data = await state.get_data()
    avatar_id = None

    if message.photo:
        avatar_id = message.photo[-1].file_id
    elif message.text and message.text.lower() == "пропустить":
        avatar_id = None
    else:
        await message.answer("❌ Отправь фото или напиши «пропустить»:")
        return

    await db.update_profile(message.from_user.id, data["nickname"], data["age"], avatar_id)
    await state.clear()

    await message.answer(
        f"✅ Профиль сохранён!\n\n"
        f"👤 Ник: <b>{data['nickname']}</b>\n"
        f"🎂 Возраст: <b>{data['age']}</b>",
        parse_mode="HTML",
        reply_markup=kb_profile(has_profile=True)
    )

@router.callback_query(F.data == "my_profile")
async def show_profile(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    if not user["nickname"]:
        await call.message.edit_text(
            "У тебя ещё нет профиля.",
            reply_markup=kb_profile(has_profile=False)
        )
        return

    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Ник: <b>{user['nickname']}</b>\n"
        f"Возраст: <b>{user['age']}</b>\n"
        f"Баланс: <b>{user['balance']} ⭐</b>"
    )
    if user["avatar_id"]:
        await call.message.delete()
        await call.message.answer_photo(
            user["avatar_id"], caption=text,
            parse_mode="HTML",
            reply_markup=kb_profile(has_profile=True)
        )
    else:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_profile(has_profile=True))
