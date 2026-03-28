#!/usr/bin/env python3
"""
CryptoManager для сервера — хэширование паролей
Шифрование E2E происходит на клиенте, сервер только хранит ключи
"""

import hashlib
import hmac  # ✅ compare_digest находится в hmac, не в hashlib!
import os
import base64  # ✅ Добавлен импорт base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CryptoManager:
    """Крипто-менеджер сервера"""

    def __init__(self, salt_length: int = 32, iterations: int = 100000):
        """
        Инициализация крипто-менеджера

        Args:
            salt_length: Длина соли в байтах
            iterations: Количество итераций PBKDF2
        """
        self.salt_length = salt_length
        self.iterations = iterations
        logger.info("✅ CryptoManager инициализирован")

    def hash_password(self, password: str) -> str:
        """
        Хэширование пароля с солью

        Args:
            password: Исходный пароль

        Returns:
            str: Хэш в формате "salt$hash"
        """
        # Генерируем случайную соль
        salt = os.urandom(self.salt_length)

        # Создаём хэш с использованием PBKDF2-HMAC-SHA256
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            self.iterations
        )

        # Возвращаем в формате "salt$hash" (оба в base64)
        salt_b64 = base64.b64encode(salt).decode('ascii')
        hash_b64 = base64.b64encode(password_hash).decode('ascii')

        return f"{salt_b64}${hash_b64}"

    def verify_password(self, password: str, stored_hash: str) -> bool:
        """
        Проверка пароля против сохранённого хэша

        Args:
            password: Введённый пароль
            stored_hash: Сохранённый хэш в формате "salt$hash"

        Returns:
            bool: True если пароль верный
        """
        try:
            # Разделяем соль и хэш
            salt_b64, hash_b64 = stored_hash.split('$')
            salt = base64.b64decode(salt_b64)
            stored_password_hash = base64.b64decode(hash_b64)

            # Вычисляем хэш введённого пароля с той же солью
            password_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                self.iterations
            )

            # ✅ ИСПРАВЛЕНО: hmac.compare_digest вместо hashlib.compare_digest
            return hmac.compare_digest(password_hash, stored_password_hash)

        except Exception as e:
            logger.error(f"Ошибка проверки пароля: {e}", exc_info=True)
            return False

    def generate_salt(self) -> str:
        """Генерация случайной соли"""
        return base64.b64encode(os.urandom(self.salt_length)).decode('ascii')