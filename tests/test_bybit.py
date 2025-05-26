#!/usr/bin/env python3
"""
Тесты для проверки работы Bybit API.
"""
import asyncio
import logging
import os
from decimal import Decimal
from pprint import pprint

import aiohttp
from aiohttp import TCPConnector

from config.settings import MAX_WEIGHT_PER_MINUTE, MIN_TRADE_VALUE_USD
from exchanges.bybit.client import BybitClient
from exchanges.bybit.analyzer import BybitAnalyzer
from utils.rate_limiter import RateLimiter
from utils.ssl_helper import create_ssl_context

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверяем SSL настройки один раз
VERIFY_SSL = not (os.environ.get('DISABLE_SSL_VERIFY', '').lower() == 'true')


async def test_bybit_connection():
    """Тест подключения к Bybit API."""
    print("\n=== Тест подключения к Bybit ===")

    ssl_context = create_ssl_context(VERIFY_SSL)
    connector = TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)
        client = BybitClient(session, rate_limiter)

        connected = await client.test_connection()
        print(f"Подключение к Bybit: {'Успешно' if connected else 'Неудачно'}")
        print(f"SSL проверка: {'включена' if VERIFY_SSL else 'отключена'}")
        return connected


async def test_get_instruments():
    """Тест получения информации об инструментах."""
    print("\n=== Тест получения инструментов ===")

    ssl_context = create_ssl_context(VERIFY_SSL)
    connector = TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)
        client = BybitClient(session, rate_limiter)

        try:
            instruments = await client.get_instruments_info()

            print(f"Получено инструментов: {len(instruments.get('result', {}).get('list', []))}")

            # Показываем первые 3 инструмента
            for i, instrument in enumerate(instruments.get('result', {}).get('list', [])[:3]):
                print(f"\nИнструмент {i + 1}:")
                print(f"  Символ: {instrument['symbol']}")
                print(f"  Базовый актив: {instrument['baseCoin']}")
                print(f"  Котировочный актив: {instrument['quoteCoin']}")
                print(f"  Статус: {instrument['status']}")

            return instruments

        except Exception as e:
            print(f"Ошибка: {e}")
            return None


async def test_get_tickers():
    """Тест получения тикеров."""
    print("\n=== Тест получения тикеров ===")

    ssl_context = create_ssl_context(VERIFY_SSL)
    connector = TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)
        client = BybitClient(session, rate_limiter)

        try:
            tickers = await client.get_24hr_tickers()

            print(f"Получено тикеров: {len(tickers)}")

            # Показываем топ-3 по объему
            sorted_tickers = sorted(
                tickers,
                key=lambda x: float(x.get('turnover24h', 0)),
                reverse=True
            )

            print("\nТоп-3 пары по объему:")
            for i, ticker in enumerate(sorted_tickers[:3]):
                print(f"\n{i + 1}. {ticker['symbol']}:")
                print(f"  Последняя цена: {ticker['lastPrice']}")
                print(f"  Объем 24ч: ${float(ticker['turnover24h']):,.2f}")
                print(f"  Изменение 24ч: {float(ticker.get('price24hPcnt', 0)) * 100:.2f}%")

            return tickers

        except Exception as e:
            print(f"Ошибка: {e}")
            return None


async def test_get_recent_trades():
    """Тест получения последних сделок."""
    print("\n=== Тест получения последних сделок ===")

    ssl_context = create_ssl_context(VERIFY_SSL)
    connector = TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)
        client = BybitClient(session, rate_limiter)

        # Тестируем на популярных парах
        test_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

        for symbol in test_symbols:
            print(f"\nПолучаем сделки для {symbol}:")

            try:
                trades = await client.get_recent_trades(symbol)

                if trades:
                    print(f"  Получено сделок: {len(trades)}")

                    # Показываем первые 3 сделки
                    for i, trade in enumerate(trades[:3]):
                        print(f"\n  Сделка {i + 1}:")
                        print(f"    ID: {trade['execId']}")
                        print(f"    Цена: {trade['price']}")
                        print(f"    Количество: {trade['size']}")
                        print(f"    Сторона: {trade['side']}")
                        print(f"    Время: {trade['time']}")
                else:
                    print(f"  Нет данных о сделках")

            except Exception as e:
                print(f"  Ошибка: {e}")


