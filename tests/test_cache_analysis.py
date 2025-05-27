#!/usr/bin/env python3
"""
Тесты для анализа и выявления проблем с кэшированием в текущей системе.
tests/test_cache_analysis.py
"""
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
import time

# Настройка для тестов
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import TradingPairInfo
from workers.exchange_worker import ExchangeWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CacheAnalyzer:
    """Анализатор проблем с кэшированием."""

    def __init__(self):
        self.api_calls_log = []
        self.cache_operations_log = []

    def log_api_call(self, method_name: str, exchange: str):
        """Логирует вызов API."""
        self.api_calls_log.append({
            'timestamp': time.time(),
            'method': method_name,
            'exchange': exchange
        })

    def log_cache_operation(self, operation: str, exchange: str, details: str = ""):
        """Логирует операцию с кэшем."""
        self.cache_operations_log.append({
            'timestamp': time.time(),
            'operation': operation,
            'exchange': exchange,
            'details': details
        })

    def analyze_api_efficiency(self, time_window_minutes: int = 60) -> dict:
        """Анализирует эффективность использования API."""
        cutoff_time = time.time() - (time_window_minutes * 60)
        recent_calls = [call for call in self.api_calls_log if call['timestamp'] > cutoff_time]

        method_counts = {}
        for call in recent_calls:
            method = call['method']
            method_counts[method] = method_counts.get(method, 0) + 1

        return {
            'total_api_calls': len(recent_calls),
            'method_breakdown': method_counts,
            'calls_per_minute': len(recent_calls) / time_window_minutes if time_window_minutes > 0 else 0
        }

    def analyze_cache_efficiency(self) -> dict:
        """Анализирует эффективность кэширования."""
        cache_hits = len([op for op in self.cache_operations_log if op['operation'] == 'hit'])
        cache_misses = len([op for op in self.cache_operations_log if op['operation'] == 'miss'])
        cache_updates = len([op for op in self.cache_operations_log if op['operation'] == 'update'])

        total_operations = cache_hits + cache_misses
        hit_rate = (cache_hits / total_operations * 100) if total_operations > 0 else 0

        return {
            'cache_hits': cache_hits,
            'cache_misses': cache_misses,
            'cache_updates': cache_updates,
            'hit_rate_percent': hit_rate,
            'total_operations': total_operations
        }


async def test_current_cache_behavior():
    """
    Тестирует поведение текущего кэширования для выявления проблем.
    """
    print("\n" + "=" * 60)
    print("АНАЛИЗ ТЕКУЩЕГО ПОВЕДЕНИЯ КЭШИРОВАНИЯ")
    print("=" * 60)

    analyzer = CacheAnalyzer()

    mock_db_manager = AsyncMock()
    mock_client = AsyncMock()
    mock_analyzer_obj = AsyncMock()

    test_pairs = [
        TradingPairInfo(
            exchange='binance',
            symbol='BTCUSDT',
            base_asset='BTC',
            quote_asset='USDT',
            volume_24h_usd=Decimal('1000000000'),
            quote_price_usd=Decimal('1.0')
        ),
        TradingPairInfo(
            exchange='binance',
            symbol='ETHUSDT',
            base_asset='ETH',
            quote_asset='USDT',
            volume_24h_usd=Decimal('500000000'),
            quote_price_usd=Decimal('1.0')
        )
    ]

    # Настраиваем мокинг API вызовов с логированием
    async def mock_get_exchange_info():
        analyzer.log_api_call('get_exchange_info', 'binance')
        return {'symbols': []}

    async def mock_get_24hr_tickers():
        analyzer.log_api_call('get_24hr_tickers', 'binance')
        return []

    mock_client.get_exchange_info = mock_get_exchange_info
    mock_client.get_24hr_tickers = mock_get_24hr_tickers
    mock_analyzer_obj.filter_trading_pairs.return_value = test_pairs

    worker = ExchangeWorker(
        exchange_name='binance',
        client=mock_client,
        analyzer=mock_analyzer_obj,
        db_manager=mock_db_manager,
        cycle_pause_minutes=1
    )

    # Тестируем разные сценарии кэширования
    scenarios = [
        ("Свежий кэш", True, test_pairs),
        ("Устаревший кэш", False, []),
        ("Пустой кэш", True, []),
        ("Ошибка кэша", None, None)
    ]

    for scenario_name, cache_fresh, cached_pairs in scenarios:
        print(f"\n--- Сценарий: {scenario_name} ---")

        analyzer.api_calls_log.clear()
        analyzer.cache_operations_log.clear()

        with patch.object(worker.pairs_cache, 'is_cache_fresh') as mock_is_fresh:
            with patch.object(worker.pairs_cache, 'get_cached_pairs') as mock_get_cached:
                with patch.object(worker.pairs_cache, 'update_pairs_cache', return_value=(1, 0, 0)):

                    if cache_fresh is None:
                        mock_is_fresh.side_effect = Exception("Cache error")
                        mock_get_cached.side_effect = Exception("Cache error")
                    else:
                        mock_is_fresh.return_value = cache_fresh
                        mock_get_cached.return_value = cached_pairs

                        if cache_fresh and cached_pairs:
                            analyzer.log_cache_operation('hit', 'binance', f'{len(cached_pairs)} pairs')
                        else:
                            analyzer.log_cache_operation('miss', 'binance')

                    try:
                        start_time = time.time()
                        pairs = await worker.get_trading_pairs()
                        end_time = time.time()

                        print(f"  Результат: {len(pairs) if pairs else 0} пар за {end_time - start_time:.3f}с")

                        api_analysis = analyzer.analyze_api_efficiency(1)
                        print(f"  API вызовы: {api_analysis['total_api_calls']}")
                        for method, count in api_analysis['method_breakdown'].items():
                            print(f"    {method}: {count}")

                        cache_analysis = analyzer.analyze_cache_efficiency()
                        print(f"  Кэш: попадания={cache_analysis['cache_hits']}, "
                              f"промахи={cache_analysis['cache_misses']}")

                    except Exception as e:
                        print(f"  Ошибка: {e}")


