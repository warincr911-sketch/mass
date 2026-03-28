#!/usr/bin/env python3
# C:\Users\Admin\PycharmProjects\PythonProject\test_crypto_direct.py

import sys
import os
import base64

# Добавляем путь к модулям
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'massenger'))

from client.crypto import ClientCrypto

print('=' * 50)
print('ПРЯМОЙ ТЕСТ КРИПТОГРАФИИ')
print('=' * 50)

# 1. Создаём пару ключей (как будто это получатель suk)
receiver = ClientCrypto()
print(f'✅ Получатель создан')

# 2. Создаём отправителя (как будто это dik)
sender = ClientCrypto()
print(f'✅ Отправитель создан')

# 3. Отправитель берёт публичный ключ получателя
pub_key = receiver.get_public_key_pem()
print(f'✅ Публичный ключ получен (длина: {len(pub_key)} симв.)')

# 4. Шифруем сообщение
msg = 'Проверка связи 123'
encrypted = sender.encrypt_message(msg, pub_key)
print(f'✅ Зашифровано (длина base64: {len(encrypted)} симв.)')

# 5. Смотрим размер бинарного пакета
package = base64.b64decode(encrypted.encode('utf-8'))
print(f'✅ Размер пакета (байт): {len(package)}')
print(f'   - Должно быть >= 272 байт (256 ключ + 16 IV + данные)')

# 6. Пытаемся расшифровать (как это делает получатель)
try:
    decrypted = receiver.decrypt_message(encrypted, None)
    print(f'✅ Расшифровано: {decrypted}')
    if decrypted == msg:
        print('\n🎉 КРИПТОГРАФИЯ РАБОТАЕТ ИДЕАЛЬНО!')
    else:
        print('\n❌ Текст не совпадает!')
except Exception as e:
    print(f'\n❌ ОШИБКА РАСШИФРОВКИ: {e}')
    print(f'   Тип ошибки: {type(e).__name__}')

print('=' * 50)