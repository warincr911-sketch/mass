import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import pytest
from client.crypto import ClientCrypto


def test_crypto_roundtrip():
    """Тест кругового шифрования/расшифрования"""

    crypto = ClientCrypto()
    public_pem = crypto.get_public_key_pem()

    original = "Привет! Это тестовое сообщение 🧪"
    original_bytes = original.encode('utf-8')

    encrypted_content, encrypted_key, iv = crypto.encrypt_file(original_bytes, "recipient")
    decrypted = crypto.decrypt_file(encrypted_content, encrypted_key, iv)
    decrypted_text = decrypted.decode('utf-8')

    assert original == decrypted_text
    print("✅ Roundtrip-тест пройден!")


if __name__ == "__main__":
    test_crypto_roundtrip()