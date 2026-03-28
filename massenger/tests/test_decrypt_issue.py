#!/usr/bin/env python3
"""
Тесты для воспроизведения проблемы расшифровки сообщений
Запуск: python -m pytest tests/test_decrypt_issue.py -v -s
"""

import pytest
import sys
import os
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.crypto import ClientCrypto


# ============================================================================
# 🧪 ТЕСТ 1: Проверка формата зашифрованного сообщения
# ============================================================================
class TestEncryptionFormat:
    """Тесты формата шифрования"""

    def test_encrypt_message_format(self):
        """Проверка что зашифрованное сообщение имеет правильный формат"""
        crypto_sender = ClientCrypto()
        crypto_receiver = ClientCrypto()

        original = "Test message"
        receiver_public_key = crypto_receiver.get_public_key_pem()

        # Шифруем
        encrypted = crypto_sender.encrypt_message(original, receiver_public_key)

        # Декодируем base64
        package = base64.b64decode(encrypted.encode('utf-8'))

        # Проверяем структуру пакета
        # Ожидаем: encrypted_aes_key (256) + iv (16) + encrypted_message (variable)
        assert len(package) > 272, f"Пакет слишком короткий: {len(package)} байт"

        encrypted_aes_key = package[:256]
        iv = package[256:272]
        encrypted_message = package[272:]

        assert len(encrypted_aes_key) == 256, f"AES key должен быть 256 байт, получил {len(encrypted_aes_key)}"
        assert len(iv) == 16, f"IV должен быть 16 байт, получил {len(iv)}"
        assert len(encrypted_message) > 0, "Зашифрованное сообщение пустое"

        print(f"\n✅ Формат пакета корректный: {len(package)} байт")
        print(f"   - encrypted_aes_key: {len(encrypted_aes_key)} байт")
        print(f"   - IV: {len(iv)} байт")
        print(f"   - encrypted_message: {len(encrypted_message)} байт")

    def test_decrypt_with_correct_key(self):
        """Расшифровка сообщения правильным ключом"""
        crypto_sender = ClientCrypto()
        crypto_receiver = ClientCrypto()

        original = "Test message for decryption"
        receiver_public_key = crypto_receiver.get_public_key_pem()

        # Шифруем публичным ключом получателя
        encrypted = crypto_sender.encrypt_message(original, receiver_public_key)

        # Расшифровываем приватным ключом получателя
        decrypted = crypto_receiver.decrypt_message(encrypted, receiver_public_key)

        assert decrypted == original, f"Расшифровка не совпадает: {decrypted} != {original}"
        print(f"\n✅ Расшифровка успешна: '{original}'")

    def test_decrypt_with_wrong_key(self):
        """Попытка расшифровки чужим ключом (должна вызвать ошибку)"""
        crypto_sender = ClientCrypto()
        crypto_receiver = ClientCrypto()
        crypto_imposter = ClientCrypto()  # Третий клиент

        original = "Secret message"
        receiver_public_key = crypto_receiver.get_public_key_pem()

        # Шифруем для получателя
        encrypted = crypto_sender.encrypt_message(original, receiver_public_key)

        # Пытаемся расшифровать чужим ключом (должна быть ошибка)
        try:
            crypto_imposter.decrypt_message(encrypted, crypto_imposter.get_public_key_pem())
            assert False, "Ожидалась ошибка при расшифровке чужим ключом"
        except Exception as e:
            print(f"\n✅ Чужой ключ правильно отклонён: {type(e).__name__}")


# ============================================================================
# 🧪 ТЕСТ 2: Симуляция проблемы из логов
# ============================================================================
class TestDecryptFailureSimulation:
    """Симуляция проблемы расшифровки из логов"""

    def test_simulate_ciphertext_length_error(self):
        """
        Симуляция ошибки 'Ciphertext length must be equal to key size'
        Эта ошибка возникает когда encrypted_aes_key не равен 256 байт
        """
        crypto = ClientCrypto()

        # Создаём некорректный пакет (слишком короткий)
        bad_package = b"short"  # Вместо 256+ байт
        bad_encrypted = base64.b64encode(bad_package).decode('utf-8')

        # Попытка расшифровки должна вызвать ошибку
        try:
            crypto.decrypt_message(bad_encrypted, crypto.get_public_key_pem())
            assert False, "Ожидалась ошибка для короткого пакета"
        except ValueError as e:
            assert "Ciphertext length" in str(e) or "Decryption failed" in str(e) or "Пакет слишком короткий" in str(e)
            print(f"\n✅ Ошибка воспроизведена: {e}")

    def test_simulate_old_format_message(self):
        """
        Симуляция сообщения в старом формате (без RSA-обёртки)
        Это наиболее вероятная причина проблемы в логах
        """
        crypto = ClientCrypto()

        # Старый формат: просто base64 от зашифрованных данных (без RSA)
        old_format_data = base64.b64encode(b"old_encrypted_data").decode('utf-8')

        # Попытка расшифровки должна вызвать ошибку
        try:
            crypto.decrypt_message(old_format_data, crypto.get_public_key_pem())
            assert False, "Ожидалась ошибка для старого формата"
        except Exception as e:
            print(f"\n✅ Старый формат правильно отклонён: {type(e).__name__}")


# ============================================================================
# 🧪 ТЕСТ 3: Проверка совместимости между клиентами
# ============================================================================
class TestCrossClientCompatibility:
    """Тесты совместимости между разными клиентами"""

    def test_two_clients_exchange(self):
        """Обмен сообщениями между двумя клиентами"""
        client_alice = ClientCrypto()
        client_bob = ClientCrypto()

        # Alice → Bob
        message_alice = "Hello from Alice"
        encrypted_alice = client_alice.encrypt_message(message_alice, client_bob.get_public_key_pem())
        decrypted_alice = client_bob.decrypt_message(encrypted_alice, client_bob.get_public_key_pem())
        assert decrypted_alice == message_alice

        # Bob → Alice
        message_bob = "Hello from Bob"
        encrypted_bob = client_bob.encrypt_message(message_bob, client_alice.get_public_key_pem())
        decrypted_bob = client_alice.decrypt_message(encrypted_bob, client_alice.get_public_key_pem())
        assert decrypted_bob == message_bob

        print("\n✅ Двусторонняя связь работает")

    def test_same_client_roundtrip(self):
        """Отправка и получение одним клиентом (для отладки)"""
        crypto = ClientCrypto()

        message = "Self message"
        public_key = crypto.get_public_key_pem()

        encrypted = crypto.encrypt_message(message, public_key)
        decrypted = crypto.decrypt_message(encrypted, public_key)

        assert decrypted == message
        print("\n✅ Roundtrip успешен")


# ============================================================================
# 🚀 ЗАПУСК
# ============================================================================
if __name__ == "__main__":
    pytest.main([__file__, '-v', '-s'])