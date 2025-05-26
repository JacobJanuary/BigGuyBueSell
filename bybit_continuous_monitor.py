"""
Непрерывный мониторинг Bybit с минимальными задержками.
Специально разработан для получения всех сделок без пропусков.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Set, Optional
from decimal import Decimal
from collections import defaultdict
import time

from aiohttp import ClientSession
from database.models import Trade, TradingPairInfo
from config.settings import MIN_TRADE_VALUE_USD

logger = logging.getLogger(__name__)


class BybitContinuousMonitor:
    """Непрерывный монитор для Bybit с агрессивным polling."""

    def __init__(self, session: ClientSession, db_manager):
        self.session = session
        self.db_manager = db_manager
        self.base_url = "https://api.bybit.com"

        # Настройки для агрессивного мониторинга
        self.request_delay = 0.05  # 50ms между запросами (очень агрессивно)
        self.max_concurrent_pairs = 5  # Ограничиваем количество одновременно мониторимых пар
        self.batch_save_size = 20  # Сохраняем батчами для производительности

        # Отслеживание состояния
        self.last_trade_times: Dict[str, int] = {}  # symbol -> last_trade_timestamp
        self.seen_trade_ids: Dict[str, Set[str]] = defaultdict(set)  # symbol -> set of execIds
        self.pending_trades: List[Trade] = []  # Буфер для батчевого сохранения

        # Статистика
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'errors': 0,
            'trades_found': 0,
            'trades_saved': 0,
            'duplicates_filtered': 0
        }

        # Контроль активных задач для каждой пары
        self.active_monitors: Dict[str, asyncio.Task] = {}
        self.stop_monitoring = False

    async def start_monitoring(self, pairs: List[TradingPairInfo]) -> None:
        """Запускает непрерывный мониторинг для списка пар."""
        # Ограничиваем количество пар для агрессивного мониторинга
        top_pairs = sorted(pairs, key=lambda x: x.volume_24h_usd, reverse=True)
        selected_pairs = top_pairs[:self.max_concurrent_pairs]

        logger.info(f"🚀 Запуск агрессивного мониторинга для {len(selected_pairs)} топ пар Bybit")
        for pair in selected_pairs:
            logger.info(f"   📊 {pair.symbol}: ${pair.volume_24h_usd:,.0f} за 24h")

        # Запускаем мониторинг каждой пары в отдельной задаче
        monitor_tasks = []
        for pair_info in selected_pairs:
            task = asyncio.create_task(
                self._monitor_pair_continuously(pair_info),
                name=f"monitor_{pair_info.symbol}"
            )
            self.active_monitors[pair_info.symbol] = task
            monitor_tasks.append(task)

        # Запускаем задачу периодического сохранения
        save_task = asyncio.create_task(self._periodic_save(), name="periodic_save")
        monitor_tasks.append(save_task)

        # Запускаем задачу статистики
        stats_task = asyncio.create_task(self._periodic_stats(), name="periodic_stats")
        monitor_tasks.append(stats_task)

        try:
            await asyncio.gather(*monitor_tasks)
        except asyncio.CancelledError:
            logger.info("Мониторинг Bybit остановлен")
        finally:
            # Сохраняем оставшиеся сделки
            await self._save_pending_trades()

    async def _monitor_pair_continuously(self, pair_info: TradingPairInfo) -> None:
        """Непрерывный мониторинг одной пары с минимальными задержками."""
        symbol = pair_info.symbol
        consecutive_errors = 0
        last_request_time = 0

        logger.info(f"🔄 Начат непрерывный мониторинг {symbol}")

        while not self.stop_monitoring:
            try:
                # Адаптивная задержка на основе предыдущих ошибок
                current_delay = self.request_delay * (1 + consecutive_errors)

                # Убеждаемся что прошло минимальное время с последнего запроса
                time_since_last = time.time() - last_request_time
                if time_since_last < current_delay:
                    await asyncio.sleep(current_delay - time_since_last)

                last_request_time = time.time()

                # Получаем сделки
                trades_data = await self._get_recent_trades(symbol)
                self.stats['total_requests'] += 1

                if trades_data is None:
                    consecutive_errors += 1
                    self.stats['errors'] += 1

                    # Экспоненциальная задержка при ошибках
                    error_delay = min(5.0, 0.1 * (2 ** consecutive_errors))
                    logger.warning(f"❌ Ошибка для {symbol}, пауза {error_delay:.1f}с")
                    await asyncio.sleep(error_delay)
                    continue

                consecutive_errors = 0
                self.stats['successful_requests'] += 1

                # Обрабатываем полученные сделки
                new_trades = await self._process_trades_data(trades_data, pair_info)

                if new_trades:
                    self.stats['trades_found'] += len(new_trades)
                    self.pending_trades.extend(new_trades)

                    # Логируем крупные сделки
                    large_trades = [t for t in new_trades if t.value_usd >= Decimal(str(MIN_TRADE_VALUE_USD))]
                    for trade in large_trades:
                        logger.info(
                            f"💰 {symbol}: ${trade.value_usd:,.0f} в {trade.trade_datetime.strftime('%H:%M:%S')}")

            except asyncio.CancelledError:
                logger.info(f"Мониторинг {symbol} отменен")
                break
            except Exception as e:
                consecutive_errors += 1
                self.stats['errors'] += 1
                logger.error(f"Неожиданная ошибка для {symbol}: {e}")
                await asyncio.sleep(1.0)

    async def _get_recent_trades(self, symbol: str) -> Optional[List[Dict]]:
        """Получает последние сделки для пары с минимальной обработкой."""
        try:
            url = f"{self.base_url}/v5/market/recent-trade"
            params = {
                'category': 'spot',
                'symbol': symbol,
                'limit': 60  # Максимум для Bybit
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 429 or response.status == 403:
                    # Rate limit - возвращаем None для обработки
                    return None

                if response.status != 200:
                    return None

                data = await response.json()

                if data.get('retCode') == 0:
                    return data['result']['list']
                else:
                    return None

        except Exception as e:
            logger.debug(f"Ошибка запроса для {symbol}: {e}")
            return None

    async def _process_trades_data(self, trades_data: List[Dict], pair_info: TradingPairInfo) -> List[Trade]:
        """Обрабатывает данные сделок и фильтрует дубликаты."""
        if not trades_data:
            return []

        symbol = pair_info.symbol
        new_trades = []

        # Получаем время последней известной сделки
        last_known_time = self.last_trade_times.get(symbol, 0)
        max_trade_time = last_known_time

        for trade_data in trades_data:
            try:
                exec_id = trade_data['execId']
                trade_time = int(trade_data['time'])

                # Фильтруем по времени и ID
                if (trade_time > last_known_time and
                        exec_id not in self.seen_trade_ids[symbol]):

                    # Создаем объект Trade
                    trade = Trade.from_bybit_response(
                        trade_data,
                        pair_info.symbol,
                        pair_info.base_asset,
                        pair_info.quote_asset,
                        pair_info.quote_price_usd
                    )

                    new_trades.append(trade)
                    self.seen_trade_ids[symbol].add(exec_id)
                    max_trade_time = max(max_trade_time, trade_time)
                else:
                    self.stats['duplicates_filtered'] += 1

            except Exception as e:
                logger.error(f"Ошибка обработки сделки {symbol}: {e}")
                continue

        # Обновляем время последней сделки
        if max_trade_time > last_known_time:
            self.last_trade_times[symbol] = max_trade_time

        # Ограничиваем размер множества ID (память)
        if len(self.seen_trade_ids[symbol]) > 10000:
            # Оставляем только половину самых новых ID
            sorted_ids = sorted(self.seen_trade_ids[symbol])
            self.seen_trade_ids[symbol] = set(sorted_ids[-5000:])

        return new_trades

    async def _periodic_save(self) -> None:
        """Периодически сохраняет накопленные сделки."""
        while not self.stop_monitoring:
            try:
                await asyncio.sleep(2.0)  # Сохраняем каждые 2 секунды
                await self._save_pending_trades()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка периодического сохранения: {e}")

    async def _save_pending_trades(self) -> None:
        """Сохраняет накопленные сделки в БД."""
        if not self.pending_trades:
            return

        try:
            trades_to_save = self.pending_trades.copy()
            self.pending_trades.clear()

            if trades_to_save:
                new_count, dup_count = await self.db_manager.save_trades(trades_to_save)
                self.stats['trades_saved'] += new_count

                if new_count > 0:
                    logger.info(f"💾 Bybit: сохранено {new_count} новых сделок, пропущено {dup_count} дубликатов")

        except Exception as e:
            logger.error(f"Ошибка сохранения сделок Bybit: {e}")
            # Возвращаем сделки обратно в буфер при ошибке
            self.pending_trades.extend(trades_to_save)

    async def _periodic_stats(self) -> None:
        """Периодически выводит статистику."""
        start_time = time.time()

        while not self.stop_monitoring:
            try:
                await asyncio.sleep(30.0)  # Статистика каждые 30 секунд

                runtime = time.time() - start_time
                rps = self.stats['total_requests'] / runtime if runtime > 0 else 0
                success_rate = (self.stats['successful_requests'] / self.stats['total_requests'] * 100
                                if self.stats['total_requests'] > 0 else 0)

                logger.info(f"📊 Bybit статистика за {runtime:.0f}с:")
                logger.info(f"   Запросов: {self.stats['total_requests']} ({rps:.1f} RPS)")
                logger.info(f"   Успешных: {success_rate:.1f}%")
                logger.info(f"   Сделок найдено: {self.stats['trades_found']}")
                logger.info(f"   Сделок сохранено: {self.stats['trades_saved']}")
                logger.info(f"   Дубликатов отфильтровано: {self.stats['duplicates_filtered']}")
                logger.info(f"   Активных мониторов: {len([t for t in self.active_monitors.values() if not t.done()])}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка вывода статистики: {e}")

    async def stop(self) -> None:
        """Останавливает мониторинг."""
        logger.info("🛑 Остановка непрерывного мониторинга Bybit...")
        self.stop_monitoring = True

        # Отменяем все активные задачи
        for task in self.active_monitors.values():
            if not task.done():
                task.cancel()

        # Ждем завершения задач
        if self.active_monitors:
            await asyncio.gather(*self.active_monitors.values(), return_exceptions=True)

        # Финальное сохранение
        await self._save_pending_trades()

        logger.info("✅ Мониторинг Bybit остановлен")

    def get_stats(self) -> Dict:
        """Возвращает статистику мониторинга."""
        return self.stats.copy()


class BybitAggressiveClient:
    """Агрессивный клиент Bybit для максимального покрытия сделок."""

    def __init__(self, session: ClientSession, rate_limiter):
        self.session = session
        self.rate_limiter = rate_limiter  # Игнорируем для агрессивного режима
        self.base_url = "https://api.bybit.com"
        self.exchange_name = 'bybit'
        self.monitor: Optional[BybitContinuousMonitor] = None

    async def start_aggressive_monitoring(self, pairs: List[TradingPairInfo], db_manager) -> None:
        """Запускает агрессивный мониторинг."""
        if self.monitor:
            await self.monitor.stop()

        self.monitor = BybitContinuousMonitor(self.session, db_manager)
        await self.monitor.start_monitoring(pairs)

    async def stop_monitoring(self) -> None:
        """Останавливает мониторинг."""
        if self.monitor:
            await self.monitor.stop()
            self.monitor = None

    async def get_monitoring_stats(self) -> Dict:
        """Получает статистику мониторинга."""
        if self.monitor:
            return self.monitor.get_stats()
        return {}

    # Стандартные методы для совместимости с базовой архитектурой
    async def test_connection(self) -> bool:
        """Проверяет соединение."""
        try:
            url = f"{self.base_url}/v5/market/time"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('retCode') == 0
                return False
        except:
            return False

    async def get_instruments_info(self) -> Dict:
        """Получает информацию об инструментах."""
        url = f"{self.base_url}/v5/market/instruments-info"
        params = {'category': 'spot'}

        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            if data.get('retCode') != 0:
                raise Exception(f"Bybit API error: {data.get('retMsg', 'Unknown error')}")

            return data

    async def get_24hr_tickers(self) -> List[Dict]:
        """Получает 24hr тикеры."""
        url = f"{self.base_url}/v5/market/tickers"
        params = {'category': 'spot'}

        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            if data.get('retCode') != 0:
                raise Exception(f"Bybit API error: {data.get('retMsg', 'Unknown error')}")

            return data['result']['list']