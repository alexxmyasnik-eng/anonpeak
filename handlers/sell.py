from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import MIN_PRICE
from keyboards.inline import kb_categories_sell, kb_cancel, kb_main_menu, kb_skip_or_back, CATEGORIES

router = Router()

class SellFSM(StatesGroup):
    category    = State()
    title       = State()
    description = State()
    price       = State()
    media       = State()

@router.callback_query(F.data == "sell_item")
async def start_sell(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await db.get_user(call.from_user.id)
    if not user or not user["nickname"]:
        await call.answer("❌ Сначала создай профиль!", show_alert=True)
        return
    try:
        await call.message.edit_text(
            "➕ <b>Выставить товар</b>\n\nВыбери категорию:",
            parse_mode="HTML",
            reply_markup=kb_categories_sell()
        )
    except Exception:
        await call.message.answer(
            "➕ <b>Выставить товар</b>\n\nВыбери категорию:",
            parse_mode="HTML",
            reply_markup=kb_categories_sell()
        )

@router.callback_query(F.data.startswith("sell_cat_"))
async def set_category(call: CallbackQuery, state: FSMContext):
    category = call.data.split("_", 2)[2]
    await state.update_data(category=category)
    await call.message.edit_text(
        f"📁 Категория: <b>{CATEGORIES[category]}</b>\n\n✏️ Введи <b>название</b> товара:",
        parse_mode="HTML",
        reply_markup=kb_cancel("main_menu")
    )
    await state.set_state(SellFSM.title)

@router.message(SellFSM.title)
async def set_title(message: Message, state: FSMContext):
    if not message.text or len(message.text) > 60:
        await message.answer("❌ Название от 1 до 60 символов:")
        return
    await state.update_data(title=message.text.strip())
    await message.answer(
        "📝 Напиши <b>описание</b> товара:",
        parse_mode="HTML",
        reply_markup=kb_cancel("main_menu")
    )
    await state.set_state(SellFSM.description)

@router.message(SellFSM.description)
async def set_description(message: Message, state: FSMContext):
    if not message.text or len(message.text) > 500:
        await message.answer("❌ Описание до 500 символов:")
        return
    await state.update_data(description=message.text.strip())
    await message.answer(
        f"💰 Укажи <b>цену</b> в рублях (минимум {MIN_PRICE} ₽):",
        parse_mode="HTML",
        reply_markup=kb_cancel("main_menu")
    )
    await state.set_state(SellFSM.price)

@router.message(SellFSM.price)
async def set_price(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Введи число:")
        return
    price = int(message.text)
    if price < MIN_PRICE:
        await message.answer(f"❌ Минимальная цена {MIN_PRICE} ₽:")
        return
    if price > 100000:
        await message.answer("❌ Максимальная цена 100 000 ₽:")
        return
    await state.update_data(price=price)
    await message.answer(
        "🖼 Отправь <b>фото или видео</b> для товара:",
        parse_mode="HTML",
        reply_markup=kb_skip_or_back("main_menu")
    )
    await state.set_state(SellFSM.media)

@router.message(SellFSM.media, F.photo)
async def set_media_photo(message: Message, state: FSMContext):
    await _finish_product(message, state, message.photo[-1].file_id, "photo")

@router.message(SellFSM.media, F.video)
async def set_media_video(message: Message, state: FSMContext):
    await _finish_product(message, state, message.video.file_id, "video")

@router.callback_query(F.data == "skip_media", SellFSM.media)
async def skip_media(call: CallbackQuery, state: FSMContext):
    await _finish_product_call(call, state, None, None)

async def _finish_product(message: Message, state: FSMContext, media_id, media_type):
    data = await state.get_data()
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
    await message.answer(
        f"✅ Товар выставлен!\n\n"
        f"📁 {CATEGORIES.get(data['category'])}\n"
        f"📦 <b>{data['title']}</b>\n"
        f"💰 {data['price']} ₽",
        parse_mode="HTML",
        reply_markup=kb_main_menu(has_profile=True)
    )

async def _finish_product_call(call: CallbackQuery, state: FSMContext, media_id, media_type):
    data = await state.get_data()
    await db.add_product(
        seller_id=call.from_user.id,
        category=data["category"],
        title=data["title"],
        description=data["description"],
        price=data["price"],
        media_id=media_id,
        media_type=media_type
    )
    await state.clear()
    await call.message.edit_text(
        f"✅ Товар выставлен!\n\n"
        f"📁 {CATEGORIES.get(data['category'])}\n"
        f"📦 <b>{data['title']}</b>\n"
        f"💰 {data['price']} ₽",
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
    products = await db.get_my_products(call.from_user.id)
    if not products:
        try:
            await call.message.edit_text(
                "📦 У тебя пока нет товаров.",
                reply_markup=kb_main_menu(has_profile=True)
            )
        except Exception:
            await call.message.answer(
                "📦 У тебя пока нет товаров.",
                reply_markup=kb_main_menu(has_profile=True)
            )
        return
    lines = []
    for p in products:
        status = "✅" if p["status"] == "active" else "🗑"
        lines.append(f"{status} <b>{p['title']}</b> — {p['price']:.0f}₽")
    text = "📦 <b>Мои товары:</b>\n\n" + "\n".join(lines)
    try:
        await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb_main_menu(has_profile=True))
    except Exception:
        await call.message.answer(text, parse_mode="HTML", reply_markup=kb_main_menu(has_profile=True))
