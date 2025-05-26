#!/usr/bin/env python3
"""
Тестовый скрипт для проверки загрузки переменных окружения.
"""
import os
from dotenv import load_dotenv


def test_env_loading():
    """Тестирует загрузку переменных окружения."""
    print("🧪 Тестирование загрузки переменных окружения...")

    # Проверяем существование .env файла
    if not os.path.exists('.env'):
        print("❌ Файл .env не найден!")
        return False
    else:
        print("✅ Файл .env найден")

    # Загружаем .env
    load_dotenv()

    # Тестируемые переменные
    test_vars = [
        'MYSQL_HOST', 'MYSQL_PASSWORD', 'MYSQL_DATABASE',
        'BINANCE_CYCLE_MINUTES', 'BYBIT_CYCLE_MINUTES', 'COINBASE_CYCLE_MINUTES',
        'LOG_LEVEL', 'DISABLE_SSL_VERIFY',
        'MIN_VOLUME_USD', 'MIN_TRADE_VALUE_USD',
        'BINANCE_ENABLED', 'BYBIT_ENABLED', 'COINBASE_ENABLED'
    ]

    print("\n📋 Проверка переменных из .env:")
    found_vars = []
    missing_vars = []

    for var in test_vars:
        value = os.getenv(var)
        if value is not None:
            if 'PASSWORD' in var:
                display_value = '***' if value else 'ПУСТОЙ'
            else:
                display_value = value
            print(f"  ✅ {var} = {display_value}")
            found_vars.append(var)
        else:
            print(f"  ❌ {var} = НЕ УСТАНОВЛЕНА")
            missing_vars.append(var)

    print(f"\n📊 Результат:")
    print(f"  Найдено: {len(found_vars)} переменных")
    print(f"  Отсутствует: {len(missing_vars)} переменных")

    if missing_vars:
        print(f"\n⚠️  Отсутствующие переменные будут использовать значения по умолчанию:")
        for var in missing_vars:
            print(f"    {var}")

    # Тестируем загрузку настроек
    print(f"\n🔧 Тестирование импорта настроек...")
    try:
        from config.settings import EXCHANGES_CONFIG, LOG_LEVEL, MIN_VOLUME_USD

        print(f"✅ Настройки успешно загружены:")
        print(f"  LOG_LEVEL: {LOG_LEVEL}")
        print(f"  MIN_VOLUME_USD: ${MIN_VOLUME_USD:,}")

        print(f"\n🏦 Статус бирж:")
        for exchange, config in EXCHANGES_CONFIG.items():
            status = "ВКЛЮЧЕНА" if config.get('enabled', True) else "ОТКЛЮЧЕНА"
            cycle_pause = config.get('cycle_pause_minutes', 'не указано')
            rate_limit = config.get('rate_limit', 'не указано')
            print(f"  {exchange.upper()}: {status}")
            print(f"    Пауза: {cycle_pause}мин")
            print(f"    Rate limit: {rate_limit}/мин")

        return True

    except Exception as e:
        print(f"❌ Ошибка загрузки настроек: {e}")
        import traceback
        print(f"Подробности ошибки:")
        traceback.print_exc()
        return False


def test_specific_setting():
    """Тестирует конкретную настройку."""
    print(f"\n🎯 Детальная проверка настроек бирж...")

    # Проверяем что значения действительно берутся из .env
    test_cases = [
        ('BINANCE_CYCLE_MINUTES', 'Binance cycle pause'),
        ('COINBASE_RATE_LIMIT', 'Coinbase rate limit'),
        ('LOG_LEVEL', 'Log level'),
    ]

    for env_var, description in test_cases:
        env_value = os.getenv(env_var)
        if env_value:
            print(f"  ✅ {description}: переменная {env_var}={env_value} найдена в окружении")
        else:
            print(f"  ⚠️  {description}: переменная {env_var} не установлена, используется значение по умолчанию")


if __name__ == "__main__":
    success = test_env_loading()
    test_specific_setting()

    if success:
        print(f"\n🎉 Тест пройден! Переменные окружения загружаются корректно.")
    else:
        print(f"\n💥 Тест не пройден! Проверьте настройки.")

    print(f"\n💡 Совет: Если переменные не загружаются:")
    print(f"   1. Убедитесь что файл .env находится в корне проекта")
    print(f"   2. Проверьте синтаксис в .env (НЕТ пробелов вокруг =)")
    print(f"   3. Убедитесь что переменные не закомментированы (#)")
    print(f"   4. Перезапустите приложение после изменения .env")