#!/usr/bin/env python3
"""
Messenger Client — Асинхронный клиент для Secure Messenger
Исправленная и оптимизированная версия
"""

import asyncio
import json
import os
import base64
import uuid
import logging
import re
import ssl
import time
import websockets
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any, Union
from pathlib import Path

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.config import ClientConfig
from client.crypto import ClientCrypto


# ============================================================================
# ⚙️ КОНСТАНТЫ
# ============================================================================
class ClientConstants:
    """Константы клиента"""
    # Таймауты (секунды)
    TIMEOUT_CONNECT = 10
    TIMEOUT_REQUEST_SHORT = 5
    TIMEOUT_REQUEST_NORMAL = 10
    TIMEOUT_REQUEST_LONG = 120
    TIMEOUT_PING = 5

    # Сетевые настройки
    MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    PING_INTERVAL = 20
    PING_TIMEOUT = 10

    # Повторные попытки
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # Экспоненциальная задержка

    # Валидация
    USERNAME_PATTERN = r'^[a-zA-Z0-9_]{3,30}$'
    EMAIL_PATTERN = r'^[^@]+@[^@]+\.[^@]+$'
    MIN_PASSWORD_LENGTH = 8

    # Логирование
    LOG_FILE = 'messenger_client.log'
    LOG_LEVEL = logging.DEBUG


# ============================================================================
# 🔧 НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================================
def _sanitize_for_log(data: Dict[str, Any]) -> Dict[str, Any]:
    """Удаляет чувствительные данные перед логированием"""
    sensitive_fields = {'password', 'encrypted_data', 'private_key', 'encrypted_key'}
    result = {}
    for k, v in data.items():
        if k in sensitive_fields:
            result[k] = '***REDACTED***'
        elif isinstance(v, dict):
            result[k] = _sanitize_for_log(v)
        else:
            result[k] = v
    return result


