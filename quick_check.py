#!/usr/bin/env python3
"""
Быстрая проверка основных настроек перед запуском.
"""


def quick_check():
    """Быстрая проверка критических настроек."""
    try:
        from config.settings import EXCHANGES_CONFIG

        print("🔍 Быстрая проверка настроек...")

        # Проверяем основные поля для каждой биржи
        required_fields = ['api_url', 'trades_limit', 'cycle_pause_minutes', 'weights']

        for exchange, config in EXCHANGES_CONFIG.items():
            missing = [field for field in required_fields if field not in config]
            if missing:
                print(f"❌ {exchange}: отсутствуют поля {missing}")
                return False
            else:
                print(f"✅ {exchange}: конфигурация корректна")

        print("🎉 Все настройки в порядке!")
        return True

    except Exception as e:
        print(f"❌ Ошибка проверки: {e}")
        return False


if __name__ == "__main__":
    import sys

    success = quick_check()
    sys.exit(0 if success else 1)