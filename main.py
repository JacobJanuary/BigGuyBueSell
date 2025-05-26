#!/usr/bin/env python3
"""
Главный модуль для мониторинга крупных сделок на криптовалютных биржах.
Каждая биржа работает в независимом цикле.
"""
import asyncio
import logging
import os
import signal
import sys
from typing import List

import aiohttp
from aiohttp import TCPConnector

from config.settings import (
    MAX_WEIGHT_PER_MINUTE, DISABLE_SSL_VERIFY, EXCHANGES_CONFIG,
    STATS_REPORT_MINUTES, HEALTH_CHECK_MINUTES, LOG_LEVEL
)
from database.manager import DatabaseManager
from exchanges.binance.client import BinanceClient
from exchanges.binance.analyzer import BinanceAnalyzer
from exchanges.bybit.client import BybitClient
from exchanges.bybit.analyzer import BybitAnalyzer
from exchanges.coinbase.client import CoinbaseClient
from exchanges.coinbase.analyzer import CoinbaseAnalyzer
from utils.logger import setup_logging
from utils.rate_limiter import RateLimiter
from utils.ssl_helper import create_ssl_context
from workers.exchange_worker import ExchangeWorker
from utils.health_monitor import HealthMonitor
from workers.statistics_manager import StatisticsManager

logger = logging.getLogger(__name__)

# Глобальные переменные для graceful shutdown
workers: List[ExchangeWorker] = []
stats_manager: StatisticsManager = None
health_monitor: HealthMonitor = None
worker_tasks: List[asyncio.Task] = []


def signal_handler(signum, frame):
    """Обработчик сигналов для graceful shutdown."""
    logger.info(f"Получен сигнал {signum}, начинаем остановку...")

    # Останавливаем все воркеры
    for worker in workers:
        worker.stop()

    # Останавливаем менеджер статистики
    if stats_manager:
        stats_manager.stop()

    # Останавливаем health monitor
    if health_monitor:
        health_monitor.stop()


async def setup_exchanges(session: aiohttp.ClientSession, db_manager: DatabaseManager) -> List[ExchangeWorker]:
    """
    Настраивает воркеры для всех бирж.

    Args:
        session: HTTP сессия
        db_manager: Менеджер базы данных

    Returns:
        Список созданных воркеров
    """
    active_workers = []

    # Создаем и тестируем воркеры для каждой биржи
    for exchange_name, config in EXCHANGES_CONFIG.items():
        # Пропускаем отключенные биржи
        if not config.get('enabled', True):
            logger.info(f"⏹️  {exchange_name.upper()} отключен в конфигурации")
            continue

        try:
            logger.info(f"Настройка {exchange_name.upper()}...")
            logger.info(f"  Пауза между циклами: {config['cycle_pause_minutes']} мин")
            logger.info(f"  Rate limit: {config['rate_limit']} запросов/мин")
            logger.info(f"  Лимит сделок за запрос: {config['trades_limit']}")

            # Создаем клиент и анализатор в зависимости от биржи
            if exchange_name == 'binance':
                client = BinanceClient(session, RateLimiter(config['rate_limit']))
                analyzer = BinanceAnalyzer()
            elif exchange_name == 'bybit':
                client = BybitClient(session, RateLimiter(config['rate_limit']))
                analyzer = BybitAnalyzer()
            elif exchange_name == 'coinbase':
                client = CoinbaseClient(session, RateLimiter(config['rate_limit']))
                analyzer = CoinbaseAnalyzer()
            else:
                logger.warning(f"⚠️  Неизвестная биржа: {exchange_name}")
                continue

            # Тестируем соединение
            if await client.test_connection():
                # Создаем воркер
                worker = ExchangeWorker(
                    exchange_name=exchange_name,
                    client=client,
                    analyzer=analyzer,
                    db_manager=db_manager,
                    cycle_pause_minutes=config['cycle_pause_minutes']
                )

                active_workers.append(worker)
                logger.info(f"✅ {exchange_name.upper()} готов к работе")
            else:
                logger.error(f"❌ Не удалось подключиться к {exchange_name.upper()}")

        except KeyError as e:
            logger.error(f"❌ Отсутствует конфигурация для {exchange_name}: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка настройки {exchange_name.upper()}: {e}")

    return active_workers


