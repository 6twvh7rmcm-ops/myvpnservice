import os
import asyncio
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- Конфиг из переменных окружения (задать в Railway -> Variables) ---
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "8363918463"))
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "@FTOT_VPN_SUPPORT")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан! Добавьте переменную окружения BOT_TOKEN в Railway.")

# Путь к базе. Если подключите Railway Volume, смонтируйте его на /data
DB_PATH = os.environ.get("DB_PATH", "ftot.db")

bot = Bot(token=TOKEN)
dp = Dispatcher()

TARIFF_DAYS = {"1m": 30, "3m": 90, "12m": 365}
TARIFF_LABELS = {"1m": "1 месяц - 129 RUB", "3m": "3 месяца - 349 RUB", "12m": "12 месяцев - 1199 RUB"}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            tariff TEXT,
            expire_date TEXT
        )
    ''')
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def save_user(user_id, username, full_name, tariff, expire_date):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        INSERT OR REPLACE INTO users (user_id, username, full_name, tariff, expire_date)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, full_name, tariff, expire_date))
    conn.commit()
    conn.close()


init_db()


@dp.message(Command("start"))
async def start(msg: types.Message):
    await msg.answer(
        "FTOT VPN\nВыберите тариф:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=TARIFF_LABELS["1m"], callback_data="1m")],
            [InlineKeyboardButton(text=TARIFF_LABELS["3m"], callback_data="3m")],
            [InlineKeyboardButton(text=TARIFF_LABELS["12m"], callback_data="12m")]
        ])
    )


@dp.callback_query(F.data.in_(["1m", "3m", "12m"]))
async def buy(call: types.CallbackQuery):
    tariff = call.data
    user = call.from_user
    username = user.username if user.username else "no username"

    await bot.send_message(
        ADMIN_ID,
        f"НОВЫЙ ЗАКАЗ\n"
        f"Имя: {user.full_name}\n"
        f"ID: {user.id}\n"
        f"Username: @{username}\n"
        f"Тариф: {tariff}\n\n"
        f"Активировать: /activate {user.id} {tariff}"
    )

    await call.message.edit_text(
        f"Заказ отправлен. Ожидайте конфиг после оплаты.\n"
        f"Поддержка: {SUPPORT_USERNAME}"
    )
    await call.answer()


@dp.message(Command("support"))
async def support(msg: types.Message):
    await msg.answer(f"Поддержка: {SUPPORT_USERNAME}")


@dp.message(Command("profile"))
async def profile(msg: types.Message):
    user_id = msg.from_user.id
    user_data = get_user(user_id)

    if not user_data:
        await msg.answer("Нет активной подписки. Используйте /start чтобы купить.")
        return

    _, username, full_name, tariff, expire_date = user_data
    await msg.answer(
        f"ПРОФИЛЬ\n"
        f"Имя: {full_name}\n"
        f"ID: {user_id}\n"
        f"Username: @{username if username else 'не задан'}\n"
        f"Тариф: {tariff}\n"
        f"Истекает: {expire_date}"
    )


@dp.message(Command("activate"))
async def activate_sub(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("Доступ запрещён")
        return

    args = msg.text.split()
    if len(args) < 3:
        await msg.answer("Использование: /activate <user_id> <1m|3m|12m>")
        return

    try:
        user_id = int(args[1])
    except ValueError:
        await msg.answer("user_id должен быть числом")
        return

    tariff = args[2]
    if tariff not in TARIFF_DAYS:
        await msg.answer("Неверный тариф. Используйте: 1m, 3m или 12m")
        return

    expire = (datetime.now() + timedelta(days=TARIFF_DAYS[tariff])).strftime("%Y-%m-%d")

    try:
        chat = await bot.get_chat(user_id)
        username = chat.username or "no username"
        full_name = chat.full_name or "unknown"
    except Exception:
        username = "unknown"
        full_name = "unknown"

    save_user(user_id, username, full_name, tariff, expire)
    await msg.answer(f"Активировано для {user_id} до {expire}")

    try:
        await bot.send_message(
            user_id,
            f"Подписка активирована.\n"
            f"Тариф: {tariff}\n"
            f"Действует до: {expire}\n"
            f"Поддержка: {SUPPORT_USERNAME}"
        )
    except Exception:
        await msg.answer(f"Не удалось отправить сообщение пользователю {user_id} (возможно, он не запускал бота)")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
