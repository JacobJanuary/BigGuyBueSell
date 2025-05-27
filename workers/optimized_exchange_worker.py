"""
Оптимизированный воркер для независимой обработки одной биржи с эффективным кэшированием.
workers/optimized_exchange_worker.py
"""
import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
import time

from config.settings import MIN_TRADE_VALUE_USD, BATCH_SIZE, MAX_CONCURRENT_REQUESTS
from database.manager import DatabaseManager
from database.pairs_cache import PairsCacheManager
from database.models import Trade, TradingPairInfo

logger = logging.getLogger(__name__)

# Настройки оптимизированного кэширования
MEMORY_CACHE_TTL_MINUTES = 30  # Время жизни in-memory кэша
API_UPDATE_INTERVAL_MINUTES = 60  # Интервал обновления через API
FALLBACK_CACHE_TTL_HOURS = 4  # TTL для fallback кэша в БД


class OptimizedExchangeWorker:
    """Оптимизированный воркер с умным кэшированием и минимальными API вызовами."""

    def __init__(
            self,
            exchange_name: str,
            client,
            analyzer,
            db_manager: DatabaseManager,
            cycle_pause_minutes: int = 5
    ):
        """
        Инициализирует оптимизированный воркер биржи.

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

        # In-memory кэш для максимальной эффективности
        self._memory_cache = {
            'pairs': None,
            'loaded_at': None,
            'last_api_update': None,
            'source': None  # 'api', 'db', 'fallback'
        }

        # Статистика эффективности
        self.stats = {
            'cycle_count': 0,
            'total_trades_found': 0,
            'total_trades_saved': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'api_calls': 0,
            'db_queries': 0,
            'memory_cache_hits': 0,
            'db_cache_hits': 0,
            'api_updates': 0,
            'fallback_uses': 0
        }

        self.is_running = False

    def _is_memory_cache_valid(self) -> bool:
        """
        Проверяет актуальность in-memory кэша.

        Returns:
            True если in-memory кэш актуален
        """
        if not self._memory_cache['pairs'] or not self._memory_cache['loaded_at']:
            return False

        cache_age_seconds = time.time() - self._memory_cache['loaded_at']
        max_age_seconds = MEMORY_CACHE_TTL_MINUTES * 60

        return cache_age_seconds < max_age_seconds

    def _should_update_from_api(self) -> bool:
        """
        Определяет, нужно ли обновлять кэш через API.

        Returns:
            True если пора обновлять кэш через API
        """
        if not self._memory_cache['last_api_update']:
            return True

        time_since_api_update = time.time() - self._memory_cache['last_api_update']
        api_update_interval = API_UPDATE_INTERVAL_MINUTES * 60

        return time_since_api_update >= api_update_interval

    async def _load_pairs_from_memory(self) -> Optional[List[TradingPairInfo]]:
        """
        Загружает пары из in-memory кэша.

        Returns:
            Список торговых пар или None
        """
        if self._is_memory_cache_valid():
            self.stats['memory_cache_hits'] += 1
            self.stats['cache_hits'] += 1

            cache_age = (time.time() - self._memory_cache['loaded_at']) / 60
            logger.debug(
                f"[{self.exchange_name.upper()}] Memory кэш: {len(self._memory_cache['pairs'])} пар, "
                f"возраст {cache_age:.1f}мин, источник: {self._memory_cache['source']}"
            )
            return self._memory_cache['pairs']

        return None

    async def _load_pairs_from_db(self) -> Optional[List[TradingPairInfo]]:
        """
        Загружает пары из БД кэша.

        Returns:
            Список торговых пар или None
        """
        try:
            self.stats['db_queries'] += 1

            # Проверяем актуальность БД кэша
            cache_fresh = await self.pairs_cache.is_cache_fresh(
                self.exchange_name,
                max_age_hours=2  # Более щадящий TTL для БД кэша
            )

            if cache_fresh:
                pairs = await self.pairs_cache.get_cached_pairs(self.exchange_name)
                if pairs:
                    # Сохраняем в memory кэш
                    self._memory_cache.update({
                        'pairs': pairs,
                        'loaded_at': time.time(),
                        'source': 'db'
                    })

                    self.stats['db_cache_hits'] += 1
                    self.stats['cache_hits'] += 1

                    logger.info(
                        f"[{self.exchange_name.upper()}] Загружено {len(pairs)} пар из БД кэша"
                    )
                    return pairs

            return None

        except Exception as e:
            logger.error(f"[{self.exchange_name.upper()}] Ошибка загрузки БД кэша: {e}")
            return None

    async def _update_pairs_from_api(self) -> Optional[List[TradingPairInfo]]:
        """
        Обновляет пары через API и сохраняет в кэш.

        Returns:
            Список торговых пар или None
        """
        try:
            logger.info(f"[{self.exchange_name.upper()}] 🔄 Обновление торговых пар через API...")

            self.stats['api_calls'] += 2  # exchange_info + tickers
            self.stats['api_updates'] += 1

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
                logger.error(f"[{self.exchange_name.upper()}] Неизвестная биржа для API обновления")
                return None

            if not filtered_pairs:
                logger.warning(f"[{self.exchange_name.upper()}] API не вернул торговых пар")
                return None

            # Обновляем БД кэш
            added, updated, deactivated = await self.pairs_cache.update_pairs_cache(
                self.exchange_name,
                filtered_pairs
            )

            # Обновляем memory кэш
            self._memory_cache.update({
                'pairs': filtered_pairs,
                'loaded_at': time.time(),
                'last_api_update': time.time(),
                'source': 'api'
            })

            logger.info(
                f"[{self.exchange_name.upper()}] ✅ API обновление завершено: "
                f"+{added} ~{updated} -{deactivated}, итого {len(filtered_pairs)} активных пар"
            )

            return filtered_pairs

        except Exception as e:
            logger.error(f"[{self.exchange_name.upper()}] ❌ Ошибка API обновления: {e}")
            return None

    async def get_trading_pairs(self) -> Optional[List[TradingPairInfo]]:
        """
        Получает список торговых пар с оптимальным кэшированием.

        Стратегия:
        1. Проверить in-memory кэш
        2. Если нужно API обновление - обновить
        3. Иначе загрузить из БД кэша
        4. Fallback к устаревшему кэшу

        Returns:
            Список торговых пар или None в случае ошибки
        """
        # 1. Проверяем memory кэш
        pairs = await self._load_pairs_from_memory()
        if pairs:
            return pairs

        # 2. Определяем нужно ли API обновление
        should_update_api = self._should_update_from_api()

        if should_update_api:
            # Пытаемся обновить через API
            pairs = await self._update_pairs_from_api()
            if pairs:
                return pairs
            else:
                logger.warning(
                    f"[{self.exchange_name.upper()}] ⚠️  API недоступен, "
                    f"пытаемся использовать БД кэш"
                )

        # 3. Загружаем из БД кэша
        pairs = await self._load_pairs_from_db()
        if pairs:
            return pairs

        # 4. Fallback - используем устаревший кэш если есть
        if self._memory_cache['pairs']:
            self.stats['fallback_uses'] += 1
            cache_age = (time.time() - self._memory_cache['loaded_at']) / 3600

            logger.warning(
                f"[{self.exchange_name.upper()}] 🔄 Используем устаревший кэш "
                f"(возраст {cache_age:.1f}ч)"
            )
            return self._memory_cache['pairs']

        # 5. Последняя попытка - принудительное API обновление
        self.stats['cache_misses'] += 1
        logger.error(f"[{self.exchange_name.upper()}] 🚨 Принудительное API обновление")
        return await self._update_pairs_from_api()

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

    def _get_cache_efficiency_report(self) -> str:
        """Возвращает отчет об эффективности кэша."""
        total_cache_ops = self.stats['cache_hits'] + self.stats['cache_misses']
        hit_rate = (self.stats['cache_hits'] / total_cache_ops * 100) if total_cache_ops > 0 else 0

        return (
            f"Кэш: {hit_rate:.1f}% эффективность, "
            f"memory:{self.stats['memory_cache_hits']}, "
            f"db:{self.stats['db_cache_hits']}, "
            f"API:{self.stats['api_updates']}, "
            f"fallback:{self.stats['fallback_uses']}"
        )

    async def run_cycle(self) -> Dict:
        """
        Выполняет один цикл обработки биржи.

        Returns:
            Словарь со статистикой цикла
        """
        self.stats['cycle_count'] += 1
        cycle_start = time.time()

        logger.info(f"[{self.exchange_name.upper()}] 🔄 Начало цикла #{self.stats['cycle_count']}")

        try:
            # Получаем торговые пары с оптимальным кэшированием
            trading_pairs = await self.get_trading_pairs()
            if not trading_pairs:
                logger.warning(f"[{self.exchange_name.upper()}] ❌ Не удалось получить торговые пары")
                return self._create_error_result(cycle_start, "Нет торговых пар")

            # Сортируем по объему
            trading_pairs.sort(key=lambda x: x.volume_24h_usd, reverse=True)

            # Показываем информацию о кэше и топ-5 пар
            cache_report = self._get_cache_efficiency_report()
            logger.info(f"[{self.exchange_name.upper()}] 📊 {cache_report}")

            logger.info(f"[{self.exchange_name.upper()}] 🏆 Топ-5 пар по объему:")
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
                        f"[{self.exchange_name.upper()}] 📈 {processed}/{len(trading_pairs)} пар | "
                        f"Найдено: {len(batch_trades)} | Новых: {new_count} | Дубли: {dup_count}"
                    )

                # Небольшая пауза между батчами
                if i + BATCH_SIZE < len(trading_pairs):
                    await asyncio.sleep(0.5)

            # Обновляем общую статистику
            self.stats['total_trades_found'] += cycle_trades_found
            self.stats['total_trades_saved'] += cycle_trades_saved

            cycle_duration = time.time() - cycle_start

            logger.info(
                f"[{self.exchange_name.upper()}] ✅ Цикл #{self.stats['cycle_count']} завершен за {cycle_duration:.1f}с | "
                f"Найдено: {cycle_trades_found} | Сохранено: {cycle_trades_saved} | Дубли: {cycle_duplicates}"
            )

            return {
                'exchange': self.exchange_name,
                'cycle': self.stats['cycle_count'],
                'pairs_count': len(trading_pairs),
                'trades_found': cycle_trades_found,
                'trades_saved': cycle_trades_saved,
                'duplicates': cycle_duplicates,
                'duration': cycle_duration,
                'cache_efficiency': self._get_cache_stats(),
                'error': None
            }

        except Exception as e:
            return self._create_error_result(cycle_start, str(e))

    def _create_error_result(self, cycle_start: float, error_msg: str) -> Dict:
        """Создает результат с ошибкой."""
        cycle_duration = time.time() - cycle_start
        logger.error(f"[{self.exchange_name.upper()}] ❌ Ошибка в цикле #{self.stats['cycle_count']}: {error_msg}")

        return {
            'exchange': self.exchange_name,
            'cycle': self.stats['cycle_count'],
            'pairs_count': 0,
            'trades_found': 0,
            'trades_saved': 0,
            'duplicates': 0,
            'duration': cycle_duration,
            'cache_efficiency': self._get_cache_stats(),
            'error': error_msg
        }

    def _get_cache_stats(self) -> Dict:
        """Возвращает статистику кэша."""
        total_ops = self.stats['cache_hits'] + self.stats['cache_misses']
        hit_rate = (self.stats['cache_hits'] / total_ops * 100) if total_ops > 0 else 0

        return {
            'hit_rate': hit_rate,
            'memory_hits': self.stats['memory_cache_hits'],
            'db_hits': self.stats['db_cache_hits'],
            'api_updates': self.stats['api_updates'],
            'fallback_uses': self.stats['fallback_uses'],
            'total_operations': total_ops
        }

    async def run_forever(self):
        """Запускает непрерывный цикл обработки биржи."""
        self.is_running = True
        logger.info(
            f"[{self.exchange_name.upper()}] 🚀 Запуск оптимизированного мониторинга "
            f"(пауза {self.cycle_pause_minutes} мин, кэш {MEMORY_CACHE_TTL_MINUTES} мин, "
            f"API {API_UPDATE_INTERVAL_MINUTES} мин)"
        )

        # При первом запуске инициализируем кэш
        logger.info(f"[{self.exchange_name.upper()}] 🔧 Инициализация кэша торговых пар...")
        try:
            initial_pairs = await self.get_trading_pairs()
            if initial_pairs:
                logger.info(
                    f"[{self.exchange_name.upper()}] ✅ Инициализация завершена, "
                    f"найдено {len(initial_pairs)} пар, источник: {self._memory_cache['source']}"
                )
            else:
                logger.warning(f"[{self.exchange_name.upper()}] ⚠️  Не удалось инициализировать кэш")
        except Exception as e:
            logger.error(f"[{self.exchange_name.upper()}] ❌ Ошибка инициализации кэша: {e}")

        while self.is_running:
            try:
                # Выполняем цикл
                cycle_result = await self.run_cycle()

                # Логируем статистику кэша каждые несколько циклов
                if self.stats['cycle_count'] % 3 == 0:
                    cache_stats = self._get_cache_stats()
                    logger.info(
                        f"[{self.exchange_name.upper()}] 📊 Статистика кэша: "
                        f"эффективность {cache_stats['hit_rate']:.1f}%, "
                        f"memory:{cache_stats['memory_hits']}, db:{cache_stats['db_hits']}, "
                        f"API:{cache_stats['api_updates']}, fallback:{cache_stats['fallback_uses']}"
                    )

                # Пауза между циклами
                if self.is_running:
                    logger.info(f"[{self.exchange_name.upper()}] ⏸️  Пауза {self.cycle_pause_minutes} минут...")

                    # Обратный отсчет с проверкой остановки
                    for remaining in range(self.cycle_pause_minutes * 60, 0, -30):
                        if not self.is_running:
                            break
                        await asyncio.sleep(min(30, remaining))

            except asyncio.CancelledError:
                logger.info(f"[{self.exchange_name.upper()}] 🛑 Получена команда остановки")
                break
            except Exception as e:
                logger.error(f"[{self.exchange_name.upper()}] 💥 Критическая ошибка: {e}")
                logger.info(f"[{self.exchange_name.upper()}] 🔄 Повтор через 1 минуту...")
                await asyncio.sleep(60)

        self.is_running = False
        logger.info(f"[{self.exchange_name.upper()}] 🏁 Оптимизированный мониторинг остановлен")

    def stop(self):
        """Останавливает воркер."""
        self.is_running = False

    def force_cache_update(self):
        """Принудительно помечает кэш как устаревший для обновления в следующем цикле."""
        self._memory_cache['last_api_update'] = None
        self._memory_cache['pairs'] = None
        self._memory_cache['loaded_at'] = None
        logger.info(f"[{self.exchange_name.upper()}] 🔄 Кэш помечен для принудительного обновления")

    def get_stats(self) -> Dict:
        """
        Возвращает расширенную статистику воркера.

        Returns:
            Словарь со статистикой
        """
        cache_stats = self._get_cache_stats()

        return {
            'exchange': self.exchange_name,
            'cycle_count': self.stats['cycle_count'],
            'total_trades_found': self.stats['total_trades_found'],
            'total_trades_saved': self.stats['total_trades_saved'],
            'cache_efficiency': cache_stats['hit_rate'],
            'memory_cache_hits': cache_stats['memory_hits'],
            'db_cache_hits': cache_stats['db_hits'],
            'api_updates': cache_stats['api_updates'],
            'fallback_uses': cache_stats['fallback_uses'],
            'api_calls_total': self.stats['api_calls'],
            'db_queries_total': self.stats['db_queries'],
            'memory_cache_valid': self._is_memory_cache_valid(),
            'last_api_update': datetime.fromtimestamp(self._memory_cache['last_api_update']).isoformat() if
            self._memory_cache['last_api_update'] else None,
            'last_cache_load': datetime.fromtimestamp(self._memory_cache['loaded_at']).isoformat() if
            self._memory_cache['loaded_at'] else None,
            'cached_pairs_count': len(self._memory_cache['pairs']) if self._memory_cache['pairs'] else 0,
            'cache_source': self._memory_cache['source'],
            'is_running': self.is_running
        }