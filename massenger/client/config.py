#!/usr/bin/env python3
"""Конфигурация клиента"""

class ClientConfig:
    # Сервер
    SERVER_HOST = "localhost"
    SERVER_PORT = 8765
    
    # Устройство
    DEVICE_NAME = "Desktop Client"
    DEVICE_TYPE = "desktop"
    
    # Таймауты
    REQUEST_TIMEOUT = 10
    CONNECT_TIMEOUT = 10
    
    # Лимиты
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
    MESSAGE_HISTORY_LIMIT = 100