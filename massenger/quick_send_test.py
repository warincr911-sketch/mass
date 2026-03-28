# quick_send_test.py
import asyncio
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client.messenger_client import MessengerClient


async def main():
    client = MessengerClient()
    await client.connect()
    await client.login("dik", "12345678")

    # Простая отправка через нормальный метод
    key = await client.get_public_key("suk")
    if key:
        enc = client.crypto.encrypt_message("QUICK_TEST", key)
        result = await client.send_message("suk", enc)
        print(f"✅ Результат: {result}")
    else:
        print("❌ Нет ключа")

    await client.disconnect()


asyncio.run(main())