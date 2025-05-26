#!/bin/bash

# Скрипт для запуска тестов Bybit

# Определяем путь к виртуальному окружению
VENV_PATH=".venv"

# Проверяем существование виртуального окружения
if [ ! -d "$VENV_PATH" ]; then
    echo "Виртуальное окружение не найдено в $VENV_PATH"
    echo "Создайте его командой: python -m venv $VENV_PATH"
    exit 1
fi

# Активируем виртуальное окружение
source "$VENV_PATH/bin/activate"

# Загружаем переменные из .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Устанавливаем переменную для отключения SSL проверки
export DISABLE_SSL_VERIFY=true

# Запускаем тесты
echo "Запуск тестов Bybit с отключенной SSL проверкой..."
python tests/test_bybit.py