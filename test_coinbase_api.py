#!/usr/bin/env python3
"""
Продвинутый тестер для изучения Coinbase Advanced Trade API.
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


class CoinbaseAPITester:
    """Тестер для исследования Coinbase Advanced Trade API (публичные endpoints)."""

    def __init__(self, disable_ssl_verify: bool = False):
        # Попробуем разные базовые URL для публичных endpoints
        self.base_urls = [
            "https://api.coinbase.com/api/v3/brokerage/public",  # Публичные endpoints
            "https://api.coinbase.com/api/v3/brokerage",  # Основной путь
            "https://api.coinbase.com",  # Базовый домен
        ]
        self.session: Optional[ClientSession] = None
        self.disable_ssl_verify = disable_ssl_verify
        self.test_symbols = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'ADA-USD', 'DOGE-USD']
        self.working_base_url = None

    def create_ssl_context(self) -> ssl.SSLContext:
        """Создает SSL контекст."""
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
        """Тестирует соединение с API, пробуя разные базовые URL."""
        print("🔍 Поиск рабочих публичных endpoints...")

        # Разные пути для тестирования
        endpoints_to_try = [
            "/v2/exchange-rates",  # Простой публичный endpoint
            "/v2/currencies",  # Список валют
            "/v2/time",  # Время сервера
            "/products",  # Продукты (может не работать)
            "/api/v3/brokerage/public/products",
            "/api/v3/brokerage/products",
        ]

        for base_url in self.base_urls:
            print(f"\n📡 Тестируем базовый URL: {base_url}")
            found_working_endpoint = False

            for endpoint in endpoints_to_try:
                try:
                    url = f"{base_url}{endpoint}"
                    print(f"   Пробуем: {url}")

                    async with self.session.get(url) as response:
                        print(f"   Статус: {response.status}")

                        if response.status == 200:
                            data = await response.json()
                            print(f"   ✅ Успех! Получен ответ")

                            # Определяем тип данных
                            if isinstance(data, dict):
                                if 'data' in data:
                                    print(f"   Тип данных: словарь с полем 'data'")
                                    if isinstance(data['data'], dict):
                                        print(f"   Ключи в data: {list(data['data'].keys())[:5]}...")
                                    elif isinstance(data['data'], list):
                                        print(f"   Количество элементов в data: {len(data['data'])}")
                                elif 'products' in data:
                                    print(f"   Тип данных: словарь с полем 'products'")
                                    print(f"   Количество продуктов: {len(data['products'])}")
                                else:
                                    print(f"   Тип данных: словарь с ключами {list(data.keys())}")
                            elif isinstance(data, list):
                                print(f"   Тип данных: массив из {len(data)} элементов")

                            if not found_working_endpoint:
                                self.working_base_url = base_url
                                self.working_endpoint = endpoint
                                found_working_endpoint = True

                            # Сохраняем все рабочие endpoints
                            if not hasattr(self, 'working_endpoints'):
                                self.working_endpoints = []
                            self.working_endpoints.append({
                                'base_url': base_url,
                                'endpoint': endpoint,
                                'full_url': url,
                                'data_format': 'dict_with_data' if isinstance(data,
                                                                              dict) and 'data' in data else 'other'
                            })

                        else:
                            error_text = await response.text()
                            print(f"   ❌ Ошибка {response.status}: {error_text[:100]}...")

                except Exception as e:
                    print(f"   ❌ Исключение: {str(e)[:100]}...")
                    continue

            if found_working_endpoint:
                break

        if hasattr(self, 'working_endpoints') and self.working_endpoints:
            print(f"\n✅ Найдено {len(self.working_endpoints)} рабочих endpoints!")
            return True
        else:
            print("\n❌ Не удалось найти рабочие публичные endpoints")
            return False

    async def find_products_and_trades_endpoints(self) -> bool:
        """Ищет специальные endpoints для продуктов и сделок."""
        if not self.working_base_url:
            return False

        print(f"\n{'=' * 60}")
        print("🔍 ПОИСК ENDPOINTS ДЛЯ ПРОДУКТОВ И СДЕЛОК")
        print(f"{'=' * 60}")
        print(f"Базовый URL: {self.working_base_url}")

        # Возможные пути для продуктов
        products_endpoints = [
            "/api/v3/brokerage/market/products",
            "/api/v3/brokerage/products",
            "/api/v3/brokerage/public/products",
            "/v2/currencies/crypto",
            "/v2/assets/search",
            "/products",
            "/public/products",
        ]

        self.products_endpoint = None

        print("\n📊 Поиск endpoints для списка продуктов...")
        for endpoint in products_endpoints:
            try:
                url = f"{self.working_base_url}{endpoint}"
                print(f"   Тестируем: {endpoint}")

                async with self.session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Проверяем, похоже ли это на список продуктов
                        products_found = False
                        product_count = 0

                        if isinstance(data, list):
                            if len(data) > 10:  # Должно быть много продуктов
                                products_found = True
                                product_count = len(data)
                        elif isinstance(data, dict):
                            if 'data' in data and isinstance(data['data'], list):
                                if len(data['data']) > 10:
                                    products_found = True
                                    product_count = len(data['data'])
                            elif 'products' in data:
                                products_found = True
                                product_count = len(data['products'])

                        if products_found:
                            print(f"   ✅ Найден список продуктов! Количество: {product_count}")
                            self.products_endpoint = endpoint

                            # Показываем пример продукта
                            sample_product = None
                            if isinstance(data, list) and data:
                                sample_product = data[0]
                            elif isinstance(data, dict):
                                if 'data' in data and data['data']:
                                    sample_product = data['data'][0]
                                elif 'products' in data and data['products']:
                                    sample_product = data['products'][0]

                            if sample_product:
                                print(f"   Пример продукта: {list(sample_product.keys())}")
                                # Ищем поле с идентификатором продукта
                                for key in ['id', 'product_id', 'symbol', 'code']:
                                    if key in sample_product:
                                        print(f"   ID поле: {key} = {sample_product[key]}")
                                        break
                            break
                    else:
                        print(f"   ❌ Ошибка {response.status}")

            except Exception as e:
                print(f"   ❌ Исключение: {str(e)[:50]}...")
                continue

        if not self.products_endpoint:
            print("   ❌ Endpoints для продуктов не найдены")
            return False

        # Теперь ищем endpoints для сделок, используя найденные продукты
        print(f"\n💱 Поиск endpoints для сделок...")

        # Получаем список продуктов для тестирования
        test_symbols = await self._get_test_symbols()
        if not test_symbols:
            print("   ❌ Не удалось получить тестовые символы")
            return False

        test_symbol = test_symbols[0]
        print(f"   Тестовый символ: {test_symbol}")

        # Возможные пути для сделок
        trades_endpoints = [
            f"/api/v3/brokerage/market/products/{test_symbol}/trades",
            f"/api/v3/brokerage/products/{test_symbol}/trades",
            f"/api/v3/brokerage/public/products/{test_symbol}/trades",
            f"/products/{test_symbol}/trades",
            f"/public/products/{test_symbol}/trades",
        ]

        self.trades_endpoint_pattern = None

        for endpoint_pattern in trades_endpoints:
            try:
                endpoint = endpoint_pattern.replace(test_symbol, "{symbol}")
                url = endpoint_pattern.replace("{symbol}", test_symbol)
                full_url = f"{self.working_base_url}{url}"

                print(f"   Тестируем: {endpoint}")

                async with self.session.get(full_url) as response:
                    if response.status == 200:
                        data = await response.json()

                        # Проверяем, похоже ли это на список сделок
                        trades_found = False
                        trades_count = 0

                        if isinstance(data, list):
                            if data:  # Есть сделки
                                trades_found = True
                                trades_count = len(data)
                        elif isinstance(data, dict):
                            if 'data' in data and isinstance(data['data'], list):
                                trades_found = True
                                trades_count = len(data['data'])
                            elif 'trades' in data:
                                trades_found = True
                                trades_count = len(data['trades'])

                        if trades_found:
                            print(f"   ✅ Найден endpoint для сделок! Количество: {trades_count}")
                            self.trades_endpoint_pattern = endpoint

                            # Показываем пример сделки
                            sample_trade = None
                            if isinstance(data, list) and data:
                                sample_trade = data[0]
                            elif isinstance(data, dict):
                                if 'data' in data and data['data']:
                                    sample_trade = data['data'][0]
                                elif 'trades' in data and data['trades']:
                                    sample_trade = data['trades'][0]

                            if sample_trade:
                                print(f"   Структура сделки: {list(sample_trade.keys())}")
                                # Ищем ключевые поля
                                for key in ['id', 'trade_id', 'price', 'size', 'amount', 'time']:
                                    if key in sample_trade:
                                        print(f"   {key}: {sample_trade[key]}")
                            return True

                    else:
                        print(f"   ❌ Ошибка {response.status}")

            except Exception as e:
                print(f"   ❌ Исключение: {str(e)[:50]}...")
                continue

        print("   ❌ Endpoints для сделок не найдены")
        return False

    async def _get_test_symbols(self) -> List[str]:
        """Получает тестовые символы из найденного products endpoint."""
        if not self.products_endpoint:

    async def analyze_products(self) -> List[str]:
        """Анализирует доступные продукты с найденным endpoint."""
        if not self.working_base_url or not hasattr(self, 'products_endpoint') or not self.products_endpoint:
            print("❌ Нет рабочего products endpoint")
            return []

        print(f"\n{'=' * 60}")
        print("🔍 АНАЛИЗ ДОСТУПНЫХ ПРОДУКТОВ")
        print(f"{'=' * 60}")
        print(f"Используется: {self.working_base_url}{self.products_endpoint}")

        try:
            url = f"{self.working_base_url}{self.products_endpoint}"

            async with self.session.get(url) as response:
                if response.status != 200:
                    print(f"❌ Ошибка получения продуктов: {response.status}")
                    return []

                data = await response.json()

                # Адаптируемся к разным форматам ответа
                products = []
                if isinstance(data, list):
                    products = data
                elif isinstance(data, dict):
                    if 'products' in data:
                        products = data['products']
                    elif 'data' in data:
                        products = data['data']
                    else:
                        print(f"❌ Неожиданный формат данных: {list(data.keys())}")
                        return []

                if not products:
                    print(f"❌ Нет доступных продуктов")
                    return []

                print(f"📊 Всего продуктов: {len(products)}")

                # Показываем структуру первого продукта
                if products:
                    print(f"\n🔬 Структура продукта:")
                    sample = products[0]
                    for key, value in sample.items():
                        print(f"   {key}: {value} ({type(value).__name__})")

                # Ищем USD пары
                usd_pairs = []
                for product in products:
                    # Разные поля для ID в зависимости от endpoint
                    product_id = product.get('id') or product.get('product_id') or product.get('symbol', '')

                    if product_id and isinstance(product_id, str):
                        if '-USD' in product_id or (product_id.endswith('USD') and len(product_id) > 3):
                            # Проверяем статус если есть
                            status = product.get('status', '').lower()
                            trading_disabled = product.get('trading_disabled', False)

                            if not status or status in ['online', 'active'] and not trading_disabled:
                                usd_pairs.append(product_id)

                # Берем первые 10 USD пар
                top_symbols = sorted(usd_pairs)[:10]

                print(f"\n🔥 Найдено USD пар для тестирования: {len(usd_pairs)}")
                for i, symbol in enumerate(top_symbols, 1):
                    print(f"   {i:2d}. {symbol}")

                return top_symbols[:5]  # Возвращаем топ-5

        except Exception as e:
            print(f"❌ Ошибка при анализе продуктов: {e}")
            return []

        try:
            url = f"{self.working_base_url}{self.products_endpoint}"
            async with self.session.get(url) as response:
                if response.status != 200:
                    return []

                data = await response.json()
                symbols = []

                # Извлекаем символы в зависимости от формата
                products = []
                if isinstance(data, list):
                    products = data
                elif isinstance(data, dict):
                    if 'data' in data:
                        products = data['data']
                    elif 'products' in data:
                        products = data['products']

                for product in products[:20]:  # Берем первые 20 для поиска USD пар
                    # Ищем ID/символ продукта
                    product_id = None
                    for key in ['id', 'product_id', 'symbol', 'code']:
                        if key in product and product[key]:
                            product_id = product[key]
                            break

                    if product_id and isinstance(product_id, str):
                        # Ищем USD пары
                        if '-USD' in product_id or 'USD' in product_id:
                            symbols.append(product_id)
                            if len(symbols) >= 5:
                                break

                return symbols

        except Exception as e:
            print(f"Ошибка получения тестовых символов: {e}")
            return []
        """Анализирует доступные продукты с найденным рабочим endpoint."""
        if not self.working_base_url:
            print("❌ Нет рабочего базового URL")
            return []

        print(f"\n{'=' * 60}")
        print("🔍 АНАЛИЗ ДОСТУПНЫХ ПРОДУКТОВ")
        print(f"{'=' * 60}")
        print(f"Используется: {self.working_base_url}{self.working_endpoint}")

        try:
            url = f"{self.working_base_url}{self.working_endpoint}"

            async with self.session.get(url) as response:
                if response.status != 200:
                    print(f"❌ Ошибка получения продуктов: {response.status}")
                    return []

                data = await response.json()

                # Адаптируемся к разным форматам ответа
                products = []
                if isinstance(data, list):
                    products = data
                elif isinstance(data, dict):
                    if 'products' in data:
                        products = data['products']
                    elif 'data' in data:
                        products = data['data']
                    else:
                        print(f"❌ Неожиданный формат данных: {list(data.keys())}")
                        return []

                if not products:
                    print(f"❌ Нет доступных продуктов")
                    return []

                print(f"📊 Всего продуктов: {len(products)}")

                # Показываем структуру первого продукта
                if products:
                    print(f"\n🔬 Структура продукта:")
                    sample = products[0]
                    for key, value in sample.items():
                        print(f"   {key}: {value} ({type(value).__name__})")

                # Ищем USD пары
                usd_pairs = []
                for product in products:
                    # Разные поля для ID в зависимости от endpoint
                    product_id = product.get('id') or product.get('product_id') or product.get('symbol', '')

                    if product_id and '-USD' in product_id:
                        # Проверяем статус если есть
                        status = product.get('status', '').lower()
                        trading_disabled = product.get('trading_disabled', False)

                        if not status or status in ['online', 'active'] and not trading_disabled:
                            usd_pairs.append(product_id)

                # Берем первые 10 USD пар
                top_symbols = sorted(usd_pairs)[:10]

                print(f"\n🔥 Найдено USD пар для тестирования: {len(usd_pairs)}")
                for i, symbol in enumerate(top_symbols, 1):
                    print(f"   {i:2d}. {symbol}")

                return top_symbols[:5]  # Возвращаем топ-5

        except Exception as e:
            print(f"❌ Ошибка при анализе продуктов: {e}")
            return []

    async def test_trades_endpoint_limits(self, symbol: str) -> Dict:
        """Тестирует лимиты endpoint'а для получения сделок."""
        print(f"\n{'=' * 60}")
        print(f"🔍 ТЕСТИРОВАНИЕ ЛИМИТОВ СДЕЛОК ДЛЯ {symbol}")
        print(f"{'=' * 60}")

        results = {}

        # Тестируем разные лимиты
        limits_to_test = [1, 5, 10, 20, 50, 100, 200, 500, 1000]

        for limit in limits_to_test:
            try:
                url = f"{self.base_url}/products/{symbol}/trades"
                params = {'limit': limit}

                start_time = time.time()
                async with self.session.get(url, params=params) as response:
                    request_time = time.time() - start_time

                    if response.status == 200:
                        data = await response.json()

                        # Coinbase может возвращать trades в разных форматах
                        if isinstance(data, list):
                            trades = data
                        elif isinstance(data, dict) and 'trades' in data:
                            trades = data['trades']
                        else:
                            trades = []

                        actual_count = len(trades)
                        results[limit] = {
                            'requested': limit,
                            'received': actual_count,
                            'request_time': request_time,
                            'success': True
                        }
                        print(f"   Лимит {limit:4d}: получено {actual_count:4d} сделок за {request_time:.3f}с")

                        # Показываем структуру первой сделки только один раз
                        if limit == limits_to_test[0] and trades:
                            print(f"\n🔬 Структура сделки:")
                            sample_trade = trades[0]
                            for key, value in sample_trade.items():
                                print(f"   {key}: {value} ({type(value).__name__})")
                    else:
                        error_text = await response.text()
                        results[limit] = {
                            'requested': limit,
                            'received': 0,
                            'request_time': request_time,
                            'success': False,
                            'error': f"HTTP {response.status}: {error_text}"
                        }
                        print(f"   Лимит {limit:4d}: ОШИБКА - {response.status}")

                # Пауза между запросами (соблюдаем rate limit 10 RPS)
                await asyncio.sleep(0.11)  # Чуть больше 0.1с для безопасности

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

    async def test_rate_limits(self) -> None:
        """Тестирует rate limits API (10 RPS для публичных endpoint'ов)."""
        print(f"\n{'=' * 60}")
        print("⚡ ТЕСТИРОВАНИЕ RATE LIMITS (10 RPS)")
        print(f"{'=' * 60}")

        test_symbol = 'BTC-USD'
        requests_per_batch = 15  # Больше лимита для тестирования

        print(f"\n📊 Тест: {requests_per_batch} запросов подряд (лимит 10 RPS)")

        start_time = time.time()
        success_count = 0
        error_count = 0
        rate_limited = 0

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
            elif result['rate_limited']:
                print(f"   Запрос {i + 1:2d}: 🚫 Rate Limited")
                rate_limited += 1
            else:
                print(f"   Запрос {i + 1:2d}: ❌ {result['error']}")
                error_count += 1

        batch_time = time.time() - start_time
        actual_rps = requests_per_batch / batch_time

        print(f"\n📈 Результат теста rate limits:")
        print(f"   Успешных: {success_count}")
        print(f"   Rate limited: {rate_limited}")
        print(f"   Ошибок: {error_count}")
        print(f"   Время выполнения: {batch_time:.2f}с")
        print(f"   Фактический RPS: {actual_rps:.1f}")
        print(f"   Рекомендуемая задержка: {1 / 10:.1f}с между запросами")

    async def _single_trade_request(self, symbol: str, request_id: int) -> Dict:
        """Выполняет один запрос сделок."""
        try:
            start_time = time.time()
            url = f"{self.base_url}/products/{symbol}/trades"
            params = {'limit': 10}

            async with self.session.get(url, params=params) as response:
                request_time = time.time() - start_time

                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        trades_count = len(data)
                    elif isinstance(data, dict) and 'trades' in data:
                        trades_count = len(data['trades'])
                    else:
                        trades_count = 0

                    return {
                        'success': True,
                        'trades_count': trades_count,
                        'time': request_time,
                        'request_id': request_id,
                        'rate_limited': False
                    }
                elif response.status == 429:
                    return {
                        'success': False,
                        'error': 'Rate Limited',
                        'time': request_time,
                        'request_id': request_id,
                        'rate_limited': True
                    }
                else:
                    error_text = await response.text()
                    return {
                        'success': False,
                        'error': f"HTTP {response.status}: {error_text}",
                        'time': request_time,
                        'request_id': request_id,
                        'rate_limited': False
                    }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'time': 0,
                'request_id': request_id,
                'rate_limited': False
            }

    async def test_data_freshness(self, symbol: str) -> None:
        """Тестирует свежесть данных и временные диапазоны."""
        print(f"\n{'=' * 60}")
        print(f"⏰ ТЕСТИРОВАНИЕ СВЕЖЕСТИ ДАННЫХ ДЛЯ {symbol}")
        print(f"{'=' * 60}")

        try:
            url = f"{self.base_url}/products/{symbol}/trades"
            params = {'limit': 100}

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    print(f"❌ Ошибка получения данных: {response.status}")
                    return

                data = await response.json()

                if isinstance(data, list):
                    trades = data
                elif isinstance(data, dict) and 'trades' in data:
                    trades = data['trades']
                else:
                    print(f"❌ Неожиданный формат данных")
                    return

                if not trades:
                    print(f"❌ Нет сделок для анализа")
                    return

                print(f"📦 Получено сделок: {len(trades)}")

                # Анализируем временные метки
                times = []
                for trade in trades:
                    time_str = trade.get('time', '')
                    if time_str:
                        try:
                            trade_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                            times.append(trade_time)
                        except:
                            continue

                if times:
                    times.sort()
                    oldest_time = times[0]
                    newest_time = times[-1]
                    now = datetime.now(oldest_time.tzinfo)

                    print(f"📅 Временной анализ:")
                    print(f"   Самая старая сделка: {oldest_time}")
                    print(f"   Самая новая сделка:  {newest_time}")
                    print(f"   Текущее время:       {now}")
                    print(f"   Задержка данных:     {(now - newest_time).total_seconds():.1f} секунд")
                    print(f"   Временной охват:     {(newest_time - oldest_time).total_seconds():.1f} секунд")

                # Анализируем ID сделок
                trade_ids = [trade.get('trade_id', trade.get('id', '')) for trade in trades]
                unique_ids = set(filter(None, trade_ids))
                print(f"🆔 Уникальность ID: {len(unique_ids)}/{len(trades)} уникальных")

                # Анализируем объемы
                volumes = []
                for trade in trades:
                    try:
                        price = float(trade.get('price', 0))
                        size = float(trade.get('size', 0))
                        volume = price * size
                        volumes.append(volume)
                    except (ValueError, TypeError):
                        continue

                if volumes:
                    print(f"💰 Анализ объемов:")
                    print(f"   Мин. объем сделки: ${min(volumes):,.2f}")
                    print(f"   Макс. объем сделки: ${max(volumes):,.2f}")
                    print(f"   Средний объем:     ${sum(volumes) / len(volumes):,.2f}")

                    large_trades = [v for v in volumes if v >= 10000]  # $10k+
                    if large_trades:
                        print(f"   Сделки $10k+: {len(large_trades)} ({len(large_trades) / len(volumes) * 100:.1f}%)")
                        print(f"   Крупнейшая сделка: ${max(large_trades):,.2f}")

        except Exception as e:
            print(f"❌ Ошибка при анализе свежести данных: {e}")

    async def generate_recommendations(self) -> None:
        """Генерирует рекомендации для оптимизации."""
        print(f"\n{'=' * 60}")
        print("💡 РЕКОМЕНДАЦИИ ДЛЯ COINBASE API")
        print(f"{'=' * 60}")

        if hasattr(self, 'trades_endpoint_pattern') and self.trades_endpoint_pattern:
            print(f"✅ УСПЕХ: Найдены торговые endpoints!")
            print(f"1️⃣ Конфигурация для мониторинга:")
            print(f"   • Базовый URL: {self.working_base_url}")
            print(f"   • Продукты: {self.products_endpoint}")
            print(f"   • Сделки: {self.trades_endpoint_pattern}")

            print(f"\n2️⃣ Настройки агрессивного мониторинга:")
            print(f"   • Rate limit: 10 запросов в секунду")
            print(f"   • Задержка между запросами: 0.1 секунды")
            print(f"   • Максимум сделок за запрос: протестировать лимиты")

            print(f"\n3️⃣ Реализация:")
            print(f"   • Обновить base_url в CoinbaseClient")
            print(f"   • Адаптировать парсинг под найденный формат данных")
            print(f"   • Настроить конверсию символов")

        elif hasattr(self, 'working_endpoints') and self.working_endpoints:
            print(f"⚠️ ЧАСТИЧНЫЙ УСПЕХ: Найдены только общие endpoints")

            print(f"1️⃣ Доступные данные:")
            for ep in self.working_endpoints:
                print(f"   • {ep['endpoint']} - {ep['data_format']}")

            print(f"\n2️⃣ Ограничения:")
            print(f"   • Торговые данные требуют аутентификации")
            print(f"   • Нет доступа к сделкам в реальном времени")
            print(f"   • Доступны только курсы валют и общая информация")

            print(f"\n3️⃣ Варианты решения:")
            print(f"   • Создать API ключи Coinbase для аутентификации")
            print(f"   • Использовать WebSocket для публичных данных")
            print(f"   • Исключить Coinbase из мониторинга")
            print(f"   • Добавить другую биржу (Kraken, KuCoin)")

        else:
            print(f"❌ НЕ НАЙДЕНО: Публичные endpoints недоступны")

            print(f"1️⃣ Рекомендации:")
            print(f"   • Coinbase требует аутентификации для всех данных")
            print(f"   • Рассмотрите использование других бирж")
            print(f"   • Или создайте API ключи Coinbase")

            print(f"\n2️⃣ Альтернативные биржи:")
            print(f"   • Kraken - хорошие публичные API")
            print(f"   • KuCoin - много пар, публичные данные")
            print(f"   • OKX - агрессивные лимиты")
            print(f"   • Gate.io - большой выбор пар")

        print(f"\n4️⃣ Общие рекомендации:")
        print(f"   • Система уже работает с Binance + Bybit")
        print(f"   • Добавление третьей биржи не критично")
        print(f"   • Можно запустить двухбиржевой мониторинг")
        print(f"   • При необходимости добавить другую биржу позже")


