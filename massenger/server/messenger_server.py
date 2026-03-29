#!/usr/bin/env python3
"""
Messenger Server — Асинхронный сервер для Secure Messenger
Исправленная версия: приоритетные исправления
"""

import asyncio
import websockets
import json

import sys
import os
import base64
import uuid
import signal
import re

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('messenger_server')

from datetime import datetime, timezone
from typing import Dict, Optional, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from massenger.server.database import DatabaseManager
from massenger.server.crypto import CryptoManager
from massenger.server.config import Config


# ============================================================================
# 🔧 КОНСТАНТЫ
# ============================================================================
class ServerConstants:
    """Константы сервера"""
    # Валидация
    USERNAME_PATTERN = r'^[a-zA-Z0-9_]{3,30}$'
    EMAIL_PATTERN = r'^[^@]+@[^@]+\.[^@]+$'
    MIN_PASSWORD_LENGTH = 8
    MIN_PUBLIC_KEY_LENGTH = 400  # RSA-2048 PEM ~450 символов

    # Файлы
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.rar', '.7z'}

    # Rate limiting
    RATE_LIMIT_REQUESTS = 100
    RATE_LIMIT_WINDOW = 60  # секунд

    # Логирование
    LOG_FILE = 'messenger_server.log'
    LOG_LEVEL = logging.INFO
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT = 5


# ============================================================================
# 🔧 НАСТРОЙКА ЛОГИРОВАНИЯ С РОТАЦИЕЙ
# ============================================================================
def _sanitize_for_log(data: Dict[str, Any]) -> Dict[str, Any]:
    """Удаляет чувствительные данные перед логированием"""
    sensitive = {'password', 'private_key'}
    result = {}
    for k, v in data.items():
        if k in sensitive:
            result[k] = '***REDACTED***'
        elif isinstance(v, dict):
            result[k] = _sanitize_for_log(v)
        else:
            result[k] = v
    return result


def setup_logging():
    """Настройка логирования с ротацией"""
    from logging.handlers import RotatingFileHandler

    logger = logging.getLogger('messenger_server')
    logger.setLevel(ServerConstants.LOG_LEVEL)

    if logger.handlers:
        logger.handlers.clear()

    log_format = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Ротируемый файл
    file_handler = RotatingFileHandler(
        ServerConstants.LOG_FILE,
        maxBytes=ServerConstants.LOG_MAX_BYTES,
        backupCount=ServerConstants.LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)

    # Консоль
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()

# ============================================================================
# 📦 ИМПОРТ ОПЦИОНАЛЬНЫХ ЗАВИСИМОСТЕЙ
# ============================================================================
# ✅ ИСПРАВЛЕНИЕ #1: aiofiles импортируется в топ файла
try:
    import aiofiles

    AIOFILES_AVAILABLE = True
    logger.info("✅ aiofiles доступен — асинхронная работа с файлами")
except ImportError:
    AIOFILES_AVAILABLE = False
    logger.warning("⚠️ aiofiles не установлен — файлы будут работать синхронно")
    logger.warning("   Установите: pip install aiofiles")

# ============================================================================
# 🔄 RATE LIMITER (простая реализация)
# ============================================================================
from collections import defaultdict, deque
import time


class RateLimiter:
    """Простой ограничитель запросов по IP"""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests: Dict[str, deque] = defaultdict(deque)

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        # Очистка старых запросов
        while self.requests[client_id] and self.requests[client_id][0] < now - self.window:
            self.requests[client_id].popleft()

        if len(self.requests[client_id]) >= self.max_requests:
            return False

        self.requests[client_id].append(now)
        return True

    def cleanup(self):
        """Очистка старых записей (вызывать периодически)"""
        now = time.time()
        for client_id in list(self.requests.keys()):
            while self.requests[client_id] and self.requests[client_id][0] < now - self.window:
                self.requests[client_id].popleft()
            if not self.requests[client_id]:
                del self.requests[client_id]


