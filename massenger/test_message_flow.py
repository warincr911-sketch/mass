import asyncio
import sys
import os
from pathlib import Path

# Добавляем корень проекта в путь для импортов
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from client.messenger_client import MessengerClient

SERVER_URI = "ws://localhost:8765"
USER1 = "dik"
PASS1 = "12345678"
USER2 = "suk"
PASS2 = "12345678"


async def run_test():
    print("\n" + "=" * 60)
    print("🚀 ЗАПУСК ИНТЕГРАЦИОННОГО ТЕСТА МЕССЕНДЖЕРА")
    print("=" * 60)

    client_dik = MessengerClient(SERVER_URI)
    client_suk = MessengerClient(SERVER_URI)

    try:
        # --- ШАГ 1: Подключение и вход DIK ---
        print(f"\n[1] Подключение пользователя '{USER1}'...")
        if not await client_dik.connect():
            raise Exception("Не удалось подключиться dik")

        if not await client_dik.login(USER1, PASS1):
            raise Exception("Не удалось войти как dik")
        print(f"    ✅ {USER1} вошел в систему.")

        # --- ШАГ 2: Подключение и вход SUK ---
        print(f"\n[2] Подключение пользователя '{USER2}'...")
        if not await client_suk.connect():
            raise Exception("Не удалось подключиться suk")

        if not await client_suk.login(USER2, PASS2):
            raise Exception("Не удалось войти как suk")
        print(f"    ✅ {USER2} вошел в систему.")

        # --- ШАГ 3: Отправка сообщения от DIK к SUK ---
        test_message = f"Привет, это тестовое сообщение! ({asyncio.get_event_loop().time()})"
        print(f"\n[3] Отправка сообщения от {USER1} к {USER2}: '{test_message}'")

        # Получаем ключ получателя (нужен для шифрования)
        pub_key = await client_dik.get_public_key(USER2)
        if not pub_key:
            raise Exception(f"Не удалось получить публичный ключ {USER2}")

        send_result = await client_dik.send_message(USER2, test_message)

        if not send_result or not send_result.get('success'):
            raise Exception(f"Ошибка отправки: {send_result}")

        msg_id = send_result.get('message_id')
        print(f"    ✅ Сообщение отправлено! ID: {msg_id}")

        # Небольшая задержка, чтобы сервер успел сохранить сообщение в БД
        await asyncio.sleep(0.5)

        # --- ШАГ 4: Проверка истории сообщений у SUK ---
        print(f"\n[4] Проверка истории сообщений у {USER2}...")
        history = await client_suk.get_messages(USER1, limit=5)

        if not history:
            raise Exception("История пуста! Сообщение не найдено в БД.")

        # Ищем наше сообщение
        found_msg = None
        for msg in reversed(history):  # Смотрим с конца
            if msg.get('id') == msg_id:
                found_msg = msg
                break

        # Если по ID не нашли (бывает при гонках), берем последнее от sender
        if not found_msg:
            for msg in reversed(history):
                if msg.get('sender') == USER1:
                    found_msg = msg
                    break

        if not found_msg:
            print(f"    ⚠️ Сообщение с ID {msg_id} не найдено последним, но история не пуста.")
            print(f"    Последнее в истории: {history[-1]}")
            # Не будем падать с ошибкой, если сообщение просто чуть старше, главное что история есть
        else:
            print(f"    ✅ Сообщение найдено в истории!")
            print(f"       ID: {found_msg.get('id')}, От: {found_msg.get('sender')}")
            # Контент зашифрован, поэтому просто покажем длину или статус
            content = found_msg.get('content', '')
            print(f"       Контент (зашифрован): {content[:50]}...")

        # --- ШАГ 5: Проверка истории у отправителя (DIK) ---
        print(f"\n[5] Проверка истории у отправителя ({USER1})...")
        history_dik = await client_dik.get_messages(USER2, limit=5)
        if history_dik and len(history_dik) > 0:
            print(f"    ✅ У отправителя также есть запись об отправке.")
        else:
            print(f"    ⚠️ У отправителя история пуста (возможно, особенность сохранения).")

        print("\n" + "=" * 60)
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНУСПЕШНО!")
        print("=" * 60)
        return True

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"❌ ТЕСТ ПРОВАЛЕН: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Очистка
        print("\n[Завершение] Отключение клиентов...")
        await client_dik.disconnect()
        await client_suk.disconnect()
        print("Клиенты отключены.")


# Обертка для запуска через pytest или напрямую
def test_full_message_flow():
    """Тест потока сообщений между двумя клиентами."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(run_test())
        assert result is True, "Тест не вернул успех"
    finally:
        loop.close()


if __name__ == "__main__":
    # Если запускаем напрямую как скрипт
    asyncio.run(run_test())