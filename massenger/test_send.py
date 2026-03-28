#!/usr/bin/env python3
"""
Минимальный тест отправки сообщения через клиент
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.messenger_client import MessengerClient


async def test_send():
    print("🔌 Тест: подключение и отправка сообщения")
    print("-" * 50)

    client = MessengerClient(host="localhost", port=8765)

    # Подключение
    if not await client.connect():
        print("❌ Не удалось подключиться к серверу")
        return 1
    print("✅ Подключено")

    # Вход (замените на ваши тестовые данные)
    if not await client.login("dik", "test123456"):
        print("❌ Не удалось войти")
        await client.disconnect()
        return 1
    print("✅ Вход выполнен")

    # Получение публичного ключа получателя
    recipient = "suk"
    pub_key = await client.get_public_key(recipient)
    if not pub_key:
        print(f"❌ Не удалось получить ключ для {recipient}")
        await client.disconnect()
        return 1
    print(f"✅ Ключ получен для {recipient}")

    # Шифрование и отправка
    text = "Тестовое сообщение 🔐"
    encrypted = client.crypto.encrypt_message(text, pub_key)
    print(f"✅ Зашифровано ({len(encrypted)} символов)")

    result = await client.send_message(recipient, encrypted)
    if result and result.get("success"):
        print(f"✅ Сообщение отправлено! ID: {result.get('message_id')}")
    else:
        print(f"❌ Ошибка отправки: {result}")
        return 1

    # Проверка истории
    await asyncio.sleep(1)  # Дать время на обработку
    history = await client.get_chat_history(recipient, limit=5)
    print(f"✅ В истории {len(history)} сообщений")

    await client.disconnect()
    print("-" * 50)
    print("🎉 Тест завершён успешно!")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(test_send())
    sys.exit(exit_code)