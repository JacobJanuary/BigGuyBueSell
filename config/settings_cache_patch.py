#!/usr/bin/env python3
"""
Патч для добавления настроек кэширования в config/settings.py
config/settings_cache_patch.py
"""
import os
import shutil
from datetime import datetime

# !/usr/bin/env python3
"""
Патч для добавления настроек кэширования в config/settings.py
config/settings_cache_patch.py
"""
import os
import shutil
from datetime import datetime
from pathlib import Path


def find_settings_file():
    """Находит файл config/settings.py в проекте."""
    possible_paths = [
        'config/settings.py',
        './config/settings.py',
        '../config/settings.py',
        '../../config/settings.py'
    ]

    # Добавляем поиск от текущего файла
    current_dir = Path(__file__).parent
    project_root = current_dir.parent if current_dir.name == 'config' else current_dir
    settings_from_root = project_root / 'config' / 'settings.py'
    possible_paths.insert(0, str(settings_from_root))

    print("🔍 Поиск config/settings.py...")
    print(f"Текущая директория: {os.getcwd()}")

    for path in possible_paths:
        abs_path = os.path.abspath(path)
        print(f"  Проверяем: {abs_path}")
        if os.path.exists(path):
            print(f"  ✅ Найден: {abs_path}")
            return path
        else:
            print(f"  ❌ Не найден: {abs_path}")

    # Последняя попытка - поиск во всех поддиректориях
    print("🔍 Расширенный поиск...")
    for root, dirs, files in os.walk('.'):
        if 'settings.py' in files and 'config' in root:
            found_path = os.path.join(root, 'settings.py')
            print(f"  ✅ Найден через поиск: {os.path.abspath(found_path)}")
            return found_path

    return None


def backup_settings(settings_file):
    """Создает резервную копию settings.py."""
    if not os.path.exists(settings_file):
        print(f"❌ Файл {settings_file} не найден")
        return None

    # Создаем backup в той же директории что и оригинал
    settings_dir = os.path.dirname(settings_file)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(settings_dir, f'settings_backup_{timestamp}.py')

    try:
        shutil.copy2(settings_file, backup_file)
        print(f"✅ Создана резервная копия: {backup_file}")
        return backup_file
    except Exception as e:
        print(f"❌ Ошибка создания резервной копии: {e}")
        return None


