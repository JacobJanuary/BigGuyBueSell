#!/usr/bin/env python3
"""
Главный модуль с агрессивным мониторингом Bybit.
Binance работает в обычном режиме, Bybit - в режиме непрерывного мониторинга.
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
from exchanges.bybit.analyzer import BybitAnalyzer
from bybit_continuous_monitor import BybitAggressiveClient  # Новый агрессивный клиент
from utils.logger import setup_logging
from utils.rate_limiter import RateLimiter
from utils.ssl_helper import create_ssl_context

logger = logging.getLogger(__name__)

import suppress_warnings  # Подавляет все предупреждения MySQL


async def process_pair_binance(
        client,
        pair_info,
        analyzer,
        semaphore: asyncio.Semaphore
) -> List[Trade]:
    """Обрабатывает одну торговую пару Binance (обычный режим)."""
    from decimal import Decimal

    async with semaphore:
        trades_data = await client.get_recent_trades(pair_info.symbol)
        if not trades_data:
            return []

        large_trades = []
        for trade_data in trades_data:
            trade = await client.parse_trade(trade_data, pair_info)

            # ФИЛЬТРАЦИЯ ПО МИНИМАЛЬНОЙ СУММЕ
            if trade.value_usd >= Decimal(str(MIN_TRADE_VALUE_USD)):
                large_trades.append(trade)

        return large_trades


async def process_binance_exchange(
        client: BinanceClient,
        analyzer: BinanceAnalyzer,
        db_manager: DatabaseManager
) -> Tuple[str, int, int, int]:
    """Обрабатывает Binance в обычном режиме."""

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    total_new = 0
    total_duplicates = 0
    total_found = 0

    try:
        logger.info("Начинаем обработку BINANCE (обычный режим)")

        # Получаем информацию о парах
        exchange_info = await client.get_exchange_info()
        tickers = await client.get_24hr_tickers()

        # Фильтруем пары
        filtered_pairs = analyzer.filter_trading_pairs(exchange_info, tickers)

        if not filtered_pairs:
            logger.warning("Не найдено подходящих пар на Binance")
            return ("binance", 0, 0, 0)

        # Сортируем по объему
        sorted_pairs = sorted(
            filtered_pairs,
            key=lambda x: x.volume_24h_usd,
            reverse=True
        )

        # Показываем топ-5 пар
        logger.info("Топ-5 пар BINANCE по объему:")
        for i, pair in enumerate(sorted_pairs[:5], 1):
            logger.info(f"{i}. {pair.symbol}: ${pair.volume_24h_usd:,.0f}")

        # Обрабатываем пары батчами
        for i in range(0, len(sorted_pairs), BATCH_SIZE):
            batch = sorted_pairs[i:i + BATCH_SIZE]

            tasks = [
                process_pair_binance(client, pair_info, analyzer, semaphore)
                for pair_info in batch
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            batch_trades = []
            for result in results:
                if isinstance(result, Exception):
                    logger.debug(f"Ошибка при обработке пары в Binance: {result}")
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
                f"Binance: {processed}/{len(sorted_pairs)} пар | "
                f"Найдено: {len(batch_trades)} | "
                f"Новых: {new_count if batch_trades else 0} | "
                f"Дубликатов: {dup_count if batch_trades else 0}"
            )

            if i + BATCH_SIZE < len(sorted_pairs):
                await asyncio.sleep(1)

        logger.info(f"Завершена обработка BINANCE: "
                    f"новых={total_new}, дубликатов={total_duplicates}")

    except Exception as e:
        logger.error(f"Ошибка при обработке Binance: {e}")

    return ("binance", total_new, total_duplicates, total_found)


async def setup_bybit_aggressive_monitoring(
        client: BybitAggressiveClient,
        analyzer: BybitAnalyzer,
        db_manager: DatabaseManager
) -> asyncio.Task:
    """Настраивает и запускает агрессивный мониторинг Bybit."""

    try:
        logger.info("Настройка агрессивного мониторинга BYBIT")

        # Получаем информацию о парах
        exchange_info = await client.get_instruments_info()
        tickers = await client.get_24hr_tickers()

        # Фильтруем пары
        filtered_pairs = analyzer.filter_trading_pairs(exchange_info, tickers)

        if not filtered_pairs:
            logger.warning("Не найдено подходящих пар на Bybit")
            return None

        # Сортируем по объему и берем топ пары для агрессивного мониторинга
        sorted_pairs = sorted(
            filtered_pairs,
            key=lambda x: x.volume_24h_usd,
            reverse=True
        )

        logger.info("Топ-10 пар BYBIT для агрессивного мониторинга:")
        for i, pair in enumerate(sorted_pairs[:10], 1):
            logger.info(f"{i}. {pair.symbol}: ${pair.volume_24h_usd:,.0f}")

        # Запускаем агрессивный мониторинг в отдельной задаче
        monitor_task = asyncio.create_task(
            client.start_aggressive_monitoring(sorted_pairs, db_manager),
            name="bybit_aggressive_monitor"
        )

        return monitor_task

    except Exception as e:
        logger.error(f"Ошибка настройки агрессивного мониторинга Bybit: {e}")
        return None


async def run_hybrid_monitoring_cycle(
        binance_data: Dict,
        bybit_client: BybitAggressiveClient,
        db_manager: DatabaseManager
) -> None:
    """
    Выполняет гибридный цикл: Binance батчами, Bybit непрерывно.
    """
    logger.info("Запуск гибридного мониторинга:")
    logger.info("• Binance: батчевая обработка с паузами")
    logger.info("• Bybit: непрерывный агрессивный мониторинг")

    # Обрабатываем Binance в обычном режиме
    binance_result = await process_binance_exchange(
        binance_data['client'],
        binance_data['analyzer'],
        db_manager
    )

    # Получаем статистику Bybit
    bybit_stats = await bybit_client.get_monitoring_stats()

    # Показываем результаты
    print(f"\n{'=' * 80}")
    print(f"ИТОГИ ГИБРИДНОГО ЦИКЛА МОНИТОРИНГА:")
    print(f"{'=' * 80}")

    exchange_name, new_count, dup_count, found_count = binance_result
    print(f"{'BINANCE':>12}: найдено {found_count:>4} | "
          f"новых {new_count:>4} | дубликатов {dup_count:>4}")

    print(f"{'BYBIT':>12}: непрерывный мониторинг | "
          f"запросов {bybit_stats.get('total_requests', 0):>4} | "
          f"сделок {bybit_stats.get('trades_found', 0):>4}")

    print(f"{'=' * 80}")

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
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║      CRYPTO LARGE TRADES MONITOR v3.0             ║
    ║                                                   ║
    ║  Гибридный мониторинг крупных сделок             ║
    ║  • Binance: батчевая обработка                   ║
    ║  • Bybit: непрерывный агрессивный мониторинг     ║
    ║  Минимальная сумма сделки: $49,000               ║
    ╚═══════════════════════════════════════════════════╝
    """)

    setup_logging(level="INFO")
    db_manager = DatabaseManager()

    try:
        await db_manager.connect()
        await db_manager.create_tables()

        verify_ssl = not (os.environ.get('DISABLE_SSL_VERIFY', '').lower() == 'true')
        ssl_context = create_ssl_context(verify_ssl)

        timeout = aiohttp.ClientTimeout(total=30)
        connector = TCPConnector(
            ssl=ssl_context,
            limit=100,  # Увеличиваем лимиты для агрессивного мониторинга
            limit_per_host=50
        )

        async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
        ) as session:

            # Инициализируем биржи
            binance_data = {
                'client': BinanceClient(session, RateLimiter(MAX_WEIGHT_PER_MINUTE)),
                'analyzer': BinanceAnalyzer()
            }

            bybit_client = BybitAggressiveClient(session, None)  # Rate limiter не используется
            bybit_analyzer = BybitAnalyzer()

            # Тестируем соединения
            logger.info("Тестирование соединений с биржами...")

            binance_ok = await binance_data['client'].test_connection()
            bybit_ok = await bybit_client.test_connection()

            if not binance_ok:
                logger.error("Не удалось подключиться к Binance")
                binance_data = None

            if not bybit_ok:
                logger.error("Не удалось подключиться к Bybit")
                bybit_client = None

            if not binance_ok and not bybit_ok:
                logger.error("Не удалось подключиться ни к одной бирже")
                return

            active_exchanges = []
            if binance_ok:
                active_exchanges.append("Binance")
            if bybit_ok:
                active_exchanges.append("Bybit (агрессивный)")

            logger.info(f"Успешно подключены биржи: {', '.join(active_exchanges)}")

            # Запускаем агрессивный мониторинг Bybit в фоне
            bybit_monitor_task = None
            if bybit_ok:
                bybit_monitor_task = await setup_bybit_aggressive_monitoring(
                    bybit_client, bybit_analyzer, db_manager
                )
                if bybit_monitor_task:
                    logger.info("🚀 Агрессивный мониторинг Bybit запущен в фоне")
                else:
                    logger.warning("Не удалось запустить агрессивный мониторинг Bybit")

            # Основной цикл мониторинга
            cycle_count = 0

            try:
                while True:
                    cycle_count += 1
                    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                    print(f"\n{'#' * 80}")
                    print(f"НАЧАЛО ЦИКЛА #{cycle_count} | Время: {current_time}")
                    print(f"Режим: ГИБРИДНЫЙ")
                    if binance_ok:
                        print(f"• Binance: батчевая обработка с паузами")
                    if bybit_ok:
                        print(f"• Bybit: непрерывный мониторинг (фоновый)")
                    print(f"SSL проверка: {'включена' if verify_ssl else 'ОТКЛЮЧЕНА'}")
                    print(f"{'#' * 80}\n")

                    try:
                        start_time = asyncio.get_event_loop().time()

                        # Запускаем гибридный мониторинг
                        if binance_ok:
                            await run_hybrid_monitoring_cycle(
                                binance_data, bybit_client, db_manager
                            )
                        else:
                            # Только показываем статистику Bybit
                            if bybit_ok:
                                bybit_stats = await bybit_client.get_monitoring_stats()
                                print(f"\n{'=' * 80}")
                                print(f"СТАТИСТИКА НЕПРЕРЫВНОГО МОНИТОРИНГА BYBIT:")
                                print(f"{'=' * 80}")
                                print(f"Всего запросов: {bybit_stats.get('total_requests', 0)}")
                                print(f"Успешных запросов: {bybit_stats.get('successful_requests', 0)}")
                                print(f"Ошибок: {bybit_stats.get('errors', 0)}")
                                print(f"Сделок найдено: {bybit_stats.get('trades_found', 0)}")
                                print(
                                    f"Крупных сделок: {bybit_stats.get('large_trades_found', 0)} (${MIN_TRADE_VALUE_USD}+)")
                                print(f"Мелких отфильтровано: {bybit_stats.get('small_trades_filtered', 0)}")
                                print(f"Сделок сохранено: {bybit_stats.get('trades_saved', 0)}")
                                print(f"Дубликатов отфильтровано: {bybit_stats.get('duplicates_filtered', 0)}")
                                print(f"{'=' * 80}\n")

                        end_time = asyncio.get_event_loop().time()
                        cycle_duration = end_time - start_time
                        logger.info(f"Цикл #{cycle_count} завершен за {cycle_duration:.1f} секунд")

                        # Проверяем состояние фонового мониторинга Bybit
                        if bybit_monitor_task and bybit_monitor_task.done():
                            logger.warning("⚠️ Агрессивный мониторинг Bybit завершился неожиданно")
                            try:
                                await bybit_monitor_task  # Проверяем на исключения
                            except Exception as e:
                                logger.error(f"Ошибка в агрессивном мониторинге Bybit: {e}")

                            # Пытаемся перезапустить
                            logger.info("Попытка перезапуска агрессивного мониторинга Bybit...")
                            bybit_monitor_task = await setup_bybit_aggressive_monitoring(
                                bybit_client, bybit_analyzer, db_manager
                            )

                        # Пауза между циклами (только для Binance, Bybit работает непрерывно)
                        if binance_ok:
                            logger.info(f"Пауза {MONITORING_PAUSE_MINUTES} минут до следующего цикла Binance...")
                            logger.info("(Bybit продолжает непрерывный мониторинг)")

                            # Обратный отсчет
                            for remaining in range(MONITORING_PAUSE_MINUTES * 60, 0, -30):
                                minutes, seconds = divmod(remaining, 60)
                                print(f"\rСледующий цикл Binance через: {minutes:02d}:{seconds:02d}",
                                      end='', flush=True)
                                await asyncio.sleep(min(30, remaining))
                            print()
                        else:
                            # Если только Bybit, делаем меньшую паузу
                            await asyncio.sleep(60)

                    except KeyboardInterrupt:
                        logger.info("Получен сигнал остановки (Ctrl+C)")
                        break
                    except Exception as e:
                        logger.error(f"Ошибка в цикле #{cycle_count}: {e}")
                        logger.info("Повтор через 1 минуту...")
                        await asyncio.sleep(60)

            finally:
                # Останавливаем агрессивный мониторинг Bybit
                if bybit_monitor_task and not bybit_monitor_task.done():
                    logger.info("Остановка агрессивного мониторинга Bybit...")
                    await bybit_client.stop_monitoring()

                    try:
                        await asyncio.wait_for(bybit_monitor_task, timeout=10.0)
                    except asyncio.TimeoutError:
                        logger.warning("Таймаут при остановке мониторинга Bybit")
                        bybit_monitor_task.cancel()

    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await db_manager.close()
        logger.info("Мониторинг завершен")


if __name__ == "__main__":
    asyncio.run(main())
