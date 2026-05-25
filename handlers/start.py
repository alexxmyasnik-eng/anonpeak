from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BotCommand, BotCommandScopeDefault
from aiogram.filters import CommandStart, Command

import database as db
from config import CHANNEL_ID
from keyboards.inline import kb_check_sub, kb_confirm_age, kb_main_menu

router = Router()

WELCOME = """
👋 Добро пожаловать в <b>AnonPeak</b>!

🛍 Анонимный маркет — сигны, фото, видео, кружки
💬 Общий чат
✉️ Личные сообщения
💰 Оплата через DonationAlerts
"""

async def is_subscribed(bot: Bot, user_id: int, channel: str) -> bool:
    try:
        m = await bot.get_chat_member(channel, user_id)
        return m.status not in ("left", "kicked", "banned")
    except Exception:
        return False

async def setup_menu(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command="start",   description="🏠 Главное меню"),
        BotCommand(command="market",  description="🛍 Маркет — купить товар"),
        BotCommand(command="balance", description="💰 Мой баланс"),
        BotCommand(command="donate",  description="💳 Пополнить баланс"),
        BotCommand(command="profile", description="👤 Мой профиль"),
        BotCommand(command="chat",    description="💬 Общий чат"),
        BotCommand(command="messages",description="✉️ Мои сообщения"),
        BotCommand(command="sell",    description="➕ Выставить товар"),
    ])

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    await setup_menu(bot)
    uid = message.from_user.id
    user = await db.get_user(uid)
    if not user:
        await db.create_user(uid, message.from_user.username or "")

    # Обработка анонимной ссылки на ЛС: /start dm_TOKEN
   # args = message.text.split(maxsplit=1)
   # if len(args) > 1 and args[1].startswith("dm_"):
      #  token = args[1][3:]
       # target_id = await db.get_user_by_dm_token(token)
      #  if target_id and target_id != uid:
            # Ищем активный заказ между ними
         #   order = await db.get_active_order_between(uid, target_id)
          #  if order:
              #  from keyboards.inline import kb_order_chat
              #  role = "buyer" if order["buyer_id"] == uid else "seller"
              #  await message.answer(
               #     "✉️ Открываю переписку...",
                #    reply_markup=kb_order_chat(order["id"], role)
           #     )
          #  else:
             #   await message.answer(
                #    "❌ Написать в ЛС можно только через заказ на маркете.\n"
              #      "Купи или продай товар этому пользователю — тогда откроется чат.",
               #     reply_markup=kb_main_menu(bool(user["nickname"]) if user else False)
                )
            #return
       # await message.answer("❌ Ссылка недействительна.",
                    #         reply_markup=kb_main_menu(bool(user["nickname"]) if user else False))
      #  return

   # if not await is_subscribed(bot, uid, CHANNEL_ID):
       # await message.answer(
           # f"📢 Для входа подпишись на канал:\n👉 {CHANNEL_ID}",
         #   reply_markup=kb_check_sub()
     #   )
        return

    user = await db.get_user(uid)
    if not user["is_adult"]:
        await message.answer("🔞 Подтверди возраст 18+:", reply_markup=kb_confirm_age())
        return

    unread = await db.count_unread(uid)
    await message.answer(WELCOME, parse_mode="HTML",
                         reply_markup=kb_main_menu(bool(user["nickname"]), unread))

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(call: CallbackQuery, bot: Bot):
    if not await is_subscribed(bot, call.from_user.id, CHANNEL_ID):
        await call.answer("❌ Ты ещё не подписан!", show_alert=True)
        return
    await call.message.delete()
    user = await db.get_user(call.from_user.id)
    if not user["is_adult"]:
        await call.message.answer("🔞 Подтверди возраст 18+:", reply_markup=kb_confirm_age())
    else:
        unread = await db.count_unread(call.from_user.id)
        await call.message.answer(WELCOME, parse_mode="HTML",
                                  reply_markup=kb_main_menu(bool(user["nickname"]), unread))

@router.callback_query(F.data == "confirm_age")
async def cb_confirm_age(call: CallbackQuery):
    await db.set_adult(call.from_user.id)
    await call.message.delete()
    user = await db.get_user(call.from_user.id)
    unread = await db.count_unread(call.from_user.id)
    await call.message.answer(WELCOME, parse_mode="HTML",
                               reply_markup=kb_main_menu(bool(user["nickname"]), unread))

@router.callback_query(F.data == "deny_age")
async def cb_deny_age(call: CallbackQuery):
    await call.message.edit_text("🚫 Бот только для 18+.")

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    unread = await db.count_unread(call.from_user.id)
    try:
        await call.message.edit_text(WELCOME, parse_mode="HTML",
                                     reply_markup=kb_main_menu(bool(user["nickname"]), unread))
    except Exception:
        await call.message.answer(WELCOME, parse_mode="HTML",
                                  reply_markup=kb_main_menu(bool(user["nickname"]), unread))


# ─── КОМАНДЫ МЕНЮ ────────────────────────────────────────

@router.message(Command("market"))
async def cmd_market(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or not user["is_adult"]: return
    from keyboards.inline import kb_market
    await message.answer("🛍 <b>Маркет</b>\n\nВыбери категорию:", parse_mode="HTML", reply_markup=kb_market())

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or not user["is_adult"]: return
    from keyboards.inline import kb_wallet
    balance = await db.get_balance(message.from_user.id)
    await message.answer(f"💰 Твой баланс: <b>{balance:.0f} ₽</b>", parse_mode="HTML", reply_markup=kb_wallet())

@router.message(Command("donate"))
async def cmd_donate(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or not user["is_adult"]: return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="topup")
    ]])
    await message.answer("💳 Пополнение баланса:", reply_markup=kb)

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or not user["is_adult"]: return
    from aiogram.types import CallbackQuery
    # Имитируем через answer
    from keyboards.inline import kb_profile, kb_main_menu as kmm
    if not user["nickname"]:
        await message.answer("У тебя нет профиля.", reply_markup=kmm(False))
        return
    text = (
        f"👤 <b>Профиль</b>\n\n"
        f"Ник: <b>{user['nickname']}</b>\n"
        f"Возраст: <b>{user['age']}</b>\n"
        f"Баланс: <b>{await db.get_balance(message.from_user.id):.0f} ₽</b>"
    )
    kb = kb_profile()
    if user["avatar_id"]:
        await message.answer_photo(user["avatar_id"], caption=text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

@router.message(Command("chat"))
async def cmd_chat(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or not user["is_adult"]: return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💬 Открыть чат", callback_data="open_chat")
    ]])
    await message.answer("💬 Общий чат:", reply_markup=kb)

@router.message(Command("messages"))
async def cmd_messages(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or not user["is_adult"]: return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✉️ Мои сообщения", callback_data="messages")
    ]])
    await message.answer("✉️ Переписка:", reply_markup=kb)

@router.message(Command("sell"))
async def cmd_sell(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user or not user["nickname"]: return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Выставить товар", callback_data="sell_item")
    ]])
    await message.answer("➕ Выставить товар на маркет:", reply_markup=kb)