def apply_cache_settings():
    """Применяет настройки кэширования к config/settings.py."""
    # Ищем файл settings.py
    settings_file = find_settings_file()

    if not settings_file:
        print("❌ Файл config/settings.py не найден в проекте")
        print("\n💡 Возможные решения:")
        print("1. Убедитесь что вы запускаете скрипт из корня проекта")
        print("2. Проверьте что файл config/settings.py существует")
        print("3. Попробуйте запустить: python config/settings_cache_patch.py")
        return False

    # Создаем резервную копию
    backup_file = backup_settings(settings_file)
    if not backup_file:
        return False

    try:
        # Читаем существующий файл
        with open(settings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Проверяем, не добавлены ли уже настройки
        if 'MEMORY_CACHE_ENABLED' in content:
            print("ℹ️  Настройки кэширования уже добавлены")
            return True

        # Проверяем есть ли уже функции get_env_*
        has_get_env_functions = 'def get_env_int(' in content and 'def get_env_bool(' in content

        # Добавляем настройки кэширования
        if has_get_env_functions:
            # Если функции уже есть, добавляем только настройки
            cache_settings = '''

# =================== ОПТИМИЗАЦИЯ КЭШИРОВАНИЯ ===================

# Основные настройки кэширования
CACHE_OPTIMIZATION_ENABLED = get_env_bool('CACHE_OPTIMIZATION_ENABLED', True)
MEMORY_CACHE_ENABLED = get_env_bool('MEMORY_CACHE_ENABLED', True)
MEMORY_CACHE_TTL_MINUTES = get_env_int('MEMORY_CACHE_TTL_MINUTES', 30)
API_UPDATE_INTERVAL_MINUTES = get_env_int('API_UPDATE_INTERVAL_MINUTES', 60)
DB_CACHE_TTL_HOURS = get_env_int('DB_CACHE_TTL_HOURS', 2)

# Настройки мониторинга кэша
CACHE_METRICS_ENABLED = get_env_bool('CACHE_METRICS_ENABLED', True)
CACHE_FALLBACK_ENABLED = get_env_bool('CACHE_FALLBACK_ENABLED', True)
CACHE_DEBUG_LOGGING = get_env_bool('CACHE_DEBUG_LOGGING', False)

# Пороги для оптимизации
CACHE_HIT_RATE_WARNING_THRESHOLD = get_env_int('CACHE_HIT_RATE_WARNING_THRESHOLD', 70)
API_CALLS_PER_HOUR_WARNING = get_env_int('API_CALLS_PER_HOUR_WARNING', 10)

if LOG_LEVEL == 'DEBUG':
    print("🚀 Настройки оптимизированного кэширования загружены")

# ============================================================
'''
        else:
            # Если функций нет, добавляем их тоже
            cache_settings = '''

# =================== ОПТИМИЗАЦИЯ КЭШИРОВАНИЯ ===================

# Вспомогательные функции (если их еще нет)
def get_env_int(key: str, default: int) -> int:
    """Безопасно получает integer из переменных окружения."""
    try:
        value = os.getenv(key)
        if value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        return default

def get_env_bool(key: str, default: bool) -> bool:
    """Безопасно получает boolean из переменных окружения."""
    value = os.getenv(key, '').lower()
    if value in ('true', '1', 'yes', 'on'):
        return True
    elif value in ('false', '0', 'no', 'off'):
        return False
    return default

# Основные настройки кэширования
CACHE_OPTIMIZATION_ENABLED = get_env_bool('CACHE_OPTIMIZATION_ENABLED', True)
MEMORY_CACHE_ENABLED = get_env_bool('MEMORY_CACHE_ENABLED', True)
MEMORY_CACHE_TTL_MINUTES = get_env_int('MEMORY_CACHE_TTL_MINUTES', 30)
API_UPDATE_INTERVAL_MINUTES = get_env_int('API_UPDATE_INTERVAL_MINUTES', 60)
DB_CACHE_TTL_HOURS = get_env_int('DB_CACHE_TTL_HOURS', 2)

# Настройки мониторинга кэша
CACHE_METRICS_ENABLED = get_env_bool('CACHE_METRICS_ENABLED', True)
CACHE_FALLBACK_ENABLED = get_env_bool('CACHE_FALLBACK_ENABLED', True)
CACHE_DEBUG_LOGGING = get_env_bool('CACHE_DEBUG_LOGGING', False)

# Пороги для оптимизации
CACHE_HIT_RATE_WARNING_THRESHOLD = get_env_int('CACHE_HIT_RATE_WARNING_THRESHOLD', 70)
API_CALLS_PER_HOUR_WARNING = get_env_int('API_CALLS_PER_HOUR_WARNING', 10)

if LOG_LEVEL == 'DEBUG':
    print("🚀 Настройки оптимизированного кэширования загружены")

# ============================================================
'''

        # Добавляем настройки в конец файла
        new_content = content + cache_settings

        # Сохраняем изменения
        with open(settings_file, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print(f"✅ Настройки кэширования добавлены в {settings_file}")
        return True

    except Exception as e:
        print(f"❌ Ошибка обновления настроек: {e}")

        # Восстанавливаем из резервной копии
        try:
            shutil.copy2(backup_file, settings_file)
            print("🔄 Файл восстановлен из резервной копии")
        except:
            pass

        return False


def create_env_patch():
    """Добавляет настройки в .env файл."""
    env_file = '.env'

    env_settings = '''
# =================== ОПТИМИЗАЦИЯ КЭШИРОВАНИЯ ===================
CACHE_OPTIMIZATION_ENABLED=true
MEMORY_CACHE_ENABLED=true
MEMORY_CACHE_TTL_MINUTES=30
API_UPDATE_INTERVAL_MINUTES=60
DB_CACHE_TTL_HOURS=2
CACHE_METRICS_ENABLED=true
CACHE_FALLBACK_ENABLED=true
CACHE_DEBUG_LOGGING=false
'''

    try:
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                content = f.read()

            if 'MEMORY_CACHE_ENABLED' not in content:
                with open(env_file, 'a', encoding='utf-8') as f:
                    f.write(env_settings)
                print("✅ Настройки кэширования добавлены в .env")
            else:
                print("ℹ️  Настройки кэширования уже есть в .env")
        else:
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write(env_settings.strip())
            print("✅ Создан .env файл с настройками кэширования")

        return True

    except Exception as e:
        print(f"❌ Ошибка обновления .env: {e}")
        return False


def main():
    """Главная функция."""
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║        ПАТЧ НАСТРОЕК КЭШИРОВАНИЯ                  ║
    ╚═══════════════════════════════════════════════════╝
    """)

    print("Выберите действие:")
    print("1. 🔧 Применить настройки к config/settings.py")
    print("2. ⚙️  Обновить .env файл")
    print("3. 🚀 Применить все настройки")
    print("4. 🚪 Выход")

    try:
        choice = input("\nВведите номер (1-4): ").strip()
    except KeyboardInterrupt:
        print("\n👋 Выход")
        return

    if choice == "1":
        print("\n🔧 Применение настроек к config/settings.py...")
        success = apply_cache_settings()
        if success:
            print("✅ Настройки успешно применены!")
        else:
            print("❌ Не удалось применить настройки")

    elif choice == "2":
        print("\n⚙️  Обновление .env файла...")
        success = create_env_patch()
        if success:
            print("✅ .env файл успешно обновлен!")
        else:
            print("❌ Не удалось обновить .env")

    elif choice == "3":
        print("\n🚀 Применение всех настроек...")

        settings_success = apply_cache_settings()
        env_success = create_env_patch()

        if settings_success and env_success:
            print("""
✅ ВСЕ НАСТРОЙКИ ПРИМЕНЕНЫ УСПЕШНО!

📋 Следующие шаги:
1. Перезапустите приложение для применения настроек
2. Проверьте логи на сообщение "🚀 Настройки оптимизированного кэширования загружены"
3. Запустите python run_cache_tests.py для проверки

🔄 Для отката используйте резервные копии в config/
            """)
        else:
            print("❌ Не все настройки применены успешно")

    elif choice == "4":
        print("👋 Выход")

    else:
        print("❌ Неверный выбор")


if __name__ == "__main__":
    main()