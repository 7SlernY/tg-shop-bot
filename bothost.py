import os
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# === Настройки ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

WEBHOOK_HOST = f"https://{os.getenv('RENDER_EXTERNAL_URL')}"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)

# Товары
PRODUCTS = [
    {"id": 1, "name": "Квадроцикл детский AODES 1000 MUD PRO", "price": 1500000, "image_url": "https://iimg.su/i/Pd8oEQ", "description": "Для детей 6-12 лет"},
    {"id": 2, "name": "Квадроцикл детский LONCIN XWOLF 700L MUD", "price": 1000000, "image_url": "https://iimg.su/i/nVqQXL", "description": "Для детей 6-12 лет"},
    {"id": 3, "name": "Квадроцикл детский Yamaha Grizzly 700", "price": 1290000, "image_url": "https://iimg.su/i/Prtx0e", "description": "Для детей 6-12 лет"},
    {"id": 4, "name": "BRP CAN-AM maverick X3 XMR turbo RR", "price": 3600000, "image_url": "https://iimg.su/i/YAEYh7", "description": "Ребёнка в садик возить"},
]

class OrderState(StatesGroup):
    waiting_for_address = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

def log_message_to_admin(text: str):
    # В webhook-режиме нельзя использовать await вне хендлера
    # Поэтому просто логируем — уведомление админу отправится в handle_all_messages
    logging.info(f"LOG: {text}")

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Ассортимент", callback_data="catalog")]
    ])
    await message.answer("Привет! Нажмите кнопку ниже:", reply_markup=kb)

@router.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery):
    kb = [[InlineKeyboardButton(text=f"{p['name']} — {p['price']} ₽", callback_data=f"buy_{p['id']}")] for p in PRODUCTS]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
    await callback.message.edit_text("Выберите товар:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("buy_"))
async def buy(callback: CallbackQuery, state: FSMContext):
    pid = int(callback.data.split("_")[1])
    p = next((x for x in PRODUCTS if x["id"] == pid), None)
    if not p:
        await callback.answer("Товар не найден!")
        return
    
    await state.update_data(pid=pid)
    await callback.message.answer_photo(p["image_url"], caption=f"{p['name']}\n{p['description']}\n\nЦена: {p['price']} ₽")
    await callback.message.answer(
        "🚚 Введите адрес доставки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ])
    )
    await state.set_state(OrderState.waiting_for_address)

@router.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await cmd_start(callback.message, state)

@router.message()
async def handle_all_messages(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state == OrderState.waiting_for_address:
        addr = message.text.strip()
        if len(addr) < 5:
            await message.answer("Адрес слишком короткий. Попробуйте снова:")
            return

        data = await state.get_data()
        p = next((x for x in PRODUCTS if x["id"] == data["pid"]), None)
        if not p:
            await message.answer("Ошибка.")
            await state.clear()
            return

        # === ЗАГЛУШКА ОПЛАТЫ (заменить на Tinkoff позже) ===
        payment_url = f"https://example.com/pay?user={message.from_user.id}&product={p['id']}"
        # ================================================

        await message.answer(f"✅ Оплатите заказ:\n{payment_url}")

        # Уведомление админу
        await bot.send_message(
            ADMIN_CHAT_ID,
            f"🆕 Заказ!\nПользователь: @{message.from_user.username} (ID: {message.from_user.id})\n"
            f"Товар: {p['name']}\nАдрес: {addr}\nСумма: {p['price']} ₽"
        )

        await state.clear()

    else:
        if not message.text.startswith("/"):
            await message.answer("Нажмите /start для начала работы.")

@router.callback_query(F.data == "back")
async def back(callback: CallbackQuery, state: FSMContext):
    await cmd_start(callback.message, state)

async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook set to {WEBHOOK_URL}")

async def on_shutdown(app: web.Application):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()

def main():
    dp.include_router(router)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
