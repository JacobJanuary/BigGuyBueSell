#!/usr/bin/env python3
"""
Быстрый тест интеграции OKX.
"""
import asyncio
import sys
import os


async def quick_test_okx():
    """Быстро тестирует работу OKX."""
    print("🧪 Быстрый тест OKX интеграции...")

    try:
        # 1. Тест импортов
        print("  🔍 Тест импортов...")
        from exchanges.okx.client import OKXClient
        from exchanges.okx.analyzer import OKXAnalyzer
        print("    ✅ Импорты успешны")

        # 2. Тест соединения
        print("  🌐 Тест соединения с OKX API...")
        import aiohttp
        from utils.rate_limiter import RateLimiter

        async with aiohttp.ClientSession() as session:
            rate_limiter = RateLimiter(1200)
            client = OKXClient(session, rate_limiter)

            connection_ok = await client.test_connection()
            if connection_ok:
                print("    ✅ Соединение установлено")
            else:
                print("    ❌ Не удалось подключиться")
                return False

            # 3. Тест получения данных
            print("  📊 Тест получения данных...")
            try:
                instruments = await client.get_instruments_info()
                instruments_count = len(instruments.get('data', []))
                print(f"    ✅ Получено {instruments_count} инструментов")

                if instruments_count > 0:
                    tickers = await client.get_24hr_tickers()
                    tickers_count = len(tickers)
                    print(f"    ✅ Получено {tickers_count} тикеров")

                    # 4. Тест анализатора
                    print("  🔧 Тест анализатора...")
                    analyzer = OKXAnalyzer()
                    filtered_pairs = analyzer.filter_trading_pairs(instruments, tickers)
                    pairs_count = len(filtered_pairs)
                    print(f"    ✅ Отфильтровано {pairs_count} пар")

                    if pairs_count > 0:
                        print("    🏆 Топ-3 пары:")
                        for i, pair in enumerate(filtered_pairs[:3], 1):
                            print(f"      {i}. {pair.symbol}: ${pair.volume_24h_usd:,.0f}")

                    return True
                else:
                    print("    ⚠️  Нет инструментов")
                    return False

            except Exception as e:
                print(f"    ❌ Ошибка получения данных: {e}")
                return False

    except ImportError as e:
        print(f"  ❌ Ошибка импорта: {e}")
        print("     Возможно, интеграция не завершена. Запустите:")
        print("     python okx_fixed_integration.py")
        return False
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return False


def check_config():
    """Проверяет конфигурацию OKX."""
    print("⚙️ Проверка конфигурации...")

    try:
        from config.settings import EXCHANGES_CONFIG

        if 'okx' in EXCHANGES_CONFIG:
            okx_config = EXCHANGES_CONFIG['okx']
            print("  ✅ Конфигурация найдена:")
            print(f"    API URL: {okx_config.get('api_url')}")
            print(f"    Включен: {okx_config.get('enabled')}")
            print(f"    Лимит сделок: {okx_config.get('trades_limit')}")
            print(f"    Пауза: {okx_config.get('cycle_pause_minutes')} мин")
            print(f"    Rate limit: {okx_config.get('rate_limit')}/мин")
            return True
        else:
            print("  ❌ Конфигурация OKX не найдена")
            return False

    except Exception as e:
        print(f"  ❌ Ошибка проверки конфигурации: {e}")
        return False


def check_models():
    """Проверяет модель Trade."""
    print("📋 Проверка модели Trade...")

    try:
        from database.models import Trade

        if hasattr(Trade, 'from_okx_response'):
            print("  ✅ Метод from_okx_response найден")

            # Тест создания объекта Trade
            from decimal import Decimal
            test_data = {
                'tradeId': '123456',
                'px': '50000.0',
                'sz': '0.1',
                'side': 'buy',
                'ts': '1640995200000'
            }

            try:
                trade = Trade.from_okx_response(
                    test_data, 'BTC-USDT', 'BTC', 'USDT', Decimal('1.0')
                )
                print(f"    ✅ Тест создания объекта: {trade.exchange} - ${trade.value_usd}")
                return True
            except Exception as e:
                print(f"    ❌ Ошибка создания объекта: {e}")
                return False
        else:
            print("  ❌ Метод from_okx_response не найден")
            return False

    except Exception as e:
        print(f"  ❌ Ошибка проверки модели: {e}")
        return False


async def main():
    """Главная функция быстрого теста."""
    print("""
╔═══════════════════════════════════════════════════╗
║              БЫСТРЫЙ ТЕСТ OKX                     ║
╚═══════════════════════════════════════════════════╝
    """)

    tests = [
        ("Конфигурация", check_config()),
        ("Модель Trade", check_models()),
        ("OKX API", await quick_test_okx())
    ]

    passed = 0
    total = len(tests)

    for test_name, result in tests:
        if result:
            print(f"✅ {test_name}: ПРОЙДЕН")
            passed += 1
        else:
            print(f"❌ {test_name}: НЕ ПРОЙДЕН")

    print(f"\n📊 Результат: {passed}/{total} тестов пройдено")

    if passed == total:
        print("""
🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!

OKX готов к использованию.
Запустите приложение: python main.py
        """)
        return True
    else:
        print(f"""
❌ ОБНАРУЖЕНЫ ПРОБЛЕМЫ

Не пройдено: {total - passed} тестов
Исправьте ошибки перед запуском основного приложения.

🔧 ВОЗМОЖНЫЕ РЕШЕНИЯ:
1. Перезапустите интеграцию: python okx_fixed_integration.py
2. Проверьте файлы конфигурации вручную
3. Убедитесь в доступности интернета для тестирования API
        """)
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Тест прерван пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Ошибка теста: {e}")
        sys.exit(1)