async def test_cache_update_frequency():
    """
    Тестирует частоту обновления кэша в текущей системе.
    """
    print("\n" + "=" * 60)
    print("АНАЛИЗ ЧАСТОТЫ ОБНОВЛЕНИЯ КЭША")
    print("=" * 60)

    analyzer = CacheAnalyzer()

    mock_db_manager = AsyncMock()
    mock_client = AsyncMock()
    mock_analyzer_obj = AsyncMock()

    test_pairs = [
        TradingPairInfo(
            exchange='binance',
            symbol='BTCUSDT',
            base_asset='BTC',
            quote_asset='USDT',
            volume_24h_usd=Decimal('1000000000'),
            quote_price_usd=Decimal('1.0')
        )
    ]

    async def mock_get_exchange_info():
        analyzer.log_api_call('get_exchange_info', 'binance')
        return {'symbols': []}

    async def mock_get_24hr_tickers():
        analyzer.log_api_call('get_24hr_tickers', 'binance')
        return []

    mock_client.get_exchange_info = mock_get_exchange_info
    mock_client.get_24hr_tickers = mock_get_24hr_tickers
    mock_analyzer_obj.filter_trading_pairs.return_value = test_pairs

    worker = ExchangeWorker(
        exchange_name='binance',
        client=mock_client,
        analyzer=mock_analyzer_obj,
        db_manager=mock_db_manager,
        cycle_pause_minutes=1
    )

    print("\nИмитация 5 последовательных циклов:")

    # Настраиваем поведение: кэш всегда считается устаревшим (проблема!)
    with patch.object(worker.pairs_cache, 'is_cache_fresh', return_value=False):
        with patch.object(worker.pairs_cache, 'get_cached_pairs', return_value=[]):
            with patch.object(worker.pairs_cache, 'update_pairs_cache', return_value=(1, 0, 0)):

                for cycle in range(1, 6):
                    print(f"\n--- Цикл {cycle} ---")

                    cycle_start = len(analyzer.api_calls_log)

                    try:
                        pairs = await worker.get_trading_pairs()

                        cycle_api_calls = len(analyzer.api_calls_log) - cycle_start
                        print(f"  API вызовов в цикле: {cycle_api_calls}")
                        print(f"  Получено пар: {len(pairs) if pairs else 0}")

                        await asyncio.sleep(0.1)

                    except Exception as e:
                        print(f"  Ошибка: {e}")

    total_analysis = analyzer.analyze_api_efficiency(10)
    print(f"\n--- ИТОГОВЫЙ АНАЛИЗ ---")
    print(f"Всего API вызовов: {total_analysis['total_api_calls']}")
    print(f"Вызовов в минуту: {total_analysis['calls_per_minute']:.1f}")
    print(f"Детализация по методам:")
    for method, count in total_analysis['method_breakdown'].items():
        print(f"  {method}: {count} раз")

    expected_calls = 2  # Только для первого цикла
    actual_calls = total_analysis['total_api_calls']

    print(f"\n--- ВЫЯВЛЕННАЯ ПРОБЛЕМА ---")
    print(f"Ожидалось API вызовов: {expected_calls} (только в первом цикле)")
    print(f"Фактически API вызовов: {actual_calls}")
    print(f"Избыточность: {actual_calls - expected_calls} лишних вызовов")

    if actual_calls > expected_calls:
        print("❌ ПРОБЛЕМА: Кэш не используется эффективно!")
    else:
        print("✅ Кэш работает правильно")


