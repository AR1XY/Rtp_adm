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
BLACKLIST_FILE = "blacklist.json"
STATS_FILE = "stats.json"

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

def load_blacklist():
    try:
        with open(BLACKLIST_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_blacklist(blacklist):
    with open(BLACKLIST_FILE, "w") as f:
        json.dump(blacklist, f)

def load_stats():
    try:
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    except:
        return {"total_tickets": 0, "closed_tickets": 0, "ratings": [], "response_times": []}

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)

ADMIN_IDS, ADMIN_NAMES = load_admins()
tickets = load_tickets()
blacklist = load_blacklist()
stats = load_stats()
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
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🟢 Мои онлайн")],
        [KeyboardButton(text="👑 Управление админами")],
        [KeyboardButton(text="🚫 Чёрный список")]
    ],
    resize_keyboard=True
)

# ========== FSM ==========
class SupportState(StatesGroup):
    waiting_for_question = State()
    add_admin_waiting = State()
    remove_admin_waiting = State()
    admin_answer = State()
    escalate_ticket = State()
    blacklist_add = State()
    blacklist_remove = State()

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

def is_blacklisted(user_id):
    return user_id in blacklist

def get_free_admins():
    """Возвращает список свободных админов (кто не ведёт активные диалоги)"""
    busy_admins = set()
    for tid, ticket in tickets.items():
        if ticket.get("status") == "active" and ticket.get("admin_id"):
            busy_admins.add(ticket["admin_id"])
    
    free_admins = [aid for aid in ADMIN_IDS if aid not in busy_admins]
    return free_admins if free_admins else ADMIN_IDS

def create_ticket(user_id, username, question, file_id=None, file_type=None):
    global next_ticket_id
    ticket_id = str(next_ticket_id)
    next_ticket_id += 1
    
    message_data = {"role": "user", "text": question, "time": datetime.now().isoformat()}
    if file_id:
        message_data["file_id"] = file_id
        message_data["file_type"] = file_type
    
    tickets[ticket_id] = {
        "id": ticket_id,
        "user_id": user_id,
        "username": username,
        "status": "waiting",
        "admin_id": None,
        "messages": [message_data],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "rating": None
    }
    save_tickets(tickets)
    
    stats["total_tickets"] += 1
    save_stats(stats)
    
    return ticket_id

def add_message(ticket_id, role, text, admin_name=None, file_id=None, file_type=None):
    if ticket_id in tickets:
        message_data = {"role": role, "text": text, "time": datetime.now().isoformat()}
        if admin_name:
            message_data["admin_name"] = admin_name
        if file_id:
            message_data["file_id"] = file_id
            message_data["file_type"] = file_type
        tickets[ticket_id]["messages"].append(message_data)
        tickets[ticket_id]["updated_at"] = datetime.now().isoformat()
        save_tickets(tickets)

def get_user_tickets(user_id):
    return {tid: t for tid, t in tickets.items() if t["user_id"] == user_id}

def calculate_avg_rating():
    if not stats["ratings"]:
        return 0
    return sum(stats["ratings"]) / len(stats["ratings"])

def calculate_avg_response_time():
    if not stats["response_times"]:
        return 0
    return sum(stats["response_times"]) / len(stats["response_times"])

# ========== УВЕДОМЛЕНИЯ (ИСПРАВЛЕНО: НЕ СПАМЯТ ВСЕМ) ==========
async def notify_free_admins_new_ticket(ticket_id, username, text, file_info=None):
    """Отправляет уведомление только свободным админам"""
    free_admins = get_free_admins()
    
    msg_text = f"🆕 **Новое обращение #{ticket_id}**\n\n👤 @{username}\n📝 {text}"
    if file_info:
        msg_text += f"\n📎 {file_info}"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Открыть список", callback_data="back_to_list")]
    ])
    
    for admin_id in free_admins:
        try:
            await bot.send_message(admin_id, msg_text, reply_markup=keyboard)
        except:
            pass

async def notify_free_admins_reopen(ticket_id, username):
    """Отправляет уведомление о переоткрытии только свободным админам"""
    free_admins = get_free_admins()
    
    msg_text = f"🔄 **Переоткрыто обращение #{ticket_id}**\n\n👤 @{username}"
    
    for admin_id in free_admins:
        try:
            await bot.send_message(admin_id, msg_text)
        except:
            pass

