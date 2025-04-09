import logging
from db import get_db_connection
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from telegram import (
    Update,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument,
    Message,
    User,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, CommandHandler, filters
from db import (
    add_user_request, get_pending_requests, get_user_active_request,
    start_request_processing, create_session, end_session,
    get_active_session_by_user, get_active_admin_session,
    add_message_to_request, add_session_message, get_messages_for_request
)
from keyboards import (
    get_main_menu_keyboard, 
    get_admin_request_keyboard,
    get_admin_session_keyboard,
    get_admin_main_keyboard
)
from config import ADMIN_ID, WORKING_HOURS_TEXT, ALBUM_THRESHOLD_SECONDS

logger = logging.getLogger(__name__)

# Глобальные переменные для обработки медиа-групп
user_media_groups = {}

class MediaGroup:
    def __init__(self, request_id: int, user_id: int, user_name: str, username: str, 
                 caption: str = None, session_id: int = None):
        self.request_id = request_id
        self.user_id = user_id
        self.user_name = user_name
        self.username = username
        self.caption = caption
        self.session_id = session_id
        self.messages = []
        self.created_at = datetime.now()
    
    def is_expired(self) -> bool:
        return (datetime.now() - self.created_at).total_seconds() > ALBUM_THRESHOLD_SECONDS
    
    def add_message(self, message):
        self.messages.append(message)
        if message.caption and not self.caption:
            self.caption = message.caption

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    welcome_text = """
<b>Компания "ЭВЕРЕСТ"</b> - поставка спецтехники, шин и запчастей.

Почта: trucks@everest-tk.ru 
Телефон: +7 914 310-53-49
Сайт: everest-tk.ru

Нажмите кнопку связаться со специалистом и отправьте ваш запрос в сообщении или перешлите пост из Telegram – мы ответим в рабочее время (пн-пт, 9:00–18:00, Хабаровск).

Чем мы можем вам помочь? Выберите действие:

• 📝 Связаться со специалистом
• 📂 Каталог - посмотрите нашу технику
• 📢 Наш канал - акции, новости, поставки
"""
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode='HTML'
    )

def is_forwarded_post(message: Message) -> bool:
    """Проверяет, является ли сообщение пересланным постом"""
    return (message.forward_from_chat is not None or 
            message.forward_from is not None or
            message.forward_sender_name is not None)
