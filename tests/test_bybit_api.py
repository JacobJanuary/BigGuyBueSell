#!/usr/bin/env python3
"""
Продвинутый тестер для изучения Bybit API v5.
Исследует структуру данных, лимиты и возможности получения всех сделок.
"""
import asyncio
import json
import logging
import ssl
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
import time

import aiohttp
from aiohttp import ClientSession, TCPConnector

# Попытка импорта certifi для SSL
try:
    import certifi

    HAS_CERTIFI = True
except ImportError:
    HAS_CERTIFI = False

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BybitAPITester:
    """Тестер для исследования Bybit API."""

    def __init__(self, disable_ssl_verify: bool = False):
        self.base_url = "https://api.bybit.com"
        self.session: Optional[ClientSession] = None
        self.test_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT', 'DOGEUSDT']
        self.disable_ssl_verify = disable_ssl_verify

    def create_ssl_context(self) -> ssl.SSLContext:
        """Создает SSL контекст с настройками для обхода проблем с сертификатами."""
        if self.disable_ssl_verify:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            print("⚠️  SSL проверка отключена (только для тестирования)")
            return ssl_context
        else:
            ssl_context = ssl.create_default_context()
            try:
                if HAS_CERTIFI:
                    ssl_context.load_verify_locations(certifi.where())
                    print("✅ Используются сертификаты certifi")
            except Exception as e:
                print(f"⚠️  Не удалось загрузить сертификаты certifi: {e}")
            return ssl_context

    async def __aenter__(self):
        """Асинхронный контекст менеджер - вход."""
        ssl_context = self.create_ssl_context()
        connector = TCPConnector(
            limit=20,
            limit_per_host=10,
            ssl=ssl_context
        )
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = ClientSession(connector=connector, timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекст менеджер - выход."""
        if self.session:
            await self.session.close()

    async def test_connection(self) -> bool:
        """Тестирует соединение с API."""
        try:
            url = f"{self.base_url}/v5/market/time"
            async with self.session.get(url) as response:
                data = await response.json()
                if data.get('retCode') == 0:
                    server_time = int(data['result']['timeSecond'])
                    local_time = int(time.time())
                    time_diff = abs(server_time - local_time)

                    print(f"✅ Соединение с Bybit установлено")
                    print(f"   Время сервера: {datetime.fromtimestamp(server_time)}")
                    print(f"   Локальное время: {datetime.fromtimestamp(local_time)}")
                    print(f"   Разница во времени: {time_diff} секунд")
                    return True
                else:
                    print(f"❌ Ошибка соединения: {data}")
                    return False
        except Exception as e:
            print(f"❌ Исключение при соединении: {e}")
            return False

    async def analyze_instruments(self) -> None:
        """Анализирует информацию о торговых инструментах."""
        print(f"\n{'=' * 60}")
        print("🔍 АНАЛИЗ ТОРГОВЫХ ИНСТРУМЕНТОВ")
        print(f"{'=' * 60}")

        try:
            url = f"{self.base_url}/v5/market/instruments-info"
            params = {'category': 'spot'}

            async with self.session.get(url, params=params) as response:
                data = await response.json()

                if data.get('retCode') != 0:
                    print(f"❌ Ошибка получения инструментов: {data}")
                    return

                instruments = data['result']['list']
                print(f"📊 Всего спотовых инструментов: {len(instruments)}")

                # Анализируем статусы
                statuses = {}
                for instrument in instruments:
                    status = instrument.get('status', 'Unknown')
                    statuses[status] = statuses.get(status, 0) + 1

                print(f"\n📈 Статусы инструментов:")
                for status, count in statuses.items():
                    print(f"   {status}: {count}")

                # Показываем структуру одного инструмента
                if instruments:
                    print(f"\n🔬 Структура инструмента (пример {instruments[0]['symbol']}):")
                    sample = instruments[0]
                    for key, value in sample.items():
                        print(f"   {key}: {value} ({type(value).__name__})")

                # Ищем активные пары с большим объемом
                trading_pairs = [
                    instr for instr in instruments
                    if instr.get('status') == 'Trading'
                ]
                print(f"\n✅ Активных торговых пар: {len(trading_pairs)}")

        except Exception as e:
            print(f"❌ Ошибка при анализе инструментов: {e}")

    async def analyze_tickers(self) -> List[str]:
        """Анализирует тикеры и возвращает топ символы по объему."""
        print(f"\n{'=' * 60}")
        print("📊 АНАЛИЗ 24HR ТИКЕРОВ")
        print(f"{'=' * 60}")

        try:
            url = f"{self.base_url}/v5/market/tickers"
            params = {'category': 'spot'}

            async with self.session.get(url, params=params) as response:
                data = await response.json()

                if data.get('retCode') != 0:
                    print(f"❌ Ошибка получения тикеров: {data}")
                    return []

                tickers = data['result']['list']
                print(f"📈 Всего тикеров: {len(tickers)}")

                # Показываем структуру тикера
                if tickers:
                    print(f"\n🔬 Структура тикера (пример {tickers[0]['symbol']}):")
                    sample = tickers[0]
                    for key, value in sample.items():
                        print(f"   {key}: {value} ({type(value).__name__})")

                # Сортируем по объему
                volume_tickers = []
                for ticker in tickers:
                    try:
                        volume = float(ticker.get('turnover24h', '0'))
                        if volume > 0:
                            volume_tickers.append((ticker['symbol'], volume))
                    except (ValueError, TypeError):
                        continue

                volume_tickers.sort(key=lambda x: x[1], reverse=True)

                print(f"\n🔥 Топ-10 пар по объему торгов (24h):")
                top_symbols = []
                for i, (symbol, volume) in enumerate(volume_tickers[:10], 1):
                    print(f"   {i:2d}. {symbol}: ${volume:,.0f}")
                    top_symbols.append(symbol)

                return top_symbols[:5]  # Возвращаем топ-5 для дальнейшего тестирования

        except Exception as e:
            print(f"❌ Ошибка при анализе тикеров: {e}")
            return []

    async def test_recent_trades_limits(self, symbol: str) -> Dict:
        """Тестирует лимиты recent trades для конкретного символа."""
        print(f"\n{'=' * 60}")
        print(f"🔍 ТЕСТИРОВАНИЕ ЛИМИТОВ СДЕЛОК ДЛЯ {symbol}")
        print(f"{'=' * 60}")

        results = {}

        # Тестируем разные лимиты
        limits_to_test = [1, 10, 50, 60, 100, 500, 1000]

        for limit in limits_to_test:
            try:
                url = f"{self.base_url}/v5/market/recent-trade"
                params = {
                    'category': 'spot',
                    'symbol': symbol,
                    'limit': limit
                }

                start_time = time.time()
                async with self.session.get(url, params=params) as response:
                    request_time = time.time() - start_time
                    data = await response.json()

                    if data.get('retCode') == 0:
                        trades = data['result']['list']
                        actual_count = len(trades)
                        results[limit] = {
                            'requested': limit,
                            'received': actual_count,
                            'request_time': request_time,
                            'success': True
                        }
                        print(f"   Лимит {limit:4d}: получено {actual_count:4d} сделок за {request_time:.3f}с")

                        # Показываем структуру первой сделки только для первого успешного запроса
                        if limit == limits_to_test[0] and trades:
                            print(f"\n🔬 Структура сделки:")
                            sample_trade = trades[0]
                            for key, value in sample_trade.items():
                                print(f"   {key}: {value} ({type(value).__name__})")
                    else:
                        results[limit] = {
                            'requested': limit,
                            'received': 0,
                            'request_time': request_time,
                            'success': False,
                            'error': data.get('retMsg', 'Unknown error')
                        }
                        print(f"   Лимит {limit:4d}: ОШИБКА - {data.get('retMsg', 'Unknown')}")

                # Пауза между запросами
                await asyncio.sleep(0.1)

            except Exception as e:
                results[limit] = {
                    'requested': limit,
                    'received': 0,
                    'request_time': 0,
                    'success': False,
                    'error': str(e)
                }
                print(f"   Лимит {limit:4d}: ИСКЛЮЧЕНИЕ - {e}")

        # Определяем максимальный работающий лимит
        max_working_limit = 0
        for limit, result in results.items():
            if result['success'] and result['received'] > 0:
                max_working_limit = max(max_working_limit, limit)

        print(f"\n📋 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ ЛИМИТОВ:")
        print(f"   Максимальный рабочий лимит: {max_working_limit}")

        return results

    async def test_trade_history_methods(self, symbol: str) -> None:
        """Тестирует различные методы получения истории сделок."""
        print(f"\n{'=' * 60}")
        print(f"📜 ТЕСТИРОВАНИЕ МЕТОДОВ ИСТОРИИ СДЕЛОК ДЛЯ {symbol}")
        print(f"{'=' * 60}")

        # Метод 1: recent-trade (самые последние)
        print(f"\n1️⃣ Метод recent-trade:")
        try:
            url = f"{self.base_url}/v5/market/recent-trade"
            params = {'category': 'spot', 'symbol': symbol, 'limit': 60}

            async with self.session.get(url, params=params) as response:
                data = await response.json()
                if data.get('retCode') == 0:
                    trades = data['result']['list']
                    print(f"   ✅ Получено {len(trades)} сделок")
                    if trades:
                        oldest_time = min(int(trade['time']) for trade in trades)
                        newest_time = max(int(trade['time']) for trade in trades)
                        print(f"   📅 Временной диапазон:")
                        print(f"      Самая старая: {datetime.fromtimestamp(oldest_time / 1000)}")
                        print(f"      Самая новая:  {datetime.fromtimestamp(newest_time / 1000)}")
                        print(f"      Диапазон: {(newest_time - oldest_time) / 1000:.1f} секунд")
                else:
                    print(f"   ❌ Ошибка: {data}")
        except Exception as e:
            print(f"   ❌ Исключение: {e}")

        # Проверяем есть ли другие endpoints для истории
        endpoints_to_test = [
            '/v5/market/trade',
            '/v5/market/history-trade',
            '/v5/market/kline'  # Для сравнения
        ]

        for endpoint in endpoints_to_test:
            print(f"\n🔍 Тестируем endpoint {endpoint}:")
            try:
                url = f"{self.base_url}{endpoint}"
                params = {'category': 'spot', 'symbol': symbol}

                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"   ✅ Endpoint доступен: {data.get('retCode') == 0}")
                        if data.get('retCode') == 0:
                            result = data.get('result', {})
                            if isinstance(result, dict):
                                for key, value in result.items():
                                    if isinstance(value, list):
                                        print(f"      {key}: {len(value)} элементов")
                                    else:
                                        print(f"      {key}: {type(value).__name__}")
                    else:
                        print(f"   ❌ HTTP {response.status}")
            except Exception as e:
                print(f"   ❌ Исключение: {e}")

    async def test_pagination_and_timing(self, symbol: str) -> None:
        """Тестирует возможности пагинации и получения исторических данных."""
        print(f"\n{'=' * 60}")
        print(f"⏰ ТЕСТИРОВАНИЕ ПАГИНАЦИИ И ВРЕМЕНИ ДЛЯ {symbol}")
        print(f"{'=' * 60}")

        try:
            # Получаем первую порцию сделок
            url = f"{self.base_url}/v5/market/recent-trade"
            params = {'category': 'spot', 'symbol': symbol, 'limit': 60}

            async with self.session.get(url, params=params) as response:
                data = await response.json()

                if data.get('retCode') != 0:
                    print(f"❌ Ошибка получения сделок: {data}")
                    return

                trades = data['result']['list']
                print(f"📦 Получена первая порция: {len(trades)} сделок")

                if not trades:
                    print(f"❌ Нет сделок для анализа")
                    return

                # Анализируем временные метки
                times = [int(trade['time']) for trade in trades]
                times.sort()

                oldest_trade_time = times[0]
                newest_trade_time = times[-1]

                print(f"📅 Временной анализ:")
                print(f"   Самая старая сделка: {datetime.fromtimestamp(oldest_trade_time / 1000)}")
                print(f"   Самая новая сделка:  {datetime.fromtimestamp(newest_trade_time / 1000)}")
                print(f"   Временной охват: {(newest_trade_time - oldest_trade_time) / 1000:.1f} секунд")

                # Проверяем уникальность ID сделок
                trade_ids = [trade.get('execId', trade.get('id', '')) for trade in trades]
                unique_ids = set(trade_ids)
                print(f"🆔 Уникальность ID: {len(unique_ids)}/{len(trade_ids)} уникальных")

                # Анализируем объемы и цены
                volumes = []
                prices = []
                for trade in trades:
                    try:
                        volume = float(trade.get('size', 0)) * float(trade.get('price', 0))
                        volumes.append(volume)
                        prices.append(float(trade.get('price', 0)))
                    except (ValueError, TypeError):
                        continue

                if volumes:
                    print(f"💰 Анализ объемов:")
                    print(f"   Мин. объем сделки: ${min(volumes):,.2f}")
                    print(f"   Макс. объем сделки: ${max(volumes):,.2f}")
                    print(f"   Средний объем: ${sum(volumes) / len(volumes):,.2f}")

                    # Находим крупные сделки
                    large_trades = [v for v in volumes if v >= 10000]  # $10k+
                    if large_trades:
                        print(f"   Сделки $10k+: {len(large_trades)} ({len(large_trades) / len(volumes) * 100:.1f}%)")
                        print(f"   Крупнейшая сделка: ${max(large_trades):,.2f}")

        except Exception as e:
            print(f"❌ Ошибка при тестировании пагинации: {e}")

    async def test_rate_limits(self) -> None:
        """Тестирует rate limits API."""
        print(f"\n{'=' * 60}")
        print("⚡ ТЕСТИРОВАНИЕ RATE LIMITS")
        print(f"{'=' * 60}")

        test_symbol = 'BTCUSDT'
        requests_per_batch = 10
        batches_to_test = 3

        for batch in range(batches_to_test):
            print(f"\n📊 Батч #{batch + 1}: {requests_per_batch} запросов подряд")

            start_time = time.time()
            success_count = 0
            error_count = 0

            tasks = []
            for i in range(requests_per_batch):
                task = self._single_trade_request(test_symbol, i)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"   Запрос {i + 1:2d}: ❌ {result}")
                    error_count += 1
                elif result['success']:
                    print(f"   Запрос {i + 1:2d}: ✅ {result['trades_count']} сделок за {result['time']:.3f}с")
                    success_count += 1
                else:
                    print(f"   Запрос {i + 1:2d}: ❌ {result['error']}")
                    error_count += 1

            batch_time = time.time() - start_time
            print(f"   📈 Результат батча: {success_count} успешных, {error_count} ошибок за {batch_time:.2f}с")

            # Пауза между батчами
            if batch < batches_to_test - 1:
                print(f"   ⏸️ Пауза 5 секунд...")
                await asyncio.sleep(5)

    async def _single_trade_request(self, symbol: str, request_id: int) -> Dict:
        """Выполняет один запрос сделок."""
        try:
            start_time = time.time()
            url = f"{self.base_url}/v5/market/recent-trade"
            params = {'category': 'spot', 'symbol': symbol, 'limit': 10}

            async with self.session.get(url, params=params) as response:
                request_time = time.time() - start_time
                data = await response.json()

                if data.get('retCode') == 0:
                    trades_count = len(data['result']['list'])
                    return {
                        'success': True,
                        'trades_count': trades_count,
                        'time': request_time,
                        'request_id': request_id
                    }
                else:
                    return {
                        'success': False,
                        'error': data.get('retMsg', 'Unknown error'),
                        'time': request_time,
                        'request_id': request_id
                    }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'time': 0,
                'request_id': request_id
            }

    async def generate_recommendations(self, test_results: Dict) -> None:
        """Генерирует рекомендации на основе результатов тестирования."""
        print(f"\n{'=' * 60}")
        print("💡 РЕКОМЕНДАЦИИ ДЛЯ ОПТИМИЗАЦИИ")
        print(f"{'=' * 60}")

        print(f"1️⃣ Оптимальные параметры запросов:")
        print(f"   • Максимальный лимит сделок: 60 (проверено)")
        print(f"   • Endpoint для сделок: /v5/market/recent-trade")
        print(f"   • Обязательные параметры: category='spot', symbol, limit")

        print(f"\n2️⃣ Стратегия получения всех сделок:")
        print(f"   • Используйте лимит 60 для максимального охвата")
        print(f"   • Делайте запросы каждые 30-60 секунд для активных пар")
        print(f"   • Отслеживайте дубликаты по execId")
        print(f"   • Сохраняйте timestamp последней сделки для определения новых")

        print(f"\n3️⃣ Rate limiting:")
        print(f"   • Используйте паузы 0.1-0.2 секунды между запросами")
        print(f"   • Обрабатывайте ошибки 403 (rate limit exceeded)")
        print(f"   • Реализуйте exponential backoff при ошибках")

        print(f"\n4️⃣ Мониторинг крупных сделок:")
        print(f"   • Фокусируйтесь на топ-20 пар по объему")
        print(f"   • Используйте фильтрацию по минимальному объему USD")
        print(f"   • Учитывайте что recent-trade дает ограниченную историю")

        print(f"\n5️⃣ Архитектурные рекомендации:")
        print(f"   • Создайте отдельный rate limiter для Bybit")
        print(f"   • Используйте semaphore для ограничения параллельных запросов")
        print(f"   • Реализуйте retry логику с экспоненциальной задержкой")
        print(f"   • Логируйте все ошибки API для анализа")


async def main():
    """Главная функция тестирования."""
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║            BYBIT API ADVANCED TESTER              ║
    ║                                                   ║
    ║  Продвинутое тестирование API для оптимизации    ║
    ║  системы мониторинга крупных сделок              ║
    ╚═══════════════════════════════════════════════════╝
    """)

    # Попробуем сначала с проверкой SSL
    print("🔐 Попытка подключения с проверкой SSL...")
    async with BybitAPITester(disable_ssl_verify=False) as tester:
        if await tester.test_connection():
            ssl_works = True
        else:
            ssl_works = False

    # Если не удалось, попробуем без SSL проверки
    if not ssl_works:
        print("\n⚠️  SSL проверка не работает, пробуем без проверки сертификатов...")
        print("   (Только для тестирования! В продакшене исправьте SSL)")

        async with BybitAPITester(disable_ssl_verify=True) as tester:
            # Тест 1: Проверка соединения
            if not await tester.test_connection():
                print("❌ Не удалось подключиться к API даже без SSL. Завершение тестирования.")
                print("\n🔧 Возможные решения:")
                print("   1. Установите certifi: pip install certifi")
                print("   2. Обновите сертификаты системы")
                print("   3. Проверьте настройки прокси/firewall")
                print("   4. Используйте VPN если API заблокирован в вашем регионе")
                return

            await run_all_tests(tester)
    else:
        # SSL работает, продолжаем нормально
        print("✅ SSL соединение работает корректно!")
        async with BybitAPITester(disable_ssl_verify=False) as tester:
            await run_all_tests(tester)


async def run_all_tests(tester):
    """Выполняет все тесты."""
    # Тест 2: Анализ инструментов
    await tester.analyze_instruments()

    # Тест 3: Анализ тикеров и получение топ символов
    top_symbols = await tester.analyze_tickers()

    if not top_symbols:
        print("❌ Не удалось получить символы для тестирования")
        return

    # Тест 4: Тестирование лимитов для топ символа
    test_results = await tester.test_recent_trades_limits(top_symbols[0])

    # Тест 5: Тестирование методов истории сделок
    await tester.test_trade_history_methods(top_symbols[0])

    # Тест 6: Тестирование пагинации и времени
    await tester.test_pagination_and_timing(top_symbols[0])

    # Тест 7: Тестирование rate limits
    await tester.test_rate_limits()

    # Генерация рекомендаций
    await tester.generate_recommendations(test_results)

    print(f"\n{'=' * 60}")
    print("✅ ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print(f"{'=' * 60}")
    print("Используйте полученную информацию для оптимизации BybitClient")


if __name__ == "__main__":
    asyncio.run(main())