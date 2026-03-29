#!/usr/bin/env python3
"""Конфигурация сервера"""


from pathlib import Path

class Config:
    # Сервер
    HOST = "localhost"
    PORT = 8765
    
    # База данных
    DB_PATH = Path(__file__).parent / "messenger.db"
    
    # Загрузка файлов
    UPLOAD_DIR = Path(__file__).parent.parent / "server" / "uploads"
    
    # Логирование
    LOG_LEVEL = "INFO"
    LOG_FILE = Path(__file__).parent.parent / "messenger_server.log"
    
    # Лимиты
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    
    # Таймауты
    PING_INTERVAL = 20
    PING_TIMEOUT = 10