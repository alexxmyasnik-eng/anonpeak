from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from keyboards.inline import kb_categories_sell, kb_cancel, kb_main_menu, CATEGORIES

router = Router()

class SellFSM(StatesGroup):
    category    = State()
    title       = State()
    description = State()
    price       = State()
    media       = State()

@router.callback_query(F.data == "sell_item")
async def start_sell(call: CallbackQuery, state: FSMContext):
    user = await db.get_user(call.from_user.id)
    if not user["nickname"]:
        await call.answer("❌ Сначала создай профиль!", show_alert=True)
        return
    await call.message.edit_text(
        "➕ <b>Выставить товар</b>\n\nВыбери категорию:",
        parse_mode="HTML",
        reply_markup=kb_categories_sell()
    )

@router.callback_query(F.data.startswith("sell_cat_"))
async def set_category(call: CallbackQuery, state: FSMContext):
    category = call.data.split("_", 2)[2]
    await state.update_data(category=category)
    await call.message.edit_text(
        f"📁 Категория: <b>{CATEGORIES[category]}</b>\n\n✏️ Введи название товара:",
        parse_mode="HTML",
        reply_markup=kb_cancel()
    )
    await state.set_state(SellFSM.title)

@router.message(SellFSM.title)
async def set_title(message: Message, state: FSMContext):
    if len(message.text) > 60:
        await message.answer("❌ Слишком длинное название (макс. 60 символов):")
        return
    await state.update_data(title=message.text.strip())
    await message.answer("📝 Напиши описание товара:", reply_markup=kb_cancel())
    await state.set_state(SellFSM.description)

@router.message(SellFSM.description)
async def set_description(message: Message, state: FSMContext):
    if len(message.text) > 500:
        await message.answer("❌ Слишком длинное описание (макс. 500 символов):")
        return
    await state.update_data(description=message.text.strip())
    await message.answer("💰 Укажи цену в звёздах ⭐ (число от 1 до 10000):", reply_markup=kb_cancel())
    await state.set_state(SellFSM.price)

@router.message(SellFSM.price)
async def set_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введи число:")
        return
    price = int(message.text)
    if price < 1 or price > 10000:
        await message.answer("❌ Цена от 1 до 10000 звёзд:")
        return
    await state.update_data(price=price)
    await message.answer(
        "🖼 Отправь фото или видео для товара\n(или напиши <b>пропустить</b>):",
        parse_mode="HTML",
        reply_markup=kb_cancel()
    )
    await state.set_state(SellFSM.media)

@router.message(SellFSM.media)
async def set_media(message: Message, state: FSMContext):
    data = await state.get_data()
    media_id = None
    media_type = None

    if message.photo:
        media_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        media_id = message.video.file_id
        media_type = "video"
    elif message.text and message.text.lower() == "пропустить":
        pass
    else:
        await message.answer("❌ Отправь фото, видео или напиши «пропустить»:")
        return

    await db.add_product(
        seller_id=message.from_user.id,
        category=data["category"],
        title=data["title"],
        description=data["description"],
        price=data["price"],
        media_id=media_id,
        media_type=media_type
    )
    await state.clear()

    cat_name = CATEGORIES.get(data["category"], data["category"])
    await message.answer(
        f"✅ Товар выставлен!\n\n"
        f"📁 {cat_name}\n"
        f"📦 <b>{data['title']}</b>\n"
        f"💰 {data['price']} ⭐",
        parse_mode="HTML",
        reply_markup=kb_main_menu(has_profile=True)
    )

@router.callback_query(F.data.startswith("del_product_"))
async def delete_product(call: CallbackQuery):
    product_id = int(call.data.split("_")[2])
    product = await db.get_product(product_id)
    if not product or product["seller_id"] != call.from_user.id:
        await call.answer("❌ Нельзя удалить этот товар.", show_alert=True)
        return
    await db.delete_product(product_id, call.from_user.id)
    await call.message.edit_text("🗑 Товар удалён.", reply_markup=kb_main_menu(has_profile=True))

@router.callback_query(F.data == "my_products")
async def my_products(call: CallbackQuery):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    products = await db.get_my_products(call.from_user.id)
    if not products:
        await call.message.edit_text(
            "📦 У тебя пока нет товаров.",
            reply_markup=kb_main_menu(has_profile=True)
        )
        return
    lines = []
    for p in products:
        status = "✅" if p["status"] == "active" else "🗑"
        lines.append(f"{status} <b>{p['title']}</b> — {p['price']}⭐")
    text = "📦 <b>Мои товары:</b>\n\n" + "\n".join(lines)
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_main_menu(has_profile=True))
