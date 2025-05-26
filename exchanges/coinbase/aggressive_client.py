"""
Агрессивный клиент для непрерывного мониторинга Coinbase.
"""

# ПОДАВЛЕНИЕ ПРЕДУПРЕЖДЕНИЙ MYSQL
import warnings

warnings.filterwarnings("ignore")
warnings.filterwarnings('ignore', message='.*Data truncated.*')

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


class CoinbaseContinuousMonitor:
    """Непрерывный монитор для Coinbase с агрессивным polling."""

    def __init__(self, session: ClientSession, db_manager):
        self.session = session
        self.db_manager = db_manager
        self.base_url = "https://api.coinbase.com/api/v3/brokerage"

        # Настройки для агрессивного мониторинга (10 RPS лимит)
        self.request_delay = 0.1  # 100ms между запросами (10 RPS)
        self.max_concurrent_pairs = 8  # Больше пар чем у Bybit
        self.batch_save_size = 25

        # Отслеживание состояния
        self.last_trade_times: Dict[str, int] = {}
        self.seen_trade_ids: Dict[str, Set[str]] = defaultdict(set)
        self.pending_trades: List[Trade] = []

        # Статистика
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'errors': 0,
            'trades_found': 0,
            'large_trades_found': 0,
            'small_trades_filtered': 0,
            'trades_saved': 0,
            'duplicates_filtered': 0
        }

        self.active_monitors: Dict[str, asyncio.Task] = {}
        self.stop_monitoring = False

    async def start_monitoring(self, pairs: List[TradingPairInfo]) -> None:
        """Запускает непрерывный мониторинг для списка пар."""
        # Выбираем топ пары для агрессивного мониторинга
        top_pairs = sorted(pairs, key=lambda x: x.volume_24h_usd, reverse=True)
        selected_pairs = top_pairs[:self.max_concurrent_pairs]

        logger.info(f"🚀 Запуск агрессивного мониторинга для {len(selected_pairs)} топ пар Coinbase")
        for pair in selected_pairs:
            logger.info(f"   📊 {pair.symbol}: ${pair.volume_24h_usd:,.0f} за 24h")

        # Запускаем мониторинг каждой пары в отдельной задаче
        monitor_tasks = []
        for pair_info in selected_pairs:
            task = asyncio.create_task(
                self._monitor_pair_continuously(pair_info),
                name=f"coinbase_monitor_{pair_info.symbol}"
            )
            self.active_monitors[pair_info.symbol] = task
            monitor_tasks.append(task)

        # Задачи сохранения и статистики
        save_task = asyncio.create_task(self._periodic_save(), name="coinbase_periodic_save")
        stats_task = asyncio.create_task(self._periodic_stats(), name="coinbase_periodic_stats")
        monitor_tasks.extend([save_task, stats_task])

        try:
            await asyncio.gather(*monitor_tasks)
        except asyncio.CancelledError:
            logger.info("Мониторинг Coinbase остановлен")
        finally:
            await self._save_pending_trades()

    async def _monitor_pair_continuously(self, pair_info: TradingPairInfo) -> None:
        """Непрерывный мониторинг одной пары с соблюдением rate limits."""
        symbol = pair_info.symbol
        consecutive_errors = 0
        last_request_time = 0

        # Конвертируем символ в формат Coinbase
        coinbase_symbol = self._convert_symbol_to_coinbase(symbol)

        logger.info(f"🔄 Начат непрерывный мониторинг {symbol} -> {coinbase_symbol} (Coinbase)")

        while not self.stop_monitoring:
            try:
                # Адаптивная задержка на основе ошибок
                current_delay = self.request_delay * (1 + consecutive_errors)

                # Соблюдаем минимальную задержку
                time_since_last = time.time() - last_request_time
                if time_since_last < current_delay:
                    await asyncio.sleep(current_delay - time_since_last)

                last_request_time = time.time()

                # Получаем сделки
                trades_data = await self._get_recent_trades(coinbase_symbol)
                self.stats['total_requests'] += 1

                if trades_data is None:
                    consecutive_errors += 1
                    self.stats['errors'] += 1

                    # Экспоненциальная задержка при ошибках
                    error_delay = min(10.0, 0.2 * (2 ** consecutive_errors))
                    logger.warning(f"❌ Ошибка для {symbol} (Coinbase), пауза {error_delay:.1f}с")
                    await asyncio.sleep(error_delay)
                    continue

                consecutive_errors = 0
                self.stats['successful_requests'] += 1

                # Обрабатываем полученные сделки
                new_trades = await self._process_trades_data(trades_data, pair_info)

                if new_trades:
                    # Фильтрация крупных сделок
                    large_trades = [
                        trade for trade in new_trades
                        if trade.value_usd >= Decimal(str(MIN_TRADE_VALUE_USD))
                    ]

                    self.stats['trades_found'] += len(new_trades)
                    self.stats['large_trades_found'] += len(large_trades)
                    self.stats['small_trades_filtered'] += len(new_trades) - len(large_trades)

                    if large_trades:
                        self.pending_trades.extend(large_trades)

                        # Логируем крупные сделки
                        for trade in large_trades:
                            logger.info(
                                f"💰 {symbol} [COINBASE]: ${trade.value_usd:,.0f} в {trade.trade_datetime.strftime('%H:%M:%S')}")

            except asyncio.CancelledError:
                logger.info(f"Мониторинг {symbol} (Coinbase) отменен")
                break
            except Exception as e:
                consecutive_errors += 1
                self.stats['errors'] += 1
                logger.error(f"Неожиданная ошибка для {symbol} (Coinbase): {e}")
                await asyncio.sleep(2.0)

    async def _get_recent_trades(self, coinbase_symbol: str) -> Optional[List[Dict]]:
        """Получает последние сделки для пары через Coinbase API."""
        try:
            url = f"{self.base_url}/products/{coinbase_symbol}/trades"
            params = {
                'limit': 100  # Coinbase позволяет до 100 сделок
            }

            # Публичный endpoint, аутентификация не требуется
            async with self.session.get(url, params=params) as response:
                if response.status == 429:
                    # Rate limit
                    return None

                if response.status != 200:
                    return None

                data = await response.json()

                # Coinbase возвращает массив trades напрямую или в поле trades
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and 'trades' in data:
                    return data['trades']
                else:
                    return None

        except Exception as e:
            logger.debug(f"Ошибка запроса для {coinbase_symbol} (Coinbase): {e}")
            return None

    def _convert_symbol_to_coinbase(self, symbol: str) -> str:
        """
        Конвертирует символ из формата Binance/Bybit в формат Coinbase.
        Например: BTCUSDT -> BTC-USD, ETHUSDT -> ETH-USD
        """
        # Основные паттерны конверсии
        conversions = {
            'USDT': 'USD',
            'USDC': 'USD'  # В некоторых случаях
        }

        # Попробуем найти известные quote currencies
        for old_quote, new_quote in conversions.items():
            if symbol.endswith(old_quote):
                base = symbol[:-len(old_quote)]
                return f"{base}-{new_quote}"

        # Если не нашли, пробуем стандартные паттерны
        if len(symbol) == 6:  # Например BTCUSD
            return f"{symbol[:3]}-{symbol[3:]}"
        elif len(symbol) == 7:  # Например ETHUSD
            return f"{symbol[:4]}-{symbol[4:]}"

        # По умолчанию возвращаем как есть
        return symbol

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
                trade_id = str(trade_data.get('trade_id', trade_data.get('id', '')))

                # Парсим время
                time_str = trade_data.get('time', '')
                if time_str:
                    # Coinbase использует ISO 8601 формат
                    trade_time = int(datetime.fromisoformat(time_str.replace('Z', '+00:00')).timestamp() * 1000)
                else:
                    continue

                # Фильтруем по времени и ID
                if (trade_time > last_known_time and
                        trade_id not in self.seen_trade_ids[symbol]):

                    # Создаем объект Trade
                    trade = Trade.from_coinbase_response(
                        trade_data,
                        pair_info.symbol,
                        pair_info.base_asset,
                        pair_info.quote_asset,
                        pair_info.quote_price_usd
                    )

                    new_trades.append(trade)
                    self.seen_trade_ids[symbol].add(trade_id)
                    max_trade_time = max(max_trade_time, trade_time)
                else:
                    self.stats['duplicates_filtered'] += 1

            except Exception as e:
                logger.error(f"Ошибка обработки сделки {symbol} (Coinbase): {e}")
                continue

        # Обновляем время последней сделки
        if max_trade_time > last_known_time:
            self.last_trade_times[symbol] = max_trade_time

        # Ограничиваем размер множества ID
        if len(self.seen_trade_ids[symbol]) > 15000:
            sorted_ids = sorted(self.seen_trade_ids[symbol])
            self.seen_trade_ids[symbol] = set(sorted_ids[-7500:])

        return new_trades

    async def _periodic_save(self) -> None:
        """Периодически сохраняет накопленные сделки."""
        while not self.stop_monitoring:
            try:
                await asyncio.sleep(3.0)  # Сохраняем каждые 3 секунды
                await self._save_pending_trades()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка периодического сохранения (Coinbase): {e}")

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
                    logger.info(f"💾 Coinbase: сохранено {new_count} новых сделок, пропущено {dup_count} дубликатов")

        except Exception as e:
            logger.error(f"Ошибка сохранения сделок Coinbase: {e}")
            # Возвращаем сделки обратно в буфер при ошибке
            self.pending_trades.extend(trades_to_save)

    async def _periodic_stats(self) -> None:
        """Периодически выводит статистику."""
        start_time = time.time()

        while not self.stop_monitoring:
            try:
                await asyncio.sleep(45.0)  # Статистика каждые 45 секунд

                runtime = time.time() - start_time
                rps = self.stats['total_requests'] / runtime if runtime > 0 else 0
                success_rate = (self.stats['successful_requests'] / self.stats['total_requests'] * 100
                                if self.stats['total_requests'] > 0 else 0)

                logger.info(f"📊 Coinbase статистика за {runtime:.0f}с:")
                logger.info(f"   Запросов: {self.stats['total_requests']} ({rps:.1f} RPS)")
                logger.info(f"   Успешных: {success_rate:.1f}%")
                logger.info(f"   Сделок найдено: {self.stats['trades_found']}")
                logger.info(f"   Крупных сделок: {self.stats['large_trades_found']} (${MIN_TRADE_VALUE_USD}+)")
                logger.info(f"   Мелких отфильтровано: {self.stats['small_trades_filtered']}")
                logger.info(f"   Сделок сохранено: {self.stats['trades_saved']}")
                logger.info(f"   Дубликатов отфильтровано: {self.stats['duplicates_filtered']}")
                logger.info(f"   Активных мониторов: {len([t for t in self.active_monitors.values() if not t.done()])}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ошибка вывода статистики (Coinbase): {e}")

    async def stop(self) -> None:
        """Останавливает мониторинг."""
        logger.info("🛑 Остановка непрерывного мониторинга Coinbase...")
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

        logger.info("✅ Мониторинг Coinbase остановлен")

    def get_stats(self) -> Dict:
        """Возвращает статистику мониторинга."""
        return self.stats.copy()


