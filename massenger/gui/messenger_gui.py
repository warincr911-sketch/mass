#!/usr/bin/env python3
"""
================================================================================
                    MESSENGER GUI CLIENT — ПОЛНАЯ ВЕРСИЯ (ИСПРАВЛЕННАЯ)
================================================================================
"""

# ============================================================================
# 📦 РАЗДЕЛ 1: ИМПОРТЫ И ЗАВИСИМОСТИ
# ============================================================================

import sys
import os
import threading
import asyncio
import base64
import logging
import tkinter as tk
import concurrent.futures
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
import traceback
import time

from tkinter import (
    ttk,
    scrolledtext,
    messagebox,
    filedialog,
    Menu,
    Toplevel,
    Frame,
    Label,
    Entry,
    Button,
    Listbox,
    Scrollbar
)

try:
    import websockets

    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    print("⚠️ Модуль websockets не установлен. Установите: pip install websockets")

# ============================================================================
# 🔧 РАЗДЕЛ 2: НАСТРОЙКА ПУТЕЙ (ИСПРАВЛЕНО!)
# ============================================================================
current_file = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file)  # massenger/gui/
project_root = os.path.dirname(current_dir)  # massenger/

# ✅ Добавляем massenger/ в sys.path чтобы работали импорты типа "from client import ..."
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Проверка структуры
logger_debug = logging.getLogger('messenger_gui_path')
logger_debug.debug(f"📁 Current: {current_file}")
logger_debug.debug(f"📁 GUI dir: {current_dir}")
logger_debug.debug(f"📁 Project root: {project_root}")
logger_debug.debug(f"📁 sys.path[0]: {sys.path[0]}")


# ============================================================================
# 🔧 РАЗДЕЛ 3: КОНСТАНТЫ
# ============================================================================
class GUIConstants:
    """Константы графического интерфейса"""
    TIMEOUT_SHORT = 5
    TIMEOUT_NORMAL = 10
    TIMEOUT_LONG = 120
    AUTO_REFRESH_INTERVAL = 3000
    SEARCH_DEBOUNCE_MS = 300
    STATUS_MESSAGE_DURATION = 5000
    MAX_FILE_SIZE = 100 * 1024 * 1024
    DOWNLOAD_DIR = Path.home() / "Downloads" / "Messenger"
    LOG_FILE = 'messenger_gui.log'
    LOG_LEVEL = logging.INFO
    USERNAME_PATTERN = r'^[a-zA-Z0-9_]{3,30}$'
    EMAIL_PATTERN = r'^[^@]+@[^@]+\.[^@]+$'
    MIN_PASSWORD_LENGTH = 8
    MIN_PUBLIC_KEY_LENGTH = 400


# ============================================================================
# 🔧 РАЗДЕЛ 4: НАСТРОЙКА ЛОГИРОВАНИЯ
# ============================================================================
def _sanitize_for_log(data: Dict[str, Any]) -> Dict[str, Any]:
    """Удаляет чувствительные данные перед логированием"""
    sensitive = {'password', 'encrypted_data', 'private_key', 'encrypted_key'}
    result = {}
    for k, v in data.items():
        if k in sensitive:
            result[k] = '***REDACTED***'
        elif isinstance(v, dict):
            result[k] = _sanitize_for_log(v)
        else:
            result[k] = v
    return result


