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

# ========== ДАННЫЕ ==========
ADMIN_FILE = "admins.json"
TICKETS_FILE = "tickets.json"

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

def load_tickets():
    try:
        with open(TICKETS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_tickets(tickets):
    with open(TICKETS_FILE, "w") as f:
        json.dump(tickets, f)

ADMIN_IDS, ADMIN_NAMES = load_admins()
tickets = load_tickets()
next_ticket_id = max([int(tid) for tid in tickets.keys()] + [0]) + 1

admin_online = {}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ========== КЛАВИАТУРЫ ==========
user_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💬 Создать обращение")],
        [KeyboardButton(text="📋 Мои обращения")]
    ],
    resize_keyboard=True
)

admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Все обращения")],
        [KeyboardButton(text="🟢 Мои онлайн")],
        [KeyboardButton(text="👑 Управление админами")]
    ],
    resize_keyboard=True
)

# ========== FSM ==========
class SupportState(StatesGroup):
    waiting_for_question = State()
    add_admin_waiting = State()
    remove_admin_waiting = State()
    admin_answer = State()

# ========== ВСПОМОГАТЕЛЬНЫЕ ==========
async def update_admin_activity(admin_id):
    admin_online[admin_id] = datetime.now()

def get_online_admins():
    online = []
    five_min_ago = datetime.now() - timedelta(minutes=5)
    for admin_id, last_seen in admin_online.items():
        if last_seen > five_min_ago and admin_id in ADMIN_IDS:
            online.append(ADMIN_NAMES.get(admin_id, str(admin_id)))
    return online

def create_ticket(user_id, username, question):
    global next_ticket_id
    ticket_id = str(next_ticket_id)
    next_ticket_id += 1
    
    tickets[ticket_id] = {
        "id": ticket_id,
        "user_id": user_id,
        "username": username,
        "status": "waiting",
        "admin_id": None,
        "messages": [{"role": "user", "text": question, "time": datetime.now().isoformat()}],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    save_tickets(tickets)
    return ticket_id

def add_message(ticket_id, role, text, admin_name=None):
    if ticket_id in tickets:
        tickets[ticket_id]["messages"].append({
            "role": role,
            "text": text,
            "admin_name": admin_name,
            "time": datetime.now().isoformat()
        })
        tickets[ticket_id]["updated_at"] = datetime.now().isoformat()
        save_tickets(tickets)

def get_user_tickets(user_id):
    return {tid: t for tid, t in tickets.items() if t["user_id"] == user_id}

# ========== КЛАВИАТУРЫ СПИСКОВ ==========
def admin_ticket_list_keyboard(page=0, status_filter="all"):
    filtered = []
    for tid, t in tickets.items():
        if status_filter == "all":
            filtered.append(t)
        elif status_filter == "waiting" and t["status"] == "waiting":
            filtered.append(t)
        elif status_filter == "active" and t["status"] == "active":
            filtered.append(t)
        elif status_filter == "closed" and t["status"] == "closed":
            filtered.append(t)
    
    filtered.sort(key=lambda x: x["updated_at"], reverse=True)
    
    items_per_page = 5
    total_pages = (len(filtered) + items_per_page - 1) // items_per_page
    start = page * items_per_page
    end = start + items_per_page
    page_tickets = filtered[start:end]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for t in page_tickets:
        status_icon = "🟡" if t["status"] == "waiting" else "🟢" if t["status"] == "active" else "⚪"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status_icon} #{t['id']} | {t['username']}", callback_data=f"view_{t['id']}")
        ])
    
    # Фильтры
    filter_row = []
    if status_filter != "all":
        filter_row.append(InlineKeyboardButton(text="📋 Все", callback_data=f"filter_all_{page}"))
    if status_filter != "waiting":
        filter_row.append(InlineKeyboardButton(text="🟡 Ожидание", callback_data=f"filter_waiting_{page}"))
    if status_filter != "active":
        filter_row.append(InlineKeyboardButton(text="🟢 Активные", callback_data=f"filter_active_{page}"))
    if status_filter != "closed":
        filter_row.append(InlineKeyboardButton(text="⚪ Закрытые", callback_data=f"filter_closed_{page}"))
    
    if filter_row:
        keyboard.inline_keyboard.append(filter_row)
    
    # Пагинация
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"tickets_page_{page-1}_{status_filter}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"tickets_page_{page+1}_{status_filter}"))
    if nav_row:
        keyboard.inline_keyboard.append(nav_row)
    
    return keyboard, len(filtered), page, total_pages