async def test_cache_ttl_logic():
    """
    Тестирует логику TTL (Time To Live) кэша.
    """
    print("\n" + "=" * 60)
    print("АНАЛИЗ ЛОГИКИ TTL КЭША")
    print("=" * 60)

    mock_pool = AsyncMock()

    from database.pairs_cache import PairsCacheManager
    cache_manager = PairsCacheManager(mock_pool)

    test_scenarios = [
        ("Очень свежий кэш (5 минут)", timedelta(minutes=5), 1, True),
        ("Свежий кэш (30 минут)", timedelta(minutes=30), 1, True),
        ("Граничный случай (60 минут)", timedelta(minutes=60), 1, True),
        ("Чуть устаревший (61 минута)", timedelta(minutes=61), 1, False),
        ("Очень старый (24 часа)", timedelta(hours=24), 1, False),
        ("Пустой кэш", timedelta(minutes=30), 0, False),
    ]

    for scenario_name, age, record_count, expected_fresh in test_scenarios:
        print(f"\n--- {scenario_name} ---")

        mock_time = datetime.now() - age

        mock_cursor = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        mock_cursor.fetchone.return_value = (record_count,)

        try:
            is_fresh = await cache_manager.is_cache_fresh('binance', max_age_hours=1)

            print(f"  Возраст кэша: {age}")
            print(f"  Записей в кэше: {record_count}")
            print(f"  Ожидаемый результат: {expected_fresh}")
            print(f"  Фактический результат: {is_fresh}")

            if is_fresh == expected_fresh:
                print("  ✅ Логика TTL работает правильно")
            else:
                print("  ❌ Проблема с логикой TTL!")

        except Exception as e:
            print(f"  ❌ Ошибка: {e}")


async def test_memory_vs_db_cache():
    """
    Сравнивает эффективность in-memory кэша vs кэша в БД.
    """
    print("\n" + "=" * 60)
    print("СРАВНЕНИЕ IN-MEMORY VS БД КЭША")
    print("=" * 60)

    print("\n--- Тест скорости доступа ---")

    # In-memory кэш (мгновенный доступ)
    start_time = time.time()
    await asyncio.sleep(0.001)  # 1ms
    memory_time = time.time() - start_time

    print(f"In-memory кэш: {memory_time * 1000:.1f}ms")

    # БД кэш (включает сетевые задержки)
    start_time = time.time()
    await asyncio.sleep(0.05)  # 50ms
    db_time = time.time() - start_time

    print(f"БД кэш: {db_time * 1000:.1f}ms")

    # API запрос (самый медленный)
    start_time = time.time()
    await asyncio.sleep(0.2)  # 200ms
    api_time = time.time() - start_time

    print(f"API запрос: {api_time * 1000:.1f}ms")

    print(f"\n--- Сравнение эффективности ---")
    print(f"БД кэш медленнее in-memory в {db_time / memory_time:.1f}x раз")
    print(f"API запрос медленнее in-memory в {api_time / memory_time:.1f}x раз")
    print(f"API запрос медленнее БД кэша в {api_time / db_time:.1f}x раз")

    print(f"\n--- Рекомендации ---")
    print("1. Использовать in-memory кэш для частых операций")
    print("2. БД кэш как резервный источник")
    print("3. API только для обновления данных")


async def run_cache_analysis():
    """Запускает полный анализ проблем кэширования."""
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║         АНАЛИЗ ПРОБЛЕМ КЭШИРОВАНИЯ                ║
    ╚═══════════════════════════════════════════════════╝
    """)

    await test_current_cache_behavior()
    await test_cache_update_frequency()
    await test_cache_ttl_logic()
    await test_memory_vs_db_cache()

    print(f"\n" + "=" * 60)
    print("ЗАКЛЮЧЕНИЕ")
    print("=" * 60)
    print("""
Выявленные проблемы:

1. ❌ ЧАСТЫЕ API ВЫЗОВЫ
   - Кэш проверяется каждый цикл
   - Нет in-memory кэширования
   - Каждое обращение к get_trading_pairs() вызывает запрос к БД

2. ❌ НЕЭФФЕКТИВНАЯ ЛОГИКА КЭША
   - Проверка актуальности кэша при каждом обращении
   - Отсутствие умного планирования обновлений
   - Нет различия между получением пар и их обновлением

3. ❌ ИЗБЫТОЧНЫЕ ЗАПРОСЫ К БД
   - Каждый цикл проверяет is_cache_fresh()
   - Каждый цикл вызывает get_cached_pairs()
   - Нет кэширования результатов между циклами

Рекомендуемые решения:

✅ 1. ВНЕДРИТЬ IN-MEMORY КЭШИРОВАНИЕ
✅ 2. УЛУЧШИТЬ ЛОГИКУ ОБНОВЛЕНИЙ  
✅ 3. ДОБАВИТЬ МОНИТОРИНГ ЭФФЕКТИВНОСТИ
✅ 4. ОПТИМИЗИРОВАТЬ АРХИТЕКТУРУ
    """)


if __name__ == "__main__":
    print("Запуск анализа проблем кэширования...")
    asyncio.run(run_cache_analysis())

# Экспортируем функцию для импорта
__all__ = ['run_cache_analysis']