class CoinbaseAggressiveClient:
    """Агрессивный клиент Coinbase для максимального покрытия сделок."""

    def __init__(self, session: ClientSession, rate_limiter):
        self.session = session
        self.rate_limiter = rate_limiter  # Игнорируем для агрессивного режима
        self.base_url = "https://api.coinbase.com/api/v3/brokerage"
        self.exchange_name = 'coinbase'
        self.monitor: Optional[CoinbaseContinuousMonitor] = None

    async def start_aggressive_monitoring(self, pairs: List[TradingPairInfo], db_manager) -> None:
        """Запускает агрессивный мониторинг."""
        if self.monitor:
            await self.monitor.stop()

        self.monitor = CoinbaseContinuousMonitor(self.session, db_manager)
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

    # Стандартные методы для совместимости
    async def test_connection(self) -> bool:
        """Проверяет соединение."""
        try:
            url = f"{self.base_url}/products"
            async with self.session.get(url) as response:
                return response.status == 200
        except:
            return False

    async def get_products(self) -> Dict:
        """Получает информацию о продуктах."""
        url = f"{self.base_url}/products"

        async with self.session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    async def get_24hr_stats(self) -> List[Dict]:
        """Получает 24hr статистику (эмуляция)."""
        # Coinbase Advanced Trade не имеет единого endpoint для всех пар
        # Возвращаем пустой список, статистику будем получать из products
        return []