async def end_session_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.answer("Вы не являетесь администратором")
        return
    
    session_id = int(query.data.split('_')[2])
    end_session(session_id)
    
    await query.edit_message_text(
        "Сессия успешно завершена",
        reply_markup=get_admin_main_keyboard()
    )
    
    # Отправляем уведомление пользователю
    session = get_active_session_by_user(session_id)
    if session:
        await context.bot.send_message(
            chat_id=session['user_id'],
            text="Сессия со специалистом завершена. Если у вас остались вопросы, создайте новый запрос."
        )
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'contact_specialist':
        user = query.from_user
        
        if get_active_session_by_user(user.id):
            await query.edit_message_text(
                "Вы уже находитесь в сессии со специалистом. Пожалуйста, дождитесь ответа.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        if get_user_active_request(user.id):
            await query.edit_message_text(
                "У вас уже есть активный запрос. Дождитесь ответа специалиста.",
                reply_markup=get_main_menu_keyboard()
            )
            return
        
        request_id = add_user_request(
            user_id=user.id,
            user_name=user.full_name,
            username=user.username,
            request_text="Запрос на связь со специалистом"
        )
        
        await query.edit_message_text(
            "Отправьте ваш запрос в сообщении или перешлите пост из Telegram. Все сообщения будут сохранены и переданы специалисту.",
            reply_markup=get_main_menu_keyboard()
        )
        
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📩 Новый запрос на связь (#{request_id}) от {user.full_name} (@{user.username or 'нет'})",
            reply_markup=get_admin_request_keyboard(request_id)
        )
    
    elif query.data.startswith('accept_request_'):
        if query.from_user.id != ADMIN_ID:
            await query.answer("Вы не являетесь администратором")
            return
        
        if get_active_admin_session():
            await query.answer("У вас уже есть активная сессия. Завершите её перед принятием нового запроса.")
            return
        
        request_id = int(query.data.split('_')[2])
        
        if start_request_processing(request_id):
            with get_db_connection() as conn:
                cursor = conn.execute(
                    "SELECT user_id, user_name, username FROM user_requests WHERE request_id = ?",
                    (request_id,)
                )
                request = cursor.fetchone()
            
            if request:
                session_id = create_session(request_id, request['user_id'])
                messages = get_messages_for_request(request_id)
                
                media_group = []
                for msg in messages:
                    if msg['media_type'] == 'photo':
                        media_group.append(InputMediaPhoto(
                            media=msg['media_id'],
                            caption=f"👤 {request['user_name']} (@{request['username'] or 'нет'}):\n{msg['message_text']}" if msg['message_text'] else None
                        ))
                    elif msg['media_type'] == 'video':
                        media_group.append(InputMediaVideo(
                            media=msg['media_id'],
                            caption=f"👤 {request['user_name']} (@{request['username'] or 'нет'}):\n{msg['message_text']}" if msg['message_text'] else None
                        ))
                    elif msg['media_type'] == 'document':
                        media_group.append(InputMediaDocument(
                            media=msg['media_id'],
                            caption=f"👤 {request['user_name']} (@{request['username'] or 'нет'}):\n{msg['message_text']}" if msg['message_text'] else None
                        ))
                    elif msg['message_text']:
                        await context.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=f"👤 {request['user_name']} (@{request['username'] or 'нет'}):\n{msg['message_text']}",
                            reply_markup=get_admin_session_keyboard(session_id)
                        )
                
                if media_group:
                    await context.bot.send_media_group(
                        chat_id=ADMIN_ID,
                        media=media_group
                    )
                
                await query.edit_message_text(
                    f"✅ Вы приняли запрос #{request_id}\n"
                    f"Пользователь: {request['user_name']} (@{request['username'] or 'нет'})\n"
                    f"Теперь вы можете общаться с пользователем.",
                    reply_markup=get_admin_session_keyboard(session_id)
                )
                
                await context.bot.send_message(
                    chat_id=request['user_id'],
                    text="👨‍💼 Специалист готов вам помочь. Пожалуйста, опишите ваш вопрос."
                )
    
    elif query.data.startswith('reject_request_'):
        if query.from_user.id != ADMIN_ID:
            await query.answer("Вы не являетесь администратором")
            return
        
        request_id = int(query.data.split('_')[2])
        
        with get_db_connection() as conn:
            conn.execute(
                "DELETE FROM user_requests WHERE request_id = ?",
                (request_id,)
            )
            conn.commit()
        
        await query.edit_message_text(f"❌ Запрос #{request_id} отклонен")
    
    elif query.data == 'show_all_requests':
        if query.from_user.id != ADMIN_ID:
            await query.answer("Вы не являетесь администратором")
            return
            
        pending_requests = get_pending_requests()
        if pending_requests:
            text = "📋 Ожидающие запросы:\n"
            for req in pending_requests:
                text += f"\n#{req['request_id']} от {req['user_name']} (@{req['username'] or 'нет'})"
            
            await query.edit_message_text(
                text,
                reply_markup=get_admin_main_keyboard()
            )
        else:
            await query.edit_message_text(
                "В настоящее время нет ожидающих запросов.",
                reply_markup=get_admin_main_keyboard()
            )
    
    elif query.data == 'end_all_sessions':
        if query.from_user.id != ADMIN_ID:
            await query.answer("Вы не являетесь администратором")
            return
            
        with get_db_connection() as conn:
            conn.execute("DELETE FROM active_sessions")
            conn.execute("UPDATE user_requests SET status = 'pending' WHERE status = 'in_progress'")
            conn.commit()
            
        await query.edit_message_text(
            "✅ Все активные сессии завершены, запросы возвращены в очередь.",
            reply_markup=get_admin_main_keyboard()
        )
    
    elif query.data == 'clear_all_requests':
        if query.from_user.id != ADMIN_ID:
            await query.answer("Вы не являетесь администратором")
            return
            
        with get_db_connection() as conn:
            conn.execute("DELETE FROM user_requests")
            conn.execute("DELETE FROM active_sessions")
            conn.execute("DELETE FROM session_messages")
            conn.commit()
            
        await query.edit_message_text(
            "✅ Все запросы, сессии и сообщения очищены.",
            reply_markup=get_admin_main_keyboard()
        )


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message
    
    if session := get_active_session_by_user(user.id):
        await forward_message_to_admin(update, context, session)
        return

    if not (request := get_user_active_request(user.id)):
        await message.reply_text(
            "Пожалуйста, используйте кнопки меню для взаимодействия с ботом.",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Обработка медиагрупп (включая одиночные медиа)
    if message.photo or message.video or message.document:
        media_group_id = message.media_group_id or f"single_{message.message_id}"
        
        if media_group_id not in user_media_groups:
            user_media_groups[media_group_id] = MediaGroup(
                request['request_id'], 
                user.id, 
                user.full_name, 
                user.username
            )
        
        user_media_groups[media_group_id].add_message(message)
    
        return
    
    # Обработка текстовых сообщений
    if message.text:
        add_message_to_request(
            request['request_id'], 
            user.id, 
            message_text=message.text
        )
        await message.reply_text(
            "Ваш запрос сохранён. Специалист свяжется с вами в рабочее время.",
            reply_markup=get_main_menu_keyboard()
        )

async def forward_message_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Dict):
    user = update.effective_user
    message = update.effective_message
    
    # Обработка медиагрупп (включая одиночные медиа)
    if message.photo or message.video or message.document:
        media_group_id = message.media_group_id or f"single_{message.message_id}"
        
        if media_group_id not in user_media_groups:
            user_media_groups[media_group_id] = MediaGroup(
                session['request_id'],
                user.id,
                user.full_name,
                user.username,
                session_id=session['session_id']
            )
        
        user_media_groups[media_group_id].add_message(message)
        return
    
    # Обработка текстовых сообщений
    if message.text:
        add_session_message(
            session['session_id'],
            user.id,
            message_text=message.text
        )
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"👤 {user.full_name}:\n{message.text}",
            reply_markup=get_admin_session_keyboard(session['session_id'])
        )

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    message = update.effective_message
    session = get_active_admin_session()
    
    if not session:
        await message.reply_text(
            "Панель администратора",
            reply_markup=get_admin_main_keyboard()
        )
        return
    
    user_id = session['user_id']
    
    # Обработка медиагрупп (включая одиночные медиа)
    if message.photo or message.video or message.document:
        media_group_id = message.media_group_id or f"single_{message.message_id}"
        
        if media_group_id not in user_media_groups:
            user_media_groups[media_group_id] = MediaGroup(
                session['request_id'],
                ADMIN_ID,
                "Специалист",
                None,
                session_id=session['session_id']
            )
        
        user_media_groups[media_group_id].add_message(message)
        return
    
    # Обработка текстовых сообщений
    if message.text:
        add_session_message(
            session['session_id'],
            ADMIN_ID,
            message_text=message.text
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=f"{message.text}"
        )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /admin для панели управления администратора"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Доступ запрещен")
        return
        
    await update.message.reply_text(
        "Панель администратора",
        reply_markup=get_admin_main_keyboard()  # Кнопки из keyboards.py
    )
