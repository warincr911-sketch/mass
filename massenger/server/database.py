#!/usr/bin/env python3
"""
DatabaseManager — Управление базой данных мессенджера
Использует SQLite для хранения пользователей, сообщений и контактов
"""

import sqlite3
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from datetime import datetime

from server.config import Config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер базы данных SQLite"""

    def __init__(self, db_path: Path = None):
        """Инициализация подключения к БД"""
        self.db_path = db_path or Config.DB_PATH
        self._init_database()
        logger.info(f"✅ DatabaseManager инициализирован: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Получение соединения с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Доступ к полям по имени
        return conn

    def _init_database(self) -> None:
        """Создание таблиц при первом запуске"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT,
                password_hash TEXT NOT NULL,
                public_key TEXT NOT NULL,
                is_online BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Таблица сообщений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                encrypted_data TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_read BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (sender_id) REFERENCES users(id),
                FOREIGN KEY (recipient_id) REFERENCES users(id)
            )
        ''')

        # Таблица контактов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                contact_username TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, contact_username)
            )
        ''')

        # Таблица файлов
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                recipient_id INTEGER NOT NULL,
                encrypted_key TEXT,
                iv TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sender_id) REFERENCES users(id),
                FOREIGN KEY (recipient_id) REFERENCES users(id)
            )
        ''')

        # Индексы для ускорения поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')

        conn.commit()
        conn.close()
        logger.info("✅ База данных инициализирована")

    # ==================== Пользователи ====================

    def create_user(self, username: str, email: str, password_hash: str, public_key: str) -> bool:
        """Создание нового пользователя"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, public_key)
                VALUES (?, ?, ?, ?)
            ''', (username, email, password_hash, public_key))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
        except Exception as e:
            logger.error(f"Ошибка создания пользователя: {e}", exc_info=True)
            return False

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Получение пользователя по имени"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {e}", exc_info=True)
            return None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по ID"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {e}", exc_info=True)
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Аутентификация пользователя"""
        from server.crypto import CryptoManager
        crypto = CryptoManager()

        user = self.get_user_by_username(username)
        if not user:
            return None

        if crypto.verify_password(password, user['password_hash']):
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE id = ?
            ''', (user['id'],))
            conn.commit()
            conn.close()
            return user
        return None

    def update_user_status(self, user_id: int, is_online: bool) -> bool:
        """Обновление статуса онлайн/офлайн"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET is_online = ?, last_seen = CURRENT_TIMESTAMP WHERE id = ?
            ''', (is_online, user_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}", exc_info=True)
            return False

    def get_user_public_key(self, username: str) -> Optional[str]:
        """Получение публичного ключа пользователя"""
        user = self.get_user_by_username(username)
        return user['public_key'] if user else None

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Получение всех пользователей"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id, username, is_online, last_seen FROM users')
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения списка пользователей: {e}", exc_info=True)
            return []

    def search_users(self, query: str, exclude_user_id: int = None) -> List[Dict[str, Any]]:
        """Поиск пользователей по имени"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            if exclude_user_id:
                cursor.execute('''
                    SELECT id, username, is_online, last_seen 
                    FROM users 
                    WHERE username LIKE ? AND id != ?
                    LIMIT 20
                ''', (f'%{query}%', exclude_user_id))
            else:
                cursor.execute('''
                    SELECT id, username, is_online, last_seen 
                    FROM users 
                    WHERE username LIKE ?
                    LIMIT 20
                ''', (f'%{query}%',))

            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка поиска пользователей: {e}", exc_info=True)
            return []

    # ==================== Сообщения ====================

    def save_message(self, sender_id: int, recipient_id: int, encrypted_data: str, timestamp: str = None) -> Optional[
        int]:
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (sender_id, recipient_id, encrypted_data, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (sender_id, recipient_id, encrypted_data, timestamp or datetime.now().isoformat()))
            conn.commit()
            message_id = cursor.lastrowid
            conn.close()
            return message_id
        except Exception as e:
            logger.error(f"Ошибка сохранения сообщения: {e}", exc_info=True)
            return None
    def get_messages_between_users(self, user1_id: int, user2_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получение истории сообщений + файлы
        ✅ ВАЖНО: файлы помечаются is_file=True
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            all_items = []

            # 1️⃣ Текстовые сообщения
            cursor.execute('''
                SELECT m.id, m.sender_id, m.recipient_id, m.encrypted_data as text, 
                       m.timestamp, u1.username as sender, u2.username as recipient
                FROM messages m
                JOIN users u1 ON m.sender_id = u1.id
                JOIN users u2 ON m.recipient_id = u2.id
                WHERE (m.sender_id = ? AND m.recipient_id = ?) 
                   OR (m.sender_id = ? AND m.recipient_id = ?)
                ORDER BY m.timestamp ASC
                LIMIT ?
            ''', (user1_id, user2_id, user2_id, user1_id, limit))

            for row in cursor.fetchall():
                item = dict(row)
                item['is_file'] = False
                item['is_encrypted'] = True
                item['is_own'] = item['sender_id'] == user1_id
                all_items.append(item)

            # 2️⃣ ФАЙЛЫ
            cursor.execute('''
                SELECT f.id, f.filename, f.file_path, f.file_size, 
                       f.sender_id, f.recipient_id, f.timestamp, f.encrypted_key, f.iv,
                       u1.username as sender, u2.username as recipient
                FROM files f
                JOIN users u1 ON f.sender_id = u1.id
                JOIN users u2 ON f.recipient_id = u2.id
                WHERE (f.sender_id = ? AND f.recipient_id = ?) 
                   OR (f.sender_id = ? AND f.recipient_id = ?)
                ORDER BY f.timestamp ASC
            ''', (user1_id, user2_id, user2_id, user1_id))

            for row in cursor.fetchall():
                item = dict(row)
                item['is_file'] = True
                item['is_own'] = item['sender_id'] == user1_id
                logger.info(f"📁 Файл добавлен в историю: {item['filename']} (ID: {item['id']})")
                all_items.append(item)

            # Сортировка по времени
            all_items.sort(key=lambda x: x.get('timestamp', ''))

            conn.close()
            logger.info(f"📋 Получено {len(all_items)} элементов истории")
            return all_items

        except Exception as e:
            logger.error(f"Ошибка получения истории: {e}", exc_info=True)
            return []

    # ==================== Контакты ====================

    def add_contact(self, user_id: int, contact_username: str) -> bool:
        """Добавление контакта"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO contacts (user_id, contact_username)
                VALUES (?, ?)
            ''', (user_id, contact_username))
            conn.commit()
            conn.close()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка добавления контакта: {e}", exc_info=True)
            return False

    def remove_contact(self, user_id: int, contact_username: str) -> bool:
        """Удаление контакта"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM contacts WHERE user_id = ? AND contact_username = ?
            ''', (user_id, contact_username))
            conn.commit()
            conn.close()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка удаления контакта: {e}", exc_info=True)
            return False

    def get_contacts(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение списка контактов пользователя"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.contact_username as username, u.is_online, u.last_seen
                FROM contacts c
                LEFT JOIN users u ON c.contact_username = u.username
                WHERE c.user_id = ?
            ''', (user_id,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения контактов: {e}", exc_info=True)
            return []

    def get_contacts_by_username(self, username: str) -> List[Dict[str, Any]]:
        """Получение пользователей, у которых данный пользователь в контактах"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.username, u.is_online
                FROM contacts c
                JOIN users u ON c.user_id = u.id
                WHERE c.contact_username = ?
            ''', (username,))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения контактов по имени: {e}", exc_info=True)
            return []

    # ==================== Файлы ====================

    def save_file(self, filename: str, file_path: str, file_size: int,
                  sender_id: int, recipient_id: int,
                  encrypted_key: str = None, iv: str = None) -> int:
        """
        Сохранение метаданных файла в БД
        Returns: ID сохранённого файла
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO files (filename, file_path, file_size, sender_id, recipient_id, encrypted_key, iv)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (filename, file_path, file_size, sender_id, recipient_id, encrypted_key, iv))
            conn.commit()
            file_id = cursor.lastrowid
            conn.close()
            logger.info(f"💾 Файл сохранён в БД с ID: {file_id}")
            return file_id
        except Exception as e:
            logger.error(f"Ошибка сохранения файла: {e}", exc_info=True)
            return -1

    def get_file_by_id(self, file_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получение файла по ID — файл НЕ удаляется после скачивания
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM files 
                WHERE id = ? AND (sender_id = ? OR recipient_id = ?)
            ''', (file_id, user_id, user_id))
            row = cursor.fetchone()
            conn.close()

            if row:
                logger.info(f"📁 Файл найден: {row['filename']} (ID: {file_id})")
                return dict(row)
            logger.warning(f"⚠️ Файл не найден: {file_id}")
            return None
        except Exception as e:
            logger.error(f"Ошибка получения файла: {e}", exc_info=True)
            return None

    def get_user_files(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение файлов пользователя"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT f.*, u1.username as sender, u2.username as recipient
                FROM files f
                JOIN users u1 ON f.sender_id = u1.id
                JOIN users u2 ON f.recipient_id = u2.id
                WHERE f.sender_id = ? OR f.recipient_id = ?
                ORDER BY f.timestamp DESC
                LIMIT ?
            ''', (user_id, user_id, limit))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения файлов: {e}", exc_info=True)
            return []