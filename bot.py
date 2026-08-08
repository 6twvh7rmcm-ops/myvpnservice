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

TON_ADDRESS = os.environ.get("TON_ADDRESS", "UQCQlaYu4idX9R1N6x2U9F0dDM3zhxIpTk5iUttwG53o6fRP")
USDT_TRC20_ADDRESS = os.environ.get("USDT_TRC20_ADDRESS", "TXrnLagFitHytJqE7RLnzKvdXzQkNQUwst")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан! Добавьте переменную окружения BOT_TOKEN в Railway.")

DB_PATH = os.environ.get("DB_PATH", "ftot.db")

bot = Bot(token=TOKEN)
dp = Dispatcher()

TARIFF_DAYS = {"1m": 30, "3m": 90, "12m": 365}
TARIFF_LABELS = {"1m": "1 месяц - 129 RUB", "3m": "3 месяца - 349 RUB", "12m": "12 месяцев - 1199 RUB"}
TARIFF_PRICE_RUB = {"1m": 129, "3m": 349, "12m": 1199}

# Сколько дней до истечения слать напоминание
REMIND_DAYS_BEFORE = 3
# Как часто проверять подписки на истечение (в секундах)
CHECK_INTERVAL_SECONDS = 6 * 60 * 60  # каждые 6 часов


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            tariff TEXT,
            expire_date TEXT,
            reminder_sent INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    # На случай если таблица создана раньше без reminder_sent
    try:
        cur.execute("ALTER TABLE users ADD COLUMN reminder_sent INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass
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
        INSERT OR REPLACE INTO users (user_id, username, full_name, tariff, expire_date, reminder_sent)
        VALUES (?, ?, ?, ?, ?, 0)
    ''', (user_id, username, full_name, tariff, expire_date))
    conn.commit()
    conn.close()


def get_users_to_remind():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id, tariff, expire_date FROM users WHERE reminder_sent = 0")
    rows = cur.fetchall()
    conn.close()
    return rows


def mark_reminded(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE users SET reminder_sent = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


init_db()


# ---------------- СТАРТ / ВЫБОР ТАРИФА ----------------

@dp.message(Command("start"))
async def start(msg: types.Message):
    await msg.answer(
        "FTOT VPN\nВыберите тариф:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=TARIFF_LABELS["1m"], callback_data="tariff_1m")],
            [InlineKeyboardButton(text=TARIFF_LABELS["3m"], callback_data="tariff_3m")],
            [InlineKeyboardButton(text=TARIFF_LABELS["12m"], callback_data="tariff_12m")]
        ])
    )


@dp.callback_query(F.data.startswith("tariff_"))
async def choose_payment(call: types.CallbackQuery):
    tariff = call.data.replace("tariff_", "")

    await call.message.edit_text(
        f"Тариф: {TARIFF_LABELS[tariff]}\n\nВыберите способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="СБП", callback_data=f"pay_sbp_{tariff}")],
            [InlineKeyboardButton(text="TON (Gram)", callback_data=f"pay_ton_{tariff}")],
            [InlineKeyboardButton(text="USDT (TRC-20)", callback_data=f"pay_usdt_{tariff}")]
        ])
    )
    await call.answer()


@dp.callback_query(F.data.startswith("pay_sbp_"))
async def pay_sbp(call: types.CallbackQuery):
    await call.answer("Платёжная система в разработке", show_alert=True)


@dp.callback_query(F.data.startswith("pay_ton_"))
async def pay_ton(call: types.CallbackQuery):
    tariff = call.data.replace("pay_ton_", "")
    price = TARIFF_PRICE_RUB[tariff]

    await call.message.edit_text(
        f"Оплата через TON\n\n"
        f"Тариф: {TARIFF_LABELS[tariff]}\n"
        f"Сумма: {price} RUB (в эквиваленте TON)\n\n"
        f"Адрес для перевода:\n`{TON_ADDRESS}`\n\n"
        f"После отправки перевода нажмите кнопку ниже — мы проверим оплату и активируем подписку.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил ✅", callback_data=f"paid_ton_{tariff}")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data=f"tariff_{tariff}")]
        ])
    )
    await call.answer()


@dp.callback_query(F.data.startswith("pay_usdt_"))
async def pay_usdt(call: types.CallbackQuery):
    tariff = call.data.replace("pay_usdt_", "")
    price = TARIFF_PRICE_RUB[tariff]

    await call.message.edit_text(
        f"Оплата через USDT (TRC-20)\n\n"
        f"Тариф: {TARIFF_LABELS[tariff]}\n"
        f"Сумма: {price} RUB (в эквиваленте USDT)\n\n"
        f"Адрес для перевода:\n`{USDT_TRC20_ADDRESS}`\n\n"
        f"⚠️ Отправляйте только в сети TRC-20, иначе средства потеряются.\n\n"
        f"После отправки перевода нажмите кнопку ниже — мы проверим оплату и активируем подписку.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Я оплатил ✅", callback_data=f"paid_usdt_{tariff}")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data=f"tariff_{tariff}")]
        ])
    )
    await call.answer()


@dp.callback_query(F.data.startswith("paid_"))
async def paid_confirmation(call: types.CallbackQuery):
    # формат: paid_<method>_<tariff>
    parts = call.data.split("_")
    method = parts[1]
    tariff = parts[2]

    method_names = {"ton": "TON (Gram)", "usdt": "USDT (TRC-20)"}
    user = call.from_user
    username = user.username if user.username else "no username"

    await bot.send_message(
        ADMIN_ID,
        f"💰 ЗАЯВКА НА ОПЛАТУ\n"
        f"Имя: {user.full_name}\n"
        f"ID: {user.id}\n"
        f"Username: @{username}\n"
        f"Тариф: {tariff}\n"
        f"Способ: {method_names.get(method, method)}\n\n"
        f"Проверьте поступление и активируйте:\n"
        f"/activate {user.id} {tariff}"
    )

    await call.message.edit_text(
        f"Спасибо! Заявка отправлена на проверку.\n"
        f"Как только оплата подтвердится, подписка будет активирована.\n"
        f"Поддержка: {SUPPORT_USERNAME}"
    )
    await call.answer()


# ---------------- ПРОФИЛЬ ----------------

@dp.message(Command("profile"))
async def profile(msg: types.Message):
    user_id = msg.from_user.id
    user_data = get_user(user_id)

    if not user_data:
        await msg.answer("Нет активной подписки. Используйте /start чтобы купить.")
        return

    _, username, full_name, tariff, expire_date, _ = user_data

    try:
        expire_dt = datetime.strptime(expire_date, "%Y-%m-%d")
        days_left = (expire_dt - datetime.now()).days
    except ValueError:
        days_left = None

    status_line = ""
    if days_left is not None:
        if days_left < 0:
            status_line = "\n⚠️ Подписка истекла"
        elif days_left <= REMIND_DAYS_BEFORE:
            status_line = f"\n⏳ Осталось дней: {days_left}"

    await msg.answer(
        f"ПРОФИЛЬ\n"
        f"Имя: {full_name}\n"
        f"Username: @{username if username else 'не задан'}\n"
        f"ID: {user_id}\n"
        f"Тариф: {tariff}\n"
        f"Действует до: {expire_date}"
        f"{status_line}"
    )


# ---------------- ПОДДЕРЖКА ----------------

@dp.message(Command("support"))
async def support(msg: types.Message):
    await msg.answer(f"Поддержка: {SUPPORT_USERNAME}")


# ---------------- АКТИВАЦИЯ (АДМИН) ----------------

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
            f"✅ Подписка активирована.\n"
            f"Тариф: {tariff}\n"
            f"Действует до: {expire}\n"
            f"Поддержка: {SUPPORT_USERNAME}"
        )
    except Exception:
        await msg.answer(f"Не удалось отправить сообщение пользователю {user_id} (возможно, он не запускал бота)")


# ---------------- ФОНОВАЯ ПРОВЕРКА ИСТЕЧЕНИЯ ПОДПИСОК ----------------

async def check_expiring_subscriptions():
    while True:
        try:
            rows = get_users_to_remind()
            today = datetime.now()

            for user_id, tariff, expire_date in rows:
                try:
                    expire_dt = datetime.strptime(expire_date, "%Y-%m-%d")
                except ValueError:
                    continue

                days_left = (expire_dt - today).days

                if 0 <= days_left <= REMIND_DAYS_BEFORE:
                    try:
                        await bot.send_message(
                            user_id,
                            f"⏳ Ваша подписка FTOT VPN истекает {expire_date} "
                            f"(осталось дней: {days_left}).\n"
                            f"Чтобы продлить, используйте /start.\n"
                            f"Поддержка: {SUPPORT_USERNAME}"
                        )
                    except Exception:
                        pass
                    mark_reminded(user_id)
        except Exception:
            pass

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- ЗАПУСК ----------------

async def main():
    asyncio.create_task(check_expiring_subscriptions())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
