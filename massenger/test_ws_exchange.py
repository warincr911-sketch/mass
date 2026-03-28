#!/usr/bin/env python3
"""
Интеграционный тест: реальное подключение к серверу + отправка сообщения
Выводит ПОШАГОВЫЙ дебаг всего потока
"""

import asyncio
import json
import sys
import os
import uuid
import logging
from datetime import datetime

# Включаем детальный лог
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
    force=True
)
logger = logging.getLogger('debug_integration')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.messenger_client import MessengerClient


def log_step(step_num: int, title: str, details: dict = None):
    """Выводит красивый лог шага"""
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"\n{'=' * 70}")
    print(f"⏱️  [{timestamp}] 🔹 ШАГ {step_num}: {title}")
    print(f"{'-' * 70}")
    if details:
        for k, v in details.items():
            val = v if isinstance(v, str) and len(v) < 100 else f"{v[:100]}..." if isinstance(v, str) else v
            print(f"   • {k}: {val}")
    print(f"{'=' * 70}\n")


async def test_real_server_connection():
    """
    Тест с РЕАЛЬНЫМ подключением к серверу
    """
    log_step(0, "ИНИЦИАЛИЗАЦИЯ", {
        "тест": "test_real_server_connection",
        "сервер": "ws://localhost:8765",
        "цель": "Проверить, что сервер отправляет request_id в ответе"
    })

    # === ШАГ 1: Подключение ===
    log_step(1, "ПОДКЛЮЧЕНИЕ К СЕРВЕРУ")

    client = MessengerClient(host="localhost", port=8765)

    connected = await client.connect()
    if not connected:
        print("❌ Не удалось подключиться к серверу")
        print("   Проверьте: запущен ли server/messenger_server.py?")
        return False

    print("✅ Подключено к серверу")
    print(f"   client.connected = {client.connected}")
    print(f"   client.websocket = {client.websocket}")

    # === ШАГ 2: Вход ===
    log_step(2, "ВХОД ПОД ПОЛЬЗОВАТЕЛЕМ")

    # ⚠️ ЗАМЕНИТЕ НА ВАШИ РЕАЛЬНЫЕ ДАННЫЕ:
    TEST_USERNAME = "dik"
    TEST_PASSWORD = "12345678"  # ← Ваш пароль

    print(f"   username: {TEST_USERNAME}")
    print(f"   password: {'*' * len(TEST_PASSWORD)}")

    logged_in = await client.login(TEST_USERNAME, TEST_PASSWORD)
    if not logged_in:
        print("❌ Не удалось войти")
        print("   Проверьте логин/пароль или зарегистрируйте пользователя")
        await client.disconnect()
        return False

    print("✅ Вход выполнен")
    print(f"   client.username = {client.username}")
    print(f"   client.user_id = {client.user_id}")

    # === ШАГ 3: Перехватываем сырые ответы от сервера ===
    log_step(3, "НАСТРОЙКА ПЕРЕХВАТА ОТВЕТОВ")

    original_recv = client.websocket.recv
    received_messages = []

    async def intercepted_recv():
        raw = await original_recv()
        received_messages.append(raw)

        try:
            data = json.loads(raw)
            logger.debug(f"📥 СЫРОЙ ОТВЕТ ОТ СЕРВЕРА:")
            logger.debug(f"   type: {data.get('type')}")
            logger.debug(f"   request_id: {data.get('request_id', 'НЕТ В ОТВЕТЕ!')}")
            logger.debug(f"   full: {raw[:300]}...")
        except json.JSONDecodeError:
            logger.debug(f"📥 СЫРОЙ ОТВЕТ (не JSON): {raw[:100]}...")

        return raw

    client.websocket.recv = intercepted_recv
    print("✅ Перехват ответов настроен")

    # === ШАГ 4: Отправка сообщения ===
    log_step(4, "ОТПРАВКА СООБЩЕНИЯ")

    # Получаем публичный ключ получателя (нужен для шифрования)
    RECIPIENT = "suk"
    print(f"   Получатель: {RECIPIENT}")

    recipient_key = await client.get_public_key(RECIPIENT)
    if not recipient_key:
        print(f"⚠️  Не удалось получить ключ для {RECIPIENT}")
        print("   Пробуем отправить без шифрования (только для теста)...")
        encrypted_data = "PLAIN_TEXT_TEST_MESSAGE"
    else:
        print(f"✅ Ключ получен ({len(recipient_key)} символов)")
        encrypted_data = client.crypto.encrypt_message("Тестовое сообщение", recipient_key)
        print(f"✅ Зашифровано ({len(encrypted_data)} символов)")

    # Генерируем свой request_id для отслеживания
    my_request_id = str(uuid.uuid4())
    print(f"   Мой request_id: {my_request_id}")

    # Отправляем сообщение ЧЕРЕЗ send_message (который использует _send_and_wait)
    print("\n📤 ОТПРАВКА ЧЕРЕЗ client.send_message()...")

    # Перехватываем данные ПЕРЕД отправкой
    original_send = client.websocket.send

    async def intercepted_send(data):
        logger.debug(f"📤 ОТПРАВЛЯЮ НА СЕРВЕР:")
        logger.debug(f"   data: {data[:300]}...")
        try:
            json_data = json.loads(data)
            logger.debug(f"   type: {json_data.get('type')}")
            logger.debug(f"   request_id: {json_data.get('request_id', 'НЕТ')}")
        except:
            pass
        return await original_send(data)

    client.websocket.send = intercepted_send

    # Отправляем
    result = await client.send_message(RECIPIENT, encrypted_data)

    print(f"\n📥 РЕЗУЛЬТАТ send_message(): {result}")

    # === ШАГ 5: Анализ полученных ответов ===
    log_step(5, "АНАЛИЗ ПОЛУЧЕННЫХ ОТВЕТОВ", {
        "всего ответов получено": len(received_messages),
        "ожидаемый request_id": my_request_id[:8] + "..."
    })

    found_matching_response = False
    found_message_sent = False

    for i, raw in enumerate(received_messages, 1):
        print(f"\n📨 Ответ #{i}:")
        try:
            data = json.loads(raw)
            print(f"   type: {data.get('type')}")
            print(f"   request_id: {data.get('request_id', 'НЕТ В ОТВЕТЕ!')}")
            print(f"   success: {data.get('success', 'N/A')}")

            if data.get('type') == 'message_sent':
                found_message_sent = True
                print(f"   ✅ Нашли 'message_sent'!")

                resp_id = data.get('request_id')
                if resp_id == my_request_id:
                    print(f"   ✅ request_id СОВПАДАЕТ с отправленным!")
                    found_matching_response = True
                elif resp_id:
                    print(f"   ❌ request_id НЕ совпадает!")
                    print(f"      Отправлено: {my_request_id[:8]}...")
                    print(f"      Получено: {resp_id[:8]}...")
                else:
                    print(f"   ❌ В ответе НЕТ request_id!")

        except json.JSONDecodeError:
            print(f"   ⚠️  Не JSON: {raw[:100]}...")

    # === ШАГ 6: Итоговый вывод ===
    log_step(6, "ИТОГОВЫЙ ДИАГНОЗ")

    print(f"\n{'🔍' * 35}")
    print("ДИАГНОСТИЧЕСКИЙ ВЫВОД:")
    print(f"{'🔍' * 35}\n")

    if found_message_sent and found_matching_response:
        print("✅ СЕРВЕР РАБОТАЕТ КОРРЕКТНО:")
        print("   • Отправляет 'message_sent' в ответ")
        print("   • request_id совпадает с отправленным")
        print("\n❌ ПРОБЛЕМА В КЛИЕНТЕ (_receive_loop или _send_and_wait)")
        print("   Нужно проверить:")
        print("   1. Обработка request_id в _receive_loop")
        print("   2. Таймауты в _send_and_wait")
        print("   3. Состояние _pending_requests")
    elif found_message_sent and not found_matching_response:
        print("⚠️  СЕРВЕР ОТПРАВЛЯЕТ ОТВЕТ, НО request_id НЕ СОВПАДАЕТ:")
        print("   • 'message_sent' получен")
        print("   • request_id в ответе ≠ request_id в запросе")
        print("\n🔧 ПРОБЛЕМА В СЕРВЕРЕ:")
        print("   Сервер должен возвращать ТОТ ЖЕ request_id, что получил")
        print("   Проверьте: server/messenger_server.py → _send_response()")
    elif not found_message_sent:
        print("❌ СЕРВЕР НЕ ОТПРАВИЛ 'message_sent':")
        print("   • Ответов получено:", len(received_messages))
        print("   • 'message_sent' не найден")
        print("\n🔧 ПРОБЛЕМА В СЕРВЕРЕ:")
        print("   • Проверьте логи сервера на ошибки")
        print("   • Проверьте handle_message() — возвращает ли ответ")
        print("   • Проверьте, не закрывает ли сервер соединение")

    print(f"\n{'🔍' * 35}\n")

    # Cleanup
    await client.disconnect()

    return found_matching_response


async def main():
    print("\n" + "🚀" * 35)
    print("   ИНТЕГРАЦИОННЫЙ ТЕСТ: реальное подключение к серверу")
    print("🚀" * 35 + "\n")

    # Проверка: запущен ли сервер?
    print("⚠️  ПЕРЕД ЗАПУСКОМ УБЕДИТЕСЬ:")
    print("   1. Сервер запущен: python server/messenger_server.py")
    print("   2. Пользователь 'dik' существует")
    print("   3. Пользователь 'suk' существует (получатель)")
    print("\n   Если нужно — измените TEST_USERNAME/TEST_PASSWORD в коде\n")

    input("Нажмите Enter для продолжения...")

    success = await test_real_server_connection()

    if success:
        print("✅ Тест завершён: сервер отправляет правильный request_id")
        print("\n📋 Следующий шаг: исправить _receive_loop в клиенте")
        return 0
    else:
        print("❌ Тест завершён: найдена проблема (см. диагноз выше)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)