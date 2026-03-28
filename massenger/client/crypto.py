#!/usr/bin/env python3
"""
ClientCrypto — Модуль криптографии для Secure Messenger
Использует библиотеку cryptography для RSA + AES шифрования
"""

import base64
import os
import logging
from typing import Tuple, Optional
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class ClientCrypto:
    """
    Криптографический модуль для end-to-end шифрования
    Схема: RSA для обмена ключами + AES-256-CBC для данных
    """

    def __init__(self):
        """Генерация пары ключей при инициализации"""
        self._private_key = None
        self._public_key = None
        self._public_key_pem = None
        self._generate_keys()

    def _generate_keys(self) -> None:
        """Генерация RSA пары ключей (2048 бит)"""
        try:
            self._private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            self._public_key = self._private_key.public_key()

            self._public_key_pem = self._public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')

            logger.debug("✅ Ключи сгенерированы успешно")
        except Exception as e:
            logger.error(f"❌ Ошибка генерации ключей: {e}", exc_info=True)
            raise

    def get_public_key_pem(self) -> str:
        """Возвращает публичный ключ в PEM формате"""
        return self._public_key_pem

    def generate_identity_keys(self) -> str:
        """Алиас для get_public_key_pem (для совместимости)"""
        return self.get_public_key_pem()

    def encrypt_message(self, message: str, recipient_public_key_pem: str) -> str:
        """
        Шифрование сообщения: гибридная схема RSA + AES-256-CBC
        """
        try:
            recipient_pub_key = serialization.load_pem_public_key(
                recipient_public_key_pem.encode('utf-8'),
                backend=default_backend()
            )

            aes_key = os.urandom(32)
            iv = os.urandom(16)

            message_bytes = message.encode('utf-8')
            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
            encryptor = cipher.encryptor()

            padding_length = 16 - (len(message_bytes) % 16)
            padded_message = message_bytes + bytes([padding_length] * padding_length)
            encrypted_message = encryptor.update(padded_message) + encryptor.finalize()

            encrypted_aes_key = recipient_pub_key.encrypt(
                aes_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )

            package = encrypted_aes_key + iv + encrypted_message
            return base64.b64encode(package).decode('utf-8')

        except Exception as e:
            logger.error(f"❌ Ошибка шифрования сообщения: {e}", exc_info=True)
            raise

    def decrypt_message(self, encrypted_data: str, sender_public_key_pem: str = None) -> str:
        """
        Расшифровка сообщения с ДИНАМИЧЕСКИМ размером ключа
        """
        try:
            package = base64.b64decode(encrypted_data.encode('utf-8'))

            # 🔑 ДИНАМИЧЕСКИЙ расчёт размера зашифрованного AES-ключа
            rsa_key_size_bytes = self._private_key.key_size // 8

            if len(package) < rsa_key_size_bytes + 16:
                raise ValueError(f"Пакет повреждён: {len(package)} < {rsa_key_size_bytes + 16}")

            # ✅ Извлечение с динамическими смещениями
            encrypted_aes_key = package[:rsa_key_size_bytes]
            iv = package[rsa_key_size_bytes:rsa_key_size_bytes + 16]
            encrypted_message = package[rsa_key_size_bytes + 16:]

            aes_key = self._private_key.decrypt(
                encrypted_aes_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )

            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            padded_message = decryptor.update(encrypted_message) + decryptor.finalize()

            padding_length = padded_message[-1]
            if not 1 <= padding_length <= 16:
                raise ValueError(f"Некорректный padding: {padding_length}")

            message = padded_message[:-padding_length]
            return message.decode('utf-8')

        except ValueError as e:
            logger.error(f"❌ Ошибка расшифровки: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка: {type(e).__name__}: {e}", exc_info=True)
            raise

    def encrypt_file(self, file_content: bytes, recipient_public_key_pem: str) -> Tuple[bytes, str, str]:
        """
        Шифрование файла: гибридная схема RSA + AES-256-CBC
        Возвращает: (encrypted_content, encrypted_key_base64, iv_base64)
        """
        try:
            aes_key = os.urandom(32)
            iv = os.urandom(16)

            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
            encryptor = cipher.encryptor()

            padding_length = 16 - (len(file_content) % 16)
            padded_content = file_content + bytes([padding_length] * padding_length)
            encrypted_content = encryptor.update(padded_content) + encryptor.finalize()

            # ✅ Шифруем AES-ключ публичным ключом ПОЛУЧАТЕЛЯ
            recipient_pub_key = serialization.load_pem_public_key(
                recipient_public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            encrypted_aes_key = recipient_pub_key.encrypt(
                aes_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )

            return encrypted_content, base64.b64encode(encrypted_aes_key).decode('utf-8'), base64.b64encode(iv).decode('utf-8')

        except Exception as e:
            logger.error(f"❌ Ошибка шифрования файла: {e}", exc_info=True)
            raise

    def decrypt_file(self, encrypted_content: bytes, encrypted_key: str, iv: str) -> bytes:
        """
        Расшифровка файла
        """
        try:
            encrypted_aes_key = base64.b64decode(encrypted_key.encode('utf-8'))
            iv_bytes = base64.b64decode(iv.encode('utf-8'))

            # ✅ Расшифровываем AES-ключ приватным ключом (RSA)
            aes_key = self._private_key.decrypt(
                encrypted_aes_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )

            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv_bytes), backend=default_backend())
            decryptor = cipher.decryptor()
            padded_content = decryptor.update(encrypted_content) + decryptor.finalize()

            padding_length = padded_content[-1]
            if not 1 <= padding_length <= 16:
                raise ValueError(f"Некорректный padding: {padding_length}")

            return padded_content[:-padding_length]

        except Exception as e:
            logger.error(f"❌ Ошибка расшифровки файла: {e}", exc_info=True)
            raise

    def sign_message(self, message: str) -> str:
        """Подпись сообщения приватным ключом"""
        try:
            signature = self._private_key.sign(
                message.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode('utf-8')
        except Exception as e:
            logger.error(f"❌ Ошибка подписи: {e}", exc_info=True)
            raise

    def verify_signature(self, message: str, signature: str, sender_public_key_pem: str) -> bool:
        """Проверка подписи сообщения"""
        try:
            public_key = serialization.load_pem_public_key(
                sender_public_key_pem.encode('utf-8'),
                backend=default_backend()
            )
            signature_bytes = base64.b64decode(signature.encode('utf-8'))
            public_key.verify(
                signature_bytes,
                message.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except Exception as e:
            logger.warning(f"⚠️ Подпись недействительна: {e}")
            return False