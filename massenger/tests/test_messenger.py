#!/usr/bin/env python3
"""
Тесты для Secure Messenger
Запуск: python -m pytest tests/test_messenger.py -v
"""

import pytest
import asyncio
import json
import base64
import os
import sys
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from datetime import datetime

# ============================================================================
# 🔧 НАСТРОЙКА ПУТЕЙ
# ============================================================================
current_file = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file)
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"📁 Project root: {project_root}")
print(f"📁 sys.path: {sys.path[:3]}...")

# ============================================================================
# 📦 ИМПОРТ ТЕСТИРУЕМЫХ МОДУЛЕЙ
# ============================================================================
try:
    from client.messenger_client import MessengerClient, ClientConstants
    from client.crypto import ClientCrypto

    print("✅ Модули успешно импортированы")
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("\n📋 Проверьте структуру проекта:")
    print(f"   {project_root}/")
    print("   ├── client/")
    print("   │   ├── __init__.py")
    print("   │   ├── messenger_client.py")
    print("   │   ├── crypto.py")
    print("   │   └── config.py")
    print("   └── tests/")
    print("       ├── __init__.py")
    print("       └── test_messenger.py")
    raise


# ============================================================================
# 🧪 ФИКСТУРЫ (ОБЯЗАТЕЛЬНО ДОЛЖНЫ БЫТЬ ЗДЕСЬ!)
# ============================================================================
@pytest.fixture
def crypto():
    """Фикстура для крипто-модуля"""
    return ClientCrypto()


@pytest.fixture
def client():
    """Фикстура для клиента (без подключения)"""
    return MessengerClient(host='localhost', port=8765)


@pytest.fixture
def valid_username():
    return "test_user_123"


@pytest.fixture
def valid_email():
    return "test@example.com"


@pytest.fixture
def valid_password():
    return "SecurePass123!"


@pytest.fixture
def valid_public_key(crypto):
    """Фикстура для валидного публичного ключа"""
    return crypto.get_public_key_pem()


# ============================================================================
# ✅ ТЕСТЫ ВАЛИДАЦИИ
# ============================================================================
class TestValidation:
    """Тесты валидации входных данных"""

    def test_validate_username_valid(self, client, valid_username):
        assert client._validate_username(valid_username) is True

    def test_validate_username_too_short(self, client):
        assert client._validate_username("ab") is False

    def test_validate_username_too_long(self, client):
        assert client._validate_username("a" * 31) is False

    def test_validate_username_invalid_chars(self, client):
        assert client._validate_username("user@name!") is False

    def test_validate_email_valid(self, client, valid_email):
        assert client._validate_email(valid_email) is True

    def test_validate_email_invalid(self, client):
        assert client._validate_email("invalid-email") is False
        assert client._validate_email("@example.com") is False

    def test_validate_password_valid(self, client, valid_password):
        assert client._validate_password(valid_password) is True

    def test_validate_password_too_short(self, client):
        assert client._validate_password("short") is False

    def test_validate_public_key_valid(self, client, valid_public_key):
        assert client._validate_public_key(valid_public_key) is True

    def test_validate_public_key_invalid(self, client):
        assert client._validate_public_key("not-a-key") is False
        assert client._validate_public_key("") is False
        assert client._validate_public_key(None) is False