logging.basicConfig(
    level=ClientConstants.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(
            ClientConstants.LOG_FILE,
            encoding='utf-8',
            mode='a'  # ✅ Дозапись вместо перезаписи
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MessengerClient:
    """Асинхронный клиент для защищённого мессенджера"""

    def __init__(self, host: str = None, port: int = None):
        self.websocket = None
        self.username: Optional[str] = None
        self.user_id: Optional[int] = None
        self.crypto = ClientCrypto()
        self.connected = False
        self._receive_task: Optional[asyncio.Task] = None
        self.sent_messages: Dict[int, str] = {}

        # Колбэки
        self.message_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.file_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.status_callback: Optional[Callable[[str], None]] = None

        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._public_keys_cache: Dict[str, str] = {}
        self._loop_ready = asyncio.Event()

        self.server_host = host or ClientConfig.SERVER_HOST
        self.server_port = port or ClientConfig.SERVER_PORT

        # Статистика для health-check
        self._last_ping_time: Optional[float] = None
        self._connection_monitor_task: Optional[asyncio.Task] = None

        logger.info("✅ MessengerClient инициализирован")

    # ==================== Валидация ====================
    @staticmethod
    def _validate_username(username: str) -> bool:
        return bool(username and re.match(ClientConstants.USERNAME_PATTERN, username))

    @staticmethod
    def _validate_email(email: str) -> bool:
        return bool(email and re.match(ClientConstants.EMAIL_PATTERN, email))

    @staticmethod
    def _validate_password(password: str) -> bool:
        return bool(password and len(password) >= ClientConstants.MIN_PASSWORD_LENGTH)

    @staticmethod
    def _validate_public_key(key: str) -> bool:
        """Проверка формата публичного ключа (PEM)"""
        if not key or not isinstance(key, str):
            return False
        return (
                "-----BEGIN PUBLIC KEY-----" in key and
                "-----END PUBLIC KEY-----" in key and
                len(key) >= 400  # Минимальная длина для валидного ключа
        )

    # ==================== Подключение ====================
    async def connect(self, uri: str = None) -> bool:
        if uri is None:
            uri = f"ws://{self.server_host}:{self.server_port}"

        try:
            logger.info(f"🔌 Подключение к {uri}...")

            # Настройка SSL для wss://
            ssl_context = None
            if uri.startswith('wss://'):
                ssl_context = ssl.create_default_context()
                logger.debug("🔐 Используется SSL-соединение")

            self.websocket = await asyncio.wait_for(
                websockets.connect(
                    uri,
                    ping_interval=ClientConstants.PING_INTERVAL,
                    ping_timeout=ClientConstants.PING_TIMEOUT,
                    max_size=ClientConstants.MAX_MESSAGE_SIZE,
                    ssl=ssl_context
                ),
                timeout=ClientConstants.TIMEOUT_CONNECT
            )
            self.connected = True
            logger.info(f"✅ Подключено к {uri}")

            self._receive_task = asyncio.create_task(self._receive_loop())
            self._loop_ready.set()

            # Запуск мониторинга соединения
            self._connection_monitor_task = asyncio.create_task(self._connection_monitor())

            return True

        except asyncio.TimeoutError:
            logger.error("⏰ Таймаут подключения")
            return False
        except ConnectionRefusedError:
            logger.error("❌ Сервер отклонил подключение")
            return False
        except ssl.SSLCertVerificationError as e:
            logger.error(f"❌ Ошибка проверки SSL-сертификата: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}", exc_info=True)
            return False

    async def _connection_monitor(self) -> None:
        """Фоновая проверка живости соединения"""
        while self.connected:
            try:
                await asyncio.sleep(30)
                if self.connected and self.websocket:
                    start = time.time()
                    await asyncio.wait_for(self.websocket.ping(), timeout=ClientConstants.TIMEOUT_PING)
                    latency = (time.time() - start) * 1000
                    self._last_ping_time = time.time()
                    logger.debug(f"🏓 Ping: {latency:.0f}ms")
            except asyncio.TimeoutError:
                logger.warning("⚠️ Ping timeout, попытка переподключения...")
                await self._reconnect()
            except websockets.exceptions.ConnectionClosed:
                logger.info("🔌 Соединение закрыто, переподключение...")
                await self._reconnect()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"⚠️ Ошибка мониторинга: {e}")

    async def _reconnect(self) -> bool:
        """Попытка переподключения с экспоненциальной задержкой"""
        if not self.connected:
            return False

        self.connected = False
        await self.disconnect()

        for attempt in range(ClientConstants.MAX_RETRIES):
            delay = ClientConstants.RETRY_BASE_DELAY * (2 ** attempt)
            logger.info(f"🔄 Попытка переподключения {attempt + 1}/{ClientConstants.MAX_RETRIES} через {delay:.1f}с...")
            await asyncio.sleep(delay)

            if await self.connect():
                logger.info("✅ Переподключение успешно")
                return True

        logger.error("❌ Не удалось переподключиться после всех попыток")
        return False

    async def disconnect(self) -> bool:
        if not self.connected or not self.websocket:
            return True
        try:
            self.connected = False
            self._loop_ready.clear()

            # Остановка мониторинга
            if self._connection_monitor_task and not self._connection_monitor_task.done():
                self._connection_monitor_task.cancel()
                try:
                    await self._connection_monitor_task
                except asyncio.CancelledError:
                    pass

            # Отмена задачи получения
            if self._receive_task and not self._receive_task.done():
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass

            # Уведомление ожидающих запросов
            for future in self._pending_requests.values():
                if not future.done():
                    future.set_exception(ConnectionError("Соединение закрыто"))
            self._pending_requests.clear()

            # Закрытие WebSocket
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            logger.info("🔌 Отключено")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отключения: {e}", exc_info=True)
            return False

    # ==================== Регистрация и вход ====================
    async def register(self, username: str, email: str, password: str, public_key: str = None) -> bool:
        if not self._validate_username(username):
            logger.error("❌ Неверный формат username")
            return False
        if not self._validate_email(email):
            logger.error("❌ Неверный формат email")
            return False
        if not self._validate_password(password):
            logger.error("❌ Пароль должен содержать минимум 8 символов")
            return False

        if public_key is None:
            public_key = self.crypto.generate_identity_keys()

        try:
            response = await self._send_with_retry({
                'type': 'register',
                'username': username,
                'email': email,
                'password': password,
                'public_key': public_key
            }, timeout=ClientConstants.TIMEOUT_REQUEST_NORMAL)

            if response is None:
                logger.error("❌ Нет ответа от сервера")
                return False
            if response.get('success'):
                logger.info(f"✅ Зарегистрирован: {username}")
                return True
            else:
                logger.warning(f"❌ Регистрация не удалась: {response.get('message')}")
                return False
        except Exception as e:
            logger.error(f"❌ Ошибка регистрации: {e}", exc_info=True)
            return False

    async def login(self, username: str, password: str) -> bool:
        if not self._validate_username(username):
            logger.error("❌ Неверный формат username")
            return False
        try:
            response = await self._send_with_retry({
                'type': 'login',
                'username': username,
                'password': password
            }, timeout=ClientConstants.TIMEOUT_REQUEST_NORMAL)

            if response is None:
                logger.error("❌ Нет ответа от сервера")
                return False
            if response.get('success'):
                self.username = username
                self.user_id = response.get('user_id')
                if response.get('public_key') and self._validate_public_key(response['public_key']):
                    self._public_keys_cache[username] = response['public_key']
                logger.info(f"✅ Вход выполнен: {username}")
                return True
            else:
                logger.warning(f"❌ Вход не удался: {response.get('message')}")
                return False
        except Exception as e:
            logger.error(f"❌ Ошибка входа: {e}", exc_info=True)
            return False

    # ==================== Отправка сообщений ====================
    async def send_message(self, recipient: str, encrypted_data: str) -> Optional[Dict]:  # ✅ ИСПРАВЛЕНО
        if not self.username:
            logger.error("❌ Отправка без авторизации")
            return None
        if not self._validate_username(recipient):
            logger.error("❌ Неверный формат получателя")
            return None
        if not encrypted_data:
            logger.error("❌ Пустые данные сообщения")
            return None

        data = {
            'type': 'message',
            'recipient': recipient,
            'encrypted_data': encrypted_data,
            'timestamp': datetime.now().isoformat()
        }
        return await self._send_and_wait(data, timeout=ClientConstants.TIMEOUT_REQUEST_NORMAL)

        try:
            await self.websocket.send(json.dumps({
                'type': 'message',
                'recipient': recipient,
                'encrypted_data': encrypted_data,
                'timestamp': datetime.now().isoformat()
            }))
            logger.debug(f"📤 Сообщение отправлено для {recipient}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}", exc_info=True)
            return False

    # ==================== Цикл получения ====================
    async def _receive_loop(self) -> None:
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    logger.debug(f"📥 Получен тип сообщения: {msg_type}")

                    if msg_type == 'new_message':
                        if self.message_callback:
                            asyncio.create_task(self._safe_callback(self.message_callback, data))
                    elif msg_type == 'file_notification':
                        logger.info(f"📁 Получено уведомление о файле: {data.get('filename')}")
                        if self.file_callback:
                            asyncio.create_task(self._safe_callback(self.file_callback, data))
                    elif 'request_id' in data:
                        request_id = data.get('request_id')
                        if request_id in self._pending_requests:
                            self._pending_requests[request_id].set_result(data)

                except json.JSONDecodeError as e:
                    logger.error(f"❌ Ошибка парсинга JSON: {e}")

        except websockets.exceptions.ConnectionClosed:
            logger.info("🔌 Соединение закрыто")
        except asyncio.CancelledError:
            logger.info("🔄 receive_loop отменён")
            raise
        except Exception as e:
            logger.error(f"❌ Ошибка в receive_loop: {e}", exc_info=True)

    async def _safe_callback(self, callback: Callable, data: Dict[str, Any]) -> None:
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                await asyncio.get_event_loop().run_in_executor(None, callback, data)
        except Exception as e:
            logger.error(f"❌ Ошибка в колбэке: {e}", exc_info=True)

    # ==================== Отправка файлов ====================
    async def send_file(self, recipient: str, file_path: str, file_name: str = None,
                        file_size: int = None, encrypted_data: str = None) -> bool:  # ✅ ИСПРАВЛЕНО
        if not self.username:
            logger.error("❌ Отправка файла без авторизации")
            return False
        if not self._validate_username(recipient):
            logger.error("❌ Неверный формат получателя")
            return False

        try:
            filename = file_name or os.path.basename(file_path)
            encrypted_key = None
            iv = None

            # Контракт: если encrypted_data передан — он уже base64-закодирован
            if encrypted_data is None:
                if not os.path.exists(file_path):
                    logger.error(f"❌ Файл не найден: {file_path}")
                    return False
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                file_size = file_size or len(file_content)
                encrypted_content, encrypted_key, iv = self.crypto.encrypt_file(file_content, recipient)
                encrypted_data = base64.b64encode(encrypted_content).decode('ascii')

            payload = {
                'type': 'file',
                'recipient': recipient,
                'filename': filename,
                'file_size': file_size,
                'encrypted_data': encrypted_data,
                'encrypted_key': encrypted_key,
                'iv': iv
            }

            await self.websocket.send(json.dumps(payload))
            logger.info(f"📁 Файл отправлен: {filename}")
            return True
        except FileNotFoundError:
            logger.error(f"❌ Файл не найден: {file_path}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка отправки файла: {e}", exc_info=True)
            return False

    # ==================== Работа с контактами и ключами ====================
    async def get_contacts(self) -> List[Dict[str, Any]]:
        result = await self._send_with_retry(
            {'type': 'get_contacts', 'username': self.username},
            timeout=ClientConstants.TIMEOUT_REQUEST_SHORT
        )
        if result and 'contacts' in result:
            contacts = result['contacts']
            for contact in contacts:
                username = contact.get('username')
                contact['has_public_key'] = username in self._public_keys_cache
            return contacts
        return []

    async def search_users(self, query: str) -> List[Dict[str, Any]]:
        if not query or len(query) < 2:
            logger.warning("⚠️ Слишком короткий поисковый запрос")
            return []
        result = await self._send_with_retry({
            'type': 'search_users',
            'username': self.username,
            'query': query
        }, timeout=ClientConstants.TIMEOUT_REQUEST_SHORT)
        return result.get('results', []) if result else []

    async def add_contact(self, contact_username: str) -> bool:
        if not self._validate_username(contact_username):
            logger.error("❌ Неверный формат имени контакта")
            return False
        result = await self._send_with_retry({
            'type': 'add_contact',
            'username': self.username,
            'contact_username': contact_username
        }, timeout=ClientConstants.TIMEOUT_REQUEST_SHORT)
        success = result.get('success', False) if result else False
        if success:
            key = await self.get_public_key(contact_username)
            if key and self._validate_public_key(key):
                self._public_keys_cache[contact_username] = key
        return success

    async def remove_contact(self, contact_username: str) -> bool:
        result = await self._send_with_retry({
            'type': 'remove_contact',
            'username': self.username,
            'contact_username': contact_username
        }, timeout=ClientConstants.TIMEOUT_REQUEST_SHORT)
        if result and result.get('success', False):
            self._public_keys_cache.pop(contact_username, None)
        return result.get('success', False) if result else False

    async def get_public_key(self, username: str) -> Optional[str]:
        if username in self._public_keys_cache:
            return self._public_keys_cache[username]
        result = await self._send_with_retry(
            {'type': 'get_public_key', 'username': username},
            timeout=ClientConstants.TIMEOUT_REQUEST_SHORT
        )
        if result and 'public_key' in result:
            key = result['public_key']
            if self._validate_public_key(key):  # ✅ Валидация ключа
                self._public_keys_cache[username] = key
                return key
            else:
                logger.error(f"❌ Неверный формат публичного ключа для {username}")
                return None
        return None

    # ==================== История чата ====================
    async def get_chat_history(self, with_user: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not self._validate_username(with_user):
            logger.error("❌ Неверный формат имени пользователя")
            return []
        limit = max(1, min(limit, 200))  # Ограничение диапазона

        result = await self._send_with_retry({
            'type': 'get_messages',
            'username': self.username,
            'with_user': with_user,
            'limit': limit
        }, timeout=ClientConstants.TIMEOUT_REQUEST_NORMAL)

        if not result or 'messages' not in result:
            return []

        messages = []
        for m in result['messages']:
            is_own = m.get('sender') == self.username
            text = m.get('text', m.get('encrypted_data', ''))

            if not is_own and m.get('encrypted_data'):
                try:
                    sender = m.get('sender')
                    sender_key = self._public_keys_cache.get(sender)
                    if sender_key:
                        text = self.crypto.decrypt_message(m['encrypted_data'], sender_key)
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка расшифровки сообщения: {e}")
                    text = "⚠️ Не расшифровано"

            messages.append({
                'sender': m.get('sender'),
                'text': text,
                'encrypted_data': m.get('encrypted_data'),
                'timestamp': m.get('timestamp'),
                'is_own': is_own,
                'is_encrypted': not is_own
            })
        return messages

    # ==================== Запросы к серверу с retry ====================
    async def _send_with_retry(self, data: dict, timeout: float = 10, max_retries: int = None) -> Optional[dict]:
        """Отправка запроса с автоматическими повторными попытками"""
        if max_retries is None:
            max_retries = ClientConstants.MAX_RETRIES

        last_error = None
        for attempt in range(max_retries):
            try:
                return await self._send_and_wait(data, timeout)
            except (websockets.exceptions.ConnectionClosed, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = ClientConstants.RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f"⚠️ Попытка {attempt + 1} не удалась, повтор через {delay:.1f}с: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"❌ Все {max_retries} попыток исчерпаны")
            except Exception as e:
                logger.error(f"❌ Ошибка запроса (без повтора): {e}", exc_info=True)
                return None
        return None

    async def _send_and_wait(self, data: dict, timeout: float = 10) -> Optional[dict]:
        if hasattr(self, '_loop_ready') and not self._loop_ready.is_set():
            try:
                await asyncio.wait_for(self._loop_ready.wait(), timeout=2)
            except asyncio.TimeoutError:
                logger.warning("⚠️ Таймаут ожидания готовности loop")

        if not self.connected or not self.websocket:
            logger.error("❌ Нет активного соединения")
            return None

        request_id = str(uuid.uuid4())
        # ✅ Санитизация перед логированием
        logger.debug(f"📤 Запрос #{request_id}: {data.get('type')} | {_sanitize_for_log(data)}")

        data['request_id'] = request_id
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_requests[request_id] = future

        try:
            await self.websocket.send(json.dumps(data))
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Таймаут запроса #{request_id}")
            return None
        except websockets.exceptions.ConnectionClosed:
            logger.error("🔌 Соединение закрыто во время запроса")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка запроса: {e}", exc_info=True)
            return None
        finally:
            self._pending_requests.pop(request_id, None)

    # ==================== Получение файлов ====================
    async def get_file_by_id(self, file_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        try:
            file_id_int = int(file_id)
        except (ValueError, TypeError):
            logger.error(f"❌ Неверный формат file_id: {file_id}")
            return None

        logger.info(f"📥 Запрос файла по ID: {file_id_int}")

        result = await self._send_with_retry({
            'type': 'get_file',
            'file_id': file_id_int,
            'username': self.username
        }, timeout=ClientConstants.TIMEOUT_REQUEST_LONG)

        if result and result.get('success'):
            logger.info(f"✅ Файл получен: {result.get('filename')}")
            return {
                'file_id': result.get('file_id'),
                'filename': result.get('filename'),
                'content': result.get('content'),
                'file_size': result.get('file_size')
            }

        logger.warning(f"⚠️ Не удалось получить файл: {file_id}")
        return None

    # ==================== Утилиты ====================
    def is_authenticated(self) -> bool:
        return bool(self.username and self.connected)

    def get_username(self) -> Optional[str]:
        return self.username

    def get_crypto(self) -> ClientCrypto:
        return self.crypto

    def set_message_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self.message_callback = callback
        logger.debug("📬 Колбэк сообщений установлен")

    def set_file_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self.file_callback = callback
        logger.debug("📁 Колбэк файлов установлен")

    def set_status_callback(self, callback: Callable[[str], None]) -> None:
        self.status_callback = callback
        logger.debug("📊 Колбэк статусов установлен")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        return False
