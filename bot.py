import uuid
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from yookassa import Configuration, Payment

# === ВСТАВЬ СВОИ ДАННЫЕ ===
BOT_TOKEN = "8456846163:AAF5zviEAzA8PH2bKziyeLWGMxAm2yi98e8"
YOO_SHOP_ID = "123456"  # ← ЗАМЕНИ НА СВОЙ Shop ID (число)
YOO_SECRET_KEY = "live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # ← ЗАМЕНИ НА СВОЙ Secret Key
ADMIN_CHAT_ID = 1835322648
# =========================

# Настройка ЮKassa
Configuration.account_id = YOO_SHOP_ID
Configuration.secret_key = YOO_SECRET_KEY
logging.basicConfig(level=logging.WARNING)

# Товары (цена в РУБЛЯХ)
PRODUCTS = [
    {
        "id": 1,
        "name": "Квадроцикл детский AODES 1000 MUD PRO",
        "price": 1500000,  # 1 500 000 ₽
        "image_url": "https://iimg.su/i/Pd8oEQ",
        "description": "Для детей 6-12 лет"
    },
    {
        "id": 2,
        "name": "Квадроцикл детский LONCIN XWOLF 700L MUD ",
        "price": 1000000,  # 1 000 000 ₽
        "image_url": "https://iimg.su/i/nVqQXL",
        "description": "Для детей 6-12 лет"
    },
    {
        "id": 3,
        "name": "Квадроцикл детский Yamaha Grizzly 700",
        "price": 1290000,  # 1 290 000 ₽
        "image_url": "https://iimg.su/i/Prtx0e",
        "description": "Для детей 6-12 лет"
    },
    {
        "id": 4,
        "name": "BRP CAN-AM maverick X3 XMR turbo RR",
        "price": 3600000,  # 3 600 000 ₽
        "image_url": "https://iimg.su/i/YAEYh7",
        "description": "Ребёнка в садик возить"
    }
]

class OrderState(StatesGroup):
    waiting_for_address = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

# === ЛОГИРОВАНИЕ ВСЕХ СООБЩЕНИЙ ===
def log_message(message: Message):
    with open("all_messages.txt", "a", encoding="utf-8") as f:
        text = message.text or "[не текст]"
        username = message.from_user.username or "no_username"
        f.write(f"[{message.date}] ID:{message.from_user.id} @{username}: {text}\n")

# /start
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    log_message(message)
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Ассортимент", callback_data="catalog")]
    ])
    await message.answer("Привет! Нажмите кнопку ниже:", reply_markup=kb)

# Каталог
@router.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery):
    log_message(callback.message)
    kb = [[InlineKeyboardButton(text=f"{p['name']} — {p['price']} ₽", callback_data=f"buy_{p['id']}")] for p in PRODUCTS]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back")])
    await callback.message.edit_text("Выберите товар:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# Выбор товара
@router.callback_query(F.data.startswith("buy_"))
async def buy(callback: CallbackQuery, state: FSMContext):
    log_message(callback.message)
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

# Отмена
@router.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery, state: FSMContext):
    log_message(callback.message)
    await state.clear()
    await cmd_start(callback.message, state)

# Обработка всех сообщений
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
            # Правильный способ получить username бота
            bot_info = await bot.get_me()
            return_url = f"https://t.me/{bot_info.username}"

            # Цена в формате "1500000.00"
            formatted_price = f"{p['price']}.00"

            payment = Payment.create({
                "amount": {"value": formatted_price, "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": return_url},
                "description": p["name"],
                "metadata": {
                    "user_id": str(message.from_user.id),
                    "address": addr
                }
            }, uuid.uuid4())
            
            await message.answer(f"✅ Оплатите заказ:\n{payment.confirmation.confirmation_url}")
            
            # Уведомление админу
            await bot.send_message(
                ADMIN_CHAT_ID,
                f"🆕 Заказ!\nПользователь: @{message.from_user.username} (ID: {message.from_user.id})\n"
                f"Товар: {p['name']}\nАдрес: {addr}\nСумма: {p['price']} ₽"
            )
            
            # Сохраняем заказ
            with open("orders.txt", "a", encoding="utf-8") as f:
                f.write(f"Заказ: {p['name']} | Адрес: {addr} | Пользователь: {message.from_user.id}\n")
            
            await state.clear()

        except Exception as e:
            logging.error(f"Ошибка ЮKassa: {e}")
            await message.answer("❌ Ошибка при создании платежа. Проверьте настройки ЮKassa.")
            await state.clear()

    else:
        if not message.text.startswith("/"):
            await message.answer("Нажмите /start для начала работы.")

# Назад
@router.callback_query(F.data == "back")
async def back(callback: CallbackQuery, state: FSMContext):
    log_message(callback.message)
    await cmd_start(callback.message, state)

dp.include_router(router)

if __name__ == "__main__":
    print("✅ Бот запущен! Нажмите Ctrl+C для остановки.")
    dp.run_polling(bot)