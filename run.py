#!/usr/bin/env python3
"""
Скрипт запуска мониторинга с правильными настройками.
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

# Проверяем наличие .env файла
if not os.path.exists('.env'):
    print("Файл .env не найден!")
    print("Создайте его из .env.example")
    sys.exit(1)

# Загружаем переменные из .env
from dotenv import load_dotenv
load_dotenv()
print("Переменные окружения загружены из .env")

# НЕ устанавливаем DISABLE_SSL_VERIFY автоматически
# Пусть берется из .env файла если нужно

# Проверяем установлены ли зависимости
try:
    result = subprocess.run(
        [python_path, "-c", "import aiohttp, aiomysql"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("Зависимости не установлены. Устанавливаем...")
        subprocess.run([python_path, "-m", "pip", "install", "-r", "requirements.txt"])
except Exception as e:
    print(f"Ошибка при проверке зависимостей: {e}")

# Быстрая проверка конфигурации
print("\n🔍 Быстрая проверка конфигурации...")
try:
    result = subprocess.run([python_path, 'quick_check.py'], capture_output=True, text=True)
    if result.returncode != 0:
        print("❌ Проблемы с конфигурацией:")
        print(result.stdout)
        print(result.stderr)
        print("Запускаем полную проверку...")
        subprocess.run([python_path, 'check_config.py'])
        sys.exit(1)
    else:
        print(result.stdout)
except FileNotFoundError:
    print("⚠️  Скрипт проверки не найден, продолжаем запуск...")

# Запускаем основной скрипт
print("Запуск мониторинга...")
subprocess.run([python_path, 'main.py'])