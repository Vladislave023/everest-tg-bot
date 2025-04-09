import logging
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from db import init_db
from config import TOKEN, ADMIN_ID
from handlers import (
    start,
    button_handler,
    handle_user_message,
    handle_admin_message,
    check_media_groups,
    admin_panel,
    end_session_handler
)
from keyboards import get_admin_main_keyboard

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    # Инициализация БД
    init_db()
    
    # Создание приложения
    application = Application.builder().token(TOKEN).build()
    
    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    # Обработчики callback-кнопок
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^(?!end_session_).*"))
    application.add_handler(CallbackQueryHandler(end_session_handler, pattern="^end_session_"))
    
    # Обработчики сообщений для администратора
    admin_filters = filters.User(ADMIN_ID)
    admin_message_filters = (
        filters.TEXT | 
        filters.PHOTO | 
        filters.VIDEO | 
        filters.Document.ALL
    ) & ~filters.COMMAND & admin_filters
    
    application.add_handler(MessageHandler(admin_message_filters, handle_admin_message))
    
    # Обработчики сообщений для пользователей
    user_filters = ~filters.User(ADMIN_ID)
    user_message_filters = (
        filters.TEXT | 
        filters.PHOTO | 
        filters.VIDEO | 
        filters.Document.ALL
    ) & ~filters.COMMAND & user_filters
    
    application.add_handler(MessageHandler(user_message_filters, handle_user_message))
    
    # Периодическая проверка медиа-групп
    application.job_queue.run_repeating(check_media_groups, interval=1.0)
    
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()