"""
Воркер для независимой обработки одной биржи с использованием кэша торговых пар.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

from config.settings import MIN_TRADE_VALUE_USD, BATCH_SIZE, MAX_CONCURRENT_REQUESTS, PAIRS_CACHE_TTL_HOURS
from database.manager import DatabaseManager
from database.pairs_cache import PairsCacheManager
from database.models import Trade, TradingPairInfo

logger = logging.getLogger(__name__)


class ExchangeWorker:
    """Независимый воркер для обработки одной биржи с кэшированием пар."""

    def __init__(
        self,
        exchange_name: str,
        client,
        analyzer,
        db_manager: DatabaseManager,
        cycle_pause_minutes: int = 5
    ):
        """
        Инициализирует воркер биржи.

        Args:
            exchange_name: Название биржи
            client: Клиент API биржи
            analyzer: Анализатор данных биржи
            db_manager: Менеджер базы данных
            cycle_pause_minutes: Пауза между циклами в минутах
        """
        self.exchange_name = exchange_name
        self.client = client
        self.analyzer = analyzer
        self.db_manager = db_manager
        self.cycle_pause_minutes = cycle_pause_minutes
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

        # Менеджер кэша торговых пар
        self.pairs_cache = PairsCacheManager(db_manager.pool)

        # Время последнего обновления кэша
        self.last_cache_update = None

        # Статистика
        self.cycle_count = 0
        self.total_trades_found = 0
        self.total_trades_saved = 0
        self.cache_updates_count = 0
        self.is_running = False

    async def process_pair(self, pair_info: TradingPairInfo) -> List[Trade]:
        """
        Обрабатывает одну торговую пару.

        Args:
            pair_info: Информация о паре

        Returns:
            Список крупных сделок
        """
        async with self.semaphore:
            try:
                trades_data = await self.client.get_recent_trades(pair_info.symbol)
                if not trades_data:
                    return []

                large_trades = []
                for trade_data in trades_data:
                    trade = await self.client.parse_trade(trade_data, pair_info)

                    if trade.value_usd >= Decimal(str(MIN_TRADE_VALUE_USD)):
                        large_trades.append(trade)

                return large_trades

            except Exception as e:
                logger.debug(f"[{self.exchange_name.upper()}] Ошибка обработки пары {pair_info.symbol}: {e}")
                return []

    async def get_trading_pairs(self) -> Optional[List[TradingPairInfo]]:
        """
        Получает список торговых пар (из кэша или API).

        Returns:
            Список торговых пар или None в случае ошибки
        """
        try:
            # Проверяем актуальность кэша
            cache_fresh = await self.pairs_cache.is_cache_fresh(
                self.exchange_name,
                PAIRS_CACHE_TTL_HOURS
            )

            if cache_fresh:
                # Используем кэш
                logger.debug(f"[{self.exchange_name.upper()}] Используем кэш торговых пар")
                pairs = await self.pairs_cache.get_cached_pairs(self.exchange_name)
                if pairs:
                    return pairs
                else:
                    logger.warning(f"[{self.exchange_name.upper()}] Кэш пуст, обновляем...")

            # Кэш устарел или пуст - обновляем через API
            logger.info(f"[{self.exchange_name.upper()}] Обновление кэша торговых пар...")
            return await self.update_pairs_cache()

        except Exception as e:
            logger.error(f"[{self.exchange_name.upper()}] Ошибка получения торговых пар: {e}")
            return None

    async def update_pairs_cache(self) -> Optional[List[TradingPairInfo]]:
        """
        Обновляет кэш торговых пар через API.

        Returns:
            Список отфильтрованных пар или None в случае ошибки
        """
        try:
            # Получаем данные через API в зависимости от биржи
            if self.exchange_name == 'binance':
                exchange_info = await self.client.get_exchange_info()
                tickers = await self.client.get_24hr_tickers()
                filtered_pairs = self.analyzer.filter_trading_pairs(exchange_info, tickers)
            elif self.exchange_name == 'bybit':
                exchange_info = await self.client.get_instruments_info()
                tickers = await self.client.get_24hr_tickers()
                filtered_pairs = self.analyzer.filter_trading_pairs(exchange_info, tickers)
            elif self.exchange_name == 'coinbase':
                products_info = await self.client.get_products_info()
                tickers = await self.client.get_24hr_tickers()
                filtered_pairs = self.analyzer.filter_trading_pairs(products_info, tickers)
            else:
                logger.error(f"[{self.exchange_name.upper()}] Неизвестная биржа для обновления кэша")
                return None

            if not filtered_pairs:
                logger.warning(f"[{self.exchange_name.upper()}] API не вернул торговых пар")
                return None

            # Обновляем кэш в БД
            added, updated, deactivated = await self.pairs_cache.update_pairs_cache(
                self.exchange_name,
                filtered_pairs
            )

            self.cache_updates_count += 1
            self.last_cache_update = datetime.now()

            logger.info(
                f"[{self.exchange_name.upper()}] Кэш обновлен: "
                f"+{added} ~{updated} -{deactivated}, итого {len(filtered_pairs)} активных пар"
            )

            return filtered_pairs

        except Exception as e:
            logger.error(f"[{self.exchange_name.upper()}] Ошибка обновления кэша: {e}")
            return None

    async def should_update_cache(self) -> bool:
        """
        Определяет, нужно ли обновлять кэш.

        Returns:
            True если пора обновлять кэш
        """
        if not self.last_cache_update:
            return True

        time_since_update = datetime.now() - self.last_cache_update
        update_interval_seconds = PAIRS_CACHE_TTL_HOURS * 3600

        return time_since_update.total_seconds() >= update_interval_seconds

    async def run_cycle(self) -> Dict:
        """
        Выполняет один цикл обработки биржи.

        Returns:
            Словарь со статистикой цикла
        """
        self.cycle_count += 1
        cycle_start = asyncio.get_event_loop().time()

        logger.info(f"[{self.exchange_name.upper()}] Начало цикла #{self.cycle_count}")

        try:
            # Получаем торговые пары (из кэша или API)
            trading_pairs = await self.get_trading_pairs()
            if not trading_pairs:
                logger.warning(f"[{self.exchange_name.upper()}] Не удалось получить торговые пары")
                return {
                    'exchange': self.exchange_name,
                    'cycle': self.cycle_count,
                    'pairs_count': 0,
                    'trades_found': 0,
                    'trades_saved': 0,
                    'duplicates': 0,
                    'duration': 0,
                    'cache_used': False,
                    'error': 'Нет торговых пар'
                }

            # Сортируем по объему
            trading_pairs.sort(key=lambda x: x.volume_24h_usd, reverse=True)

            # Показываем топ-5 пар
            logger.info(f"[{self.exchange_name.upper()}] Топ-5 пар по объему:")
            for i, pair in enumerate(trading_pairs[:5], 1):
                logger.info(f"  {i}. {pair.symbol}: ${pair.volume_24h_usd:,.0f}")

            cycle_trades_found = 0
            cycle_trades_saved = 0
            cycle_duplicates = 0

            # Обрабатываем пары батчами
            for i in range(0, len(trading_pairs), BATCH_SIZE):
                batch = trading_pairs[i:i + BATCH_SIZE]

                # Создаем задачи для батча
                tasks = [
                    self.process_pair(pair_info)
                    for pair_info in batch
                ]

                # Выполняем задачи параллельно
                results = await asyncio.gather(*tasks, return_exceptions=True)

                batch_trades = []
                for result in results:
                    if isinstance(result, Exception):
                        logger.debug(f"[{self.exchange_name.upper()}] Исключение в обработке пары: {result}")
                        continue
                    batch_trades.extend(result)

                # Сохраняем в БД
                if batch_trades:
                    new_count, dup_count = await self.db_manager.save_trades(batch_trades)
                    cycle_trades_saved += new_count
                    cycle_duplicates += dup_count
                    cycle_trades_found += len(batch_trades)

                # Прогресс
                processed = min(i + BATCH_SIZE, len(trading_pairs))
                if len(batch_trades) > 0:
                    logger.info(
                        f"[{self.exchange_name.upper()}] {processed}/{len(trading_pairs)} пар | "
                        f"Найдено: {len(batch_trades)} | Новых: {new_count} | Дубли: {dup_count}"
                    )

                # Небольшая пауза между батчами
                if i + BATCH_SIZE < len(trading_pairs):
                    await asyncio.sleep(0.5)

            # Обновляем общую статистику
            self.total_trades_found += cycle_trades_found
            self.total_trades_saved += cycle_trades_saved

            cycle_duration = asyncio.get_event_loop().time() - cycle_start

            logger.info(
                f"[{self.exchange_name.upper()}] Цикл #{self.cycle_count} завершен за {cycle_duration:.1f}с | "
                f"Найдено: {cycle_trades_found} | Сохранено: {cycle_trades_saved} | Дубли: {cycle_duplicates}"
            )

            return {
                'exchange': self.exchange_name,
                'cycle': self.cycle_count,
                'pairs_count': len(trading_pairs),
                'trades_found': cycle_trades_found,
                'trades_saved': cycle_trades_saved,
                'duplicates': cycle_duplicates,
                'duration': cycle_duration,
                'cache_used': True,
                'cache_updates': self.cache_updates_count,
                'error': None
            }

        except Exception as e:
            cycle_duration = asyncio.get_event_loop().time() - cycle_start
            logger.error(f"[{self.exchange_name.upper()}] Ошибка в цикле #{self.cycle_count}: {e}")

            return {
                'exchange': self.exchange_name,
                'cycle': self.cycle_count,
                'pairs_count': 0,
                'trades_found': 0,
                'trades_saved': 0,
                'duplicates': 0,
                'duration': cycle_duration,
                'cache_used': False,
                'cache_updates': self.cache_updates_count,
                'error': str(e)
            }

    async def run_forever(self):
        """
        Запускает непрерывный цикл обработки биржи.
        """
        self.is_running = True
        logger.info(f"[{self.exchange_name.upper()}] Запуск непрерывного мониторинга (пауза {self.cycle_pause_minutes} мин)")

        # При первом запуске проверяем и инициализируем кэш
        logger.info(f"[{self.exchange_name.upper()}] Инициализация кэша торговых пар...")
        try:
            initial_pairs = await self.get_trading_pairs()
            if initial_pairs:
                logger.info(f"[{self.exchange_name.upper()}] Инициализация завершена, найдено {len(initial_pairs)} пар")
            else:
                logger.warning(f"[{self.exchange_name.upper()}] Не удалось инициализировать кэш")
        except Exception as e:
            logger.error(f"[{self.exchange_name.upper()}] Ошибка инициализации кэша: {e}")

        while self.is_running:
            try:
                # Выполняем цикл
                cycle_result = await self.run_cycle()

                # Пауза между циклами
                if self.is_running:  # Проверяем, что не было команды остановки
                    logger.info(f"[{self.exchange_name.upper()}] Пауза {self.cycle_pause_minutes} минут...")

                    # Обратный отсчет с проверкой остановки
                    for remaining in range(self.cycle_pause_minutes * 60, 0, -30):
                        if not self.is_running:
                            break
                        await asyncio.sleep(min(30, remaining))

            except asyncio.CancelledError:
                logger.info(f"[{self.exchange_name.upper()}] Получена команда остановки")
                break
            except Exception as e:
                logger.error(f"[{self.exchange_name.upper()}] Критическая ошибка: {e}")
                logger.info(f"[{self.exchange_name.upper()}] Повтор через 1 минуту...")
                await asyncio.sleep(60)

        self.is_running = False
        logger.info(f"[{self.exchange_name.upper()}] Мониторинг остановлен")

    def stop(self):
        """Останавливает воркер."""
        self.is_running = False

    def get_stats(self) -> Dict:
        """
        Возвращает статистику воркера.

        Returns:
            Словарь со статистикой
        """
        return {
            'exchange': self.exchange_name,
            'cycle_count': self.cycle_count,
            'total_trades_found': self.total_trades_found,
            'total_trades_saved': self.total_trades_saved,
            'cache_updates_count': self.cache_updates_count,
            'last_cache_update': self.last_cache_update.isoformat() if self.last_cache_update else None,
            'is_running': self.is_running
        }