async def notify_all_admins_taken(ticket_id, admin_name, user_id):
    """Уведомляет всех админов о том, кто принял обращение"""
    msg_text = f"👤 **{admin_name}** принял обращение #{ticket_id}"
    
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, msg_text)
        except:
            pass

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
            keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔄 Передать", callback_data=f"escalate_{ticket_id}")])
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

def rating_keyboard(ticket_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 ⭐", callback_data=f"rate_{ticket_id}_1"),
         InlineKeyboardButton(text="2 ⭐⭐", callback_data=f"rate_{ticket_id}_2"),
         InlineKeyboardButton(text="3 ⭐⭐⭐", callback_data=f"rate_{ticket_id}_3")],
        [InlineKeyboardButton(text="4 ⭐⭐⭐⭐", callback_data=f"rate_{ticket_id}_4"),
         InlineKeyboardButton(text="5 ⭐⭐⭐⭐⭐", callback_data=f"rate_{ticket_id}_5")],
        [InlineKeyboardButton(text="❌ Пропустить", callback_data=f"rate_skip_{ticket_id}")]
    ])
    return keyboard

# ========== ПОЛЬЗОВАТЕЛЬ ==========
@dp.message(Command('start'))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    
    if is_blacklisted(user_id):
        await message.answer("⛔ Вы заблокированы в системе поддержки.")
        return
    
    if user_id in ADMIN_IDS:
        await update_admin_activity(user_id)
        
        # ИНСТРУКЦИЯ ДЛЯ АДМИНОВ
        instructions = """
📖 **Инструкция для администратора**

🔹 **Основные кнопки:**
• 📋 **Все обращения** — список всех тикетов (фильтры: все/ожидание/активные/закрытые)
• 📊 **Статистика** — отчёты по обращениям, рейтинг операторов
• 🟢 **Мои онлайн** — ваш статус и кто ещё в сети
• 👑 **Управление админами** — добавлять/удалять админов (удаляет только AR1XY)
• 🚫 **Чёрный список** — блокировка спамеров

🔹 **Работа с обращением:**
• ✅ **Принять** — взять в работу
• 💬 **Ответить** — написать пользователю (можно фото/файлы)
• 🔄 **Передать** — перевести другому админу
• 🔒 **Закрыть** — завершить диалог (пользователь оценит работу)
• 📜 **История** — вся переписка

🔹 **Уведомления:**
• Новые обращения получают ТОЛЬКО свободные админы
• О принятии узнают все (чтобы не дублировать)

🔹 **Советы:**
• После ответа пользователь может продолжить диалог
• Закрывайте обращения только после решения проблемы
• Оценки пользователей влияют на рейтинг в статистике

✅ **Вы готовы к работе!**
"""
        await message.answer(instructions, reply_markup=admin_keyboard)
        return
    
    await message.answer(
        "👋 Добро пожаловать в поддержку!\n\n"
        "💬 «Создать обращение» — задать вопрос\n"
        "📋 «Мои обращения» — история",
        reply_markup=user_keyboard
    )

@dp.message(lambda message: message.text == "💬 Создать обращение")
async def create_ticket_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    if is_blacklisted(user_id):
        await message.answer("⛔ Вы заблокированы.")
        return
    
    if user_id in ADMIN_IDS:
        await message.answer("❌ Вы админ")
        return
    
    await message.answer("📝 Напишите ваш вопрос (можно прикрепить фото/файл):")
    await state.set_state(SupportState.waiting_for_question)

