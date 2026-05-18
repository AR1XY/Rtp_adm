import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
import os
import json
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Загружаем админов из файла
ADMIN_FILE = "admins.json"

def load_admins():
    try:
        with open(ADMIN_FILE, "r") as f:
            data = json.load(f)
            return data["ids"], data["names"]
    except:
        return [7587802819, 7331748184, 1243980540], {
            7587802819: "Вадим",
            7331748184: "AR1XY",
            1243980540: "Илья"
        }

def save_admins(ids, names):
    with open(ADMIN_FILE, "w") as f:
        json.dump({"ids": ids, "names": names}, f)

ADMIN_IDS, ADMIN_NAMES = load_admins()

# Хранилище
admin_online = {}
active_tickets = {}
ticket_status = {}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Клавиатуры
user_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💬 Задать вопрос")],
        [KeyboardButton(text="👥 Админы онлайн")]
    ],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Активные диалоги")],
        [KeyboardButton(text="🟢 Мои онлайн")],
        [KeyboardButton(text="👑 Управление админами")]
    ],
    resize_keyboard=True
)

class SupportState(StatesGroup):
    waiting_for_question = State()
    in_dialog = State()
    add_admin_waiting = State()
    remove_admin_waiting = State()

def admin_ticket_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять запрос", callback_data=f"take_{user_id}")]
    ])

def close_dialog_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 Закрыть диалог", callback_data=f"close_{user_id}")]
    ])

async def update_admin_activity(admin_id):
    admin_online[admin_id] = datetime.now()

def get_online_admins():
    online_names = []
    five_min_ago = datetime.now() - timedelta(minutes=5)
    for admin_id, last_seen in admin_online.items():
        if last_seen > five_min_ago and admin_id in ADMIN_IDS:
            online_names.append(ADMIN_NAMES.get(admin_id, str(admin_id)))
    return online_names

# ========== УПРАВЛЕНИЕ АДМИНАМИ ==========

@dp.message(lambda message: message.text == "👑 Управление админами" and message.from_user.id in ADMIN_IDS)
async def admin_management(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="add_admin")],
        [InlineKeyboardButton(text="➖ Удалить админа", callback_data="remove_admin")],
        [InlineKeyboardButton(text="📋 Список админов", callback_data="list_admins")]
    ])
    await message.answer("👑 **Управление администраторами**", reply_markup=keyboard)

# Добавление админа
@dp.callback_query(lambda c: c.data == "add_admin" and c.from_user.id in ADMIN_IDS)
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 **Добавление админа**\n\nОтправьте ID пользователя (число) или перешлите любое его сообщение.")
    await state.set_state(SupportState.add_admin_waiting)
    await callback.answer()

@dp.message(SupportState.add_admin_waiting)
async def add_admin_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    user_id = None
    name = None
    
    if message.forward_from:
        user_id = message.forward_from.id
        name = message.forward_from.first_name
    elif message.text.isdigit():
        user_id = int(message.text)
        name = f"Admin_{user_id}"
    else:
        await message.answer("❌ Неверный формат. Отправьте ID или перешлите сообщение.")
        return
    
    if user_id in ADMIN_IDS:
        await message.answer(f"❌ Уже является администратором")
        await state.clear()
        return
    
    ADMIN_IDS.append(user_id)
    ADMIN_NAMES[user_id] = name
    save_admins(ADMIN_IDS, ADMIN_NAMES)
    
    await message.answer(f"✅ **Админ добавлен!**\n\nID: `{user_id}`\nИмя: {name}")
    
    try:
        await bot.send_message(user_id, "🎉 Вы стали администратором техподдержки!\n\nНапишите /start")
    except:
        pass
    
    await state.clear()

# Удаление админа (только AR1XY)
@dp.callback_query(lambda c: c.data == "remove_admin" and c.from_user.id in ADMIN_IDS)
async def remove_admin_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != 7331748184:
        await callback.answer("❌ Только AR1XY может удалять админов", show_alert=True)
        return
    
    admin_list = "\n".join([f"• `{uid}` — {ADMIN_NAMES.get(uid, uid)}" for uid in ADMIN_IDS])
    await callback.message.answer(f"📝 **Удаление админа**\n\nТекущие админы:\n{admin_list}\n\nОтправьте ID админа для удаления:")
    await state.set_state(SupportState.remove_admin_waiting)
    await callback.answer()

@dp.message(SupportState.remove_admin_waiting)
async def remove_admin_process(message: types.Message, state: FSMContext):
    if message.from_user.id != 7331748184:
        await message.answer("❌ Только AR1XY может удалять админов")
        await state.clear()
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Отправьте числовой ID")
        return
    
    user_id = int(message.text)
    
    if user_id not in ADMIN_IDS:
        await message.answer(f"❌ Админ не найден")
        await state.clear()
        return
    
    if user_id == 7331748184:
        await message.answer("❌ Нельзя удалить главного админа AR1XY")
        await state.clear()
        return
    
    removed_name = ADMIN_NAMES.get(user_id, str(user_id))
    ADMIN_IDS.remove(user_id)
    if user_id in ADMIN_NAMES:
        del ADMIN_NAMES[user_id]
    save_admins(ADMIN_IDS, ADMIN_NAMES)
    
    await message.answer(f"✅ **Админ {removed_name} (ID: {user_id}) удалён**")
    await state.clear()

# Список админов
@dp.callback_query(lambda c: c.data == "list_admins" and c.from_user.id in ADMIN_IDS)
async def list_admins(callback: types.CallbackQuery):
    text = "👑 **Список администраторов:**\n\n"
    for uid in ADMIN_IDS:
        name = ADMIN_NAMES.get(uid, str(uid))
        online = "🟢" if uid in admin_online and admin_online[uid] > datetime.now() - timedelta(minutes=5) else "⚪"
        text += f"{online} `{uid}` — {name}\n"
    
    await callback.message.answer(text)
    await callback.answer()