def ticket_detail_keyboard(ticket_id):
    t = tickets.get(ticket_id)
    if not t:
        return None
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    if t["status"] == "waiting":
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="✅ Принять", callback_data=f"take_{ticket_id}")])
    elif t["status"] == "active":
        if t["admin_id"]:
            keyboard.inline_keyboard.append([InlineKeyboardButton(text="💬 Ответить", callback_data=f"answer_{ticket_id}")])
            keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"close_{ticket_id}")])
    elif t["status"] == "closed":
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="📂 Открыть заново", callback_data=f"reopen_{ticket_id}")])
    
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="📜 История", callback_data=f"history_{ticket_id}")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="◀️ Назад к списку", callback_data="back_to_list")])
    
    return keyboard

def user_ticket_list_keyboard(user_id, page=0):
    user_tickets = get_user_tickets(user_id)
    items = list(user_tickets.values())
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    
    items_per_page = 5
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    start = page * items_per_page
    end = start + items_per_page
    page_items = items[start:end]
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    for t in page_items:
        status_icon = "🟡" if t["status"] == "waiting" else "🟢" if t["status"] == "active" else "⚪"
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"{status_icon} #{t['id']}", callback_data=f"user_view_{t['id']}")
        ])
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"user_page_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"user_page_{page+1}"))
    if nav_row:
        keyboard.inline_keyboard.append(nav_row)
    
    return keyboard, len(items)

def user_ticket_detail_keyboard(ticket_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Переписка", callback_data=f"user_history_{ticket_id}")],
        [InlineKeyboardButton(text="◀️ Мои обращения", callback_data="back_to_user_tickets")]
    ])

# ========== ПОЛЬЗОВАТЕЛЬ ==========
@dp.message(Command('start'))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    
    if user_id in ADMIN_IDS:
        await update_admin_activity(user_id)
        await message.answer(
            f"✅ **{ADMIN_NAMES.get(user_id)}**, вы администратор\n\n📌 Используйте кнопки для управления",
            reply_markup=admin_keyboard
        )
        return
    
    await message.answer(
        "👋 Добро пожаловать в поддержку!\n\n"
        "💬 «Создать обращение» — задать вопрос\n"
        "📋 «Мои обращения» — история",
        reply_markup=user_keyboard
    )

@dp.message(lambda message: message.text == "💬 Создать обращение")
async def create_ticket_start(message: types.Message, state: FSMContext):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("❌ Вы админ")
        return
    
    await message.answer("📝 Напишите ваш вопрос:")
    await state.set_state(SupportState.waiting_for_question)

@dp.message(SupportState.waiting_for_question)
async def create_ticket_submit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    
    ticket_id = create_ticket(user_id, username, message.text)
    
    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"🆕 **Новое обращение #{ticket_id}**\n\n👤 @{username}\n📝 {message.text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Открыть список", callback_data="back_to_list")]
            ])
        )
    
    await message.answer(
        f"✅ **Обращение #{ticket_id} создано!**\n\nОператор ответит здесь.",
        reply_markup=user_keyboard
    )
    await state.clear()

@dp.message(lambda message: message.text == "📋 Мои обращения")
async def my_tickets(message: types.Message):
    user_id = message.from_user.id
    if user_id in ADMIN_IDS:
        return
    
    user_tickets = get_user_tickets(user_id)
    if not user_tickets:
        await message.answer("📭 У вас нет обращений. Нажмите «Создать обращение».")
        return
    
    keyboard, total = user_ticket_list_keyboard(user_id, 0)
    await message.answer(f"📋 **Ваши обращения** ({total})", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("user_page_"))