@dp.message(SupportState.waiting_for_question)
async def create_ticket_submit(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # ИСПРАВЛЕНО: проверка чёрного списка при создании обращения
    if is_blacklisted(user_id):
        await message.answer("⛔ Вы заблокированы в системе поддержки.")
        await state.clear()
        return
    
    username = message.from_user.username or str(user_id)
    
    text = message.text or "Прикреплён файл"
    file_id = None
    file_type = None
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    
    ticket_id = create_ticket(user_id, username, text, file_id, file_type)
    
    # ИСПРАВЛЕНО: уведомления только свободным админам
    await notify_free_admins_new_ticket(ticket_id, username, text, "📎 Есть вложение" if file_id else None)
    
    await message.answer(
        f"✅ **Обращение #{ticket_id} создано!**\n\nОператор ответит здесь.",
        reply_markup=user_keyboard
    )
    await state.clear()

@dp.message(lambda message: message.text == "📋 Мои обращения")
async def my_tickets(message: types.Message):
    user_id = message.from_user.id
    
    if is_blacklisted(user_id):
        await message.answer("⛔ Вы заблокированы.")
        return
    
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
    
    rating_text = f"\n⭐ Оценка: {t['rating']}/5" if t.get("rating") else ""
    
    await callback.message.edit_text(
        f"🔖 **Обращение #{ticket_id}**\n\n"
        f"📅 Создано: {datetime.fromisoformat(t['created_at']).strftime('%d.%m.%Y %H:%M')}\n"
        f"📊 Статус: {status_text}{rating_text}",
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
        history += f"{role} ({time}):\n{msg['text'][:200]}\n"
        if msg.get("file_id"):
            history += f"📎 [Вложение]\n"
        history += "\n"
    
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
    rating_text = f"\n⭐ Оценка: {t['rating']}/5" if t.get("rating") else ""
    
    await callback.message.edit_text(
        f"🔖 **Обращение #{ticket_id}**\n\n"
        f"👤 Пользователь: @{t['username']}\n"
        f"🆔 ID: {t['user_id']}\n"
        f"📅 Создано: {datetime.fromisoformat(t['created_at']).strftime('%d.%m.%Y %H:%M')}\n"
        f"📊 Статус: {status_text}{admin_text}{rating_text}",
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
    
    # ИСПРАВЛЕНО: уведомляем всех админов, кто принял
    await notify_all_admins_taken(ticket_id, admin_name, t["user_id"])
    
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
    await callback.message.answer(f"💬 **Ответ на обращение #{ticket_id}**\n\nНапишите ответ (можно прикрепить фото/файл):")
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
    text = message.text or "Прикреплён файл"
    file_id = None
    file_type = None
    
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    
    add_message(ticket_id, "admin", text, admin_name, file_id, file_type)
    
    # ИСПРАВЛЕНО: поддержка файлов при ответе админа
    if file_id:
        if file_type == "photo":
            await bot.send_photo(t["user_id"], file_id, caption=f"📨 **Оператор {admin_name}:**\n\n{text}")
        else:
            await bot.send_document(t["user_id"], file_id, caption=f"📨 **Оператор {admin_name}:**\n\n{text}")
    else:
        await bot.send_message(
            t["user_id"],
            f"📨 **Оператор {admin_name}:**\n\n{text}\n\n➡️ Просто напишите сюда, чтобы ответить."
        )
    
    await message.answer(f"✅ Ответ отправлен!\n\nПользователь может продолжить диалог.")
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("escalate_"))
async def escalate_ticket_start(callback: types.CallbackQuery, state: FSMContext):
    ticket_id = callback.data.split("_")[1]
    t = tickets.get(ticket_id)
    
    if not t or t["status"] != "active":
        await callback.answer("❌ Недоступно", show_alert=True)
        return
    
    if t["admin_id"] != callback.from_user.id:
        await callback.answer("❌ Не ваш диалог", show_alert=True)
        return
    
    admin_list = []
    for uid in ADMIN_IDS:
        if uid != callback.from_user.id:
            admin_list.append(f"{uid} — {ADMIN_NAMES.get(uid)}")
    
    await state.update_data(escalate_ticket_id=ticket_id)
    await callback.message.answer(
        f"🔄 **Перевести обращение #{ticket_id}**\n\n"
        f"Выберите ID администратора:\n\n" + "\n".join(admin_list) + "\n\n"
        f"Введите ID админа:"
    )
    await state.set_state(SupportState.escalate_ticket)
    await callback.answer()

@dp.message(SupportState.escalate_ticket)
async def escalate_ticket_process(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("escalate_ticket_id")
    t = tickets.get(ticket_id)
    
    if not t or t["status"] != "active":
        await message.answer("❌ Обращение уже не активно")
        await state.clear()
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Введите числовой ID")
        return
    
    new_admin_id = int(message.text)
    
    if new_admin_id not in ADMIN_IDS:
        await message.answer("❌ Админ с таким ID не найден")
        return
    
    old_admin_name = ADMIN_NAMES.get(t["admin_id"])
    new_admin_name = ADMIN_NAMES.get(new_admin_id)
    
    t["admin_id"] = new_admin_id
    save_tickets(tickets)
    
    # ИСПРАВЛЕНО: добавляем запись в историю о передаче
    add_message(ticket_id, "admin", f"Обращение передано от {old_admin_name} к {new_admin_name}", "Система")
    
    await bot.send_message(
        new_admin_id,
        f"🔄 **Вам передано обращение #{ticket_id}**\n\n"
        f"👤 Пользователь: @{t['username']}\n"
        f"От: {old_admin_name}\n\n"
        f"➡️ Нажмите «Просмотреть» в списке обращений"
    )
    
    await message.answer(f"✅ Обращение #{ticket_id} передано администратору {new_admin_name}")
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
    
    # ИСПРАВЛЕНО: замер времени ответа для статистики
    if t["messages"]:
        first_admin_msg = None
        for msg in t["messages"]:
            if msg["role"] == "admin" and msg.get("admin_name") != "Система":
                first_admin_msg = msg
                break
        if first_admin_msg:
            created = datetime.fromisoformat(t["created_at"])
            answered = datetime.fromisoformat(first_admin_msg["time"])
            response_time = (answered - created).seconds // 60
            stats["response_times"].append(response_time)
            save_stats(stats)
    
    t["status"] = "closed"
    save_tickets(tickets)
    
    stats["closed_tickets"] += 1
    save_stats(stats)
    
    await bot.send_message(
        t["user_id"],
        f"🔒 **Обращение #{ticket_id} закрыто**\n\n"
        f"Спасибо за обращение! Оцените работу оператора:",
        reply_markup=rating_keyboard(ticket_id)
    )
    
    await callback.message.edit_text(
        callback.message.text + f"\n\n🔒 **Закрыто**",
        reply_markup=ticket_detail_keyboard(ticket_id)
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("rate_"))
async def handle_rating(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    ticket_id = parts[1]
    
    if parts[2] == "skip":
        await callback.message.edit_text("🙏 Спасибо за обращение!")
        await callback.answer()
        return
    
    rating = int(parts[2])
    t = tickets.get(ticket_id)
    
    if t:
        t["rating"] = rating
        save_tickets(tickets)
        stats["ratings"].append(rating)
        save_stats(stats)
        
        # ИСПРАВЛЕНО: уведомляем админа об оценке
        if t.get("admin_id"):
            await bot.send_message(
                t["admin_id"],
                f"⭐ **Оценка за обращение #{ticket_id}:** {rating}/5\n\n"
                f"От пользователя @{t['username']}"
            )
        
        await callback.message.edit_text(
            f"⭐ **Спасибо за оценку {rating}/5!**\n\n"
            f"Мы стараемся стать лучше."
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
    
    # ИСПРАВЛЕНО: уведомления только свободным админам
    await notify_free_admins_reopen(ticket_id, t["username"])
    
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
        history += f"{role} ({time}):\n{msg['text'][:200]}\n"
        if msg.get("file_id"):
            history += f"📎 [Вложение]\n"
        history += "\n"
    
    if len(history) > 4000:
        history = history[:3900] + "\n\n..."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"view_{ticket_id}")]
    ])
    await callback.message.edit_text(history, reply_markup=keyboard)
    await callback.answer()

@dp.message(lambda message: message.text == "📊 Статистика" and message.from_user.id in ADMIN_IDS)
async def show_statistics(message: types.Message):
    avg_rating = calculate_avg_rating()
    avg_response = calculate_avg_response_time()
    
    waiting = len([t for t in tickets.values() if t["status"] == "waiting"])
    active = len([t for t in tickets.values() if t["status"] == "active"])
    closed = len([t for t in tickets.values() if t["status"] == "closed"])
    
    # ИСПРАВЛЕНО: привязка оценок к админам
    admin_ratings = {}
    for t in tickets.values():
        if t.get("rating") and t.get("admin_id"):
            aid = t["admin_id"]
            if aid not in admin_ratings:
                admin_ratings[aid] = {"sum": 0, "count": 0}
            admin_ratings[aid]["sum"] += t["rating"]
            admin_ratings[aid]["count"] += 1
    
    rating_text = ""
    for aid, data in admin_ratings.items():
        avg = data["sum"] / data["count"]
        rating_text += f"• {ADMIN_NAMES.get(aid, aid)}: {avg:.1f}⭐ ({data['count']} оценок)\n"
    
    await message.answer(
        f"📊 **Статистика поддержки**\n\n"
        f"📈 **Всего обращений:** {stats['total_tickets']}\n"
        f"✅ **Закрыто:** {stats['closed_tickets']}\n"
        f"🟡 **Ожидают:** {waiting}\n"
        f"🟢 **В работе:** {active}\n"
        f"⚪ **Закрыто:** {closed}\n\n"
        f"⭐ **Средний рейтинг:** {avg_rating:.1f}/5\n"
        f"⏱️ **Среднее время ответа:** {avg_response:.0f} мин\n\n"
        f"🏆 **Рейтинг операторов:**\n{rating_text if rating_text else 'Нет оценок'}"
    )

@dp.message(lambda message: message.text == "🚫 Чёрный список" and message.from_user.id in ADMIN_IDS)
async def blacklist_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить в ЧС", callback_data="blacklist_add")],
        [InlineKeyboardButton(text="➖ Удалить из ЧС", callback_data="blacklist_remove")],
        [InlineKeyboardButton(text="📋 Список ЧС", callback_data="blacklist_list")]
    ])
    await message.answer("🚫 **Управление чёрным списком**", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "blacklist_add" and c.from_user.id in ADMIN_IDS)
