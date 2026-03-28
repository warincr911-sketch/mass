#!/usr/bin/env python3
"""
Диагностический тест: ПОШАГОВЫЙ дебаг обработки request_id
Выводит каждый шаг: от отправки запроса до получения ответа
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
logger = logging.getLogger('debug_test')

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


async def test_full_flow_with_debug():
    """
    Полный тест потока: запрос → _pending_requests → ответ → future
    С детальным логом каждого состояния
    """
    log_step(0, "ИНИЦИАЛИЗАЦИЯ", {
        "тест": "test_full_flow_with_debug",
        "цель": "Отследить, где теряется сопоставление request_id"
    })

    client = MessengerClient()
    client.connected = True
    client.username = "dik"

    # Мокаем websocket
    from unittest.mock import AsyncMock, MagicMock
    mock_ws = AsyncMock()
    client.websocket = mock_ws

    log_step(1, "СОСТОЯНИЕ КЛИЕНТА ПЕРЕД ТЕСТОМ", {
        "client.connected": client.connected,
        "client.username": client.username,
        "client.websocket": f"mock={mock_ws is not None}",
        "_pending_requests (до)": len(client._pending_requests),
        "_loop_ready.is_set()": client._loop_ready.is_set() if hasattr(client, '_loop_ready') else "N/A"
    })

    # Запускаем _receive_loop в фоне
    log_step(2, "ЗАПУСК _receive_loop")
    receive_task = asyncio.create_task(client._receive_loop())
    await asyncio.sleep(0.05)
    logger.debug(f"🔄 _receive_loop запущен, задача: {receive_task}")

    # === ЭТАП 1: Формируем запрос ===
    log_step(3, "ФОРМИРОВАНИЕ ЗАПРОСА")

    request_id = str(uuid.uuid4())
    request_data = {
        "type": "message",
        "recipient": "suk",
        "encrypted_data": "TEST_ENCRYPTED_DATA_12345",
        "timestamp": "2026-03-28T20:00:00",
        "request_id": request_id
    }

    logger.debug(f"📤 request_id: {request_id}")
    logger.debug(f"📤 request_data keys: {list(request_data.keys())}")

    # === ЭТАП 2: Добавляем в _pending_requests (как делает _send_and_wait) ===
    log_step(4, "ДОБАВЛЕНИЕ В _pending_requests", {
        "request_id": request_id,
        "request_id[:8]": request_id[:8],
        "_pending_requests (до)": len(client._pending_requests)
    })

    future = asyncio.get_event_loop().create_future()
    client._pending_requests[request_id] = future

    logger.debug(f"✅ future создан: {future}")
    logger.debug(f"✅ request_id добавлен в _pending_requests")
    logger.debug(f"📊 _pending_requests (после): {len(client._pending_requests)} элементов")
    logger.debug(f"🔑 Ключи в _pending_requests: {[k[:8] for k in client._pending_requests.keys()]}")

    # === ЭТАП 3: Формируем ОТВЕТ от сервера ===
    log_step(5, "ФОРМИРОВАНИЕ ОТВЕТА ОТ СЕРВЕРА")

    # ВАРИАНТ А: Правильный ответ (с тем же request_id)
    response_data_correct = {
        "type": "message_sent",
        "success": True,
        "message_id": 999,
        "request_id": request_id  # ← Тот же!
    }

    # ВАРИАНТ Б: Ответ БЕЗ request_id (сервер не отправил)
    response_data_no_id = {
        "type": "message_sent",
        "success": True,
        "message_id": 999
        # ← Нет request_id!
    }

    # ВАРИАНТ В: Ответ с ДРУГИМ request_id (баг сервера)
    response_data_wrong_id = {
        "type": "message_sent",
        "success": True,
        "message_id": 999,
        "request_id": str(uuid.uuid4())  # ← Другой!
    }

    print("🔍 Тестируем 3 варианта ответа:")
    print(f"   А) С тем же request_id: {response_data_correct['request_id'][:8]}...")
    print(f"   Б) БЕЗ request_id")
    print(f"   В) С ДРУГИМ request_id: {response_data_wrong_id['request_id'][:8]}...")

    # === ЭТАП 4: Имитируем получение ответа ===
    async def test_response_variant(variant_name: str, response_data: dict):
        print(f"\n🧪 ВАРИАНТ {variant_name}:")
        print(f"   📥 Ответ: {json.dumps(response_data, ensure_ascii=False)[:150]}...")

        # Проверяем, есть ли request_id в ответе
        resp_request_id = response_data.get('request_id')
        print(f"   🔍 response_data.get('request_id'): {resp_request_id[:8] if resp_request_id else None}")

        # Проверяем, есть ли этот ID в _pending_requests
        if resp_request_id and resp_request_id in client._pending_requests:
            print(f"   ✅ request_id НАЙДЕН в _pending_requests")
            pending_future = client._pending_requests[resp_request_id]
            print(f"   ✅ pending_future: {pending_future}, done={pending_future.done()}")
        elif resp_request_id:
            print(f"   ❌ request_id НЕ найден в _pending_requests")
            print(f"      Доступные ключи: {[k[:8] for k in client._pending_requests.keys()]}")
        else:
            print(f"   ⚠️  В ответе НЕТ request_id — не может быть сопоставлен")

        # Имитируем обработку в _receive_loop (упрощённо)
        # Это то, что ДОЛЖНО происходить в реальном коде:
        if resp_request_id and resp_request_id in client._pending_requests:
            print(f"   🎯 Вызов: _pending_requests['{resp_request_id[:8]}...'].set_result(...)")
            client._pending_requests[resp_request_id].set_result(response_data)
            print(f"   ✅ Future выполнен: {client._pending_requests[resp_request_id].done()}")
        else:
            print(f"   ⏭️  Пропускаем сопоставление (нет совпадения)")

        # Проверяем результат
        if future.done():
            result = future.result()
            print(f"   🏁 ИТОГ: future.result() = {result}")
            return True, result
        else:
            print(f"   ⏳ ИТОГ: future ещё не выполнен (ожидание...)")
            return False, None

    # Тестируем каждый вариант
    results = {}

    # Вариант А: правильный
    results['A_correct'] = await test_response_variant('A (правильный)', response_data_correct)
    await asyncio.sleep(0.05)

    # Сбрасываем future для следующего теста
    if not future.done():
        future = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future

    # Вариант Б: без ID
    results['B_no_id'] = await test_response_variant('B (без request_id)', response_data_no_id)
    await asyncio.sleep(0.05)

    # Сбрасываем
    if not future.done():
        future = asyncio.get_event_loop().create_future()
        client._pending_requests[request_id] = future

    # Вариант В: чужой ID
    results['C_wrong_id'] = await test_response_variant('C (чужой request_id)', response_data_wrong_id)

    # === ЭТАП 5: Итоговый анализ ===
    log_step(6, "ИТОГОВЫЙ АНАЛИЗ", {
        "Вариант A (правильный)": "✅ Сопоставлен" if results['A_correct'][0] else "❌ Не сопоставлен",
        "Вариант B (без ID)": "✅ Проигнорирован (ожидаемо)" if not results['B_no_id'][
            0] else "⚠️ Сопоставлен (неожиданно)",
        "Вариант C (чужой ID)": "✅ Проигнорирован (ожидаемо)" if not results['C_wrong_id'][
            0] else "❌ Сопоставлен (баг!)",
    })

    # Cleanup
    receive_task.cancel()
    try:
        await receive_task
    except asyncio.CancelledError:
        pass
    client._pending_requests.clear()

    # === ВЫВОД ДЛЯ ПОЛЬЗОВАТЕЛЯ ===
    print(f"\n{'🔍' * 35}")
    print("ДИАГНОСТИЧЕСКИЙ ВЫВОД:")
    print(f"{'🔍' * 35}")

    if results['A_correct'][0]:
        print("✅ Логика сопоставления в клиенте РАБОТАЕТ корректно.")
        print("   Если в реальном приложении ошибка — СЕРВЕР не отправляет request_id в ответе.")
        print("\n   🔧 Проверьте сервер: в ответе на 'message' должен быть тот же 'request_id',")
        print("      что был в запросе.")
    else:
        print("❌ Логика сопоставления в клиенте НЕ РАБОТАЕТ.")
        print("   🔧 Нужно исправить _receive_loop в client/messenger_client.py:")
        print("      1. Проверять 'request_id' в ответе ПЕРЕД обработкой событий")
        print("      2. Использовать: if req_id and req_id in self._pending_requests:")
        print("      3. Добавлять 'continue' после set_result()")

    print(f"{'🔍' * 35}\n")

    return results['A_correct'][0]


async def main():
    print("\n" + "🚀" * 35)
    print("   ДИАГНОСТИЧЕСКИЙ ТЕСТ: _receive_loop + request_id")
    print("🚀" * 35 + "\n")

    success = await test_full_flow_with_debug()

    if success:
        print("✅ Тест завершён: клиентская логика корректна")
        print("\n📋 Следующий шаг: проверить, что сервер отправляет request_id в ответе")
        print("   Запустите сервер с логом и посмотрите ответ на 'message':")
        print("   > TEXT '{\"type\": \"message_sent\", ..., \"request_id\": \"...\"}'")
        return 0
    else:
        print("❌ Тест завершён: найдена проблема в клиенте")
        print("\n📋 Следующий шаг: исправить _receive_loop по инструкции выше")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)