async def user_tickets_page(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    keyboard, total = user_ticket_list_keyboard(callback.from_user.id, page)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("user_view_"))
async def user_view_ticket(callback: types.CallbackQuery):
    ticket_id = callback.data.split("_")[2]
    t = tickets.get(ticket_id)
    
    if not t or t["user_id"] != callback.from_user.id:
        await callback.answer("❌ Не найдено", show_alert=True)
        return
    
    status_text = {
        "waiting": "🟡 Ожидает ответа",
        "active": f"🟢 В работе",
        "closed": "⚪ Закрыто"
    }.get(t["status"], "❓")
    
    await callback.message.edit_text(
        f"🔖 **Обращение #{ticket_id}**\n\n"
        f"📅 Создано: {datetime.fromisoformat(t['created_at']).strftime('%d.%m.%Y %H:%M')}\n"
        f"📊 Статус: {status_text}",
        reply_markup=user_ticket_detail_keyboard(ticket_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_user_tickets")
async def back_to_user_tickets(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    keyboard, total = user_ticket_list_keyboard(user_id, 0)
    await callback.message.edit_text(f"📋 **Ваши обращения** ({total})", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("user_history_"))
async def user_history(callback: types.CallbackQuery):
    ticket_id = callback.data.split("_")[2]
    t = tickets.get(ticket_id)
    
    if not t or t["user_id"] != callback.from_user.id:
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    history = "💬 **Переписка:**\n\n"
    for msg in t["messages"]:
        if msg["role"] == "user":
            role = "👤 Вы"
        else:
            role = f"🛠 {msg.get('admin_name', 'Оператор')}"
        time = datetime.fromisoformat(msg["time"]).strftime("%H:%M %d.%m")
        history += f"{role} ({time}):\n{msg['text'][:200]}\n\n"
    
    if len(history) > 4000:
        history = history[:3900] + "\n\n..."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"user_view_{ticket_id}")]
    ])
    await callback.message.edit_text(history, reply_markup=keyboard)
    await callback.answer()

# ========== АДМИН ==========
@dp.message(lambda message: message.text == "📋 Все обращения" and message.from_user.id in ADMIN_IDS)
async def admin_ticket_list(message: types.Message):
    keyboard, total, page, total_pages = admin_ticket_list_keyboard(0, "all")
    await message.answer(
        f"📋 **Все обращения** ({total})\n🟡 Ожидание | 🟢 Активен | ⚪ Закрыт",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith("tickets_page_"))
async def tickets_page(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    page = int(parts[2])
    status_filter = parts[3] if len(parts) > 3 else "all"
    
    keyboard, total, page, total_pages = admin_ticket_list_keyboard(page, status_filter)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("filter_"))
async def filter_tickets(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    status_filter = parts[1]
    page = int(parts[2])
    
    keyboard, total, page, total_pages = admin_ticket_list_keyboard(page, status_filter)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("view_"))
