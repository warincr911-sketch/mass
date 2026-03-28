#!/usr/bin/env python3
"""
Просмотр структуры базы данных
Запуск: python massenger/tests/test_db_structure.py
"""

import sqlite3
import os

db_path = os.path.abspath('massenger/server/messenger.db')

print('=' * 80)
print('📊 СТРУКТУРА БАЗЫ ДАННЫХ')
print('=' * 80)
print(f'Путь к БД: {db_path}')
print('=' * 80)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Все таблицы
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print(f'\n✅ Найдено таблиц: {len(tables)}')

for table in tables:
    table_name = table[0]
    print(f'\n📁 Таблица: {table_name}')
    print('-' * 40)

    # Структура таблицы
    cursor.execute(f'PRAGMA table_info({table_name})')
    columns = cursor.fetchall()

    for col in columns:
        print(f'   {col[1]} ({col[2]})')

    # Количество записей
    cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
    count = cursor.fetchone()[0]
    print(f'   Записей: {count}')

    # Покажем первые 3 записи
    if count > 0:
        print(f'   Пример данных:')
        cursor.execute(f'SELECT * FROM {table_name} LIMIT 3')
        rows = cursor.fetchall()
        for row in rows:
            print(f'      {row}')

conn.close()
print('\n' + '=' * 80)