async def blacklist_add_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 Введите ID пользователя для блокировки:")
    await state.set_state(SupportState.blacklist_add)
    await callback.answer()

@dp.message(SupportState.blacklist_add)
async def blacklist_add_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Введите числовой ID")
        return
    
    user_id = int(message.text)
    
    if user_id in blacklist:
        await message.answer(f"❌ Пользователь {user_id} уже в ЧС")
        await state.clear()
        return
    
    blacklist.append(user_id)
    save_blacklist(blacklist)
    
    await message.answer(f"✅ Пользователь {user_id} добавлен в чёрный список")
    await state.clear()

@dp.callback_query(lambda c: c.data == "blacklist_remove" and c.from_user.id in ADMIN_IDS)
async def blacklist_remove_start(callback: types.CallbackQuery, state: FSMContext):
    if not blacklist:
        await callback.answer("📭 Список пуст", show_alert=True)
        return
    
    await callback.message.answer(f"📝 Введите ID пользователя для разблокировки:\n\nТекущие: {', '.join(map(str, blacklist))}")
    await state.set_state(SupportState.blacklist_remove)
    await callback.answer()

@dp.message(SupportState.blacklist_remove)
async def blacklist_remove_process(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    if not message.text.isdigit():
        await message.answer("❌ Введите числовой ID")
        return
    
    user_id = int(message.text)
    
    if user_id not in blacklist:
        await message.answer(f"❌ Пользователь {user_id} не в ЧС")
        await state.clear()
        return
    
    blacklist.remove(user_id)
    save_blacklist(blacklist)
    
    await message.answer(f"✅ Пользователь {user_id} удалён из чёрного списка")
    await state.clear()

@dp.callback_query(lambda c: c.data == "blacklist_list" and c.from_user.id in ADMIN_IDS)
async def blacklist_list(callback: types.CallbackQuery):
    if not blacklist:
        await callback.answer("📭 Чёрный список пуст", show_alert=True)
        return
    
    text = "🚫 **Чёрный список:**\n\n"
    for uid in blacklist:
        text += f"• {uid}\n"
    
    await callback.message.answer(text)
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
    
    if is_blacklisted(user_id):
        await message.answer("⛔ Вы заблокированы в системе поддержки.")
        return
    
    if user_id in ADMIN_IDS:
        return
    
    for tid, t in tickets.items():
        if t["user_id"] == user_id and t["status"] == "active":
            text = message.text or "Прикреплён файл"
            file_id = None
            file_type = None
            
            if message.photo:
                file_id = message.photo[-1].file_id
                file_type = "photo"
            elif message.document:
                file_id = message.document.file_id
                file_type = "document"
            
            add_message(tid, "user", text, None, file_id, file_type)
            admin_id = t["admin_id"]
            
            if file_id:
                if file_type == "photo":
                    await bot.send_photo(admin_id, file_id, caption=f"📨 **Пользователь @{t['username']} (#{tid}):**\n\n{text}")
                else:
                    await bot.send_document(admin_id, file_id, caption=f"📨 **Пользователь @{t['username']} (#{tid}):**\n\n{text}")
            else:
                await bot.send_message(
                    admin_id,
                    f"📨 **Пользователь @{t['username']} (#{tid}):**\n\n{text}\n\n"
                    f"➡️ Нажмите «Ответить» в меню обращения"
                )
            await message.answer("✅ Сообщение отправлено оператору")
            return
    
    # ИСПРАВЛЕНО: понятное сообщение, если нет активного диалога
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