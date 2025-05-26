#!/usr/bin/env python3
"""
Скрипт для запуска тестов Bybit с отключенной SSL проверкой.
"""
import os
import sys
import subprocess
import platform

# Определяем путь к виртуальному окружению
VENV_PATH = ".venv"

# Проверяем существование виртуального окружения
if not os.path.exists(VENV_PATH):
    print(f"Виртуальное окружение не найдено в {VENV_PATH}")
    print(f"Создайте его командой: python -m venv {VENV_PATH}")
    sys.exit(1)

# Определяем путь к Python в виртуальном окружении
if platform.system() == "Windows":
    python_path = os.path.join(VENV_PATH, "Scripts", "python.exe")
else:
    python_path = os.path.join(VENV_PATH, "bin", "python")

# Проверяем, что Python существует
if not os.path.exists(python_path):
    print(f"Python не найден в виртуальном окружении: {python_path}")
    sys.exit(1)

print(f"Используется Python из: {python_path}")

# Загружаем переменные из .env
if os.path.exists('.env'):
    from dotenv import load_dotenv
    load_dotenv()

# Устанавливаем переменную окружения для отключения SSL проверки
os.environ['DISABLE_SSL_VERIFY'] = 'true'

print("SSL проверка отключена для тестов")
print("Запуск тестов Bybit...\n")

# Запускаем тесты
subprocess.run([python_path, 'tests/test_bybit.py'])