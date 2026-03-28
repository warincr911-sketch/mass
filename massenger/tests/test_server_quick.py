#!/usr/bin/env python3
"""
Быстрый тест подключения к серверу
Запуск: python -m pytest tests/test_server_quick.py -v -s
"""

import asyncio
import websockets
import json
import sys
import os

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.crypto import ClientCrypto


async def test_connection():
    """Тест подключения и регистрации с реальным ключом"""
    uri = "ws://localhost:8765"

    # ✅ Генерируем реальную пару ключей
    crypto = ClientCrypto()
    real_public_key = crypto.get_public_key_pem()

    print(f"🔑 Сгенерирован публичный ключ (длина: {len(real_public_key)} символов)")
    print(f"📡 Подключение к {uri}...")

    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
            print("✅ Подключение установлено")

            # Тест регистрации
            register_data = {
                'type': 'register',
                'username': 'test_user_pytest',
                'password': 'SecurePass123!',
                'email': 'test@example.com',
                'public_key': real_public_key  # ✅ Реальный ключ
            }

            print(f"📤 Отправка регистрации...")
            await ws.send(json.dumps(register_data))

            response = await ws.recv()
            response_data = json.loads(response)

            print(f"📥 Ответ сервера: {json.dumps(response_data, ensure_ascii=False, indent=2)}")

            if response_data.get('success'):
                print("✅ РЕГИСТРАЦИЯ УСПЕШНА!")
            else:
                print(f"⚠️ Регистрация отклонена: {response_data.get('message')}")

            # Тест входа
            print(f"\n📤 Отправка входа...")
            await ws.send(json.dumps({
                'type': 'login',
                'username': 'test_user_pytest',
                'password': 'SecurePass123!'
            }))

            response = await ws.recv()
            response_data = json.loads(response)

            print(f"📥 Ответ сервера: {json.dumps(response_data, ensure_ascii=False, indent=2)}")

            if response_data.get('success'):
                print("✅ ВХОД УСПЕШЕН!")
            else:
                print(f"⚠️ Вход отклонён: {response_data.get('message')}")

    except websockets.exceptions.ConnectionClosedError:
        print("❌ Ошибка: Сервер закрыл соединение")
        print("   Проверьте, запущен ли сервер: python massenger/server/messenger_server.py")
    except ConnectionRefusedError:
        print("❌ Ошибка: Не удалось подключиться к серверу")
        print("   Проверьте, запущен ли сервер на ws://localhost:8765")
    except Exception as e:
        print(f"❌ Ошибка: {e}")


async def test_health_check():
    """Тест доступности сервера (без регистрации)"""
    uri = "ws://localhost:8765"

    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
            print("✅ Сервер доступен!")
            return True
    except Exception as e:
        print(f"❌ Сервер недоступен: {e}")
        return False


# ============================================================================
# 🚀 ЗАПУСК ТЕСТОВ
# ============================================================================
async def main():
    print("=" * 80)
    print("🧪 ТЕСТ СЕРВЕРА MESSENGER")
    print("=" * 80)
    print()

    # Шаг 1: Проверка доступности
    print("1️⃣ Проверка доступности сервера...")
    if not await test_health_check():
        print("\n⚠️ Сервер не запущен! Запустите:")
        print("   python massenger/server/messenger_server.py")
        return

    print()

    # Шаг 2: Тест регистрации и входа
    print("2️⃣ Тест регистрации и входа...")
    await test_connection()

    print()
    print("=" * 80)
    print("✅ ТЕСТ ЗАВЕРШЁН")
    print("=" * 80)


if __name__ == "__main__":
    # Для запуска через pytest
    import pytest


    def test_server_connection():
        """Pytest-обёртка для теста"""
        asyncio.run(main())


    # Если запускаем напрямую
    if len(sys.argv) > 1 and sys.argv[1] == '--direct':
        asyncio.run(main())
    else:
        # Запуск через pytest
        pytest.main([__file__, '-v', '-s'])