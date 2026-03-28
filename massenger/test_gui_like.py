#!/usr/bin/env python3
"""
Тест подключения как GUI клиент
Максимально похоже на messenger_gui.py, но с подробным логом каждого шага
"""

import asyncio
import json
import sys
import os
import logging
from datetime import datetime

# Включаем детальный лог
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
    force=True
)
logger = logging.getLogger('test_gui_like')

# Добавляем путь как в GUI
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logger.info(f"📁 Project root: {project_root}")
logger.info(f"📁 sys.path[0]: {sys.path[0]}")

# ============================================================================
# КОНФИГУРАЦИЯ (ЗАМЕНИТЕ НА ВАШИ ДАННЫЕ)
# ============================================================================
SERVER_HOST = "localhost"
SERVER_PORT = 8765
TEST_USERNAME = "dik"
TEST_PASSWORD = "12345678"  # ← Ваш пароль
RECIPIENT = "suk"


# ============================================================================
# ТЕСТ
# ============================================================================
async def main():
    print("\n" + "=" * 70)
    print("🧪 ТЕСТ: Подключение как GUI клиент")
    print("=" * 70 + "\n")

    from client.messenger_client import MessengerClient

    # === ШАГ 1: Создание клиента ===
    print("📌 ШАГ 1: Создание MessengerClient...")
    client = MessengerClient(host=SERVER_HOST, port=SERVER_PORT)
    print(f"   ✅ client создан: {client}")
    print(f"   • client.server_host = {client.server_host}")
    print(f"   • client.server_port = {client.server_port}")
    print(f"   • client.connected = {client.connected}")
    print()

    # === ШАГ 2: Подключение ===
    print("📌 ШАГ 2: Подключение к серверу...")
    print(f"   🔌 Адрес: ws://{SERVER_HOST}:{SERVER_PORT}")

    connected = await client.connect()
    print(f"   • client.connected = {client.connected}")
    print(f"   • client.websocket = {client.websocket}")

    if not connected:
        print("   ❌ НЕ УДАЛОСЬ ПОДКЛЮЧИТЬСЯ")
        print("   Проверьте: запущен ли server/messenger_server.py?")
        print()
        return False

    print("   ✅ ПОДКЛЮЧЕНО")
    print()

    # === ШАГ 3: Вход ===
    print("📌 ШАГ 3: Вход под пользователем...")
    print(f"   👤 username: {TEST_USERNAME}")
    print(f"   🔑 password: {'*' * len(TEST_PASSWORD)}")

    logged_in = await client.login(TEST_USERNAME, TEST_PASSWORD)
    print(f"   • client.username = {client.username}")
    print(f"   • client.user_id = {client.user_id}")

    if not logged_in:
        print("   ❌ НЕ УДАЛОСЬ ВОЙТИ")
        print("   Проверьте логин/пароль или зарегистрируйте пользователя")
        print()
        await client.disconnect()
        return False

    print("   ✅ ВХОД ВЫПОЛНЕН")
    print()

    # === ШАГ 4: Получение контактов ===
    print("📌 ШАГ 4: Получение списка контактов...")

    contacts = await client.get_contacts()
    print(f"   • Найдено контактов: {len(contacts)}")
    for c in contacts:
        print(f"     - {c.get('username')} (online={c.get('online')})")
    print()

    # === ШАГ 5: Получение публичного ключа получателя ===
    print("📌 ШАГ 5: Получение публичного ключа для получателя...")
    print(f"   👤 Получатель: {RECIPIENT}")

    recipient_key = await client.get_public_key(RECIPIENT)
    if not recipient_key:
        print(f"   ⚠️  Не удалось получить ключ для {RECIPIENT}")
        print("   Пробуем отправить без шифрования...")
        message_to_send = "PLAIN_TEXT_TEST"
    else:
        print(f"   ✅ Ключ получен ({len(recipient_key)} символов)")
        print(f"   • Начало ключа: {recipient_key[:50]}...")

        # === ШАГ 6: Шифрование ===
        print()
        print("📌 ШАГ 6: Шифрование сообщения...")
        from client.crypto import ClientCrypto
        message_text = "Тестовое сообщение из теста"
        message_to_send = client.crypto.encrypt_message(message_text, recipient_key)
        print(f"   ✅ Зашифровано ({len(message_to_send)} символов base64)")
    print()

    # === ШАГ 7: Отправка сообщения (УПРОЩЁННО, как в test_ws_exchange.py) ===
    print("📌 ШАГ 7: Отправка сообщения (упрощённо)...")
    print(f"   📤 Получатель: {RECIPIENT}")

    # 🔥 ОТПРАВЛЯЕМ ПРЯМО ЧЕРЕЗ WEBSOCKET, как в рабочем тесте
    test_message = {
        "type": "message",
        "recipient": RECIPIENT,
        "encrypted_data": "DIRECT_TEST_MESSAGE_12345",  # ← Простой текст, без шифрования
        "timestamp": datetime.now().isoformat()
    }

    print(f"   🔐 Данные: {test_message['encrypted_data']}")
    print(f"   📡 Отправляю через client.websocket.send()...")

    try:
        await client.websocket.send(json.dumps(test_message))
        print("   ✅ Данные отправлены в сеть")

        # Ждём ответ с таймаутом
        response = await asyncio.wait_for(client.websocket.recv(), timeout=5)
        resp_data = json.loads(response)
        print(f"   📥 Ответ: {resp_data.get('type')} | success={resp_data.get('success')}")

        if resp_data.get('success'):
            print("   ✅ СЕРВЕР ПОДТВЕРДИЛ! Проблема в send_message(), не в сети.")
        else:
            print(f"   ❌ Сервер отклонил: {resp_data.get('message')}")

    except asyncio.TimeoutError:
        print("   ❌ Таймаут: сервер не ответил")
    except Exception as e:
        print(f"   ❌ Ошибка: {type(e).__name__}: {e}")

    # === ШАГ 8: Проверка истории ===
    print("📌 ШАГ 8: Проверка истории сообщений...")

    history = await client.get_chat_history(RECIPIENT, limit=5)
    print(f"   📋 Найдено сообщений: {len(history)}")
    for msg in history[:3]:
        sender = msg.get('sender', 'unknown')
        text = msg.get('text', msg.get('encrypted_data', ''))[:50]
        print(f"      • [{sender}]: {text}...")
    print()

    # === ИТОГ ===
    print("=" * 70)
    print("📊 ИТОГ ТЕСТА:")
    print("=" * 70)

    if result and result.get('success'):
        print("✅ ТЕСТ ПРОЙДЕН: сообщение отправлено успешно!")
        print()
        print("🔍 Если в GUI не работает — проблема в:")
        print("   1. Обработке ответа в _receive_loop")
        print("   2. Таймаутах в _send_and_wait")
        print("   3. Отображении в GUI (не в сети)")
        success = True
    else:
        print("❌ ТЕСТ НЕ ПРОЙДЕН: сообщение не отправлено")
        print()
        print("🔍 Проблема в:")
        print("   1. Сервер не ответил (проверьте логи сервера)")
        print("   2. request_id не совпадает")
        print("   3. Ошибка в send_message / _send_and_wait")
        success = False

    print("=" * 70 + "\n")

    # Cleanup
    await client.disconnect()

    return success


if __name__ == "__main__":
    print("\n⚠️  ПЕРЕД ЗАПУСКОМ УБЕДИТЕСЬ:")
    print("   1. Сервер запущен: python server/messenger_server.py")
    print("   2. Пользователь '{0}' существует".format(TEST_USERNAME))
    print("   3. Пользователь '{0}' существует (получатель)".format(RECIPIENT))
    print()

    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Ошибка: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
