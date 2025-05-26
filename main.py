#!/usr/bin/env python3
"""
Главный модуль для мониторинга крупных сделок на криптовалютных биржах.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Tuple

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


async def process_exchange(
        exchange_name: str,
        exchange_data: Dict,
        db_manager: DatabaseManager
) -> Tuple[str, int, int, int]:
    """
    Обрабатывает одну биржу полностью.

    Args:
        exchange_name: Название биржи
        exchange_data: Данные биржи (client, analyzer)
        db_manager: Менеджер БД

    Returns:
        Кортеж (exchange_name, новых_сделок, дубликатов, всего_найдено)
    """
    client = exchange_data['client']
    analyzer = exchange_data['analyzer']

    # Семафор для ограничения параллельных запросов внутри биржи
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    total_new = 0
    total_duplicates = 0
    total_found = 0

    try:
        logger.info(f"Начинаем обработку {exchange_name.upper()}")

        # Получаем информацию о парах
        if exchange_name == 'binance':
            exchange_info = await client.get_exchange_info()
        elif exchange_name == 'bybit':
            exchange_info = await client.get_instruments_info()
        else:
            logger.warning(f"Неизвестная биржа: {exchange_name}")
            return (exchange_name, 0, 0, 0)

        # Получаем тикеры
        tickers = await client.get_24hr_tickers()

        # Фильтруем пары
        filtered_pairs = analyzer.filter_trading_pairs(exchange_info, tickers)

        if not filtered_pairs:
            logger.warning(f"Не найдено подходящих пар на {exchange_name}")
            return (exchange_name, 0, 0, 0)

        # Сортируем по объему
        sorted_pairs = sorted(
            filtered_pairs,
            key=lambda x: x.volume_24h_usd,
            reverse=True
        )

        # Показываем топ-5 пар
        logger.info(f"Топ-5 пар {exchange_name.upper()} по объему:")
        for i, pair in enumerate(sorted_pairs[:5], 1):
            logger.info(f"{i}. {pair.symbol}: ${pair.volume_24h_usd:,.0f}")

        # Обрабатываем пары батчами
        for i in range(0, len(sorted_pairs), BATCH_SIZE):
            batch = sorted_pairs[i:i + BATCH_SIZE]

            # Создаем задачи для батча
            tasks = [
                process_pair(client, pair_info, analyzer, semaphore)
                for pair_info in batch
            ]

            # Выполняем задачи параллельно
            results = await asyncio.gather(*tasks, return_exceptions=True)

            batch_trades = []
            for result in results:
                if isinstance(result, Exception):
                    logger.debug(f"Ошибка при обработке пары в {exchange_name}: {result}")
                    continue
                batch_trades.extend(result)

            # Сохраняем в БД
            if batch_trades:
                new_count, dup_count = await db_manager.save_trades(batch_trades)
                total_new += new_count
                total_duplicates += dup_count
                total_found += len(batch_trades)

            # Прогресс
            processed = min(i + BATCH_SIZE, len(sorted_pairs))
            logger.info(
                f"{exchange_name}: {processed}/{len(sorted_pairs)} пар | "
                f"Найдено: {len(batch_trades)} | "
                f"Новых: {new_count if batch_trades else 0} | "
                f"Дубликатов: {dup_count if batch_trades else 0}"
            )

            # Небольшая пауза между батчами внутри биржи
            if i + BATCH_SIZE < len(sorted_pairs):
                await asyncio.sleep(1)

        logger.info(f"Завершена обработка {exchange_name.upper()}: "
                    f"новых={total_new}, дубликатов={total_duplicates}")

    except Exception as e:
        logger.error(f"Ошибка при обработке {exchange_name}: {e}")

    return (exchange_name, total_new, total_duplicates, total_found)


async def run_monitoring_cycle(
        exchanges: Dict,
        db_manager: DatabaseManager
) -> None:
    """
    Выполняет один цикл мониторинга для всех бирж параллельно.

    Args:
        exchanges: Словарь с клиентами и анализаторами бирж
        db_manager: Менеджер базы данных
    """
    logger.info("Запуск параллельной обработки всех бирж")

    # Создаем задачи для параллельной обработки каждой биржи
    tasks = [
        process_exchange(exchange_name, exchange_data, db_manager)
        for exchange_name, exchange_data in exchanges.items()
    ]

    # Выполняем все биржи параллельно
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Собираем результаты
    total_new = 0
    total_duplicates = 0
    total_found = 0

    print(f"\n{'=' * 80}")
    print(f"ИТОГИ ЦИКЛА МОНИТОРИНГА:")
    print(f"{'=' * 80}")

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Ошибка при обработке биржи: {result}")
            continue

        exchange_name, new_count, dup_count, found_count = result
        total_new += new_count
        total_duplicates += dup_count
        total_found += found_count

        print(f"{exchange_name.upper():>12}: найдено {found_count:>4} | "
              f"новых {new_count:>4} | дубликатов {dup_count:>4}")

    print(f"{'=' * 80}")
    print(f"{'ИТОГО':>12}: найдено {total_found:>4} | "
          f"новых {total_new:>4} | дубликатов {total_duplicates:>4}")

    # Общая статистика по биржам
    stats_by_exchange = await db_manager.get_statistics_by_exchange()
    if stats_by_exchange:
        print(f"\nСтатистика за 24 часа по биржам:")
        print(f"{'Биржа':>12} | {'Сделок':>8} | {'Объем, $':>15} | {'Средний размер, $':>18}")
        print(f"{'-' * 80}")

        total_stats_volume = 0
        total_stats_count = 0

        for exchange, stats in stats_by_exchange.items():
            print(f"{exchange.upper():>12} | "
                  f"{stats['trade_count']:>8} | "
                  f"{stats['total_volume']:>15,.0f} | "
                  f"{stats['avg_trade_size']:>18,.0f}")
            total_stats_volume += stats['total_volume']
            total_stats_count += stats['trade_count']

        print(f"{'-' * 80}")
        avg_all = total_stats_volume / total_stats_count if total_stats_count > 0 else 0
        print(f"{'ИТОГО':>12} | "
              f"{total_stats_count:>8} | "
              f"{total_stats_volume:>15,.0f} | "
              f"{avg_all:>18,.0f}")

    print(f"{'=' * 80}\n")


async def main() -> None:
    """Основная функция программы."""
    # Выводим стартовый баннер
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║      CRYPTO LARGE TRADES MONITOR v2.0             ║
    ║                                                   ║
    ║  Мониторинг крупных сделок на криптобиржах       ║
    ║  Минимальная сумма сделки: $49,000               ║
    ║  Режим: ПАРАЛЛЕЛЬНАЯ ОБРАБОТКА БИРЖ              ║
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
            # Инициализируем биржи с отдельными rate limiter'ами
            exchanges = {
                'binance': {
                    'client': BinanceClient(session, RateLimiter(MAX_WEIGHT_PER_MINUTE)),
                    'analyzer': BinanceAnalyzer()
                },
                'bybit': {
                    'client': BybitClient(session, RateLimiter(MAX_WEIGHT_PER_MINUTE)),
                    'analyzer': BybitAnalyzer()
                }
            }

            # Тестируем соединения параллельно
            connection_tasks = [
                exchange['client'].test_connection()
                for exchange in exchanges.values()
            ]
            connection_results = await asyncio.gather(*connection_tasks)

            failed_exchanges = []
            for i, (name, result) in enumerate(zip(exchanges.keys(), connection_results)):
                if not result:
                    failed_exchanges.append(name)
                    logger.error(f"Не удалось подключиться к {name}")

            # Удаляем биржи с неудачными подключениями
            for failed_exchange in failed_exchanges:
                exchanges.pop(failed_exchange, None)

            if not exchanges:
                logger.error("Не удалось подключиться ни к одной бирже")
                return

            logger.info(f"Успешно подключены биржи: {', '.join(exchanges.keys())}")

            # Бесконечный цикл мониторинга
            cycle_count = 0

            while True:
                cycle_count += 1
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                print(f"\n{'#' * 80}")
                print(f"НАЧАЛО ЦИКЛА #{cycle_count} | Время: {current_time}")
                print(f"Активные биржи: {', '.join(exchanges.keys())} (параллельная обработка)")
                print(f"SSL проверка: {'включена' if verify_ssl else 'ОТКЛЮЧЕНА'}")
                print(f"{'#' * 80}\n")

                try:
                    start_time = asyncio.get_event_loop().time()
                    await run_monitoring_cycle(exchanges, db_manager)
                    end_time = asyncio.get_event_loop().time()

                    cycle_duration = end_time - start_time
                    logger.info(f"Цикл #{cycle_count} завершен за {cycle_duration:.1f} секунд")

                    # Пауза между циклами
                    logger.info(f"Пауза {MONITORING_PAUSE_MINUTES} минут до следующего цикла...")

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