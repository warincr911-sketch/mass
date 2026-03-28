#!/usr/bin/env python3
"""
Диагностика зашифрованных данных из базы данных
Запуск: python massenger/tests/test_debug_database.py
"""

import sys
import os
import base64
import sqlite3
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.crypto import ClientCrypto


def find_database():
    """Поиск файла базы данных"""
    possible_paths = [
        "../server/messenger.db",
        "../massenger/server/messenger.db",
        "server/messenger.db",
        "../server/data/messenger.db",
        os.path.expanduser("~") + "/messenger.db",
        "messenger.db"
    ]

    for path in possible_paths:
        abs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), path))
        if os.path.exists(abs_path):
            return abs_path

    # Поиск в директории server
    server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../server"))
    if os.path.exists(server_dir):
        for f in os.listdir(server_dir):
            if f.endswith(".db"):
                return os.path.join(server_dir, f)

    return None


def analyze_database():
    """Анализ зашифрованных сообщений в БД"""

    print("=" * 80)
    print("🔍 ДИАГНОСТИКА БАЗЫ ДАННЫХ")
    print("=" * 80)

    db_path = find_database()

    if not db_path:
        print("❌ База данных не найдена!")
        print("\n📁 Поиск в следующих путях:")
        print("   - ../server/messenger.db")
        print("   - ../massenger/server/messenger.db")
        print("   - server/messenger.db")
        print("\n💡 Запустите сервер сначала, чтобы создать БД")
        return

    print(f"\n✅ База данных найдена: {db_path}")
    print("=" * 80)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Проверяем существование таблицы
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages'")
        if not cursor.fetchone():
            print("❌ Таблица 'messages' не найдена в БД")
            conn.close()
            return

        # Получаем сообщения
        cursor.execute("""
            SELECT id, sender_id, recipient_id, encrypted_data, timestamp 
            FROM messages 
            ORDER BY id DESC 
            LIMIT 10
        """)

        messages = cursor.fetchall()

        if not messages:
            print("❌ В базе данных нет сообщений")
            print("\n💡 Отправьте тестовые сообщения между клиентами")
            conn.close()
            return

        print(f"\n✅ Найдено сообщений: {len(messages)}")
        print("\n" + "-" * 80)

        crypto = ClientCrypto()

        old_format_count = 0
        new_format_count = 0

        for i, msg in enumerate(messages, 1):
            print(f"\n📦 Сообщение #{msg['id']}")
            print(f"   Отправитель ID: {msg['sender_id']}")
            print(f"   Получатель ID: {msg['recipient_id']}")
            print(f"   Время: {msg['timestamp']}")

            encrypted_data = msg['encrypted_data']

            # Анализ размера
            print(f"   Длина encrypted_data: {len(encrypted_data)} символов")

            # Пробуем декодировать base64
            try:
                package = base64.b64decode(encrypted_data.encode('utf-8'))
                print(f"   Размер пакета (bytes): {len(package)}")

                # Проверяем формат
                if len(package) < 272:
                    print(f"   ⚠️ ПРЕДУПРЕЖДЕНИЕ: Пакет слишком короткий!")
                    print(f"      Ожидалось >= 272 байт, получено {len(package)}")
                    print(f"      Это СТАРЫЙ формат данных!")
                    old_format_count += 1
                else:
                    print(f"   ✅ Формат пакета корректный (>= 272 байт)")
                    new_format_count += 1

                    # Показываем структуру
                    encrypted_aes_key = package[:256]
                    iv = package[256:272]
                    encrypted_message = package[272:]

                    print(f"      - encrypted_aes_key: {len(encrypted_aes_key)} байт")
                    print(f"      - IV: {len(iv)} байт")
                    print(f"      - encrypted_message: {len(encrypted_message)} байт")

            except Exception as e:
                print(f"   ❌ Ошибка декодирования base64: {e}")
                old_format_count += 1

            # Пробуем расшифровать
            print(f"\n   🔓 Попытка расшифровки...")
            try:
                decrypted = crypto.decrypt_message(encrypted_data, crypto.get_public_key_pem())
                print(f"   ✅ Расшифровка успешна: '{decrypted[:50]}...'")
            except Exception as e:
                print(f"   ❌ Расшифровка НЕ удалась: {type(e).__name__}: {str(e)[:100]}")

            print("-" * 80)

        conn.close()

        # Итоги
        print("\n" + "=" * 80)
        print("📊 ИТОГИ ДИАГНОСТИКИ")
        print("=" * 80)
        print(f"   Сообщений в новом формате: {new_format_count}")
        print(f"   Сообщений в старом формате: {old_format_count}")

        if old_format_count > 0:
            print("\n⚠️ ОБНАРУЖЕНЫ СООБЩЕНИЯ В СТАРОМ ФОРМАТЕ!")
            print("\n💡 РЕШЕНИЕ:")
            print("   1. Очистите таблицу сообщений в БД")
            print("   2. Или удалите файл messenger.db")
            print("   3. Перезапустите сервер")
            print("   4. Отправьте новые сообщения")
            print("\n   Команда для очистки:")
            print("   sqlite3 " + db_path + " \"DELETE FROM messages;\"")
        else:
            print("\n✅ Все сообщения в правильном формате!")
            print("   Проблема может быть в ключах клиентов")

    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        traceback.print_exc()

    print("\n" + "=" * 80)
    print("Диагностика завершена")
    print("=" * 80)


if __name__ == "__main__":
    analyze_database()