async def view_ticket(callback: types.CallbackQuery):
    ticket_id = callback.data.split("_")[1]
    t = tickets.get(ticket_id)
    
    if not t:
        await callback.answer("❌ Не найдено", show_alert=True)
        return
    
    status_text = {
        "waiting": "🟡 Ожидает",
        "active": f"🟢 В работе",
        "closed": "⚪ Закрыто"
    }.get(t["status"], "❓")
    
    admin_text = f"\n👤 Оператор: {ADMIN_NAMES.get(t['admin_id'])}" if t.get("admin_id") else ""
    
    await callback.message.edit_text(
        f"🔖 **Обращение #{ticket_id}**\n\n"
        f"👤 Пользователь: @{t['username']}\n"
        f"🆔 ID: {t['user_id']}\n"
        f"📅 Создано: {datetime.fromisoformat(t['created_at']).strftime('%d.%m.%Y %H:%M')}\n"
        f"📊 Статус: {status_text}{admin_text}",
        reply_markup=ticket_detail_keyboard(ticket_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_list")
async def back_to_list(callback: types.CallbackQuery):
    keyboard, total, page, total_pages = admin_ticket_list_keyboard(0, "all")
    await callback.message.edit_text(
        f"📋 **Все обращения** ({total})\n🟡 Ожидание | 🟢 Активен | ⚪ Закрыт",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("take_"))
async def take_ticket(callback: types.CallbackQuery):
    ticket_id = callback.data.split("_")[1]
    t = tickets.get(ticket_id)
    
    if not t or t["status"] != "waiting":
        await callback.answer("❌ Недоступно", show_alert=True)
        return
    
    admin_name = ADMIN_NAMES.get(callback.from_user.id)
    t["status"] = "active"
    t["admin_id"] = callback.from_user.id
    save_tickets(tickets)
    await update_admin_activity(callback.from_user.id)
    
    await bot.send_message(
        t["user_id"],
        f"🎧 **Обращение #{ticket_id} принял {admin_name}**\n\nОператор ответит здесь."
    )
    
    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ **Принял: {admin_name}**",
        reply_markup=ticket_detail_keyboard(ticket_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("answer_"))
async def answer_ticket_start(callback: types.CallbackQuery, state: FSMContext):
    ticket_id = callback.data.split("_")[1]
    t = tickets.get(ticket_id)
    
    if not t or t["status"] != "active":
        await callback.answer("❌ Обращение не активно", show_alert=True)
        return
    
    if t["admin_id"] != callback.from_user.id:
        await callback.answer("❌ Другой оператор", show_alert=True)
        return
    
    await state.update_data(answer_ticket_id=ticket_id)
    await callback.message.answer(f"💬 **Ответ на обращение #{ticket_id}**\n\nНапишите ответ:")
    await state.set_state(SupportState.admin_answer)
    await callback.answer()

@dp.message(SupportState.admin_answer)
async def answer_ticket_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("answer_ticket_id")
    t = tickets.get(ticket_id)
    
    if not t or t["status"] != "active":
        await message.answer("❌ Обращение уже закрыто")
        await state.clear()
        return
    
    admin_name = ADMIN_NAMES.get(message.from_user.id)
    add_message(ticket_id, "admin", message.text, admin_name)
    
    await bot.send_message(
        t["user_id"],
        f"📨 **Оператор {admin_name}:**\n\n{message.text}\n\n➡️ Просто напишите сюда, чтобы ответить."
    )
    
    await message.answer(f"✅ Ответ отправлен!\n\nПользователь может продолжить диалог.")
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("close_"))
async def close_ticket(callback: types.CallbackQuery):
    ticket_id = callback.data.split("_")[1]
    t = tickets.get(ticket_id)
    
    if not t or t["status"] != "active":
        await callback.answer("❌ Не активно", show_alert=True)
        return
    
    if t["admin_id"] != callback.from_user.id:
        await callback.answer("❌ Не ваш диалог", show_alert=True)
        return
    
    t["status"] = "closed"
    save_tickets(tickets)
    
    await bot.send_message(
        t["user_id"],
        f"🔒 **Обращение #{ticket_id} закрыто**\n\nСпасибо! Если нужна помощь — создайте новое обращение."
    )
    
    await callback.message.edit_text(
        callback.message.text + f"\n\n🔒 **Закрыто**",
        reply_markup=ticket_detail_keyboard(ticket_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("reopen_"))
async def reopen_ticket(callback: types.CallbackQuery):
    ticket_id = callback.data.split("_")[1]
    t = tickets.get(ticket_id)
    
    if not t or t["status"] != "closed":
        await callback.answer("❌ Не закрыто", show_alert=True)
        return
    
    t["status"] = "waiting"
    t["admin_id"] = None
    save_tickets(tickets)
    
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, f"🔄 **Переоткрыто обращение #{ticket_id}**\n\n👤 @{t['username']}")
    
    await callback.message.edit_text(
        callback.message.text + f"\n\n🔄 **Переоткрыто**",
        reply_markup=ticket_detail_keyboard(ticket_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("history_"))
async def ticket_history(callback: types.CallbackQuery):
    ticket_id = callback.data.split("_")[1]
    t = tickets.get(ticket_id)
    
    if not t:
        await callback.answer("❌ Не найдено", show_alert=True)
        return
    
    history = "💬 **Полная переписка:**\n\n"
    for msg in t["messages"]:
        if msg["role"] == "user":
            role = "👤 Пользователь"
        else:
            role = f"🛠 {msg.get('admin_name', 'Оператор')}"
        time = datetime.fromisoformat(msg["time"]).strftime("%H:%M %d.%m")
        history += f"{role} ({time}):\n{msg['text'][:200]}\n\n"
    
    if len(history) > 4000:
        history = history[:3900] + "\n\n..."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"view_{ticket_id}")]
    ])
    await callback.message.edit_text(history, reply_markup=keyboard)
    await callback.answer()

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