def setup_logging() -> logging.Logger:
    """Настройка системы логирования приложения"""
    logger = logging.getLogger('messenger_gui')
    logger.setLevel(GUIConstants.LOG_LEVEL)

    if logger.handlers:
        logger.handlers.clear()

    log_format = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    try:
        file_handler = logging.FileHandler(
            filename=GUIConstants.LOG_FILE,
            encoding='utf-8',
            mode='a'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
    except OSError as e:
        print(f"⚠️ Не удалось создать файл лога: {e}")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()


# ============================================================================
# 📦 РАЗДЕЛ 5: ИМПОРТ ЗАВИСИМОСТЕЙ ПРОЕКТА
# ============================================================================
def import_project_modules():
    """Импорт модулей проекта с обработкой ошибок"""
    try:
        logger.info(f"📁 Project root: {project_root}")
        logger.info(f"📁 sys.path[0]: {sys.path[0]}")

        # Проверка наличия файлов
        client_path = os.path.join(project_root, 'client', 'messenger_client.py')
        crypto_path = os.path.join(project_root, 'client', 'crypto.py')

        if not os.path.exists(client_path):
            raise FileNotFoundError(f"❌ Файл не найден: {client_path}")
        if not os.path.exists(crypto_path):
            raise FileNotFoundError(f"❌ Файл не найден: {crypto_path}")

        logger.info(f"✅ client/messenger_client.py найден")
        logger.info(f"✅ client/crypto.py найден")

        from client.messenger_client import MessengerClient
        from client.crypto import ClientCrypto
        logger.info("✅ Все зависимости импортированы успешно")
        return MessengerClient, ClientCrypto
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта модулей: {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка импорта: {e}", exc_info=True)
        raise


MessengerClient, ClientCrypto = import_project_modules()


# ============================================================================
# 🏗️ РАЗДЕЛ 6: КЛАСС MESSENGERGUI
# ============================================================================
class MessengerGUI:
    """Графический интерфейс мессенджера с поддержкой end-to-end шифрования"""

    def __init__(self) -> None:
        """Инициализация основного окна приложения"""
        logger.info("=" * 80)
        logger.info("ИНИЦИАЛИЗАЦИЯ MESSENGERGUI")
        logger.info("=" * 80)

        try:
            self.root = tk.Tk()
            self.root.title("🔐 Secure Messenger")
            self.root.geometry("1100x750")
            self.root.minsize(900, 600)
            self.root.maxsize(1920, 1080)
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)


            try:
                icon_path = Path(__file__).parent / "icon.ico"
                if icon_path.exists():
                    self.root.iconbitmap(str(icon_path))
                    logger.debug("🖼️ Иконка приложения установлена")
            except Exception:
                logger.debug("⚠️ Иконка не установлена (необязательно)")

            logger.info("✅ Главное окно создано")
        except tk.TclError as e:
            logger.error(f"❌ Не удалось создать окно Tkinter: {e}", exc_info=True)
            raise

        self.client: Optional[MessengerClient] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.current_chat: Optional[str] = None
        self.username: Optional[str] = None
        self.known_public_keys: Dict[str, str] = {}
        self.sent_messages: Dict[str, str] = {}

        self.chat_listbox: Optional[tk.Listbox] = None
        self.messages_area: Optional[scrolledtext.ScrolledText] = None
        self.message_entry: Optional[ttk.Entry] = None
        self.status_bar: Optional[ttk.Label] = None
        self.chat_title: Optional[ttk.Label] = None
        self.typing_label: Optional[ttk.Label] = None
        self.search_entry: Optional[ttk.Entry] = None

        self.search_after_id: Optional[str] = None
        self._refresh_job: Optional[str] = None
        self.last_message_time: Dict[str, str] = {}

        self.download_dir = GUIConstants.DOWNLOAD_DIR

        try:
            self.download_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"📁 Директория загрузок: {self.download_dir}")
        except OSError as e:
            logger.warning(f"⚠️ Не удалось создать директорию загрузок: {e}")

        self.message_status_map: Dict[str, str] = {}

        try:
            self.show_login_window()
            logger.info("✅ Окно входа создано")
        except Exception as e:
            logger.error(f"❌ Ошибка при создании окна входа: {e}", exc_info=True)
            raise

        logger.info("✅ MessengerGUI полностью инициализирован")
        logger.info("=" * 80)

    # ========================================================================
    # 🔐 ВАЛИДАЦИЯ
    # ========================================================================
    @staticmethod
    def _validate_username(username: str) -> bool:
        return bool(username and re.match(GUIConstants.USERNAME_PATTERN, username))

    @staticmethod
    def _validate_email(email: str) -> bool:
        return bool(email and re.match(GUIConstants.EMAIL_PATTERN, email))

    @staticmethod
    def _validate_password(password: str) -> bool:
        return bool(password and len(password) >= GUIConstants.MIN_PASSWORD_LENGTH)

    @staticmethod
    def _validate_public_key(key: str) -> bool:
        """Проверка формата публичного ключа (PEM)"""
        if not key or not isinstance(key, str):
            return False
        return (
                "-----BEGIN PUBLIC KEY-----" in key and
                "-----END PUBLIC KEY-----" in key and
                len(key) >= GUIConstants.MIN_PUBLIC_KEY_LENGTH
        )

    # ========================================================================
    # ⚡ АСИНХРОННОСТЬ И ПОТОКИ
    # ========================================================================
    def _run_async(self, coro: Any, timeout: int = 10) -> Any:
        """Безопасный запуск асинхронной функции из потока Tkinter"""
        if not self.loop or not self.client:
            logger.error("❌ Event loop или клиент не инициализирован")
            return None
        if self.loop.is_closed():
            logger.error("❌ Event loop закрыт")
            return None
        if not self.loop.is_running():
            logger.warning("⚠️ Event loop не запущен")
            return None

        try:
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            result = future.result(timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.error(f"⏰ Таймаут операции (>{timeout}с)")
            self.root.after(0, lambda: self.show_error("Таймаут операции"))
            return None
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                logger.warning(f"⚠️ Loop закрыт: {e}")
            elif "Cannot run coroutines from a running event loop" in str(e):
                logger.warning(f"⚠️ Предупреждение asyncio: {e}")
            else:
                logger.error(f"❌ RuntimeError: {e}", exc_info=True)
            return None
        except asyncio.CancelledError:
            logger.warning("⚠️ Операция отменена")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка в _run_async: {e}", exc_info=True)
            self.root.after(0, lambda err=str(e): self.show_error(f"Ошибка: {err}"))
            return None

    def _decrypt_in_thread(self, encrypted_data: str, public_key: str) -> str:
        """Выполняет расшифровку в отдельном потоке, чтобы не блокировать UI"""

        def _decrypt():
            return self.client.crypto.decrypt_message(encrypted_data, None)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(_decrypt)
            return future.result(timeout=10)

    def _safe_callback(self, callback: Callable, data: Dict[str, Any]) -> None:
        """Безопасный вызов колбэка (поддержка sync/async)"""
        try:
            if asyncio.iscoroutinefunction(callback):
                asyncio.run_coroutine_threadsafe(callback(data), self.loop)
            else:
                self.root.after(0, lambda: callback(data))
        except Exception as e:
            logger.error(f"❌ Ошибка в колбэке: {e}", exc_info=True)

    # ========================================================================
    # 🔐 ОКНО ВХОДА И РЕГИСТРАЦИИ
    # ========================================================================
    def show_login_window(self) -> None:
        """Создание и показ модального окна входа и регистрации"""
        logger.info("Показ окна входа")

        try:
            login = tk.Toplevel(self.root)
            login.title("🔐 Вход в Messenger")
            login.geometry("350x400")
            login.resizable(False, False)
            login.transient(self.root)
            login.grab_set()
            login.attributes('-topmost', True)
            login.update_idletasks()
            x = (login.winfo_screenwidth() - login.winfo_width()) // 2
            y = (login.winfo_screenheight() - login.winfo_height()) // 2
            login.geometry(f"+{x}+{y}")
            logger.info("✅ Окно входа создано")
        except tk.TclError as e:
            logger.error(f"❌ Не удалось создать окно входа: {e}", exc_info=True)
            raise

        title_frame = ttk.Frame(login)
        title_frame.pack(fill=tk.X, pady=15)
        ttk.Label(title_frame, text="🔐 Secure Messenger", font=('Segoe UI', 16, 'bold'), foreground='#1a73e8').pack()
        ttk.Label(title_frame, text="Защищённый мессенджер", font=('Segoe UI', 9), foreground='#5f6368').pack()

        username_frame = ttk.Frame(login)
        username_frame.pack(fill=tk.X, padx=20, pady=(10, 5))
        ttk.Label(username_frame, text="Имя пользователя:", font=('Segoe UI', 9)).pack(anchor='w')
        username_entry = ttk.Entry(username_frame, width=40, font=('Segoe UI', 10))
        username_entry.pack(fill=tk.X, pady=3)
        username_entry.focus()

        password_frame = ttk.Frame(login)
        password_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(password_frame, text="Пароль:", font=('Segoe UI', 9)).pack(anchor='w')
        password_entry = ttk.Entry(password_frame, show="*", width=40, font=('Segoe UI', 10))
        password_entry.pack(fill=tk.X, pady=3)

        email_frame = ttk.Frame(login)
        email_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(email_frame, text="Email (для регистрации):", font=('Segoe UI', 9)).pack(anchor='w')
        email_entry = ttk.Entry(email_frame, width=40, font=('Segoe UI', 10))
        email_entry.pack(fill=tk.X, pady=3)

        status_lbl = ttk.Label(login, text="Готов к работе", foreground="#5f6368", font=('Segoe UI', 9))
        status_lbl.pack(pady=15)

        def on_login() -> None:
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            if not username or not password:
                messagebox.showwarning("Предупреждение", "Введите имя пользователя и пароль", parent=login)
                return
            login_btn.config(state=tk.DISABLED)
            register_btn.config(state=tk.DISABLED)
            status_lbl.config(text="⏳ Подключение к серверу...")
            login.update()

            def _do_login() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    client = MessengerClient()
                    if not loop.run_until_complete(client.connect()):
                        raise ConnectionError("Не удалось подключиться к серверу")
                    success = loop.run_until_complete(client.login(username, password))
                    if success:
                        def keep_loop_alive():
                            try:
                                loop.run_forever()
                            except Exception as e:
                                logger.error(f"❌ Ошибка в keep_loop_alive: {e}", exc_info=True)
                            finally:
                                loop.close()

                        threading.Thread(target=keep_loop_alive, daemon=True, name="EventLoopThread").start()
                        self.root.after(0, lambda: self._on_login_success(client, loop, username))
                    else:
                        self.root.after(0, lambda: self._reset_login_ui(status_lbl, login_btn, register_btn, login,
                                                                        "Неверное имя пользователя или пароль"))
                except Exception as e:
                    self.root.after(0,
                                    lambda err=str(e): self._reset_login_ui(status_lbl, login_btn, register_btn, login,
                                                                            f"Ошибка: {err}"))

            threading.Thread(target=_do_login, daemon=True, name="LoginThread").start()

        def on_register() -> None:
            username = username_entry.get().strip()
            password = password_entry.get().strip()
            email = email_entry.get().strip()
            if not username or not password or len(password) < 6:
                messagebox.showwarning("Предупреждение", "Заполните все поля (пароль мин. 6 символов)", parent=login)
                return
            login_btn.config(state=tk.DISABLED)
            register_btn.config(state=tk.DISABLED)
            status_lbl.config(text="⏳ Регистрация...")
            login.update()

            def _do_register() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    client = MessengerClient()
                    if not loop.run_until_complete(client.connect()):
                        raise ConnectionError("Не удалось подключиться к серверу")
                    crypto = ClientCrypto()
                    public_key = crypto.get_public_key_pem()
                    success = loop.run_until_complete(client.register(username, email, password, public_key))
                    if success:
                        self.root.after(0, lambda: self._reset_login_ui(status_lbl, login_btn, register_btn, login,
                                                                        f"✅ '{username}' зарегистрирован!",
                                                                        is_info=True))
                    else:
                        self.root.after(0, lambda: self._reset_login_ui(status_lbl, login_btn, register_btn, login,
                                                                        "Не удалось зарегистрировать"))
                except Exception as e:
                    self.root.after(0,
                                    lambda err=str(e): self._reset_login_ui(status_lbl, login_btn, register_btn, login,
                                                                            f"Ошибка: {err}"))

            threading.Thread(target=_do_register, daemon=True, name="RegisterThread").start()

        button_frame = ttk.Frame(login)
        button_frame.pack(fill=tk.X, padx=20, pady=10)
        login_btn = ttk.Button(button_frame, text="🚪 Войти", command=on_login)
        login_btn.pack(fill=tk.X, pady=5)
        register_btn = ttk.Button(button_frame, text="📝 Регистрация", command=on_register)
        register_btn.pack(fill=tk.X, pady=5)
        login.bind('<Return>', lambda event: on_login())

        login.login_btn = login_btn
        login.register_btn = register_btn
        login.status_lbl = status_lbl
        logger.info("Окно входа готово к работе")

    def _reset_login_ui(self, status_lbl, login_btn, register_btn, login, message: str, is_info: bool = False) -> None:
        """Сброс UI окна входа после операции"""
        status_lbl.config(text="Готов к работе")
        login_btn.config(state=tk.NORMAL)
        register_btn.config(state=tk.NORMAL)
        if is_info:
            messagebox.showinfo("Успех", message, parent=login)
        else:
            messagebox.showerror("Ошибка", message, parent=login)

    def _on_login_success(self, client: MessengerClient, loop: asyncio.AbstractEventLoop, username: str) -> None:
        """Вызывается после успешного входа в систему"""
        self.client = client
        self.loop = loop
        self.username = username

        # ✅ КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: убеждаемся, что client.username установлен
        if not self.client.username:
            logger.warning(f"⚠️ client.username не установлен, исправляю...")
            self.client.username = username

        logger.info(f"✅ Клиент авторизован: {self.client.username}")

        self.client.message_callback = lambda msg: self._safe_callback(self.on_message, msg)
        self.client.file_callback = lambda info: self._safe_callback(self.on_file_received, info)

        try:
            self.known_public_keys[username] = client.crypto.get_public_key_pem()
            logger.info("🔑 Публичный ключ сохранён")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось получить публичный ключ: {e}")

        for widget in self.root.winfo_children():
            if isinstance(widget, tk.Toplevel):
                try:
                    widget.destroy()
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при закрытии окна входа: {e}")

        try:
            self.setup_main_ui()
            logger.info("✅ Основной интерфейс создан")
        except Exception as e:
            logger.error(f"❌ Ошибка при создании интерфейса: {e}", exc_info=True)
            return

        try:
            self._fetch_contact_public_keys()
            self.refresh_contacts()
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить контакты/ключи: {e}")

        self.show_status(f"👋 Добро пожаловать, {username}!")
        self._start_auto_refresh()

    # ========================================================================
    # 🎨 ОСНОВНОЙ ИНТЕРФЕЙС
    # ========================================================================
    def setup_main_ui(self) -> None:
        """Создание главного интерфейса мессенджера"""
        logger.info("Создание основного интерфейса")
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame, width=300)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left_frame.pack_propagate(False)

        left_header = ttk.Frame(left_frame)
        left_header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(left_header, text="💬 Контакты", font=('Segoe UI', 14, 'bold'), foreground='#1a73e8').pack(
            side=tk.LEFT)
        ttk.Button(left_header, text="🔄", width=3, command=self.refresh_contacts).pack(side=tk.RIGHT)

        self.chat_listbox = tk.Listbox(left_frame, height=20, font=('Segoe UI', 10), selectbackground='#e3f2fd',
                                       activestyle='none', borderwidth=1, relief='solid')
        self.chat_listbox.pack(fill=tk.BOTH, expand=True)
        self.chat_listbox.bind('<<ListboxSelect>>', self.on_chat_select)
        self.chat_listbox.bind("<Button-3>", self.show_contact_menu)

        search_container = ttk.LabelFrame(left_frame, text="🔍 Поиск контактов", padding=10)
        search_container.pack(fill=tk.X, pady=10)
        self.search_entry = ttk.Entry(search_container, font=('Segoe UI', 9))
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.search_entry.bind('<KeyRelease>', lambda e: self.search_contacts())
        ttk.Button(search_container, text="➕", width=3, command=self.search_contacts).pack(side=tk.RIGHT)

        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        title_container = ttk.Frame(right_frame)
        title_container.pack(fill=tk.X, pady=(0, 10))
        self.chat_title = ttk.Label(title_container, text="Выберите контакт для начала чата",
                                    font=('Segoe UI', 14, 'bold'), foreground='#5f6368')
        self.chat_title.pack()

        self.messages_area = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, height=20, state=tk.DISABLED,
                                                       font=('Segoe UI', 10), bg='#fafafa', padx=15, pady=15,
                                                       borderwidth=1, relief='solid')
        self.messages_area.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self._configure_message_tags()

        self.typing_label = ttk.Label(right_frame, text="", foreground='#5f6368', font=('Segoe UI', 9, 'italic'))
        self.typing_label.pack(anchor='w', pady=(0, 5))

        input_container = ttk.Frame(right_frame)
        input_container.pack(fill=tk.X)
        self.message_entry = ttk.Entry(input_container, font=('Segoe UI', 10))
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.message_entry.bind('<Return>', lambda e: self.send_message())
        ttk.Button(input_container, text="📎", width=3, command=self.attach_file).pack(side=tk.RIGHT, padx=(0, 5))
        ttk.Button(input_container, text="➤ Отправить", command=self.send_message).pack(side=tk.RIGHT)

        self.status_bar = ttk.Label(self.root, text="Готов", relief=tk.SUNKEN, anchor=tk.W, padding=5,
                                    font=('Segoe UI', 9))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        logger.info("✅ Основной интерфейс создан")

    def _configure_message_tags(self) -> None:
        """Настройка тегов для форматирования сообщений"""
        self.messages_area.tag_config("own", foreground="#1a73e8", justify="right", spacing3=5,
                                      font=('Segoe UI', 10, 'normal'))
        self.messages_area.tag_config("other", foreground="#202124", justify="left", spacing3=5,
                                      font=('Segoe UI', 10, 'normal'))
        self.messages_area.tag_config("system", foreground="#5f6368", justify="center", font=('Segoe UI', 9, 'italic'),
                                      spacing3=3)
        self.messages_area.tag_config("error", foreground="#d93025", justify="center",
                                      font=('Segoe UI', 9, 'bold italic'), spacing3=3)
        self.messages_area.tag_config("file_link", foreground="#0066CC", underline=True)

    # ========================================================================
    # 📬 ОБРАБОТКА СООБЩЕНИЙ И ФАЙЛОВ
    # ========================================================================
    def on_message(self, msg: Dict[str, Any]) -> None:
        logger.debug(f"📬 Получено сообщение: {msg.get('sender')}")
        sender = msg.get('sender')
        encrypted_data = msg.get('encrypted_data')
        logger.info(f"🔍 DEBUG: encrypted_data length: {len(encrypted_data)}")
        try:
            import base64
            pkg = base64.b64decode(encrypted_data.encode('utf-8'))
            logger.info(f"🔍 DEBUG: decoded package size: {len(pkg)} bytes")
            logger.info(f"🔍 DEBUG: expected >= 272 bytes (256+16+data)")
        except Exception as e:
            logger.error(f"🔍 DEBUG: base64 decode error: {e}")
        timestamp = msg.get('timestamp', datetime.now(timezone.utc).isoformat())

        if not sender or not encrypted_data:
            logger.warning(f"⚠️ Неверный формат сообщения: {_sanitize_for_log(msg)}")
            return

        decrypted_text = "❌ Ошибка расшифровки"
        try:
            sender_public_key = self.known_public_keys.get(sender)
            if not sender_public_key:
                logger.info(f"🔑 Запрос публичного ключа для {sender}")
                sender_public_key = self._run_async(self.client.get_public_key(sender),
                                                    timeout=GUIConstants.TIMEOUT_NORMAL)
                if sender_public_key and self._validate_public_key(sender_public_key):
                    self.known_public_keys[sender] = sender_public_key
                    logger.info(f"✅ Публичный ключ получен для {sender}")
                else:
                    logger.warning(f"⚠️ Не удалось получить/валидировать ключ для {sender}")

            if sender_public_key:
                try:
                    decrypted_text = self._decrypt_in_thread(encrypted_data, sender_public_key)
                    logger.debug(f"✅ Сообщение расшифровано: {len(decrypted_text)} символов")
                except Exception as decrypt_error:
                    logger.error(f"❌ Ошибка расшифровки: {decrypt_error}", exc_info=True)
                    decrypted_text = f"⚠️ Ошибка: {str(decrypt_error)[:50]}"
            else:
                decrypted_text = "⚠️ Нет ключа для расшифровки"
        except Exception as e:
            logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
            decrypted_text = f"❌ Ошибка: {str(e)[:50]}"

        if self.current_chat == sender:
            self.root.after(0, lambda: self.display_new_message(sender, decrypted_text, timestamp, status="delivered"))
            self.last_message_time[sender] = timestamp
        else:
            self.root.after(0, lambda: self.refresh_contacts())
        self.root.after(0, lambda: self.show_status(f"📩 Новое сообщение от {sender}"))
        self.root.after(0, self._play_notification_sound)

    def on_file_received(self, file_info: Dict[str, Any]) -> None:
        sender = file_info.get('sender')
        filename = file_info.get('filename')
        file_size = file_info.get('file_size', 0)
        file_id = file_info.get('file_id')

        logger.info(f"📁 УВЕДОМЛЕНИЕ: {filename} от {sender} (ID: {file_id})")

        if file_id is None:
            logger.error(f"❌ Нет file_id в уведомлении!")
            self.root.after(0, lambda: self.show_error("Файл получен без ID"))
            return

        self.root.after(0, lambda: self.show_status(f"📁 Файл от {sender}: {filename}"))
        self.root.after(0, self._play_notification_sound)

        if self.current_chat == sender:
            def display_file():
                self.messages_area.config(state=tk.NORMAL)
                ts = datetime.now().strftime("%H:%M")
                self.messages_area.insert(tk.END, f"[{ts}] {sender}:\n", "other")
                self.messages_area.insert(tk.END, f"   📎 Файл: {filename}\n", "other")
                self.messages_area.insert(tk.END, f"   📊 Размер: {self._format_file_size(file_size)}\n", "other")
                self._insert_download_link(filename, str(file_id), sender)
                self.messages_area.insert(tk.END, "\n\n")
                self.messages_area.config(state=tk.DISABLED)
                self.messages_area.see(tk.END)

            self.root.after(0, display_file)
            self.root.after(2000, lambda: self.load_chat_history())
        else:
            self.root.after(0, lambda: self.refresh_contacts())

    def display_new_message(self, sender: str, text: str, timestamp: Optional[str] = None,
                            status: Optional[str] = None) -> None:
        self.messages_area.config(state=tk.NORMAL)
        ts = timestamp[:16] if timestamp and len(timestamp) > 16 else datetime.now().strftime("%H:%M")
        tag = "own" if sender == "Вы" else "other"
        message_text = f"[{ts}] {sender}:\n{text}"
        if status:
            indicators = {"sending": " ⏳", "sent": " ✓", "delivered": " ✓✓", "read": " 👁️", "failed": " ❌"}
            message_text += indicators.get(status, "")
        self.messages_area.insert(tk.END, f"{message_text}\n\n", tag)
        self.messages_area.config(state=tk.DISABLED)
        self.messages_area.see(tk.END)

    def display_system_message(self, text: str) -> None:
        self.messages_area.config(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M")
        self.messages_area.insert(tk.END, f"[{ts}] ℹ️ {text}\n\n", "system")
        self.messages_area.config(state=tk.DISABLED)
        self.messages_area.see(tk.END)

    def load_chat_history(self) -> None:
        if not self.current_chat or not self.client:
            return
        self.messages_area.config(state=tk.NORMAL)
        self.messages_area.delete(1.0, tk.END)
        self.messages_area.insert(tk.END, "⏳ Загрузка истории...\n")
        self.messages_area.config(state=tk.DISABLED)

        def _load() -> None:
            try:
                msgs = self._run_async(self.client.get_chat_history(self.current_chat),
                                       timeout=GUIConstants.TIMEOUT_NORMAL)
                if msgs:
                    self.root.after(0, lambda: self.display_messages(msgs))
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки истории: {e}", exc_info=True)
                self.root.after(0, lambda: self.show_error("Не удалось загрузить историю"))

        threading.Thread(target=_load, daemon=True).start()

    def on_chat_select(self, event: Any = None) -> None:
        sel = self.chat_listbox.curselection()
        if not sel:
            return
        item = self.chat_listbox.get(sel[0])
        self.current_chat = item.split(' ', 1)[-1] if ' ' in item else item
        logger.info(f"💬 Выбран чат с {self.current_chat}")
        self.chat_title.config(text=f"💬 Чат с {self.current_chat}")
        self.last_message_time[self.current_chat] = ''
        self.load_chat_history()

    def display_messages(self, msgs: List[Dict[str, Any]]) -> None:
        self.messages_area.config(state=tk.NORMAL)
        self.messages_area.delete(1.0, tk.END)
        if not msgs:
            self.messages_area.insert(tk.END, "\n📭 История пуста\n\n", "system")
        else:
            last_timestamp = ''
            file_count = 0
            for m in msgs:
                ts_raw = m.get('timestamp', '')
                ts = ts_raw[:16] if isinstance(ts_raw, str) and len(ts_raw) > 16 else str(ts_raw)
                last_timestamp = ts_raw

                if m.get('is_file', False):
                    filename = m.get('filename', 'unknown')
                    file_size = m.get('file_size', 0)
                    file_id = m.get('id') or m.get('file_id')
                    sender = m.get('sender', 'Неизвестно')
                    is_own = m.get('is_own', False)
                    tag = "own" if is_own else "other"
                    sender_label = "Вы" if is_own else sender
                    logger.info(f"📎 ФАЙЛ: {filename} | ID: {file_id}")

                    self.messages_area.insert(tk.END, f"[{ts}] {sender_label}:\n", tag)
                    self.messages_area.insert(tk.END, f"   📎 Файл: {filename}\n", tag)
                    self.messages_area.insert(tk.END, f"   📊 Размер: {self._format_file_size(file_size)}\n", tag)

                    if file_id is not None and str(file_id) != 'None':
                        self._insert_download_link(filename, str(file_id), sender)
                        file_count += 1
                    else:
                        self.messages_area.insert(tk.END, "   ⚠️ Файл недоступен\n", "error")
                    self.messages_area.insert(tk.END, "\n\n")
                else:
                    # Чужие или свои сообщения
                    msg_id = m.get('id')  # ← ← ← ИЗВЛЕЧЬ msg_id ПЕРЕД использованием!

                    if m.get('is_own', False):
                        # Свои сообщения — проверяем с приведением типов
                        if msg_id is not None:
                            # Пробуем найти по строковому ключу (как сохраняется при отправке)
                            msg_id_str = str(msg_id)
                            if msg_id_str in self.sent_messages:
                                text = self.sent_messages[msg_id_str]
                            elif msg_id in self.sent_messages:  # На случай, если ключ числовой
                                text = self.sent_messages[msg_id]
                            else:
                                text = m.get('text', m.get('encrypted_data', '🔒 Зашифрованное сообщение'))
                                logger.debug(
                                    f"⚠️ Сообщение не найдено в кэше: msg_id={msg_id} (type={type(msg_id).__name__})")
                        else:
                            text = m.get('text', m.get('encrypted_data', '🔒 Зашифрованное сообщение'))
                        self.messages_area.insert(tk.END, f"[{ts}] Вы:\n{text}\n\n", "own")
                    else:
                        # Чужие сообщения
                        text = m.get('text', m.get('encrypted_data', ''))
                        if m.get('is_encrypted', False):
                            try:
                                sender_key = self.known_public_keys.get(m.get('sender', ''))
                                if sender_key:
                                    text = self.client.crypto.decrypt_message(text, sender_key)
                                else:
                                    text = "⚠️ Нет ключа"
                            except Exception as e:
                                text = f"⚠️ Не расшифровано: {str(e)[:50]}"
                        self.messages_area.insert(tk.END, f"[{ts}] {m.get('sender')}:\n{text}\n\n", "other")

    def _download_file_by_id(self, file_id: str, filename: str, sender: str) -> None:
        save_path = filedialog.asksaveasfilename(defaultextension=".*", initialfile=filename,
                                                 title="Сохранить файл как", initialdir=str(self.download_dir),
                                                 filetypes=[("Все файлы", "*.*"),
                                                            ("Изображения", "*.jpg *.jpeg *.png *.gif *.bmp"),
                                                            ("Документы", "*.pdf *.doc *.docx *.txt"),
                                                            ("Архивы", "*.zip *.rar *.7z")])
        if not save_path:
            logger.info("⚠️ Скачивание отменено")
            self.root.after(0, lambda: self.show_status("Скачивание отменено"))
            return

        def _download():
            try:
                self.root.after(0, lambda: self.show_status(f"📥 Скачивание {filename}..."))
                file_data = self._run_async(self.client.get_file_by_id(file_id), timeout=GUIConstants.TIMEOUT_LONG)
                if file_data and 'content' in file_data:
                    file_content = base64.b64decode(file_data['content'])
                    with open(save_path, 'wb') as f:
                        f.write(file_content)
                    logger.info(f"✅ Файл скачан: {save_path}")
                    self.root.after(0, lambda: messagebox.showinfo("Успех",
                                                                   f"Файл сохранён:\n{save_path}\n\nРазмер: {self._format_file_size(len(file_content))}"))
                    self.root.after(0, lambda: self.show_status(f"✅ Файл скачан: {filename}"))
                else:
                    self.root.after(0, lambda: self.show_error("Не удалось получить файл"))
            except Exception as e:
                logger.error(f"❌ Ошибка скачивания: {e}", exc_info=True)
                self.root.after(0, lambda: self.show_error(f"Ошибка: {e}"))

        threading.Thread(target=_download, daemon=True).start()

    def send_message(self) -> None:
        text = self.message_entry.get().strip()
        if not text or not self.current_chat:
            if not text:
                logger.warning("⚠️ Пустое сообщение")
            else:
                messagebox.showwarning("Предупреждение", "Выберите контакт для отправки сообщения")
            return

        logger.info(f"📤 Отправка сообщения для {self.current_chat}")
        self.display_new_message("Вы", text, status="sending")
        self.message_entry.delete(0, tk.END)

        def _send() -> None:
            try:
                # 🔑 1. Получаем публичный ключ получателя
                recipient_public_key = self.known_public_keys.get(self.current_chat)

                if not recipient_public_key:
                    logger.info(f"🔑 Ключ не в кэше, запрашиваю у сервера для {self.current_chat}")
                    recipient_public_key = self._run_async(
                        self.client.get_public_key(self.current_chat),
                        timeout=GUIConstants.TIMEOUT_SHORT
                    )
                    logger.debug(
                        f"🔍 get_public_key вернул: {type(recipient_public_key)}, len={len(recipient_public_key) if recipient_public_key else 0}")

                    if recipient_public_key and self.client.crypto._validate_public_key(recipient_public_key):
                        self.known_public_keys[self.current_chat] = recipient_public_key
                        logger.info(f"✅ Ключ получен и сохранён для {self.current_chat}")
                    else:
                        logger.error(f"❌ Не удалось получить/валидировать ключ для {self.current_chat}")
                        self.root.after(0, lambda: self.show_error(f"Нет ключа шифрования для {self.current_chat}"))
                        return

                # 🔐 2. Шифруем сообщение
                logger.debug(f"🔐 Шифрую сообщение ({len(text)} символов) ключом ({len(recipient_public_key)} символов)")
                try:
                    encrypted_data = self.client.crypto.encrypt_message(text, recipient_public_key)
                    logger.debug(f"✅ encrypt_message вернул: {len(encrypted_data) if encrypted_data else 0} символов")
                except Exception as encrypt_err:
                    logger.error(f"❌ encrypt_message упал: {type(encrypt_err).__name__}: {encrypt_err}", exc_info=True)
                    self.root.after(0, lambda: self.show_error(f"Ошибка шифрования: {str(encrypt_err)[:50]}"))
                    return

                if not encrypted_data:
                    logger.error("❌ encrypted_data пустой после шифрования!")
                    self.root.after(0, lambda: self.show_error("Ошибка: пустые данные после шифрования"))
                    return

                # 📤 3. Проверяем соединение перед отправкой
                if not self.client or not self.client.connected:
                    logger.error("❌ Нет активного соединения с сервером")
                    self.root.after(0, lambda: self.show_error("Нет соединения с сервером"))
                    return

                logger.debug(f"📤 Вызываю client.send_message (connected={self.client.connected})")

                # 4. Отправляем через клиент
                response = self._run_async(
                    self.client.send_message(self.current_chat, encrypted_data),
                    timeout=GUIConstants.TIMEOUT_NORMAL
                )

                logger.debug(f"📥 client.send_message вернул: {response}")

                # ✅ 5. Обработка ответа
                if response and response.get("success"):
                    message_id = response.get("message_id")
                    if message_id:
                        self.root.after(0, lambda: self._store_sent_message(str(message_id), text))
                    self.root.after(0, lambda: self.display_new_message("Вы", text, status="sent"))
                    logger.info(f"✅ Сообщение отправлено успешно: {message_id}")
                elif response is None:
                    logger.error("❌ send_message вернул None (таймаут или ошибка соединения)")
                    self.root.after(0, lambda: self.show_error("Таймаут или ошибка соединения"))
                else:
                    logger.error(f"❌ Сервер ответил с ошибкой: {response}")
                    error_msg = response.get("message", "Неизвестная ошибка")
                    self.root.after(0, lambda: self.show_error(f"Ошибка сервера: {error_msg}"))

            except asyncio.TimeoutError:
                logger.error("⏰ Таймаут операции отправки")
                self.root.after(0, lambda: self.show_error("Таймаут отправки"))
            except ValueError as e:
                logger.error(f"❌ Ошибка криптографии: {e}", exc_info=True)
                self.root.after(0, lambda: self.show_error(f"Ошибка шифрования: {str(e)[:50]}"))
            except Exception as e:
                logger.error(f"❌ Ошибка в _send: {type(e).__name__}: {e}", exc_info=True)
                self.root.after(0, lambda: self.show_error(f"Не удалось отправить: {str(e)[:50]}"))

        threading.Thread(target=_send, daemon=True).start()

    def _store_sent_message(self, message_id: str, text: str) -> None:
        """Сохраняет отправленный текст сообщения по его ID."""
        # Безопасная инициализация на всякий случай
        if not hasattr(self, 'sent_messages'):
            self.sent_messages = {}
        # message_id приходит как строка (UUID), не как int
            msg_id_str = str(message_id)
            self.sent_messages[msg_id_str] = text
            logger.debug(f"💾 Сообщение сохранено в кэш: msg_id={msg_id_str[:8]}...")

    def attach_file(self) -> None:
        if not self.current_chat:
            messagebox.showwarning("Предупреждение", "Сначала выберите контакт")
            return
        path = filedialog.askopenfilename(title="Выберите файл для отправки", filetypes=[("Все файлы", "*.*"),
                                                                                         ("Изображения",
                                                                                          "*.jpg *.jpeg *.png *.gif *.bmp"),
                                                                                         ("Документы",
                                                                                          "*.pdf *.doc *.docx *.txt"),
                                                                                         ("Архивы",
                                                                                          "*.zip *.rar *.7z")])
        if not path:
            logger.info("⚠️ Выбор файла отменён")
            return
        filename = os.path.basename(path)
        logger.info(f"📁 Выбор файла: {filename}")
        self.show_status(f"📄 Чтение файла {filename}...")

        def read_and_send() -> None:
            try:
                with open(path, 'rb') as f:
                    file_content = f.read()
                file_size = len(file_content)
                logger.info(f"📊 Размер файла: {self._format_file_size(file_size)}")
                if file_size > GUIConstants.MAX_FILE_SIZE:
                    self.root.after(0, lambda: self.show_error(
                        f"Файл слишком большой!\nРазмер: {self._format_file_size(file_size)}\nМаксимум: 100 MB"))
                    return
                self.root.after(0, lambda: self.show_status(f"🔄 Кодирование {filename}..."))
                encoded_data = base64.b64encode(file_content).decode('ascii')
                self.root.after(0, lambda: self.show_status(f"📤 Отправка {filename}..."))
                future = asyncio.run_coroutine_threadsafe(
                    self.client.send_file(recipient=self.current_chat, file_path=path, file_name=filename,
                                          file_size=file_size, encrypted_data=encoded_data), self.loop)
                result = future.result(timeout=GUIConstants.TIMEOUT_LONG)
                if result:
                    self.root.after(0, lambda: self.show_status(f"✅ Файл отправлен"))
                    self.root.after(0, lambda: self.display_system_message(f"📎 Файл отправлен: {filename}"))
                else:
                    self.root.after(0, lambda: self.show_error("Не удалось отправить файл"))
            except FileNotFoundError:
                logger.error(f"❌ Файл не найден: {path}")
                self.root.after(0, lambda: self.show_error("Файл не найден"))
            except Exception as e:
                logger.error(f"❌ Ошибка отправки файла: {e}", exc_info=True)
                self.root.after(0, lambda err=str(e): self.show_error(f"Ошибка: {err}"))

        threading.Thread(target=read_and_send, daemon=True).start()

    def _format_file_size(self, size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"

    def _insert_download_link(self, filename: str, file_id: str, sender: str) -> None:
        logger.info(f"🔗 Создание гиперссылки: {filename} (ID: {file_id})")
        tag_name = f"hyperlink_{file_id}"
        self.messages_area.tag_config(tag_name, foreground="#0066CC", underline=True, font=('Segoe UI', 10, 'bold'))
        self.messages_area.insert(tk.END, "   ⬇️ НАЖМИТЕ ЧТОБЫ СКАЧАТЬ", tag_name)
        self.messages_area.insert(tk.END, "\n")

        def on_click(event):
            logger.info(f"🖱️ КЛИК НА ГИПЕРССЫЛКУ: {filename} (ID: {file_id})")
            self._download_file_by_id(file_id, filename, sender)

        self.messages_area.tag_bind(tag_name, "<Button-1>", on_click)

        def on_enter(event):
            self.messages_area.tag_config(tag_name, foreground="#003366")
            self.messages_area.config(cursor="hand2")

        def on_leave(event):
            self.messages_area.tag_config(tag_name, foreground="#0066CC")
            self.messages_area.config(cursor="")

        self.messages_area.tag_bind(tag_name, "<Enter>", on_enter)
        self.messages_area.tag_bind(tag_name, "<Leave>", on_leave)
        logger.info(f"✅ ГИПЕРССЫЛКА создана и активна (ID: {file_id})")

    # ========================================================================
    # 👥 УПРАВЛЕНИЕ КОНТАКТАМИ
    # ========================================================================
    def refresh_contacts(self) -> None:
        if self.client is None or self.loop is None or not self.client.is_authenticated():
            self.root.after(1000, self.refresh_contacts)
            return

        def _refresh() -> None:
            contacts = self._run_async(self.client.get_contacts(), timeout=GUIConstants.TIMEOUT_SHORT)
            if contacts is not None:
                self.root.after(0, lambda: self.update_contact_list(contacts))

        threading.Thread(target=_refresh, daemon=True).start()

    def update_contact_list(self, contacts: List[Dict[str, Any]]) -> None:
        self.chat_listbox.delete(0, tk.END)
        for c in contacts:
            username = c.get('username', 'Unknown')
            is_online = c.get('online', False)
            status_icon = "🟢" if is_online else "⚫"
            self.chat_listbox.insert(tk.END, f"{status_icon} {username}")
        logger.info(f"📋 Список контактов обновлён: {len(contacts)} контактов")

    def search_contacts(self) -> None:
        if self.search_after_id:
            self.root.after_cancel(self.search_after_id)

        def _do_search() -> None:
            query = self.search_entry.get().strip()
            if not query or not self.client:
                return

            def _search_thread() -> None:
                results = self._run_async(self.client.search_users(query), timeout=GUIConstants.TIMEOUT_SHORT)
                if results:
                    self.root.after(0, lambda: self.show_search_results(results))

            threading.Thread(target=_search_thread, daemon=True).start()

        self.search_after_id = self.root.after(GUIConstants.SEARCH_DEBOUNCE_MS, _do_search)

    def show_search_results(self, results: List[Dict[str, Any]]) -> None:
        if not results:
            messagebox.showinfo("Поиск", "Ничего не найдено")
            return
        win = tk.Toplevel(self.root)
        win.title("Результаты поиска")
        win.geometry("450x350")
        win.transient(self.root)
        win.grab_set()
        ttk.Label(win, text="Найденные пользователи:", font=('Segoe UI', 11, 'bold')).pack(pady=10)
        listbox = tk.Listbox(win, font=('Segoe UI', 10))
        listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        for user in results:
            listbox.insert(tk.END, user.get('username', 'Unknown'))

        def add_selected() -> None:
            sel = listbox.curselection()
            if not sel:
                return
            username = listbox.get(sel[0])

            def _add() -> None:
                success = self._run_async(self.client.add_contact(username), timeout=GUIConstants.TIMEOUT_SHORT)
                if success:
                    self.root.after(0, lambda: messagebox.showinfo("Успех", f"{username} добавлен в контакты"))
                    self.root.after(0, self.refresh_contacts)
                else:
                    self.root.after(0, lambda: messagebox.showerror("Ошибка", "Не удалось добавить контакт"))
                win.destroy()

            threading.Thread(target=_add, daemon=True).start()

        ttk.Button(win, text="➕ Добавить в контакты", command=add_selected).pack(pady=10)
        ttk.Button(win, text="Закрыть", command=win.destroy).pack(pady=5)

    def show_contact_menu(self, event: tk.Event) -> None:
        sel = self.chat_listbox.curselection()
        if not sel:
            return
        item = self.chat_listbox.get(sel[0])
        contact = item.split(' ', 1)[-1] if ' ' in item else item
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="🗑️ Удалить контакт", command=lambda: self._on_remove_contact_selected(contact))
        menu.post(event.x_root, event.y_root)

    def _on_remove_contact_selected(self, contact_username: str) -> None:
        if not messagebox.askyesno("Подтверждение",
                                   f"Удалить контакт '{contact_username}'?\n\nЭто действие нельзя отменить."):
            return

        def _remove() -> None:
            try:
                success = self._run_async(self.client.remove_contact(contact_username),
                                          timeout=GUIConstants.TIMEOUT_SHORT)
                if success:
                    self.root.after(0, self.refresh_contacts)
                    self.root.after(0, lambda: self.show_status(f"Контакт {contact_username} удалён"))
                else:
                    self.root.after(0, lambda: messagebox.showerror("Ошибка", "Не удалось удалить контакт"))
            except Exception as e:
                logger.error(f"❌ Ошибка удаления контакта: {e}", exc_info=True)
                self.root.after(0, lambda: self.show_error("Ошибка при удалении"))

        threading.Thread(target=_remove, daemon=True).start()

    def _fetch_contact_public_keys(self) -> None:
        def _fetch() -> None:
            try:
                contacts = self._run_async(self.client.get_contacts(), timeout=GUIConstants.TIMEOUT_NORMAL)
                if contacts:
                    logger.info(f"📋 Загружено {len(contacts)} контактов")
                    for contact in contacts:
                        username = contact.get('username')
                        if username and username not in self.known_public_keys:
                            logger.info(f"🔑 Загрузка ключа для {username}")
                            key = self._run_async(self.client.get_public_key(username),
                                                  timeout=GUIConstants.TIMEOUT_NORMAL)
                            if key and self._validate_public_key(key):
                                self.known_public_keys[username] = key
                                logger.info(f"✅ Ключ загружен: {username}")
                            else:
                                logger.warning(f"⚠️ Не удалось загрузить/валидировать ключ: {username}")
                else:
                    logger.info("📋 Контактов нет")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки ключей: {e}", exc_info=True)

        fetch_thread = threading.Thread(target=_fetch, daemon=False)
        fetch_thread.start()
        fetch_thread.join(timeout=30)
        logger.info("🔑 Загрузка ключей завершена")

    # ========================================================================
    # 🔄 АВТООБНОВЛЕНИЕ И УВЕДОМЛЕНИЯ
    # ========================================================================
    def _start_auto_refresh(self) -> None:
        def _refresh_active_chat() -> None:
            if self.current_chat and self.client and self.client.is_authenticated():
                def _load() -> None:
                    try:
                        msgs = self._run_async(self.client.get_chat_history(self.current_chat),
                                               timeout=GUIConstants.TIMEOUT_NORMAL)
                        if msgs:
                            last_time = self.last_message_time.get(self.current_chat, '')
                            if any(m.get('timestamp', '') > last_time for m in msgs):
                                self.root.after(0, lambda: self.display_messages(msgs))
                    except Exception as e:
                        logger.debug(f"⚠️ Автообновление: {e}")

                threading.Thread(target=_load, daemon=True).start()
            self._refresh_job = self.root.after(GUIConstants.AUTO_REFRESH_INTERVAL, _refresh_active_chat)

        self._refresh_job = self.root.after(1000, _refresh_active_chat)
        logger.info("🔄 Автообновление чата запущено (интервал: 3 сек)")

    def show_typing_indicator(self, username: str, is_typing: bool) -> None:
        if self.typing_label:
            self.typing_label.config(text=f"✍️ {username} печатает..." if is_typing else "")

    def show_status(self, msg: str) -> None:
        if self.status_bar:
            self.status_bar.config(text=msg)
            self.root.after(GUIConstants.STATUS_MESSAGE_DURATION, lambda: self.status_bar.config(text="Готов"))

    def show_error(self, msg: str) -> None:
        if self.status_bar:
            self.status_bar.config(text=f"❌ Ошибка: {msg}")
        messagebox.showerror("Ошибка", msg)
        logger.error(f"GUI Error: {msg}")

    def _play_notification_sound(self) -> None:
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except ImportError:
            try:
                os.system('afplay /System/Library/Sounds/Glass.aiff 2>/dev/null || echo -e "\\a"')
            except Exception:
                pass

    # ========================================================================
    # 🚪 ЗАКРЫТИЕ ПРИЛОЖЕНИЯ
    # ========================================================================
    def on_closing(self) -> None:
        logger.info("=" * 80)
        logger.info("Закрытие приложения")
        logger.info("=" * 80)
        if not messagebox.askyesno("Выход",
                                   "Вы действительно хотите выйти?\n\nВсе несохранённые данные будут потеряны."):
            logger.info("⚠️ Пользователь отменил выход")
            return

        for attr in ['_refresh_job', 'search_after_id']:
            if hasattr(self, attr) and getattr(self, attr) is not None:
                try:
                    self.root.after_cancel(getattr(self, attr))
                    setattr(self, attr, None)
                    logger.info(f"🛑 Таймер {attr} остановлен")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось остановить {attr}: {e}")

        if self.client is not None and self.loop is not None:
            try:
                if self.loop.is_running() and not self.loop.is_closed():
                    logger.info("🔌 Отключение клиента от сервера...")
                    disconnect_future = asyncio.run_coroutine_threadsafe(self.client.disconnect(), self.loop)
                    try:
                        disconnect_future.result(timeout=3)
                    except (concurrent.futures.TimeoutError, Exception) as e:
                        logger.warning(f"⚠️ Таймаут/ошибка при отключении: {e}")
                    self.loop.call_soon_threadsafe(self.loop.stop)
                    logger.info("🛑 Event loop остановлен")
                else:
                    logger.warning("⚠️ Event loop не активен или уже закрыт")
            except Exception as e:
                logger.error(f"⚠️ Ошибка при отключении клиента: {e}", exc_info=True)

        for cache_name in ['known_public_keys', 'last_message_time', 'message_status_map']:
            if hasattr(self, cache_name):
                getattr(self, cache_name).clear()
                logger.debug(f"🧹 Кэш {cache_name} очищен")

        try:
            self.root.destroy()
            logger.info("✅ Окно приложения закрыто")
        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии окна: {e}", exc_info=True)
        logger.info("👋 Приложение закрыто успешно")
        logger.info("=" * 80)

    def run(self) -> None:
        logger.info("=" * 80)
        logger.info("Запуск главного цикла Tkinter")
        logger.info("=" * 80)
        try:
            self.root.mainloop()
        except Exception as e:
            logger.error(f"❌ Ошибка в mainloop: {e}", exc_info=True)
        finally:
            logger.info("Главный цикл завершён")
            logger.info("=" * 80)


# ============================================================================
# 🚀 РАЗДЕЛ 7: ТОЧКА ВХОДА
# ============================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("🚀 Secure Messenger GUI v1.1.0")
    print("=" * 80)
    print("Запуск приложения...")
    try:
        gui = MessengerGUI()
        gui.run()
    except KeyboardInterrupt:
        logger.info("🛑 Приложение остановлено пользователем")
    except Exception as e:
        error_msg = str(e)
        logger.exception(f"❌ Критическая ошибка: {e}")
        try:
            messagebox.showerror("Критическая ошибка", f"Приложение не может быть запущено:\n\n{error_msg}")
        except Exception:
            pass
    finally:
        print("\n" + "=" * 80)
        print("Приложение завершено")
        print("=" * 80)