# ============================================================================
# 🏗️ КЛАСС MESSENGERSERVER
# ============================================================================
class MessengerServer:
    """Сервер мессенджера с исправлениями"""

    def __init__(self):
        """Инициализация сервера"""
        self.db = DatabaseManager()
        self.crypto = CryptoManager()
        self.clients: Dict[str, websockets.WebSocketServerProtocol] = {}

        # ✅ Rate limiter
        self.rate_limiter = RateLimiter(
            max_requests=ServerConstants.RATE_LIMIT_REQUESTS,
            window_seconds=ServerConstants.RATE_LIMIT_WINDOW
        )

        # ✅ Thread pool для блокирующих операций БД
        self._db_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='DBWorker')

        logger.info("✅ Сервер инициализирован")

    # ========================================================================
    # 🔐 ВАЛИДАЦИЯ
    # ========================================================================
    @staticmethod
    def _validate_username(username: str) -> bool:
        return bool(username and re.match(ServerConstants.USERNAME_PATTERN, username))

    @staticmethod
    def _validate_email(email: str) -> bool:
        return bool(email and re.match(ServerConstants.EMAIL_PATTERN, email))

    @staticmethod
    def _validate_password(password: str) -> bool:
        return bool(password and len(password) >= ServerConstants.MIN_PASSWORD_LENGTH)

    # ✅ ИСПРАВЛЕНИЕ #3: Валидация публичного ключа
    @staticmethod
    def _validate_public_key(key: str) -> bool:
        """Проверка формата публичного ключа (PEM)"""
        if not key or not isinstance(key, str):
            return False
        return (
                "-----BEGIN PUBLIC KEY-----" in key and
                "-----END PUBLIC KEY-----" in key and
                len(key) >= ServerConstants.MIN_PUBLIC_KEY_LENGTH
        )

    # ========================================================================
    # 📤 ОТВЕТЫ КЛИЕНТУ
    # ========================================================================
    async def _send_error(self, websocket: websockets.WebSocketServerProtocol,
                          error_message: str, request_id: Optional[str] = None) -> None:
        """Отправка ошибки клиенту"""
        response = {
            'type': 'error',
            'message': error_message
        }
        await self._send_response(websocket, response, request_id)
        logger.error(f"❌ Ошибка отправлена клиенту: {error_message}")

    async def _send_response(self, websocket: websockets.WebSocketServerProtocol,
                             response: dict, request_id: Optional[str] = None) -> None:
        """Отправка ответа клиенту"""
        if request_id:
            response['request_id'] = request_id

        try:
            if websocket and hasattr(websocket, 'send'):
                # ✅ Санитизация перед логированием
                logger.debug(f"📤 Ответ: {response.get('type')} | {_sanitize_for_log(response)}")
                await websocket.send(json.dumps(response))
            else:
                logger.error(f"❌ Неверный websocket объект: {type(websocket)}")
        except websockets.exceptions.ConnectionClosed:
            logger.warning("⚠️ Клиент отключился во время отправки ответа")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки ответа: {e}", exc_info=True)

    # ========================================================================
    # 🔄 ОБРАБОТКА КЛИЕНТОВ
    # ========================================================================
    async def handle_client(self, websocket: websockets.WebSocketServerProtocol) -> None:
        """Обработка подключений клиентов"""
        authenticated_username = None
        client_id = websocket.remote_address[0] if websocket.remote_address else 'unknown'

        try:
            async for message in websocket:
                # ✅ Rate limiting
                if not self.rate_limiter.is_allowed(client_id):
                    await self._send_error(websocket, 'Слишком много запросов')
                    await asyncio.sleep(1)  # Небольшая задержка
                    continue

                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    request_id = data.get('request_id')

                    # ✅ Санитизированное логирование
                    logger.debug(f"📥 Запрос: {msg_type} | {_sanitize_for_log(data)}")

                    if msg_type == 'register':
                        authenticated_username = await self.handle_register(websocket, data, request_id)
                    elif msg_type == 'login':
                        authenticated_username = await self.handle_login(websocket, data, request_id)
                    elif msg_type == 'get_messages':
                        await self.handle_get_messages(websocket, data, request_id)
                    elif msg_type == 'message':
                        await self.handle_message(websocket, data, authenticated_username, request_id)
                    elif msg_type == 'file':
                        await self.handle_file(websocket, data, authenticated_username, request_id)
                    elif msg_type == 'get_file':
                        await self.handle_get_file(websocket, data, request_id)
                    elif msg_type == 'get_contacts':
                        await self.handle_get_contacts(websocket, data, authenticated_username, request_id)
                    elif msg_type == 'search_users':
                        await self.handle_search_users(websocket, data, authenticated_username, request_id)
                    elif msg_type == 'add_contact':
                        await self.handle_add_contact(websocket, data, authenticated_username, request_id)
                    elif msg_type == 'remove_contact':
                        await self.handle_remove_contact(websocket, data, authenticated_username, request_id)
                    elif msg_type == 'get_public_key':
                        await self.handle_get_public_key(websocket, data, request_id)
                    else:
                        logger.warning(f"⚠️ Неизвестный тип запроса: {msg_type}")
                        await self._send_error(websocket, 'Неизвестный тип запроса', request_id)

                except json.JSONDecodeError as e:
                    logger.error(f"❌ Ошибка парсинга JSON: {e}")
                    await self._send_error(websocket, 'Неверный формат запроса')

        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"🔌 Клиент отключился: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_client: {e}", exc_info=True)
        finally:
            # ✅ ИСПРАВЛЕНИЕ #9: Корректная очистка по websocket
            for username, ws in list(self.clients.items()):
                if ws == websocket:
                    self.clients.pop(username)
                    logger.info(f"👋 Пользователь {username} вышел из системы")
                    # Уведомляем контакты об оффлайне (неблокирующе)
                    asyncio.create_task(self._notify_contacts_status(username, False))
                    break

    # ========================================================================
    # 👤 РЕГИСТРАЦИЯ И ВХОД
    # ========================================================================
    async def handle_register(self, websocket: websockets.WebSocketServerProtocol,
                              data: dict, request_id: Optional[str] = None) -> Optional[str]:
        """Регистрация пользователя"""
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        public_key = data.get('public_key')

        # Валидация входных данных
        if not self._validate_username(username):
            await self._send_error(websocket, 'Неверный формат имени пользователя', request_id)
            return None
        if not self._validate_password(password):
            await self._send_error(websocket, 'Пароль должен содержать минимум 8 символов', request_id)
            return None
        if email and not self._validate_email(email):
            await self._send_error(websocket, 'Неверный формат email', request_id)
            return None

        # ✅ ИСПРАВЛЕНИЕ #3: Валидация публичного ключа
        if public_key and not self._validate_public_key(public_key):
            logger.warning(f"⚠️ Неверный формат ключа при регистрации: {username}")
            await self._send_error(websocket, 'Неверный формат публичного ключа', request_id)
            return None

        try:
            # ✅ ИСПРАВЛЕНИЕ #2: БД в executor
            loop = asyncio.get_event_loop()
            password_hash = await loop.run_in_executor(
                self._db_executor,
                self.crypto.hash_password,
                password
            )

            success = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.create_user(username, email, password_hash, public_key)
            )

            if success:
                logger.info(f"✅ Пользователь {username} успешно зарегистрирован")
                await self._send_response(websocket, {
                    'type': 'register_response',
                    'success': True,
                    'username': username
                }, request_id)
                return username
            else:
                await self._send_error(websocket, 'Пользователь уже существует', request_id)
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации: {e}", exc_info=True)
            await self._send_error(websocket, 'Ошибка регистрации', request_id)
            return None

    async def handle_login(self, websocket: websockets.WebSocketServerProtocol,
                           data: dict, request_id: Optional[str] = None) -> Optional[str]:
        """Вход пользователя"""
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            await self._send_error(websocket, 'Имя и пароль обязательны', request_id)
            return None

        try:
            # ✅ ИСПРАВЛЕНИЕ #2: БД в executor
            loop = asyncio.get_event_loop()
            user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.authenticate_user(username, password)
            )

            if user:
                self.clients[username] = websocket
                logger.info(f"✅ Пользователь {username} успешно вошёл в систему")

                # Уведомляем контакты об онлайне
                asyncio.create_task(self._notify_contacts_status(username, True))

                await self._send_response(websocket, {
                    'type': 'login_response',
                    'success': True,
                    'user_id': user['id'],
                    'username': username,
                    'public_key': user.get('public_key')
                }, request_id)
                return username
            else:
                await self._send_error(websocket, 'Неверное имя или пароль', request_id)
                return None
        except Exception as e:
            logger.error(f"❌ Ошибка входа: {e}", exc_info=True)
            await self._send_error(websocket, 'Ошибка входа', request_id)
            return None

    # ========================================================================
    # 📬 СООБЩЕНИЯ
    # ========================================================================
    async def handle_message(self, websocket: websockets.WebSocketServerProtocol,
                             data: dict,
                             authenticated_username: Optional[str],
                             request_id: Optional[str] = None) -> None:
        """Отправка сообщения — ПОЛНОСТЬЮ ИСПРАВЛЕННАЯ ВЕРСИЯ"""


        logger.debug(f"📥 handle_message: from={authenticated_username}, to={data.get('recipient')}")

        if not authenticated_username:
            await self._send_error(websocket, 'Требуется авторизация', request_id)
            return

        recipient = data.get('recipient')
        encrypted_data = data.get('encrypted_data')

        if not recipient or not encrypted_data:
            logger.warning(
                f"⚠️ Неверные параметры: recipient={recipient}, encrypted_data={'present' if encrypted_data else 'missing'}")
            await self._send_error(websocket, 'Отсутствуют параметры', request_id)
            return

        try:
            loop = asyncio.get_event_loop()

            # Получение пользователей
            sender_user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(authenticated_username)
            )
            recipient_user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(recipient)
            )

            if not sender_user or not recipient_user:
                logger.warning(f"⚠️ Пользователь не найден: sender={authenticated_username}, recipient={recipient}")
                await self._send_error(websocket, 'Пользователь не найден', request_id)
                return

            # ✅ Сохранение в БД — ТОЛЬКО ОДИН РАЗ
            message_id = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.save_message(
                    sender_user['id'],
                    recipient_user['id'],
                    encrypted_data
                )
            )
            logger.debug(f"💾 Сообщение сохранено: id={message_id}")

            # ✅ Уведомление получателю — БЕЗОПАСНОЕ
            if recipient in self.clients:
                try:
                    recipient_ws = self.clients[recipient]
                    await recipient_ws.send(json.dumps({
                        'type': 'new_message',
                        'sender': authenticated_username,
                        'encrypted_data': encrypted_data,
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }, ensure_ascii=False))
                    logger.info(f"📤 Уведомление отправлено: {recipient}")
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(f"⚠️ Получатель {recipient} отключился (удаление из clients)")
                    # Безопасное удаление
                    self.clients.pop(recipient, None)
                except KeyError:
                    logger.warning(f"⚠️ Получатель {recipient} не найден в self.clients")
                except Exception as e:
                    logger.error(f"❌ Не удалось уведомить {recipient}: {type(e).__name__}: {e}")

            # ✅ Отправка ответа отправителю
            await self._send_response(websocket, {
                'type': 'message_sent',
                'success': True,
                'message_id': message_id
            }, request_id)
            logger.debug(f"✅ Ответ отправлен: {authenticated_username}")

        except KeyError as e:
            logger.error(f"❌ KeyError в handle_message: {e}", exc_info=True)
            await self._send_error(websocket, f'Внутренняя ошибка: {str(e)}', request_id)
        except Exception as e:
            logger.error(f"❌ Ошибка в handle_message: {type(e).__name__}: {e}", exc_info=True)
            await self._send_error(websocket, f'Ошибка сервера: {str(e)[:100]}', request_id)
    # ========================================================================
    # 📁 ФАЙЛЫ
    # ========================================================================
    async def handle_file(self, websocket: websockets.WebSocketServerProtocol,
                          data: dict, authenticated_username: Optional[str],
                          request_id: Optional[str] = None) -> None:
        """Загрузка файла — ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        if not authenticated_username:
            await self._send_error(websocket, 'Требуется авторизация', request_id)
            return

        sender = authenticated_username
        recipient = data.get('recipient')
        filename = data.get('filename')
        file_size = data.get('file_size', 0)
        encrypted_data = data.get('encrypted_data')

        if not all([recipient, filename, encrypted_data]):
            await self._send_error(websocket, 'Отсутствуют параметры', request_id)
            return

        # ✅ Проверка размера файла (base64 увеличивает на ~33%)
        if len(encrypted_data) > ServerConstants.MAX_FILE_SIZE * 1.33:
            await self._send_error(websocket, 'Файл слишком большой', request_id)
            return

        file_saved = False
        file_path = None

        try:
            upload_dir = Path(Config.UPLOAD_DIR)
            upload_dir.mkdir(parents=True, exist_ok=True)

            file_uuid = str(uuid.uuid4())
            safe_filename = Path(filename).name  # Защита от path traversal

            # ✅ Проверка расширения файла
            file_ext = Path(safe_filename).suffix.lower()
            if file_ext and file_ext not in ServerConstants.ALLOWED_EXTENSIONS:
                await self._send_error(websocket, 'Неподдерживаемый тип файла', request_id)
                return

            file_path = upload_dir / f"{file_uuid}_{safe_filename}"

            file_content = base64.b64decode(encrypted_data)

            # ✅ Запись файла (async если aiofiles доступен)
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(file_content)
            else:
                with open(file_path, 'wb') as f:
                    f.write(file_content)
            file_saved = True

            logger.info(f"📁 Файл сохранён: {file_path.name}")

            loop = asyncio.get_event_loop()

            # ✅ Получение пользователей через executor
            sender_user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(sender)
            )
            recipient_user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(recipient)
            )

            if not sender_user or not recipient_user:
                raise ValueError("Пользователь не найден")

            # ✅ Сохранение в БД через executor
            db_file_id = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.save_file(
                    filename=safe_filename,
                    file_path=str(file_path),
                    file_size=file_size,
                    sender_id=sender_user['id'],
                    recipient_id=recipient_user['id']
                )
            )

            logger.info(f"💾 Файл сохранён в БД с ID: {db_file_id}")

            # ✅ Уведомление получателю
            if recipient in self.clients:
                try:
                    await self.clients[recipient].send(json.dumps({
                        'type': 'file_notification',
                        'filename': safe_filename,
                        'file_size': file_size,
                        'sender': sender,
                        'file_id': str(db_file_id),  # ✅ Явно в str для совместимости
                        'timestamp': datetime.now(timezone.utc).isoformat()
                    }))
                    logger.info(f"📤 Уведомление отправлено: {recipient}")
                except websockets.exceptions.ConnectionClosed:
                    logger.warning(f"⚠️ Получатель {recipient} отключился")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки уведомления: {e}")

            await self._send_response(websocket, {
                'type': 'file_sent',
                'success': True,
                'file_id': str(db_file_id),
                'filename': safe_filename
            }, request_id)

        except Exception as e:
            logger.exception(f"❌ Ошибка обработки файла: {e}")
            await self._send_error(websocket, f'Ошибка обработки файла: {str(e)[:100]}', request_id)

            # ✅ ИСПРАВЛЕНИЕ #6: Очистка файла при ошибке
            if file_saved and file_path and file_path.exists():
                try:
                    file_path.unlink()
                    logger.warning(f"🗑️ Файл удалён из-за ошибки: {file_path}")
                except Exception as cleanup_error:
                    logger.error(f"❌ Не удалось удалить файл при очистке: {cleanup_error}")

    async def handle_get_file(self, websocket: websockets.WebSocketServerProtocol,
                              data: dict, request_id: Optional[str] = None) -> None:
        """Скачивание файла"""
        file_id = data.get('file_id')
        username = data.get('username')

        if not file_id or not username:
            await self._send_error(websocket, 'Отсутствуют параметры', request_id)
            return

        try:
            loop = asyncio.get_event_loop()

            user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(username)
            )
            if not user:
                await self._send_error(websocket, 'Пользователь не найден', request_id)
                return

            file_info = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_file_by_id(int(file_id), user['id'])
            )

            if not file_info:
                await self._send_error(websocket, 'Файл не найден', request_id)
                return

            # Чтение файла
            if AIOFILES_AVAILABLE:
                async with aiofiles.open(file_info['file_path'], 'rb') as f:
                    file_content = await f.read()
            else:
                with open(file_info['file_path'], 'rb') as f:
                    file_content = f.read()

            encoded_content = base64.b64encode(file_content).decode('ascii')

            await self._send_response(websocket, {
                'type': 'file_data',
                'success': True,
                'file_id': file_info['id'],
                'filename': file_info['filename'],
                'content': encoded_content,
                'file_size': file_info['file_size']
            }, request_id)

            logger.info(f"📤 Файл отправлен: {file_info['filename']}")

        except FileNotFoundError:
            await self._send_error(websocket, 'Файл не найден на сервере', request_id)
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}", exc_info=True)
            await self._send_error(websocket, 'Ошибка чтения файла', request_id)

    # ========================================================================
    # 📋 КОНТАКТЫ И ПОИСК
    # ========================================================================
    async def handle_get_messages(self, websocket: websockets.WebSocketServerProtocol,
                                  data: dict, request_id: Optional[str] = None) -> None:
        """Получение истории сообщений"""
        username = data.get('username')
        with_user = data.get('with_user')
        limit = min(data.get('limit', 50), 200)  # Ограничение

        if not username or not with_user:
            await self._send_error(websocket, 'Отсутствуют параметры', request_id)
            return

        try:
            loop = asyncio.get_event_loop()

            user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(username)
            )
            other_user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(with_user)
            )

            if not user or not other_user:
                await self._send_error(websocket, 'Пользователь не найден', request_id)
                return

            messages = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_messages_between_users(user['id'], other_user['id'], limit)
            )

            await self._send_response(websocket, {
                'type': 'message_history',
                'messages': messages
            }, request_id)

            logger.info(f"📋 История отправлена: {len(messages)} элементов для {username}")

        except Exception as e:
            logger.error(f"❌ Ошибка получения истории: {e}", exc_info=True)
            await self._send_error(websocket, 'Ошибка получения истории', request_id)

    async def handle_get_public_key(self, websocket: websockets.WebSocketServerProtocol,
                                    data: dict, request_id: Optional[str] = None) -> None:
        """Отправка публичного ключа"""
        username = data.get('username')
        if not username:
            await self._send_error(websocket, 'Не указано имя пользователя', request_id)
            return

        try:
            loop = asyncio.get_event_loop()
            public_key = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_public_key(username)
            )

            if public_key:
                await self._send_response(websocket, {
                    'type': 'public_key',
                    'public_key': public_key
                }, request_id)
            else:
                await self._send_error(websocket, 'Пользователь не найден', request_id)
        except Exception as e:
            logger.error(f"❌ Ошибка получения ключа: {e}", exc_info=True)
            await self._send_error(websocket, 'Ошибка получения ключа', request_id)

    async def handle_search_users(self, websocket: websockets.WebSocketServerProtocol,
                                  data: dict, authenticated_username: Optional[str],
                                  request_id: Optional[str] = None) -> None:
        """Поиск пользователей"""
        query = data.get('query')
        request_username = data.get('username')

        if not query or len(query) < 2:
            await self._send_error(websocket, 'Поисковый запрос слишком короткий', request_id)
            return

        try:
            loop = asyncio.get_event_loop()
            user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(request_username)
            ) if request_username else None
            user_id = user['id'] if user else None

            results = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.search_users(query, exclude_user_id=user_id)
            )

            await self._send_response(websocket, {
                'type': 'search_results',
                'results': results
            }, request_id)

        except Exception as e:
            logger.error(f"❌ Ошибка поиска: {e}", exc_info=True)
            await self._send_error(websocket, 'Ошибка поиска', request_id)

    async def handle_add_contact(self, websocket: websockets.WebSocketServerProtocol,
                                 data: dict, authenticated_username: Optional[str],
                                 request_id: Optional[str] = None) -> None:
        """Добавление контакта"""
        username = data.get('username')
        contact_username = data.get('contact_username')

        if not username or not contact_username:
            await self._send_error(websocket, 'Отсутствуют обязательные параметры', request_id)
            return

        if not self._validate_username(contact_username):
            await self._send_error(websocket, 'Неверный формат имени контакта', request_id)
            return

        try:
            loop = asyncio.get_event_loop()
            user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(username)
            )
            if not user:
                await self._send_error(websocket, 'Пользователь не найден', request_id)
                return

            success = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.add_contact(user['id'], contact_username)
            )

            await self._send_response(websocket, {
                'type': 'add_contact_response',
                'success': success
            }, request_id)

        except Exception as e:
            logger.error(f"❌ Ошибка добавления контакта: {e}", exc_info=True)
            await self._send_error(websocket, 'Ошибка добавления контакта', request_id)

    async def handle_remove_contact(self, websocket: websockets.WebSocketServerProtocol,
                                    data: dict, authenticated_username: Optional[str],
                                    request_id: Optional[str] = None) -> None:
        """Удаление контакта"""
        username = data.get('username')
        contact_username = data.get('contact_username')

        if not username or not contact_username:
            await self._send_error(websocket, 'Отсутствуют обязательные параметры', request_id)
            return

        try:
            loop = asyncio.get_event_loop()
            user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(username)
            )
            if not user:
                await self._send_error(websocket, 'Пользователь не найден', request_id)
                return

            success = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.remove_contact(user['id'], contact_username)
            )

            await self._send_response(websocket, {
                'type': 'remove_contact_response',
                'success': success
            }, request_id)

        except Exception as e:
            logger.error(f"❌ Ошибка удаления контакта: {e}", exc_info=True)
            await self._send_error(websocket, 'Ошибка удаления контакта', request_id)

    async def handle_get_contacts(self, websocket: websockets.WebSocketServerProtocol,
                                  data: dict, authenticated_username: Optional[str],
                                  request_id: Optional[str] = None) -> None:
        """Получение списка контактов"""
        username = data.get('username')

        if not username:
            await self._send_error(websocket, 'Не указано имя пользователя', request_id)
            return

        try:
            loop = asyncio.get_event_loop()
            user = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_user_by_username(username)
            )
            if not user:
                await self._send_error(websocket, 'Пользователь не найден', request_id)
                return

            contacts = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_contacts(user['id'])
            )

            # Добавляем статус онлайн
            for contact in contacts:
                contact_username = contact.get('username')
                contact['online'] = contact_username in self.clients

            await self._send_response(websocket, {
                'type': 'contacts_list',
                'contacts': contacts
            }, request_id)

        except Exception as e:
            logger.error(f"❌ Ошибка получения контактов: {e}", exc_info=True)
            await self._send_error(websocket, 'Ошибка получения контактов', request_id)

    # ========================================================================
    # 🔔 УВЕДОМЛЕНИЯ О СТАТУСЕ
    # ========================================================================
    async def _notify_contacts_status(self, username: str, online: bool) -> None:
        """Уведомление контактов об изменении статуса"""
        try:
            loop = asyncio.get_event_loop()
            contacts = await loop.run_in_executor(
                self._db_executor,
                lambda: self.db.get_contacts_by_username(username)
            )

            for contact in contacts:
                contact_username = contact.get('username')
                if contact_username in self.clients:
                    try:
                        await self.clients[contact_username].send(json.dumps({
                            'type': 'user_status',
                            'username': username,
                            'online': online
                        }))
                    # ✅ ИСПРАВЛЕНИЕ #4: Конкретные исключения вместо голого except
                    except websockets.exceptions.ConnectionClosed:
                        # Клиент отключился — нормально
                        pass
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось уведомить {contact_username}: {e}")

        except Exception as e:
            logger.error(f"❌ Ошибка уведомления о статусе: {e}")

    # ========================================================================
    # 🛑 ЗАВЕРШЕНИЕ РАБОТЫ
    # ========================================================================
    async def shutdown(self):
        """Корректное завершение работы сервера"""
        logger.info("🔄 Завершение работы сервера...")

        # Уведомить всех клиентов
        for username, websocket in list(self.clients.items()):
            try:
                await websocket.send(json.dumps({'type': 'server_shutdown'}))
                await websocket.close()
            except:
                pass
        self.clients.clear()

        # Закрыть executor
        if hasattr(self, '_db_executor'):
            self._db_executor.shutdown(wait=True)

        # Закрыть БД
        if hasattr(self.db, 'close'):
            self.db.close()

        logger.info("✅ Сервер завершил работу")

    # ========================================================================
    # 🧹 ПЕРИОДИЧЕСКАЯ ОЧИСТКА
    # ========================================================================
    async def _periodic_cleanup(self):
        """Фоновая задача для очистки старых данных rate limiter"""
        while True:
            await asyncio.sleep(300)  # Каждые 5 минут
            self.rate_limiter.cleanup()
            logger.debug("🧹 Rate limiter очищен")


# ============================================================================
# 🚀 ТОЧКА ВХОДА
# ============================================================================
async def main():
    """Точка входа сервера"""
    server = MessengerServer()

    # Запуск фоновой задачи очистки
    cleanup_task = asyncio.create_task(server._periodic_cleanup())

    # Обработка сигналов для graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown_signal():
        logger.info("🛑 Получен сигнал завершения")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown_signal)
        except NotImplementedError:
            # Windows не поддерживает add_signal_handler для всех сигналов
            pass

    # Настройка SSL (опционально)
    ssl_context = None
    if hasattr(Config, 'USE_SSL') and Config.USE_SSL:
        try:
            import ssl
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(
                getattr(Config, 'SSL_CERT_PATH', 'cert.pem'),
                getattr(Config, 'SSL_KEY_PATH', 'key.pem')
            )
            logger.info(f"🔐 SSL включён")
        except Exception as e:
            logger.error(f"❌ Ошибка настройки SSL: {e}")
            logger.warning("⚠️ Сервер запустится без SSL")

    async with websockets.serve(
            server.handle_client,
            Config.HOST,
            Config.PORT,
            ping_interval=20,
            ping_timeout=10,
            max_size=10 * 1024 * 1024,
            ssl=ssl_context
    ):
        scheme = 'wss' if ssl_context else 'ws'
        logger.info(f"🚀 Сервер запущен на {scheme}://{Config.HOST}:{Config.PORT}")
        await stop_event.wait()  # Ждём сигнал завершения

        # Корректное завершение
        await server.shutdown()
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Сервер остановлен пользователем")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка сервера: {e}")