# ============================================================================
# 🔐 ТЕСТЫ КРИПТОГРАФИИ
# ============================================================================
class TestCrypto:
    """Тесты криптографических операций"""

    def test_generate_identity_keys(self, crypto):
        """Генерация ключей возвращает валидный PEM"""
        public_key = crypto.generate_identity_keys()
        assert "-----BEGIN PUBLIC KEY-----" in public_key
        assert "-----END PUBLIC KEY-----" in public_key
        assert len(public_key) > 400  # Реальный RSA 2048 ключ ~450 символов

    def test_encrypt_decrypt_message_roundtrip(self, crypto):
        """Шифрование и расшифровка сообщения"""
        original = "Hello, Secure World!"
        public_key = crypto.get_public_key_pem()

        encrypted = crypto.encrypt_message(original, public_key)
        assert isinstance(encrypted, str)
        assert len(encrypted) > len(original)

        # Расшифровка тем же клиентом (приватный ключ внутри)
        decrypted = crypto.decrypt_message(encrypted, public_key)
        assert decrypted == original

    def test_encrypt_file(self, crypto, tmp_path):
        """Шифрование файла"""
        content = b"Secret file content"
        recipient = "test_recipient"

        encrypted_content, encrypted_key, iv = crypto.encrypt_file(content, recipient)

        assert isinstance(encrypted_content, bytes)
        assert isinstance(encrypted_key, str)  # base64 строка
        assert isinstance(iv, str)  # base64 строка
        assert encrypted_content != content
        assert len(encrypted_key) > 0
        assert len(iv) > 0

    def test_encrypt_file_with_unicode(self, crypto):
        """Шифрование файла с Unicode контентом"""
        content = "Secret file content with unicode: Privet!".encode('utf-8')
        recipient = "test_recipient"

        encrypted_content, encrypted_key, iv = crypto.encrypt_file(content, recipient)

        assert isinstance(encrypted_content, bytes)
        assert encrypted_content != content

        # Проверка расшифровки
        decrypted = crypto.decrypt_file(encrypted_content, encrypted_key, iv)
        assert decrypted == content

    def test_encrypt_decrypt_file_roundtrip(self, crypto, tmp_path):
        """Полный цикл шифрования-расшифровки файла"""
        original_content = b"Test file content for roundtrip"
        recipient = "test_user"

        encrypted_content, encrypted_key, iv = crypto.encrypt_file(original_content, recipient)
        decrypted_content = crypto.decrypt_file(encrypted_content, encrypted_key, iv)

        assert decrypted_content == original_content

    def test_sanitize_for_log(self):
        """Санитизация чувствительных данных в логах"""
        from client.messenger_client import _sanitize_for_log

        data = {
            'username': 'alice',
            'password': 'secret123',
            'message': 'Hello',
            'nested': {
                'encrypted_data': '***',
                'public_key': 'valid-key'
            }
        }

        sanitized = _sanitize_for_log(data)

        assert sanitized['username'] == 'alice'
        assert sanitized['password'] == '***REDACTED***'
        assert sanitized['message'] == 'Hello'
        assert sanitized['nested']['encrypted_data'] == '***REDACTED***'
        assert sanitized['nested']['public_key'] == 'valid-key'


# ============================================================================
# 🔗 ТЕСТЫ КЛИЕНТА (без сети)
# ============================================================================
class TestMessengerClient:
    """Тесты клиента (мок-тесты без реального подключения)"""

    @pytest.mark.asyncio
    async def test_connect_timeout(self, client):
        """Таймаут подключения"""
        with patch('websockets.connect', side_effect=asyncio.TimeoutError):
            result = await client.connect()
            assert result is False
            assert client.connected is False

    @pytest.mark.asyncio
    async def test_send_message_unauthenticated(self, client):
        """Отправка сообщения без авторизации"""
        result = await client.send_message("recipient", "encrypted_data")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_invalid_recipient(self, client):
        """Отправка сообщения невалидному получателю"""
        client.username = "test_user"
        client.connected = True
        result = await client.send_message("invalid@user!", "data")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_public_key_cache(self, client, valid_public_key):
        """Кэширование публичного ключа"""
        username = "cached_user"
        client._public_keys_cache[username] = valid_public_key

        result = await client.get_public_key(username)
        assert result == valid_public_key

    def test_is_authenticated(self, client):
        """Проверка статуса авторизации"""
        assert client.is_authenticated() is False

        client.username = "user"
        assert client.is_authenticated() is False

        client.connected = True
        assert client.is_authenticated() is True


# ============================================================================
# 🔄 ТЕСТЫ ПОВТОРНЫХ ПОПЫТОК
# ============================================================================
class TestRetryLogic:
    """Тесты retry-логики"""

    @pytest.mark.asyncio
    async def test_send_with_retry_success_first_try(self, client):
        """Успех с первой попытки"""
        client.connected = True
        client.websocket = Mock()
        client.websocket.send = AsyncMock()

        with patch.object(client, '_send_and_wait', return_value={'success': True}) as mock_send:
            result = await client._send_with_retry({'type': 'test'}, timeout=5)
            assert result == {'success': True}
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_with_retry_eventual_success(self, client):
        """Успех после повторной попытки"""
        client.connected = True

        call_count = 0

        async def mock_send(data, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return {'success': True}

        with patch.object(client, '_send_and_wait', side_effect=mock_send):
            result = await client._send_with_retry({'type': 'test'}, timeout=5, max_retries=3)
            assert result == {'success': True}
            assert call_count == 2


# ============================================================================
# 🧩 ИНТЕГРАЦИОННЫЕ ТЕСТЫ
# ============================================================================
@pytest.mark.integration
class TestIntegration:
    """Интеграционные тесты (требуют сервер)"""

    @pytest.mark.asyncio
    async def test_full_registration_flow(self):
        """Полный тест регистрации -> входа -> отправки сообщения"""
        pytest.skip("Требуется тестовый сервер")


# ============================================================================
# 🚀 ЗАПУСК ТЕСТОВ
# ============================================================================
if __name__ == "__main__":
    pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '-x',
        '-m', 'not integration',
    ])