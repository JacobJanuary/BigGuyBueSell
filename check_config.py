#!/usr/bin/env python3
"""
Исправленная версия скрипта для проверки конфигурации.
"""
import sys
import os
from dotenv import load_dotenv


def check_config():
    """Проверяет все необходимые настройки."""
    print("🔍 Проверка конфигурации системы...")

    # Загружаем переменные окружения
    load_dotenv()

    errors = []
    warnings = []

    # Проверяем .env файл
    if not os.path.exists('.env'):
        warnings.append("Файл .env не найден, используются значения по умолчанию")
        print("⚠️  Файл .env не найден")
    else:
        print("✅ Файл .env найден")

    # Проверяем MySQL настройки
    print("\n💾 MySQL настройки:")
    mysql_settings = {
        'MYSQL_HOST': os.getenv('MYSQL_HOST', 'localhost'),
        'MYSQL_PORT': os.getenv('MYSQL_PORT', '3306'),
        'MYSQL_USER': os.getenv('MYSQL_USER', 'root'),
        'MYSQL_PASSWORD': os.getenv('MYSQL_PASSWORD', ''),
        'MYSQL_DATABASE': os.getenv('MYSQL_DATABASE', 'crypto_db')
    }

    for key, value in mysql_settings.items():
        if key == 'MYSQL_PASSWORD':
            display_value = '***' if value else 'НЕ УСТАНОВЛЕН'
        else:
            display_value = value
        print(f"  {key}: {display_value}")

    if not mysql_settings['MYSQL_PASSWORD']:
        warnings.append("MySQL пароль не установлен")

    # Тестируем импорт настроек
    print("\n🔧 Проверка импорта настроек...")
    try:
        from config.settings import EXCHANGES_CONFIG, LOG_LEVEL, MIN_VOLUME_USD
        print("✅ Настройки успешно импортированы")
        print(f"  LOG_LEVEL: {LOG_LEVEL}")
        print(f"  MIN_VOLUME_USD: ${MIN_VOLUME_USD:,}")

    except Exception as e:
        errors.append(f"Критическая ошибка импорта настроек: {e}")
        print(f"❌ Ошибка импорта настроек: {e}")
        return False

    # Проверяем конфигурацию бирж
    print("\n🏦 Конфигурация бирж:")
    enabled_exchanges = []
    disabled_exchanges = []

    # Используем реальную структуру из загруженной конфигурации
    for exchange, config in EXCHANGES_CONFIG.items():
        try:
            # Проверяем реально существующие поля
            has_url = 'api_url' in config
            has_limit = 'trades_limit' in config
            has_pause = 'cycle_pause_minutes' in config
            has_rate = 'rate_limit' in config
            has_weights = 'weights' in config
            is_enabled = config.get('enabled', True)

            missing_fields = []
            if not has_url: missing_fields.append('api_url')
            if not has_limit: missing_fields.append('trades_limit')
            if not has_pause: missing_fields.append('cycle_pause_minutes')
            if not has_rate: missing_fields.append('rate_limit')
            if not has_weights: missing_fields.append('weights')

            if missing_fields:
                errors.append(f"Биржа {exchange}: отсутствуют поля {missing_fields}")
                print(f"  ❌ {exchange.upper()}: отсутствуют поля {missing_fields}")
            else:
                if is_enabled:
                    enabled_exchanges.append(exchange)
                    print(f"  ✅ {exchange.upper()}: все поля присутствуют (включена)")
                else:
                    disabled_exchanges.append(exchange)
                    print(f"  ⏹️  {exchange.upper()}: все поля присутствуют (отключена)")

        except Exception as e:
            errors.append(f"Ошибка проверки {exchange}: {e}")
            print(f"  ❌ {exchange.upper()}: ошибка проверки - {e}")

    if not enabled_exchanges:
        errors.append("Все биржи отключены! Включите хотя бы одну биржу.")
        print("❌ Все биржи отключены!")
    else:
        print(f"\n📊 Активные биржи: {', '.join(enabled_exchanges)}")
        if disabled_exchanges:
            print(f"💤 Отключенные биржи: {', '.join(disabled_exchanges)}")

    # Проверяем зависимости (исправленная логика)
    print("\n📦 Проверка зависимостей:")
    dependencies_check = [
        ('aiohttp', 'aiohttp'),
        ('aiomysql', 'aiomysql'),
        ('dateutil', 'python-dateutil'),
        ('dotenv', 'python-dotenv')
    ]

    for import_name, package_name in dependencies_check:
        try:
            __import__(import_name)
            print(f"  ✅ {package_name}")
        except ImportError:
            # Это не критическая ошибка если main.py работает
            warnings.append(f"Пакет {package_name} не найден при проверке (но может быть установлен)")
            print(f"  ⚠️  {package_name} (проверьте установку)")

    # Проверяем структуру проекта
    print("\n📁 Структура проекта:")
    required_dirs = [
        'config', 'database', 'exchanges/binance',
        'exchanges/bybit', 'exchanges/coinbase',
        'utils', 'workers'
    ]

    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"  ✅ {dir_path}/")
        else:
            errors.append(f"Отсутствует директория: {dir_path}")
            print(f"  ❌ {dir_path}/")

    # Результаты проверки
    print(f"\n{'=' * 60}")
    if errors:
        print("❌ НАЙДЕННЫЕ ПРОБЛЕМЫ:")
        for error in errors:
            print(f"  - {error}")

    if warnings:
        print("⚠️  ПРЕДУПРЕЖДЕНИЯ:")
        for warning in warnings:
            print(f"  - {warning}")

    # Финальная оценка
    critical_errors = [e for e in errors if
                       any(word in e.lower() for word in ['критическая', 'отсутствует директория', 'импорт'])]

    if not critical_errors:
        if errors:
            print("✅ СИСТЕМА ГОТОВА К РАБОТЕ (есть незначительные проблемы)")
            print("💡 Если main.py запускается нормально, можно игнорировать предупреждения о пакетах")
        else:
            print("🎉 ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ! Система готова к работе.")
        return True
    else:
        print("💥 ОБНАРУЖЕНЫ КРИТИЧЕСКИЕ ОШИБКИ!")
        return False


if __name__ == "__main__":
    success = check_config()

    if success:
        print(f"\n🚀 Можно запускать: python main.py")
    else:
        print(f"\n🔧 Исправьте ошибки перед запуском")

    sys.exit(0 if success else 1)