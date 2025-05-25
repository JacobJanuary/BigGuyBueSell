#!/bin/bash

# Скрипт запуска мониторинга

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

# Проверяем, что виртуальное окружение активировано
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Не удалось активировать виртуальное окружение"
    exit 1
fi

echo "Используется Python из: $(which python)"
echo "Виртуальное окружение: $VIRTUAL_ENV"

# Загружаем переменные из .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "Переменные окружения загружены из .env"
else
    echo "Файл .env не найден!"
    echo "Создайте его из .env.example"
    exit 1
fi

# НЕ устанавливаем DISABLE_SSL_VERIFY автоматически
# Если нужно отключить SSL, добавьте в .env файл:
# DISABLE_SSL_VERIFY=true

# Проверяем установлены ли зависимости
if ! python -c "import aiohttp" 2>/dev/null; then
    echo "Зависимости не установлены. Устанавливаем..."
    pip install -r requirements.txt
fi

# Запускаем скрипт
echo "Запуск мониторинга..."
python main.py