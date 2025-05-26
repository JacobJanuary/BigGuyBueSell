#!/usr/bin/env python3
"""
Тест работы обеих бирж (Binance и Bybit) одновременно.
"""
import asyncio
import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import List

import aiohttp
from aiohttp import TCPConnector

from config.settings import (
    MAX_WEIGHT_PER_MINUTE, MIN_TRADE_VALUE_USD,
    MAX_CONCURRENT_REQUESTS, BATCH_SIZE
)
from database.manager import DatabaseManager
from database.models import Trade
from exchanges.binance.client import BinanceClient
from exchanges.binance.analyzer import BinanceAnalyzer
from exchanges.bybit.client import BybitClient
from exchanges.bybit.analyzer import BybitAnalyzer
from utils.logger import setup_logging
from utils.rate_limiter import RateLimiter
from utils.ssl_helper import create_ssl_context

# Настройка логирования
setup_logging(level="INFO")
logger = logging.getLogger(__name__)


async def process_pair(
        client,
        pair_info,
        analyzer,
        semaphore: asyncio.Semaphore
) -> List[Trade]:
    """
    Обрабатывает одну торговую пару.

    Args:
        client: Клиент биржи API
        pair_info: Информация о паре
        analyzer: Анализатор данных
        semaphore: Семафор для ограничения параллельных запросов

    Returns:
        Список крупных сделок
    """
    async with semaphore:
        trades_data = await client.get_recent_trades(pair_info.symbol)
        if not trades_data:
            return []

        large_trades = []
        for trade_data in trades_data:
            trade = await client.parse_trade(trade_data, pair_info)

            if trade.value_usd >= Decimal(str(MIN_TRADE_VALUE_USD)):
                large_trades.append(trade)

        return large_trades


