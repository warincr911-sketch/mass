#!/usr/bin/env python3
"""
Отладка: проверяем что именно приходит в display_messages
"""

import sys
import os
import base64

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'massenger'))

from client.crypto import ClientCrypto

print('=' * 80)
print('🔍 ОТЛАДКА: расшифровка как в display_messages')
print('=' * 80)

# Создаём получателя (suk)
receiver = ClientCrypto()
print(f'\n✅ Получатель создан')
print(f'   Public key hash: {hash(receiver.get_public_key_pem()) % 100000}')

# Эмулируем сообщение из БД (как приходит в display_messages)
# Это то, что dik отправил, зашифровав публичным ключом suk
sender = ClientCrypto()
original_msg = "Тестовое сообщение для проверки 🔐"
encrypted = sender.encrypt_message(original_msg, receiver.get_public_key_pem())

print(f'\n📦 Эмуляция сообщения из БД:')
print(f'   is_encrypted: True')
print(f'   is_own: False')
print(f'   encrypted_data (base64): {encrypted[:80]}...')
print(f'   Длина base64: {len(encrypted)}')

# Проверяем размер пакета
package = base64.b64decode(encrypted.encode('utf-8'))
print(f'   Размер пакета: {len(package)} байт (ожидалось >= 272)')

# 🔴 ЭМУЛИРУЕМ ВАШ КОД (как было):
print(f'\n🔴 ТЕСТ 1: Старый код (с is_own проверкой)')
text = encrypted
is_encrypted = True
is_own = False  # получатель

if is_encrypted and not is_own:  # ← условие выполняется
    try:
        result = receiver.decrypt_message(text, None)
        print(f'   ✅ Расшифровано: "{result}"')
        if result == original_msg:
            print(f'   🎉 Текст совпадает!')
        else:
            print(f'   ❌ Текст НЕ совпадает!')
    except Exception as e:
        print(f'   ❌ ОШИБКА: {type(e).__name__}: {e}')
else:
    print(f'   ⚠️ Условие не выполнено, текст не расшифрован')

# ✅ ЭМУЛИРУЕМ ИСПРАВЛЕННЫЙ КОД:
print(f'\n✅ ТЕСТ 2: Исправленный код (без is_own)')
text = encrypted
is_encrypted = True

if is_encrypted:  # ← всегда расшифровываем
    try:
        result = receiver.decrypt_message(text, None)
        print(f'   ✅ Расшифровано: "{result}"')
        if result == original_msg:
            print(f'   🎉 Текст совпадает!')
        else:
            print(f'   ❌ Текст НЕ совпадает!')
    except Exception as e:
        print(f'   ❌ ОШИБКА: {type(e).__name__}: {e}')
else:
    print(f'   ⚠️ Сообщение не зашифровано')

print('\n' + '=' * 80)
print('💡 ВЫВОД:')
print('   Если ТЕСТ 1 ✅ а ТЕСТ 2 ✅ — код исправлен правильно')
print('   Если ТЕСТ 1 ❌ а ТЕСТ 2 ✅ — нужно убрать "and not is_own"')
print('   Если оба ❌ — проблема в ключах или данных в БД')
print('=' * 80)
