from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import WEBSITE_URL, CHANNEL_URL

def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Связаться со специалистом", callback_data='contact_specialist')],
        [InlineKeyboardButton("📂 Каталог", url=WEBSITE_URL)],
        [InlineKeyboardButton("📢 Наш канал", url=CHANNEL_URL)]
    ])
def get_admin_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Посмотреть все запросы", callback_data='show_all_requests')],
        [InlineKeyboardButton("🔚 Завершить все сессии", callback_data='end_all_sessions')],
        [InlineKeyboardButton("❌ Очистить все запросы", callback_data='clear_all_requests')]
    ])
def get_admin_request_keyboard(request_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Принять запрос", callback_data=f'accept_request_{request_id}')],
        [InlineKeyboardButton("❌ Отклонить запрос", callback_data=f'reject_request_{request_id}')]
    ])

def get_admin_session_keyboard(session_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔚 Завершить сессию", callback_data=f'end_session_{session_id}')]
    ])