async def test_both_exchanges():
    """Тестирует работу обеих бирж одновременно."""
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║    ТЕСТ МОНИТОРИНГА BINANCE И BYBIT              ║
    ╚═══════════════════════════════════════════════════╝
    """)

    # Проверяем SSL настройки
    verify_ssl = not (os.environ.get('DISABLE_SSL_VERIFY', '').lower() == 'true')
    print(f"SSL проверка: {'включена' if verify_ssl else 'отключена'}\n")

    # Создаем SSL контекст
    ssl_context = create_ssl_context(verify_ssl)

    # Настраиваем HTTP сессию
    timeout = aiohttp.ClientTimeout(total=30)
    connector = TCPConnector(
        ssl=ssl_context,
        limit=50,
        limit_per_host=10
    )

    async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
    ) as session:
        # Инициализируем биржи
        rate_limiter = RateLimiter(MAX_WEIGHT_PER_MINUTE)

        exchanges = {
            'binance': {
                'client': BinanceClient(session, rate_limiter),
                'analyzer': BinanceAnalyzer()
            },
            'bybit': {
                'client': BybitClient(session, rate_limiter),
                'analyzer': BybitAnalyzer()
            }
        }

        # Тестируем соединения
        print("\n=== Проверка подключения ===")
        for name, exchange in exchanges.items():
            connected = await exchange['client'].test_connection()
            print(f"{name.upper()}: {'✓ Подключено' if connected else '✗ Ошибка'}")
            if not connected:
                exchanges.pop(name)

        if not exchanges:
            print("\nНет доступных бирж!")
            return

        # Семафор для ограничения параллельных запросов
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        # Обрабатываем каждую биржу
        for exchange_name, exchange_data in exchanges.items():
            client = exchange_data['client']
            analyzer = exchange_data['analyzer']

            print(f"\n=== Обработка {exchange_name.upper()} ===")

            try:
                # Получаем информацию о парах
                if exchange_name == 'binance':
                    exchange_info = await client.get_exchange_info()
                elif exchange_name == 'bybit':
                    exchange_info = await client.get_instruments_info()
                else:
                    continue

                # Получаем тикеры
                tickers = await client.get_24hr_tickers()

                # Фильтруем пары
                filtered_pairs = analyzer.filter_trading_pairs(exchange_info, tickers)

                print(f"Найдено подходящих пар: {len(filtered_pairs)}")

                if not filtered_pairs:
                    continue

                # Сортируем по объему
                sorted_pairs = sorted(
                    filtered_pairs,
                    key=lambda x: x.volume_24h_usd,
                    reverse=True
                )

                # Показываем топ-5 пар
                print(f"\nТоп-5 пар по объему:")
                for i, pair in enumerate(sorted_pairs[:5], 1):
                    print(f"{i}. {pair.symbol}: ${pair.volume_24h_usd:,.0f}")

                # Ищем крупные сделки в топ-10 парах
                print(f"\nИщем крупные сделки (>=${MIN_TRADE_VALUE_USD:,})...")

                test_pairs = sorted_pairs[:10]  # Берем только топ-10 для теста
                all_large_trades = []

                # Обрабатываем батчами
                for i in range(0, len(test_pairs), BATCH_SIZE):
                    batch = test_pairs[i:i + BATCH_SIZE]

                    tasks = [
                        process_pair(client, pair_info, analyzer, semaphore)
                        for pair_info in batch
                    ]

                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in results:
                        if isinstance(result, Exception):
                            logger.debug(f"Ошибка: {result}")
                            continue
                        all_large_trades.extend(result)

                print(f"Найдено крупных сделок: {len(all_large_trades)}")

                # Показываем первые 5 крупных сделок
                if all_large_trades:
                    print("\nПримеры крупных сделок:")
                    for i, trade in enumerate(all_large_trades[:5], 1):
                        print(f"\n{i}. {trade.symbol}")
                        print(f"   Сумма: ${trade.value_usd:,.2f}")
                        print(f"   Цена: {trade.price} {trade.quote_asset}")
                        print(f"   Количество: {trade.quantity}")
                        print(f"   Тип: {trade.trade_type}")

            except Exception as e:
                logger.error(f"Ошибка при обработке {exchange_name}: {e}")

    print("\n=== ТЕСТ ЗАВЕРШЕН ===")


async def test_database_save():
    """Тестирует сохранение в базу данных."""
    print("\n=== Тест сохранения в БД ===")

    # Создаем тестовые сделки
    test_trades = [
        Trade(
            id="test_binance_1",
            symbol="BTCUSDT",
            base_asset="BTC",
            price=Decimal("100000"),
            quantity=Decimal("1"),
            value_usd=Decimal("100000"),
            quote_asset="USDT",
            is_buyer_maker=False,
            trade_time=int(datetime.now().timestamp() * 1000)
        ),
        Trade(
            id="test_bybit_1",
            symbol="ETHUSDT",
            base_asset="ETH",
            price=Decimal("5000"),
            quantity=Decimal("20"),
            value_usd=Decimal("100000"),
            quote_asset="USDT",
            is_buyer_maker=True,
            trade_time=int(datetime.now().timestamp() * 1000)
        )
    ]

    # Инициализируем БД
    db_manager = DatabaseManager()

    try:
        await db_manager.connect()
        await db_manager.create_tables()

        # Сохраняем сделки
        new_count, dup_count = await db_manager.save_trades(test_trades)

        print(f"Сохранено новых: {new_count}")
        print(f"Дубликатов: {dup_count}")

        # Получаем статистику
        stats = await db_manager.get_statistics()
        print(f"\nСтатистика БД:")
        print(f"  Всего сделок за 24ч: {stats.get('trade_count', 0)}")
        print(f"  Общий объем: ${stats.get('total_volume', 0):,.0f}")

    except Exception as e:
        logger.error(f"Ошибка БД: {e}")
    finally:
        await db_manager.close()


if __name__ == "__main__":
    # Запускаем тесты
    asyncio.run(test_both_exchanges())

    # Опционально: тест БД
    # asyncio.run(test_database_save())