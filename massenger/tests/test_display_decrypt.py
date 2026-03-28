#!/usr/bin/env python3
"""
Тест расшифровки сообщений
Запуск: Правой кнопкой → Run 'test_display_decrypt'
"""

import sys
import os
import base64

# Добавляем пути к модулям
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'massenger'))

from client.crypto import ClientCrypto

print('=' * 80)
print('🔐 ТЕСТ РАСШИФРОВКИ СООБЩЕНИЙ')
print('=' * 80)

# Создаём двух клиентов
sender_crypto = ClientCrypto()  # dik
receiver_crypto = ClientCrypto()  # suk

print('\n📝 ТЕСТ 1: Шифрование и расшифровка')
print('-' * 80)

# 1. Отправитель шифрует сообщение публичным ключом получателя
message = "Привет, это тестовое сообщение! 🔐"
receiver_public_key = receiver_crypto.get_public_key_pem()

print(f"   Отправитель ключ: {sender_crypto.get_public_key_pem()[:50]}...")
print(f"   Получатель ключ: {receiver_public_key[:50]}...")

encrypted = sender_crypto.encrypt_message(message, receiver_public_key)
print(f"   ✅ Зашифровано (base64 длина: {len(encrypted)})")

# 2. Проверяем размер пакета
package = base64.b64decode(encrypted.encode('utf-8'))
print(f"   ✅ Размер пакета: {len(package)} байт")

if len(package) < 272:
    print(f"   ❌ ОШИБКА: пакет слишком короткий (< 272 байт)!")
    sys.exit(1)

# 3. Получатель расшифровывает СВОИМ приватным ключом (параметр None)
try:
    decrypted = receiver_crypto.decrypt_message(encrypted, None)
    print(f"   ✅ Расшифровано (параметр=None): '{decrypted}'")

    if decrypted == message:
        print(f"   🎉 СООБЩЕНИЕ РАСШИФРОВАНО ВЕРНО!")
    else:
        print(f"   ❌ Текст не совпадает!")
        sys.exit(1)

except Exception as e:
    print(f"   ❌ ОШИБКА РАСШИФРОВКИ: {e}")
    print(f"      Тип: {type(e).__name__}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print('\n' + '=' * 80)
print('✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ!')
print('=' * 80)