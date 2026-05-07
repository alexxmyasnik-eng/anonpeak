from aiogram import Router, F
from aiogram.types import CallbackQuery

import database as db
from keyboards.inline import kb_market, kb_product_list, kb_product_detail, CATEGORIES

router = Router()

@router.callback_query(F.data == "market")
async def show_market(call: CallbackQuery):
    try:
        await call.message.edit_text(
            "🛍 <b>Маркет</b>\n\nВыбери категорию:",
            parse_mode="HTML",
            reply_markup=kb_market()
        )
    except Exception:
        await call.message.answer(
            "🛍 <b>Маркет</b>\n\nВыбери категорию:",
            parse_mode="HTML",
            reply_markup=kb_market()
        )

@router.callback_query(F.data.startswith("cat_"))
async def show_category(call: CallbackQuery):
    category = call.data.split("_", 1)[1]
    cat_name = CATEGORIES.get(category, category)
    products = await db.get_products_by_category(category)

    if not products:
        await call.message.edit_text(
            f"{cat_name}\n\n😔 Пока нет товаров в этой категории.",
            reply_markup=kb_market()
        )
        return

    await call.message.edit_text(
        f"{cat_name}\n\n📋 Товаров: <b>{len(products)}</b>\nВыбери товар:",
        parse_mode="HTML",
        reply_markup=kb_product_list(products, category)
    )

@router.callback_query(F.data.startswith("product_"))
async def show_product(call: CallbackQuery):
    product_id = int(call.data.split("_")[1])
    product = await db.get_product(product_id)
    if not product:
        await call.answer("Товар не найден.", show_alert=True)
        return

    seller = await db.get_user(product["seller_id"])
    is_own = call.from_user.id == product["seller_id"]
    cat_name = CATEGORIES.get(product["category"], product["category"])

    text = (
        f"{'📦 Твой товар' if is_own else '📦'} <b>{product['title']}</b>\n\n"
        f"📁 {cat_name}\n"
        f"💰 Цена: <b>{product['price']:.0f} ₽</b>\n\n"
        f"📝 {product['description']}\n\n"
        f"👤 Продавец: <b>{seller['nickname'] if seller else 'Аноним'}</b>"
    )
    kb = kb_product_detail(product_id, is_own)

    if product["media_id"]:
        try:
            await call.message.delete()
        except Exception:
            pass
        if product["media_type"] == "photo":
            await call.message.answer_photo(product["media_id"], caption=text, parse_mode="HTML", reply_markup=kb)
        elif product["media_type"] == "video":
            await call.message.answer_video(product["media_id"], caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        try:
            await call.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await call.message.answer(text, parse_mode="HTML", reply_markup=kb)
