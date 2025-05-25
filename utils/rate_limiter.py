"""
Rate limiter для контроля частоты запросов к API.
"""
import asyncio
import logging
import time
from typing import List, Tuple

logger = logging.getLogger(__name__)


class RateLimiter:
    """Контроллер rate limits для API запросов."""

    def __init__(self, max_weight_per_minute: int):
        """
        Инициализирует rate limiter.

        Args:
            max_weight_per_minute: Максимальный вес запросов в минуту
        """
        self.max_weight_per_minute = max_weight_per_minute
        self.requests: List[Tuple[float, int]] = []  # (timestamp, weight)
        self.lock = asyncio.Lock()

    async def acquire(self, weight: int) -> None:
        """
        Ожидает, пока можно будет выполнить запрос с указанным весом.

        Args:
            weight: Вес запроса
        """
        while True:
            async with self.lock:
                current_time = time.time()

                # Удаляем запросы старше минуты
                self.requests = [
                    (ts, w) for ts, w in self.requests
                    if current_time - ts < 60
                ]

                # Считаем текущий вес
                current_weight = sum(w for _, w in self.requests)

                # Если можем выполнить запрос - выполняем
                if current_weight + weight <= self.max_weight_per_minute:
                    self.requests.append((current_time, weight))
                    return

                # Иначе вычисляем время ожидания
                if self.requests:
                    oldest_request_time = min(ts for ts, _ in self.requests)
                    wait_time = max(0.1, 60 - (current_time - oldest_request_time) + 1)
                else:
                    wait_time = 1.0

            # Ждем вне блокировки
            logger.info(
                f"Rate limit достигнут ({current_weight + weight}/{self.max_weight_per_minute}), "
                f"ожидание {wait_time:.1f} секунд"
            )
            await asyncio.sleep(wait_time)

    async def reset(self) -> None:
        """Сбрасывает счетчик запросов."""
        async with self.lock:
            self.requests.clear()

    def get_current_weight(self) -> int:
        """
        Возвращает текущий вес запросов за последнюю минуту.

        Returns:
            Текущий суммарный вес
        """
        current_time = time.time()
        active_requests = [
            (ts, w) for ts, w in self.requests
            if current_time - ts < 60
        ]
        return sum(w for _, w in active_requests)