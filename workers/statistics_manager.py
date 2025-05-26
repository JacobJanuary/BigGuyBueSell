"""
Менеджер статистики для мониторинга работы всех бирж.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List

from database.manager import DatabaseManager

logger = logging.getLogger(__name__)


class StatisticsManager:
    """Менеджер для отображения общей статистики работы всех бирж."""

    def __init__(self, db_manager: DatabaseManager, report_interval_minutes: int = 10):
        """
        Инициализирует менеджер статистики.

        Args:
            db_manager: Менеджер базы данных
            report_interval_minutes: Интервал вывода отчетов в минутах
        """
        self.db_manager = db_manager
        self.report_interval_minutes = report_interval_minutes
        self.workers: List = []
        self.is_running = False

    def register_worker(self, worker):
        """
        Регистрирует воркер биржи для мониторинга.

        Args:
            worker: Экземпляр ExchangeWorker
        """
        self.workers.append(worker)
        logger.info(f"Зарегистрирован воркер {worker.exchange_name}")

    async def print_status_report(self):
        """Выводит отчет о текущем состоянии всех бирж."""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        print(f"\n{'=' * 100}")
        print(f"ОТЧЕТ О РАБОТЕ БИРЖ | Время: {current_time}")
        print(f"{'=' * 100}")

        # Статистика воркеров
        if self.workers:
            print(f"{'Биржа':>12} | {'Циклов':>8} | {'Найдено':>10} | {'Сохранено':>12} | {'Кэш обн.':>10} | {'Статус':>10}")
            print(f"{'-' * 100}")

            for worker in self.workers:
                stats = worker.get_stats()
                status = "🟢 Работает" if stats['is_running'] else "🔴 Остановлен"
                cache_updates = stats.get('cache_updates_count', 0)

                print(f"{stats['exchange'].upper():>12} | "
                      f"{stats['cycle_count']:>8} | "
                      f"{stats['total_trades_found']:>10} | "
                      f"{stats['total_trades_saved']:>12} | "
                      f"{cache_updates:>10} | "
                      f"{status:>10}")

        # Статистика кэша торговых пар
        try:
            from database.pairs_cache import PairsCacheManager
            pairs_cache = PairsCacheManager(self.db_manager.pool)

            print(f"\n📊 Статистика кэша торговых пар:")
            print(f"{'Биржа':>12} | {'Всего пар':>12} | {'Активных':>10} | {'Средний объем':>15} | {'Обновление':>20}")
            print(f"{'-' * 90}")

            for worker in self.workers:
                exchange = worker.exchange_name
                cache_stats = await pairs_cache.get_cache_stats(exchange)

                last_update = "Никогда"
                if cache_stats['last_update']:
                    last_update = cache_stats['last_update'].strftime('%H:%M:%S')

                avg_volume = cache_stats['avg_volume']
                print(f"{exchange.upper():>12} | "
                      f"{cache_stats['total_pairs']:>12} | "
                      f"{cache_stats['active_pairs']:>10} | "
                      f"${avg_volume:>14,.0f} | "
                      f"{last_update:>20}")

        except Exception as e:
            logger.error(f"Ошибка получения статистики кэша: {e}")

        # Статистика из БД за 24 часа
        try:
            stats_by_exchange = await self.db_manager.get_statistics_by_exchange()
            if stats_by_exchange:
                print(f"\nСтатистика сделок за 24 часа:")
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

        except Exception as e:
            logger.error(f"Ошибка получения статистики из БД: {e}")

        print(f"{'=' * 100}\n")

    async def run_forever(self):
        """Запускает непрерывный вывод статистики."""
        self.is_running = True
        logger.info(f"Запуск менеджера статистики (отчеты каждые {self.report_interval_minutes} мин)")

        # Первый отчет сразу
        await self.print_status_report()

        while self.is_running:
            try:
                # Ждем интервал
                for remaining in range(self.report_interval_minutes * 60, 0, -30):
                    if not self.is_running:
                        break
                    await asyncio.sleep(min(30, remaining))

                if self.is_running:
                    await self.print_status_report()

            except asyncio.CancelledError:
                logger.info("Менеджер статистики остановлен")
                break
            except Exception as e:
                logger.error(f"Ошибка в менеджере статистики: {e}")
                await asyncio.sleep(60)

        self.is_running = False

    def stop(self):
        """Останавливает менеджер статистики."""
        self.is_running = False