#!/usr/bin/env python3
"""Быстрые тесты для MessengerGUI"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.crypto import ClientCrypto
from gui.messenger_gui import MessengerGUI, GUIConstants

def test_gui_constants():
    """Проверка констант"""
    assert GUIConstants.TIMEOUT_SHORT == 5
    assert GUIConstants.MAX_FILE_SIZE == 100 * 1024 * 1024
    assert GUIConstants.MIN_PUBLIC_KEY_LENGTH == 400

def test_validate_public_key():
    """Валидация публичного ключа"""
    crypto = ClientCrypto()
    valid_key = crypto.get_public_key_pem()
    assert MessengerGUI._validate_public_key(valid_key) is True
    assert MessengerGUI._validate_public_key("not-a-key") is False
    assert MessengerGUI._validate_public_key("") is False
    assert MessengerGUI._validate_public_key(None) is False

def test_sanitize_for_log():
    """Санитизация логов"""
    from gui.messenger_gui import _sanitize_for_log
    data = {'password': 'secret', 'message': 'hello'}
    sanitized = _sanitize_for_log(data)
    assert sanitized['password'] == '***REDACTED***'
    assert sanitized['message'] == 'hello'

if __name__ == "__main__":
    pytest.main([__file__, '-v'])