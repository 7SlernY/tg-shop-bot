import os
import uuid
import logging
import requests
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# === Настройки ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
TINKOFF_TERMINAL_KEY = os.getenv("TINKOFF_TERMINAL_KEY")  # ← получается в личном кабинете Тинькофф
TINKOFF_SECRET_KEY = os.getenv("TINKOFF_SECRET_KEY")      # ← пароль от терминала
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID"))

logging.basicConfig(level=logging.INFO)

PRODUCTS = [
    {
        "id": 1,
        "name": "Квадроцикл детский AODES 1000 MUD PRO",
        "price": 1500000,
        "image_url": "https://iimg.su/i/Pd8oEQ",
        "description": "Для детей 6-12 лет"
    },
    {
        "id": 2,
        "name": "Квадроцикл детский LONCIN XWOLF 700L MUD",
        "price": 1000000,
        "image_url": "https://iimg.su/i/nVqQXL",
        "description": "Для детей 6-12 лет"
    },
    {
        "id": 3,
        "name": "Квадроцикл детский Yamaha Grizzly 700",
        "price": 1290000,
        "image_url": "https://iimg.su/i/Prtx0e",
        "description": "Для детей 6-12 лет"
    },
    {
        "id": 4,
        "name": "BRP CAN-AM maverick X3 XMR turbo RR",
        "price": 3600000,
        "image_url": "https://iimg.su/i/YAEYh7",
        "description": "Ребёнка в садик возить"
    }
]

class OrderState(StatesGroup):
    waiting_for_address = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

def log_message(message: Message):
    with open("all_messages.txt", "a", encoding="utf-8") as f:
        text = message.text or "[media]"
        username = message.from_user.username or "no_username"
        f.write(f"[{message.date}] ID:{message.from_user.id} @{username}: {text}\n")

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    log_message(message)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Ассортимент", callback_data="catalog")]
    ])
    await message.answer("Привет! Нажмите кнопку ниже:", reply_markup=kb)

@router.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery):
    log_message(callback.message)
    kb = [[InlineKeyboardButton(text=f"{p['name']} — {p['price']} ₽", callback_data=f"buy_{p['id']}")] for p in PRODUCTS]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
    await callback.message.edit_text("Выберите товар:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("buy_"))
async def buy(callback: CallbackQuery, state: FSMContext):
    log_message(callback.message)
    pid = int(callback.data.split("_")[1])
    p = next((x for x in PRODUCTS if x["id"] == pid), None)
    if not p:
        await callback.answer("Товар найден!")
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
    log_message(callback.message)
    await state.clear()
    await cmd_start(callback.message, state)

@router.message()
async def handle_all_messages(message: Message, state: FSMContext):
    log_message(message)
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

        try:
            # Получаем username бота
            bot_info = await bot.get_me()
            return_url = f"https://t.me/{bot_info.username}"

            # Формируем запрос к Tinkoff
            amount = p["price"]
            order_id = f"ORD_{uuid.uuid4().hex[:8]}"

            payload = {
                "TerminalKey": TINKOFF_TERMINAL_KEY,
                "Amount": amount * 100,  # в копейках
                "OrderId": order_id,
                "Description": p["name"],
                "NotificationURL": "",  # можно оставить пустым для теста
                "SuccessURL": return_url,
                "FailURL": return_url,
                "DATA": {
                    "CustomerKey": str(message.from_user.id),
                    "Address": addr
                }
            }

            # Подпись (упрощённая — для теста; в продакшене используй HMAC-SHA256)
            # Но Tinkoff позволяет без подписи, если включён режим "безопасный ключ"
            # → лучше использовать официальный метод: https://oplata.tinkoff.ru/develop/api/payments/init/

            # Для быстрого старта: используем sandbox (если есть тестовый терминал)
            url = "https://securepay.tinkoff.ru/v2/Init"
            # ИЛИ для продакшена: "https://api.tinkoff.ru/v2/Init"

            response = requests.post(url, json=payload, timeout=10)
            data = response.json()

            if data.get("ErrorCode") == "0":
                payment_url = data.get("PaymentURL")
                await message.answer(f"✅ Оплатите заказ:\n{payment_url}")

                # Уведомление админу
                await bot.send_message(
                    ADMIN_CHAT_ID,
                    f"🆕 Заказ!\nПользователь: @{message.from_user.username} (ID: {message.from_user.id})\n"
                    f"Товар: {p['name']}\nАдрес: {addr}\nСумма: {p['price']} ₽\nСсылка: {payment_url}"
                )

                # Сохраняем заказ
                with open("orders.txt", "a", encoding="utf-8") as f:
                    f.write(f"Заказ: {p['name']} | Адрес: {addr} | ID: {order_id} | Сумма: {p['price']} ₽\n")

                await state.clear()
            else:
                error_msg = data.get("Message", "Неизвестная ошибка")
                await message.answer(f"❌ Ошибка Tinkoff: {error_msg}")

        except Exception as e:
            logging.error(f"Tinkoff error: {e}")
            await message.answer("❌ Не удалось создать платёж. Проверьте настройки.")

    else:
        if not message.text.startswith("/"):
            await message.answer("Нажмите /start для начала работы.")

@router.callback_query(F.data == "back")
async def back(callback: CallbackQuery, state: FSMContext):
    log_message(callback.message)
    await cmd_start(callback.message, state)

dp.include_router(router)

if __name__ == "__main__":
    print("✅ Бот запущен! Нажмите Ctrl+C для остановки.")
    dp.run_polling(bot)
