import sqlite3
from contextlib import contextmanager
from typing import Dict, List, Optional
from datetime import datetime

import os
DB_FILE = os.path.join(os.path.dirname(__file__), "bot_database.db")

@contextmanager
def get_db_connection():
    """Контекстный менеджер для работы с базой данных"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Инициализация структуры базы данных"""
    with get_db_connection() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_requests (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            username TEXT,
            request_text TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS active_sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (request_id) REFERENCES user_requests(request_id)
        )""")
        
        conn.execute("""
        CREATE TABLE IF NOT EXISTS session_messages (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            request_id INTEGER,
            sender_id INTEGER NOT NULL,
            message_text TEXT,
            media_type TEXT,  -- 'photo', 'video', 'document', 'forward'
            media_id TEXT,
            message_link TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES active_sessions(session_id),
            FOREIGN KEY (request_id) REFERENCES user_requests(request_id)
        )""")
        conn.commit()

def add_user_request(user_id: int, user_name: str, username: str, request_text: str) -> int:
    """Добавляет новый запрос пользователя"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_requests (user_id, user_name, username, request_text) VALUES (?, ?, ?, ?)",
            (user_id, user_name, username, request_text)
        )
        conn.commit()
        return cursor.lastrowid

def get_pending_requests() -> List[Dict]:
    """Возвращает список ожидающих запросов"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM user_requests WHERE status = 'pending' ORDER BY created_at ASC"
        )
        return [dict(row) for row in cursor.fetchall()]

def get_user_active_request(user_id: int) -> Optional[Dict]:
    """Возвращает активный запрос пользователя"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM user_requests WHERE user_id = ? AND status = 'pending' LIMIT 1",
            (user_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

def start_request_processing(request_id: int) -> bool:
    """Начинает обработку запроса"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE user_requests SET status = 'in_progress' WHERE request_id = ? AND status = 'pending'",
            (request_id,)
        )
        conn.commit()
        return cursor.rowcount > 0

def create_session(request_id: int, user_id: int) -> int:
    """Создает новую сессию для запроса"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO active_sessions (request_id, user_id) VALUES (?, ?)",
            (request_id, user_id)
        )
        conn.commit()
        return cursor.lastrowid

def end_session(session_id: int):
    """Завершает сессию и помечает запрос как выполненный"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT request_id FROM active_sessions WHERE session_id = ?",
            (session_id,)
        )
        request_id = cursor.fetchone()['request_id']
        
        conn.execute(
            "UPDATE user_requests SET status = 'completed' WHERE request_id = ?",
            (request_id,)
        )
        
        conn.execute(
            "DELETE FROM active_sessions WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()

def get_active_session_by_user(user_id: int) -> Optional[Dict]:
    """Возвращает активную сессию пользователя"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """SELECT s.session_id, s.request_id, r.user_id, r.user_name, r.username 
               FROM active_sessions s
               JOIN user_requests r ON s.request_id = r.request_id
               WHERE r.user_id = ?""",
            (user_id,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None

def get_active_admin_session() -> Optional[Dict]:
    """Возвращает активную сессию администратора"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            """SELECT s.session_id, s.request_id, r.user_id, r.user_name, r.username 
               FROM active_sessions s
               JOIN user_requests r ON s.request_id = r.request_id
               LIMIT 1"""
        )
        row = cursor.fetchone()
        return dict(row) if row else None

def add_message_to_request(request_id: int, sender_id: int, message_text: str = None, 
                         media_type: str = None, media_id: str = None):
    """Добавляет сообщение к запросу (до начала сессии)"""
    with get_db_connection() as conn:
        conn.execute(
            """INSERT INTO session_messages 
               (request_id, sender_id, message_text, media_type, media_id) 
               VALUES (?, ?, ?, ?, ?)""",
            (request_id, sender_id, message_text, media_type, media_id)
        )
        conn.commit()

def add_session_message(session_id: int, sender_id: int, message_text: str = None, 
                       media_type: str = None, media_id: str = None):
    """Добавляет сообщение в активную сессию"""
    with get_db_connection() as conn:
        # Получаем request_id из сессии
        cursor = conn.execute(
            "SELECT request_id FROM active_sessions WHERE session_id = ?",
            (session_id,)
        )
        request_id = cursor.fetchone()['request_id']
        
        conn.execute(
            """INSERT INTO session_messages 
               (session_id, request_id, sender_id, message_text, media_type, media_id) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, request_id, sender_id, message_text, media_type, media_id)
        )
        conn.commit()

def get_messages_for_request(request_id: int) -> List[Dict]:
    """Возвращает все сообщения для запроса"""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM session_messages WHERE request_id = ? ORDER BY sent_at ASC",
            (request_id,)
        )
        return [dict(row) for row in cursor.fetchall()]