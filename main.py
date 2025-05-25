#!/usr/bin/env python3
"""
Главный модуль для мониторинга крупных сделок на криптовалютных биржах.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict

import aiohttp
from aiohttp import TCPConnector

from config.settings import (
    MIN_TRADE_VALUE_USD, MONITORING_PAUSE_MINUTES, BATCH_SIZE,
    MAX_CONCURRENT_REQUESTS, MAX_WEIGHT_PER_MINUTE, DISABLE_SSL_VERIFY
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
    from decimal import Decimal

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


async def run_monitoring_cycle(
        exchanges: Dict,
        db_manager: DatabaseManager
) -> None:
    """
    Выполняет один цикл мониторинга для всех бирж.

    Args:
        exchanges: Словарь с клиентами и анализаторами бирж
        db_manager: Менеджер базы данных
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    total_new = 0
    total_duplicates = 0

    for exchange_name, exchange_data in exchanges.items():
        client = exchange_data['client']
        analyzer = exchange_data['analyzer']

        try:
            logger.info(f"\n--- Обработка {exchange_name.upper()} ---")

            # Получаем информацию о парах
            if exchange_name == 'binance':
                exchange_info = await client.get_exchange_info()
            elif exchange_name == 'bybit':
                exchange_info = await client.get_instruments_info()
            else:
                # Для других бирж будет другая логика
                continue

            # Получаем тикеры
            tickers = await client.get_24hr_tickers()

            # Фильтруем пары
            filtered_pairs = analyzer.filter_trading_pairs(exchange_info, tickers)

            if not filtered_pairs:
                logger.warning(f"Не найдено подходящих пар на {exchange_name}")
                continue

            # Сортируем по объему
            sorted_pairs = sorted(
                filtered_pairs,
                key=lambda x: x.volume_24h_usd,
                reverse=True
            )

            # Показываем топ-5 пар
            print(f"\nТоп-5 пар {exchange_name.upper()} по объему:")
            for i, pair in enumerate(sorted_pairs[:5], 1):
                print(f"{i}. {pair.symbol}: ${pair.volume_24h_usd:,.0f}")

            # Обрабатываем пары батчами
            all_large_trades = []

            for i in range(0, len(sorted_pairs), BATCH_SIZE):
                batch = sorted_pairs[i:i + BATCH_SIZE]

                tasks = [
                    process_pair(client, pair_info, analyzer, semaphore)
                    for pair_info in batch
                ]

                results = await asyncio.gather(*tasks, return_exceptions=True)

                batch_trades = []
                for result in results:
                    if isinstance(result, Exception):
                        logger.debug(f"Ошибка при обработке: {result}")
                        continue
                    batch_trades.extend(result)

                # Сохраняем в БД
                if batch_trades:
                    new_count, dup_count = await db_manager.save_trades(batch_trades)
                    total_new += new_count
                    total_duplicates += dup_count

                all_large_trades.extend(batch_trades)

                # Прогресс
                processed = min(i + BATCH_SIZE, len(sorted_pairs))
                logger.info(
                    f"{exchange_name}: {processed}/{len(sorted_pairs)} пар | "
                    f"Найдено: {len(all_large_trades)} | "
                    f"Новых: {new_count} | Дубликатов: {dup_count}"
                )

                if i + BATCH_SIZE < len(sorted_pairs):
                    await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Ошибка при обработке {exchange_name}: {e}")

    # Итоги цикла
    print(f"\n{'=' * 80}")
    print(f"ИТОГИ ЦИКЛА МОНИТОРИНГА:")
    print(f"Новых сделок сохранено: {total_new}")
    print(f"Дубликатов пропущено: {total_duplicates}")

    # Общая статистика
    stats = await db_manager.get_statistics()
    if stats and stats['trade_count'] > 0:
        print(f"\nСтатистика за 24 часа:")
        print(f"Всего сделок: {stats['trade_count']}")
        print(f"Общий объем: ${stats['total_volume']:,.0f}")
        print(f"Средний размер: ${stats['avg_trade_size']:,.0f}")
        print(f"Максимальная сделка: ${stats['max_trade_size']:,.0f}")
    print(f"{'=' * 80}\n")


async def main() -> None:
    """Основная функция программы."""
    # Выводим стартовый баннер
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║      CRYPTO LARGE TRADES MONITOR v1.0             ║
    ║                                                   ║
    ║  Мониторинг крупных сделок на криптобиржах       ║
    ║  Минимальная сумма сделки: $89,000               ║
    ╚═══════════════════════════════════════════════════╝
    """)

    # Настраиваем логирование
    setup_logging(level="INFO")

    # Инициализируем БД
    db_manager = DatabaseManager()

    try:
        # Подключаемся к БД
        await db_manager.connect()
        await db_manager.create_tables()

        # Проверяем переменную окружения для SSL
        verify_ssl = not (os.environ.get('DISABLE_SSL_VERIFY', '').lower() == 'true')

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
            connection_ok = True
            for name, exchange in exchanges.items():
                if not await exchange['client'].test_connection():
                    logger.error(f"Не удалось подключиться к {name}")
                    connection_ok = False

            if not connection_ok:
                logger.error("Не удалось подключиться к биржам")
                return

            # Бесконечный цикл мониторинга
            cycle_count = 0

            while True:
                cycle_count += 1
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                print(f"\n{'#' * 80}")
                print(f"НАЧАЛО ЦИКЛА #{cycle_count} | Время: {current_time}")
                print(f"Активные биржи: {', '.join(exchanges.keys())}")
                print(f"SSL проверка: {'включена' if verify_ssl else 'ОТКЛЮЧЕНА'}")
                print(f"{'#' * 80}\n")

                try:
                    await run_monitoring_cycle(exchanges, db_manager)

                    # Пауза между циклами
                    logger.info(f"Цикл #{cycle_count} завершен. "
                                f"Пауза {MONITORING_PAUSE_MINUTES} минут...")

                    # Обратный отсчет
                    for remaining in range(MONITORING_PAUSE_MINUTES * 60, 0, -30):
                        minutes, seconds = divmod(remaining, 60)
                        print(f"\rСледующий цикл через: {minutes:02d}:{seconds:02d}",
                              end='', flush=True)
                        await asyncio.sleep(min(30, remaining))
                    print()

                except KeyboardInterrupt:
                    logger.info("Получен сигнал остановки (Ctrl+C)")
                    break
                except Exception as e:
                    logger.error(f"Ошибка в цикле #{cycle_count}: {e}")
                    logger.info("Повтор через 1 минуту...")
                    await asyncio.sleep(60)

    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await db_manager.close()
        logger.info("Мониторинг завершен")


if __name__ == "__main__":
    asyncio.run(main())