async def main():
    """Главная функция тестирования."""
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║          COINBASE API ENDPOINT EXPLORER           ║
    ║                                                   ║
    ║  Поиск и тестирование публичных API endpoints    ║
    ║  для агрессивного мониторинга крупных сделок     ║
    ╚═══════════════════════════════════════════════════╝
    """)

    # Пробуем сначала с SSL, потом без
    print("🔐 Попытка подключения с проверкой SSL...")
    async with CoinbaseAPITester(disable_ssl_verify=False) as tester:
        if await tester.test_connection():
            ssl_works = True
        else:
            ssl_works = False

    if not ssl_works:
        print("\n⚠️  SSL проверка не работает, пробуем без проверки сертификатов...")
        async with CoinbaseAPITester(disable_ssl_verify=True) as tester:
            if not await tester.test_connection():
                print("\n❌ Не удалось найти рабочие публичные endpoints")
                print("\n💡 Возможные причины:")
                print("   • Coinbase требует аутентификации для всех endpoints")
                print("   • Изменились пути к публичным API")
                print("   • Необходимо использовать WebSocket для публичных данных")
                print("   • API заблокирован в вашем регионе")
                return

            await run_all_tests(tester)
    else:
        print("✅ SSL соединение работает!")
        async with CoinbaseAPITester(disable_ssl_verify=False) as tester:
            if await tester.test_connection():
                await run_all_tests(tester)
            else:
                print("❌ Не удалось найти рабочие endpoints даже с SSL")


async def run_all_tests(tester):
    """Выполняет все тесты."""
    # Сначала ищем endpoints для продуктов и сделок
    found_trading_endpoints = await tester.find_products_and_trades_endpoints()

    if found_trading_endpoints:
        print(f"\n🎉 Найдены endpoints для торговых данных!")
        print(f"   Продукты: {tester.products_endpoint}")
        print(f"   Сделки: {tester.trades_endpoint_pattern}")

        # Анализ продуктов
        top_symbols = await tester.analyze_products()

        if top_symbols:
            # Тестирование лимитов trades
            test_results = await tester.test_trades_endpoint_limits(top_symbols[0])

            if test_results:
                # Тестирование rate limits
                await tester.test_rate_limits()

                # Тестирование свежести данных
                await tester.test_data_freshness(top_symbols[0])
    else:
        print(f"\n⚠️ Торговые endpoints не найдены")
        print(f"Найдены только общие endpoints:")
        if hasattr(tester, 'working_endpoints'):
            for ep in tester.working_endpoints:
                print(f"   • {ep['full_url']}")

    # Генерация рекомендаций в любом случае
    await tester.generate_recommendations()

    print(f"\n{'=' * 60}")
    print("✅ ИССЛЕДОВАНИЕ COINBASE API ЗАВЕРШЕНО")
    print(f"{'=' * 60}")

    if hasattr(tester, 'trades_endpoint_pattern') and tester.trades_endpoint_pattern:
        print(f"🎯 Можно использовать для мониторинга сделок:")
        print(f"   Базовый URL: {tester.working_base_url}")
        print(f"   Продукты: {tester.products_endpoint}")
        print(f"   Сделки: {tester.trades_endpoint_pattern}")
    elif hasattr(tester, 'working_endpoints') and tester.working_endpoints:
        print(f"🎯 Доступны только общие данные:")
        print(f"   Курсы валют, время сервера и т.д.")
        print(f"   Для торговых данных нужна аутентификация")
    else:
        print("❌ Рабочие публичные endpoints не найдены")
        print("💡 Рекомендация: использовать WebSocket или другие источники данных")


if __name__ == "__main__":
    asyncio.run(main())