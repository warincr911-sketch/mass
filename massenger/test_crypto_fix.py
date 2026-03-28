#!/usr/bin/env python3
"""
Тест криптографии после исправлений
Проверяет: encrypt_message ↔ decrypt_message roundtrip
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.crypto import ClientCrypto


def test_roundtrip():
    """Тест: шифрование → расшифровка одного клиента"""
    print("🔐 Тест криптографии: roundtrip")
    print("-" * 50)

    crypto = ClientCrypto()
    public_key = crypto.get_public_key_pem()

    test_messages = [
        "Привет, мир! 🌍",
        "Тестовое сообщение с эмодзи 🔐✨",
        "A" * 1000,  # Длинное сообщение
        "Спецсимволы: !@#$%^&*()_+-=[]{}|;':\",./<>?",
    ]

    all_passed = True

    for i, original in enumerate(test_messages, 1):
        try:
            # Шифрование
            encrypted = crypto.encrypt_message(original, public_key)

            # Расшифровка
            decrypted = crypto.decrypt_message(encrypted)

            # Проверка
            if original == decrypted:
                print(f"✅ Тест {i}: PASS ({len(original)} символов)")
            else:
                print(f"❌ Тест {i}: FAIL — не совпадает!")
                print(f"   Original:  {original[:50]}...")
                print(f"   Decrypted: {decrypted[:50]}...")
                all_passed = False

        except Exception as e:
            print(f"❌ Тест {i}: ERROR — {type(e).__name__}: {e}")
            all_passed = False

    print("-" * 50)
    if all_passed:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
        return 0
    else:
        print("⚠️ ЕСТЬ ОШИБКИ — проверьте код")
        return 1


def test_cross_client():
    """Тест: шифрование для другого клиента (имитация)"""
    print("\n🔐 Тест криптографии: кросс-клиент")
    print("-" * 50)

    # Создаём двух "клиентов" с разными ключами
    client_a = ClientCrypto()
    client_b = ClientCrypto()

    original = "Секретное сообщение от A к B 🔐"

    try:
        # A шифрует публичным ключом B
        encrypted = client_a.encrypt_message(original, client_b.get_public_key_pem())
        print(f"✅ A зашифровал сообщение ({len(encrypted)} символов base64)")

        # B расшифровывает своим приватным ключом
        decrypted = client_b.decrypt_message(encrypted)
        print(f"✅ B расшифровал сообщение")

        # Проверка
        if original == decrypted:
            print(f"✅ Кросс-клиент тест: PASS")
            print(f"   Сообщение: {decrypted}")
            return 0
        else:
            print(f"❌ Кросс-клиент тест: FAIL — не совпадает!")
            return 1

    except Exception as e:
        print(f"❌ Кросс-клиент тест: ERROR — {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    print("🚀 Secure Messenger — Crypto Test Suite")
    print("=" * 50)

    result1 = test_roundtrip()
    result2 = test_cross_client()

    print("\n" + "=" * 50)
    if result1 == 0 and result2 == 0:
        print("✅ ALL TESTS PASSED — криптография работает!")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED — нужна доработка")
        sys.exit(1)