# ========== ОСНОВНАЯ ЛОГИКА ==========

@dp.message(Command('start'))
async def start_cmd(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id in ADMIN_IDS:
        await update_admin_activity(user_id)
        await message.answer(
            f"✅ **{ADMIN_NAMES.get(user_id)}**, вы администратор\n\n"
            f"🟢 Онлайн обновляется автоматически",
            reply_markup=admin_keyboard
        )
        return
    
    await message.answer(
        "👋 Добро пожаловать в техподдержку!\n\n"
        "📌 «👥 Админы онлайн» — кто на связи\n"
        "📌 «💬 Задать вопрос» — ответит оператор",
        reply_markup=user_keyboard
    )

@dp.message(lambda message: message.text == "👥 Админы онлайн")
async def show_online(message: types.Message):
    user_id = message.from_user.id
    online_list = get_online_admins()
    
    if user_id in ADMIN_IDS:
        text = "🟢 **Админы онлайн:**\n" + "\n".join([f"• {name}" for name in online_list])
        text += f"\n\n📊 Всего: {len(ADMIN_IDS)}"
        await message.answer(text)
        return
    
    if online_list:
        text = "🟢 **Сейчас онлайн:**\n" + "\n".join([f"• {name}" for name in online_list])
    else:
        text = "🔴 Нет админов онлайн. Отправьте вопрос — ответим!"
    
    await message.answer(text)

@dp.message(lambda message: message.text == "📊 Активные диалоги" and message.from_user.id in ADMIN_IDS)
async def admin_active_dialogs(message: types.Message):
    if active_tickets:
        text = "**📋 Активные диалоги:**\n\n"
        for uid, aid in active_tickets.items():
            text += f"👤 {uid} → {ADMIN_NAMES.get(aid, aid)}\n"
    else:
        text = "📭 Нет активных диалогов"
    await message.answer(text)

@dp.message(lambda message: message.text == "🟢 Мои онлайн" and message.from_user.id in ADMIN_IDS)
async def admin_my_status(message: types.Message):
    await update_admin_activity(message.from_user.id)
    online_list = get_online_admins()
    my_name = ADMIN_NAMES.get(message.from_user.id)
    
    text = f"✅ **{my_name}**, вы онлайн!\n\n"
    others = [n for n in online_list if n != my_name]
    if others:
        text += f"🟢 Ещё онлайн: {', '.join(others)}"
    else:
        text += "🟡 Других админов нет"
    await message.answer(text)

@dp.message(lambda message: message.text == "💬 Задать вопрос")
async def ask_question(message: types.Message, state: FSMContext):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("❌ Вы админ, используйте админские кнопки")
        return
    
    await message.answer("📝 Напишите ваш вопрос:")
    await state.set_state(SupportState.waiting_for_question)

@dp.message(SupportState.waiting_for_question)
async def get_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    
    ticket_status[user_id] = "free"
    
    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"🆕 **Новый запрос**\n\n👤 @{username}\n🆔 `{user_id}`\n\n📝 {message.text}",
            reply_markup=admin_ticket_keyboard(user_id)
        )
    
    await message.answer("✅ Вопрос отправлен! Оператор скоро ответит.", reply_markup=user_keyboard)
    await state.set_state(SupportState.in_dialog)

@dp.callback_query(lambda c: c.data.startswith('take_'))
async def take_ticket(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Только для админов", show_alert=True)
        return
    
    await update_admin_activity(callback.from_user.id)
    user_id = int(callback.data.split('_')[1])
    
    if ticket_status.get(user_id) != "free":
        await callback.answer("❌ Уже принят", show_alert=True)
        return
    
    admin_name = ADMIN_NAMES.get(callback.from_user.id, callback.from_user.first_name)
    ticket_status[user_id] = callback.from_user.id
    active_tickets[user_id] = callback.from_user.id
    
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, f"👤 **{admin_name}** принял запрос от {user_id}")
    
    await bot.send_message(user_id, f"🎧 Ваш запрос принял **{admin_name}**!\n\nПишите сюда.", reply_markup=user_keyboard)
    await callback.message.edit_text(callback.message.text + f"\n\n✅ **Принято: {admin_name}**")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith('close_'))
async def close_ticket(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Недоступно", show_alert=True)
        return
    
    user_id = int(callback.data.split('_')[1])
    
    if user_id in active_tickets and active_tickets[user_id] == callback.from_user.id:
        await bot.send_message(user_id, "🔒 **Диалог закрыт**\n\nСпасибо! Для нового вопроса /start", reply_markup=user_keyboard)
        del active_tickets[user_id]
        ticket_status[user_id] = "closed"
        await callback.answer("✅ Диалог закрыт")
        await callback.message.delete()
    elif user_id in active_tickets:
        await callback.answer("❌ Диалог принял другой админ", show_alert=True)
    else:
        await callback.answer("❌ Не найден")

@dp.message(SupportState.in_dialog)
async def forward_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id in ADMIN_IDS:
        await update_admin_activity(user_id)
        for uid, aid in active_tickets.items():
            if aid == user_id:
                await bot.send_message(uid, f"📨 **Оператор:** {message.text}")
                await message.answer("✅ Отправлено")
                break
    else:
        admin_id = active_tickets.get(user_id)
        if admin_id:
            await bot.send_message(admin_id, f"📨 **Пользователь:** {message.text}")
        else:
            await message.answer("⏳ Оператор ещё не принял запрос.")

async def main():
    print("🤖 Бот поддержки запущен!")
    print(f"👥 Админы: {', '.join(ADMIN_NAMES.values())}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())