async def main() -> None:
    """Основная функция программы."""
    global workers, stats_manager, health_monitor, worker_tasks

    # Выводим стартовый баннер
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║      CRYPTO LARGE TRADES MONITOR v3.0             ║
    ║                                                   ║
    ║  Мониторинг крупных сделок на криптобиржах       ║
    ║  Минимальная сумма сделки: $49,000               ║
    ║  Режим: НЕЗАВИСИМЫЕ ЦИКЛЫ ДЛЯ КАЖДОЙ БИРЖИ      ║
    ║  Поддерживаемые биржи: Binance, Bybit, Coinbase  ║
    ╚═══════════════════════════════════════════════════╝
    """)

    # Настраиваем логирование
    setup_logging(level=LOG_LEVEL)

    # Настраиваем обработчики сигналов для graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Инициализируем БД
    db_manager = DatabaseManager()

    try:
        # Подключаемся к БД
        await db_manager.connect()
        await db_manager.create_tables()

        # Проверяем переменную окружения для SSL
        verify_ssl = not (os.environ.get('DISABLE_SSL_VERIFY', '').lower() == 'true')
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

            # Настраиваем воркеры бирж
            workers = await setup_exchanges(session, db_manager)

            if not workers:
                logger.error("Не удалось настроить ни одну биржу")
                return

            logger.info(f"Настроено {len(workers)} бирж: {[w.exchange_name for w in workers]}")
            print(f"SSL проверка: {'включена' if verify_ssl else 'ОТКЛЮЧЕНА'}")

            # Создаем и настраиваем менеджеры
            stats_manager = StatisticsManager(db_manager, report_interval_minutes=STATS_REPORT_MINUTES)
            health_monitor = HealthMonitor(check_interval_minutes=HEALTH_CHECK_MINUTES)

            for worker in workers:
                stats_manager.register_worker(worker)
                health_monitor.register_worker(worker)

            # Запускаем все воркеры и менеджеры
            logger.info("🚀 Запуск всех воркеров и менеджеров...")

            worker_tasks = []

            # Запускаем воркеры бирж
            for worker in workers:
                task = asyncio.create_task(worker.run_forever())
                task.set_name(f"worker_{worker.exchange_name}")
                worker_tasks.append(task)

            # Запускаем менеджер статистики
            stats_task = asyncio.create_task(stats_manager.run_forever())
            stats_task.set_name("statistics_manager")
            worker_tasks.append(stats_task)

            # Запускаем health monitor
            health_task = asyncio.create_task(health_monitor.run_forever())
            health_task.set_name("health_monitor")
            worker_tasks.append(health_task)

            logger.info(f"✅ Запущено {len(worker_tasks)} задач (воркеры + менеджеры)")

            # Ждем завершения всех задач
            try:
                await asyncio.gather(*worker_tasks)
            except asyncio.CancelledError:
                logger.info("Получена команда остановки")
            except Exception as e:
                logger.error(f"Ошибка в выполнении задач: {e}")

    except KeyboardInterrupt:
        logger.info("Программа остановлена пользователем (Ctrl+C)")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        # Graceful shutdown
        logger.info("Начинаем graceful shutdown...")

        # Останавливаем воркеры
        for worker in workers:
            worker.stop()

        # Останавливаем менеджеры
        if stats_manager:
            stats_manager.stop()

        if health_monitor:
            health_monitor.stop()

        # Отменяем все задачи
        for task in worker_tasks:
            if not task.done():
                task.cancel()

        # Ждем завершения задач
        if worker_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*worker_tasks, return_exceptions=True),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.warning("Некоторые задачи не завершились в течение 10 секунд")

        # Закрываем БД
        await db_manager.close()
        logger.info("Мониторинг завершен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Программа завершена пользователем")
    except Exception as e:
        print(f"💥 Критическая ошибка: {e}")
        sys.exit(1)