# ========== УПРАВЛЕНИЕ АДМИНАМИ ==========
@dp.message(lambda message: message.text == "👑 Управление админами" and message.from_user.id in ADMIN_IDS)
async def admin_management(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить", callback_data="add_admin")],
        [InlineKeyboardButton(text="➖ Удалить", callback_data="remove_admin")],
        [InlineKeyboardButton(text="📋 Список", callback_data="list_admins")]
    ])
    await message.answer("👑 **Управление**", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "add_admin" and c.from_user.id in ADMIN_IDS)
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Отправьте ID или перешлите сообщение:")
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
        await message.answer("❌ Отправьте ID или перешлите сообщение")
        return
    
    if user_id in ADMIN_IDS:
        await message.answer("❌ Уже админ")
        await state.clear()
        return
    
    ADMIN_IDS.append(user_id)
    ADMIN_NAMES[user_id] = name
    save_admins(ADMIN_IDS, ADMIN_NAMES)
    
    await message.answer(f"✅ Добавлен: {name} (ID: {user_id})")
    try:
        await bot.send_message(user_id, "🎉 Вы стали администратором!\n\nНапишите /start")
    except:
        pass
    await state.clear()

@dp.callback_query(lambda c: c.data == "remove_admin" and c.from_user.id in ADMIN_IDS)
async def remove_admin_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != 7331748184:
        await callback.answer("❌ Только AR1XY", show_alert=True)
        return
    
    admin_list = "\n".join([f"• {uid} — {ADMIN_NAMES.get(uid, uid)}" for uid in ADMIN_IDS])
    await callback.message.answer(f"📝 **Удаление**\n\n{admin_list}\n\nВведите ID:")
    await state.set_state(SupportState.remove_admin_waiting)
    await callback.answer()

@dp.message(SupportState.remove_admin_waiting)
async def remove_admin_process(message: types.Message, state: FSMContext):
    if message.from_user.id != 7331748184:
        await message.answer("❌ Только AR1XY")
        await state.clear()
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Введите ID")
        return
    
    user_id = int(message.text)
    
    if user_id not in ADMIN_IDS:
        await message.answer("❌ Не найден")
        await state.clear()
        return
    
    if user_id == 7331748184:
        await message.answer("❌ Нельзя удалить AR1XY")
        await state.clear()
        return
    
    removed = ADMIN_NAMES.get(user_id, str(user_id))
    ADMIN_IDS.remove(user_id)
    if user_id in ADMIN_NAMES:
        del ADMIN_NAMES[user_id]
    save_admins(ADMIN_IDS, ADMIN_NAMES)
    
    await message.answer(f"✅ Удалён: {removed}")
    await state.clear()

@dp.callback_query(lambda c: c.data == "list_admins" and c.from_user.id in ADMIN_IDS)
async def list_admins(callback: types.CallbackQuery):
    text = "👑 **Администраторы:**\n\n"
    for uid in ADMIN_IDS:
        name = ADMIN_NAMES.get(uid, str(uid))
        online = "🟢" if uid in admin_online and admin_online[uid] > datetime.now() - timedelta(minutes=5) else "⚪"
        text += f"{online} {uid} — {name}\n"
    await callback.message.answer(text)
    await callback.answer()

# ========== ПОЛЬЗОВАТЕЛЬ ПИШЕТ В АКТИВНОМ ЧАТЕ ==========
@dp.message()
async def user_message_in_chat(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id in ADMIN_IDS:
        return
    
    # Ищем активный тикет пользователя
    for tid, t in tickets.items():
        if t["user_id"] == user_id and t["status"] == "active":
            add_message(tid, "user", message.text)
            admin_id = t["admin_id"]
            
            await bot.send_message(
                admin_id,
                f"📨 **Пользователь @{t['username']} (#{tid}):**\n\n{message.text}\n\n"
                f"➡️ Нажмите «Ответить» в меню обращения"
            )
            await message.answer("✅ Сообщение отправлено оператору")
            return
    
    # Если нет активного тикета
    await message.answer(
        "⚠️ У вас нет активного диалога.\n\n"
        "Нажмите «💬 Создать обращение», чтобы задать вопрос."
    )

# ========== ЗАПУСК ==========
async def main():
    print("🤖 Бот поддержки запущен!")
    print(f"👥 Админы: {', '.join(ADMIN_NAMES.values())}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())