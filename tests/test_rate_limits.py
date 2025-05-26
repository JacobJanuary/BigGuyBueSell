#!/usr/bin/env python3
"""
Тесты для проверки соблюдения rate limits на биржах.
"""
import asyncio
import time
import logging
import os

import aiohttp
from aiohttp import TCPConnector

from config.settings import MAX_WEIGHT_PER_MINUTE
from exchanges.binance.client import BinanceClient
from exchanges.bybit.client import BybitClient
from utils.rate_limiter import RateLimiter
from utils.ssl_helper import create_ssl_context

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверяем SSL настройки
VERIFY_SSL = not (os.environ.get('DISABLE_SSL_VERIFY', '').lower() == 'true')


async def test_binance_rate_limits():
    """Тест rate limits для Binance."""
    print("\n=== Тест Rate Limits Binance ===")
    print(f"Максимальный вес в минуту: {MAX_WEIGHT_PER_MINUTE}")

    ssl_context = create_ssl_context(VERIFY_SSL)
    connector = TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)
        client = BinanceClient(session, rate_limiter)

        # Тестовые символы
        test_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT']

        print("\nТестируем множественные запросы...")
        start_time = time.time()
        request_count = 0

        try:
            # 1. Получаем информацию о бирже (вес 20)
            await client.get_exchange_info()
            request_count += 1
            print(f"✓ Запрос {request_count}: exchange_info (вес 20)")

            # 2. Получаем тикеры (вес 40)
            await client.get_24hr_tickers()
            request_count += 1
            print(f"✓ Запрос {request_count}: tickers (вес 40)")

            # 3. Получаем сделки для нескольких символов (вес 10 каждый)
            for symbol in test_symbols:
                await client.get_recent_trades(symbol)
                request_count += 1
                print(f"✓ Запрос {request_count}: trades {symbol} (вес 10)")

            elapsed_time = time.time() - start_time
            print(f"\nВыполнено {request_count} запросов за {elapsed_time:.2f} секунд")
            print(f"Текущий вес: {rate_limiter.get_current_weight()}/{MAX_WEIGHT_PER_MINUTE}")

        except Exception as e:
            print(f"❌ Ошибка: {e}")


async def test_bybit_rate_limits():
    """Тест rate limits для Bybit."""
    print("\n=== Тест Rate Limits Bybit ===")
    print("Bybit использует другую систему лимитов (600 запросов за 5 секунд)")

    ssl_context = create_ssl_context(VERIFY_SSL)
    connector = TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)
        client = BybitClient(session, rate_limiter)

        # Тестовые символы
        test_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT']

        print("\nТестируем множественные запросы...")
        start_time = time.time()
        request_count = 0

        try:
            # 1. Проверяем время сервера
            connected = await client.test_connection()
            if connected:
                request_count += 1
                print(f"✓ Запрос {request_count}: server time")

            # 2. Получаем инструменты
            await client.get_instruments_info()
            request_count += 1
            print(f"✓ Запрос {request_count}: instruments info")

            # 3. Получаем тикеры
            await client.get_24hr_tickers()
            request_count += 1
            print(f"✓ Запрос {request_count}: tickers")

            # 4. Получаем сделки для нескольких символов
            for symbol in test_symbols:
                await client.get_recent_trades(symbol)
                request_count += 1
                print(f"✓ Запрос {request_count}: trades {symbol}")
                # Небольшая задержка между запросами
                await asyncio.sleep(0.1)

            elapsed_time = time.time() - start_time
            print(f"\nВыполнено {request_count} запросов за {elapsed_time:.2f} секунд")
            print(f"Средняя скорость: {request_count / elapsed_time:.2f} запросов/сек")

        except Exception as e:
            print(f"❌ Ошибка: {e}")


async def test_concurrent_requests():
    """Тест параллельных запросов с соблюдением лимитов."""
    print("\n=== Тест параллельных запросов ===")

    ssl_context = create_ssl_context(VERIFY_SSL)
    connector = TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)

        # Создаем клиенты для обеих бирж
        binance_client = BinanceClient(session, rate_limiter)
        bybit_client = BybitClient(session, rate_limiter)

        print("\nЗапускаем параллельные запросы к обеим биржам...")
        start_time = time.time()

        # Создаем задачи для параллельного выполнения
        tasks = [
            # Binance
            binance_client.get_recent_trades('BTCUSDT'),
            binance_client.get_recent_trades('ETHUSDT'),
            # Bybit
            bybit_client.get_recent_trades('BTCUSDT'),
            bybit_client.get_recent_trades('ETHUSDT'),
        ]

        # Выполняем параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Анализируем результаты
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = sum(1 for r in results if isinstance(r, Exception))

        elapsed_time = time.time() - start_time

        print(f"\nРезультаты:")
        print(f"  Успешных запросов: {success_count}")
        print(f"  Ошибок: {error_count}")
        print(f"  Время выполнения: {elapsed_time:.2f} секунд")
        print(f"  Текущий вес rate limiter: {rate_limiter.get_current_weight()}")


async def main():
    """Запускает все тесты rate limits."""
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║           ТЕСТЫ RATE LIMITS                       ║
    ╚═══════════════════════════════════════════════════╝
    """)
    print(f"SSL проверка: {'включена' if VERIFY_SSL else 'отключена'}\n")

    # Тест Binance
    await test_binance_rate_limits()

    # Небольшая пауза
    await asyncio.sleep(2)

    # Тест Bybit
    await test_bybit_rate_limits()

    # Небольшая пауза
    await asyncio.sleep(2)

    # Тест параллельных запросов
    await test_concurrent_requests()

    print("\n=== ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ ===")


if __name__ == "__main__":
    asyncio.run(main())