async def test_filter_pairs():
    """Тест фильтрации торговых пар."""
    print("\n=== Тест фильтрации пар ===")

    ssl_context = create_ssl_context(VERIFY_SSL)
    connector = TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)
        client = BybitClient(session, rate_limiter)
        analyzer = BybitAnalyzer()

        try:
            # Получаем данные
            instruments = await client.get_instruments_info()
            tickers = await client.get_24hr_tickers()

            # Фильтруем
            filtered_pairs = analyzer.filter_trading_pairs(instruments, tickers)

            print(f"Отфильтровано пар: {len(filtered_pairs)}")

            # Показываем топ-5 по объему
            sorted_pairs = sorted(
                filtered_pairs,
                key=lambda x: x.volume_24h_usd,
                reverse=True
            )

            print("\nТоп-5 пар после фильтрации:")
            for i, pair in enumerate(sorted_pairs[:5]):
                print(f"\n{i + 1}. {pair.symbol}:")
                print(f"  Базовый актив: {pair.base_asset}")
                print(f"  Котировочный актив: {pair.quote_asset}")
                print(f"  Объем 24ч: ${pair.volume_24h_usd:,.2f}")

            return filtered_pairs

        except Exception as e:
            print(f"Ошибка: {e}")
            return None


async def test_find_large_trades():
    """Тест поиска крупных сделок."""
    print("\n=== Тест поиска крупных сделок ===")

    ssl_context = create_ssl_context(VERIFY_SSL)
    connector = TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)
        client = BybitClient(session, rate_limiter)
        analyzer = BybitAnalyzer()

        try:
            # Получаем данные
            instruments = await client.get_instruments_info()
            tickers = await client.get_24hr_tickers()

            # Фильтруем пары
            filtered_pairs = analyzer.filter_trading_pairs(instruments, tickers)

            # Берем топ-10 пар по объему
            sorted_pairs = sorted(
                filtered_pairs,
                key=lambda x: x.volume_24h_usd,
                reverse=True
            )[:10]

            print(f"Проверяем топ-{len(sorted_pairs)} пар на крупные сделки...")

            large_trades_found = []

            for pair in sorted_pairs:
                trades_data = await client.get_recent_trades(pair.symbol)

                if trades_data:
                    # Парсим сделки
                    for trade_data in trades_data:
                        trade = await client.parse_trade(trade_data, pair)

                        if trade.value_usd >= Decimal(str(MIN_TRADE_VALUE_USD)):
                            large_trades_found.append(trade)

            print(f"\nНайдено крупных сделок (>=${MIN_TRADE_VALUE_USD:,}): {len(large_trades_found)}")

            # Показываем первые 5 крупных сделок
            for i, trade in enumerate(large_trades_found[:5]):
                print(f"\n{i + 1}. {trade.symbol}")
                print(f"  Сумма: ${trade.value_usd:,.2f}")
                print(f"  Цена: {trade.price}")
                print(f"  Количество: {trade.quantity}")
                print(f"  Тип: {trade.trade_type}")

        except Exception as e:
            print(f"Ошибка: {e}")


async def test_full_cycle():
    """Полный тестовый цикл работы с Bybit."""
    print("\n=== ПОЛНЫЙ ТЕСТОВЫЙ ЦИКЛ BYBIT ===")

    # 1. Тест подключения
    connected = await test_bybit_connection()
    if not connected:
        print("Не удалось подключиться к Bybit")
        return

    # 2. Тест получения инструментов
    await test_get_instruments()

    # 3. Тест получения тикеров
    await test_get_tickers()

    # 4. Тест получения сделок
    await test_get_recent_trades()

    # 5. Тест фильтрации пар
    await test_filter_pairs()

    # 6. Тест поиска крупных сделок
    await test_find_large_trades()

    print("\n=== ТЕСТЫ ЗАВЕРШЕНЫ ===")


if __name__ == "__main__":
    # Запускаем полный цикл тестов
    asyncio.run(test_full_cycle())