async def check_media_groups(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    
    for media_group_id, group in list(user_media_groups.items()):
        if group.is_expired():
            try:
                media = []
                for i, msg in enumerate(sorted(group.messages, key=lambda m: m.message_id)):
                    caption = group.caption if i == 0 else None
                    
                    if msg.photo:
                        media.append(InputMediaPhoto(
                            media=msg.photo[-1].file_id,
                            caption=caption
                        ))
                    elif msg.video:
                        media.append(InputMediaVideo(
                            media=msg.video.file_id,
                            caption=caption
                        ))
                    elif msg.document:
                        media.append(InputMediaDocument(
                            media=msg.document.file_id,
                            caption=caption
                        ))
                
                if media:
                    if group.session_id:
                        # Получаем информацию о сессии из базы данных
                        with get_db_connection() as conn:
                            cursor = conn.execute(
                                """SELECT s.session_id, s.request_id, r.user_id, r.user_name, r.username 
                                   FROM active_sessions s
                                   JOIN user_requests r ON s.request_id = r.request_id
                                   WHERE s.session_id = ?""",
                                (group.session_id,)
                            )
                            session_info = cursor.fetchone()
                        
                        if session_info:
                            session_info = dict(session_info)
                            # Определяем направление отправки
                            if group.user_id == ADMIN_ID:
                                # Медиа от администратора - отправляем пользователю
                                target_chat_id = session_info['user_id']
                                sender_name = "Специалист"
                            else:
                                # Медиа от пользователя - отправляем администратору
                                target_chat_id = ADMIN_ID
                                sender_name = f"{group.user_name} (@{group.username or 'нет'})"
                            
                            # Отправка медиа
                            await context.bot.send_media_group(
                                chat_id=target_chat_id,
                                media=media
                            )
                            
                            # Сохранение в базу данных
                            for msg in group.messages:
                                if msg.photo:
                                    add_session_message(
                                        group.session_id,
                                        group.user_id,
                                        media_type='photo',
                                        media_id=msg.photo[-1].file_id,
                                        message_text=group.caption if msg == group.messages[0] else None
                                    )
                                elif msg.video:
                                    add_session_message(
                                        group.session_id,
                                        group.user_id,
                                        media_type='video',
                                        media_id=msg.video.file_id,
                                        message_text=group.caption if msg == group.messages[0] else None
                                    )
                                elif msg.document:
                                    add_session_message(
                                        group.session_id,group.user_id,
                                        media_type='document',
                                        media_id=msg.document.file_id,
                                        message_text=group.caption if msg == group.messages[0] else None
                                    )
                    else:
                        # Отправка нового запроса (только от пользователя к администратору)
                        await context.bot.send_media_group(
                            chat_id=ADMIN_ID,
                            media=media
                        )
                        
                        for msg in group.messages:
                            if msg.photo:
                                add_message_to_request(
                                    group.request_id,
                                    group.user_id,
                                    media_type='photo',
                                    media_id=msg.photo[-1].file_id,
                                    message_text=group.caption if msg == group.messages[0] else None
                                )
                            elif msg.video:
                                add_message_to_request(
                                    group.request_id,
                                    group.user_id,
                                    media_type='video',
                                    media_id=msg.video.file_id,
                                    message_text=group.caption if msg == group.messages[0] else None
                                )
                            elif msg.document:
                                add_message_to_request(
                                    group.request_id,
                                    group.user_id,
                                    media_type='document',
                                    media_id=msg.document.file_id,
                                    message_text=group.caption if msg == group.messages[0] else None
                                )
                
                del user_media_groups[media_group_id]
            except Exception as e:
                logger.error(f"Ошибка обработки медиагруппы: {e}")