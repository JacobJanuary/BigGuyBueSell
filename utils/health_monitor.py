"""
Монитор здоровья системы для отслеживания состояния воркеров.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Монитор для отслеживания здоровья воркеров."""

    def __init__(self, check_interval_minutes: int = 15):
        """
        Инициализирует монитор здоровья.

        Args:
            check_interval_minutes: Интервал проверки в минутах
        """
        self.check_interval_minutes = check_interval_minutes
        self.workers: List = []
        self.is_running = False
        self.last_check_time = None
        self.health_history: Dict[str, List] = {}

    def register_worker(self, worker):
        """
        Регистрирует воркер для мониторинга.

        Args:
            worker: Экземпляр ExchangeWorker
        """
        self.workers.append(worker)
        self.health_history[worker.exchange_name] = []
        logger.info(f"Health Monitor: зарегистрирован воркер {worker.exchange_name}")

    def check_worker_health(self, worker) -> Dict:
        """
        Проверяет здоровье одного воркера.

        Args:
            worker: Экземпляр ExchangeWorker

        Returns:
            Словарь с информацией о здоровье
        """
        now = datetime.now()
        stats = worker.get_stats()

        health_info = {
            'exchange': worker.exchange_name,
            'is_running': worker.is_running,
            'cycle_count': stats['cycle_count'],
            'total_trades_found': stats['total_trades_found'],
            'total_trades_saved': stats['total_trades_saved'],
            'check_time': now,
            'status': 'healthy',
            'issues': []
        }

        # Проверяем различные аспекты здоровья
        if not worker.is_running:
            health_info['status'] = 'stopped'
            health_info['issues'].append('Воркер остановлен')

        # Проверяем, есть ли прогресс в циклах
        if worker.exchange_name in self.health_history:
            recent_checks = self.health_history[worker.exchange_name]
            if recent_checks:
                last_cycle_count = recent_checks[-1].get('cycle_count', 0)
                if stats['cycle_count'] == last_cycle_count and worker.is_running:
                    health_info['status'] = 'stalled'
                    health_info['issues'].append('Нет прогресса в циклах')

        # Сохраняем в историю (последние 10 проверок)
        self.health_history[worker.exchange_name].append(health_info.copy())
        if len(self.health_history[worker.exchange_name]) > 10:
            self.health_history[worker.exchange_name].pop(0)

        return health_info

    async def perform_health_check(self):
        """Выполняет проверку здоровья всех воркеров."""
        self.last_check_time = datetime.now()

        logger.info("🏥 Выполняется проверка здоровья воркеров...")

        all_healthy = True
        health_results = []

        for worker in self.workers:
            try:
                health_info = self.check_worker_health(worker)
                health_results.append(health_info)

                if health_info['status'] != 'healthy':
                    all_healthy = False
                    logger.warning(
                        f"⚠️  {worker.exchange_name.upper()}: {health_info['status']} - "
                        f"{', '.join(health_info['issues'])}"
                    )
                else:
                    logger.info(f"✅ {worker.exchange_name.upper()}: здоров")

            except Exception as e:
                logger.error(f"❌ Ошибка проверки здоровья {worker.exchange_name}: {e}")
                all_healthy = False

        # Общий статус
        if all_healthy:
            logger.info("🎉 Все воркеры работают нормально")
        else:
            logger.warning("⚠️  Обнаружены проблемы с некоторыми воркерами")

        return health_results

    def get_system_summary(self) -> Dict:
        """
        Возвращает общую сводку состояния системы.

        Returns:
            Словарь с общей информацией о системе
        """
        now = datetime.now()
        summary = {
            'total_workers': len(self.workers),
            'running_workers': sum(1 for w in self.workers if w.is_running),
            'stopped_workers': sum(1 for w in self.workers if not w.is_running),
            'last_check': self.last_check_time,
            'uptime_hours': 0,  # Можно добавить отслеживание uptime
            'exchanges': [w.exchange_name for w in self.workers]
        }

        return summary

    async def run_forever(self):
        """Запускает непрерывный мониторинг здоровья."""
        self.is_running = True
        logger.info(f"🏥 Запуск Health Monitor (проверки каждые {self.check_interval_minutes} мин)")

        # Первая проверка через минуту после запуска
        await asyncio.sleep(60)

        while self.is_running:
            try:
                await self.perform_health_check()

                # Ждем до следующей проверки
                for remaining in range(self.check_interval_minutes * 60, 0, -30):
                    if not self.is_running:
                        break
                    await asyncio.sleep(min(30, remaining))

            except asyncio.CancelledError:
                logger.info("Health Monitor остановлен")
                break
            except Exception as e:
                logger.error(f"Ошибка в Health Monitor: {e}")
                await asyncio.sleep(60)

        self.is_running = False
        logger.info("Health Monitor завершен")

    def stop(self):
        """Останавливает монитор здоровья."""
        self.is_running = False