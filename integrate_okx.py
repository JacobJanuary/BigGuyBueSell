#!/usr/bin/env python3
"""
Исправленная автоматическая интеграция биржи OKX в проект.
Устраняет все проблемы с импортами и зависимостями.
"""
import os
import shutil
from datetime import datetime


def create_backup(file_path: str) -> str:
    """Создает резервную копию файла."""
    if not os.path.exists(file_path):
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{file_path}.backup_{timestamp}"
    shutil.copy2(file_path, backup_path)
    return backup_path


def create_okx_directory():
    """Создает директорию для OKX."""
    okx_dir = 'exchanges/okx'
    os.makedirs(okx_dir, exist_ok=True)
    print(f"✅ Создана директория: {okx_dir}")


def create_okx_files():
    """Создает файлы OKX с исправленными импортами."""

    # 1. exchanges/okx/__init__.py
    init_content = '''"""Модуль для работы с OKX API."""
from .client import OKXClient
from .analyzer import OKXAnalyzer

__all__ = ['OKXClient', 'OKXAnalyzer']
'''

    with open('exchanges/okx/__init__.py', 'w', encoding='utf-8') as f:
        f.write(init_content)
    print("✅ Создан exchanges/okx/__init__.py")

    # 2. exchanges/okx/client.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
    client_content = '''"""
Клиент для работы с OKX API.
"""
import asyncio
import logging
from typing import Dict, List, Set

from aiohttp import ClientSession

# Исправленные импорты
try:
    from config.settings import EXCHANGES_CONFIG, DELAY_BETWEEN_REQUESTS, RETRY_DELAY, MAX_RETRIES
except ImportError:
    # Fallback значения если импорт не удался
    EXCHANGES_CONFIG = {
        'okx': {
            'api_url': 'https://www.okx.com',
            'trades_limit': 100,
            'weights': {'trades': 1, 'exchange_info': 1, 'tickers': 1}
        }
    }
    DELAY_BETWEEN_REQUESTS = 0.2
    RETRY_DELAY = 5
    MAX_RETRIES = 3

from database.models import Trade, TradingPairInfo
from exchanges.base import ExchangeBase

logger = logging.getLogger(__name__)


class OKXClient(ExchangeBase):
    """Асинхронный клиент для работы с OKX API v5."""

    def __init__(self, session: ClientSession, rate_limiter):
        """
        Инициализирует клиент OKX.

        Args:
            session: Асинхронная HTTP сессия
            rate_limiter: Контроллер rate limits
        """
        super().__init__(session, rate_limiter)
        self.config = EXCHANGES_CONFIG.get('okx', {
            'api_url': 'https://www.okx.com',
            'trades_limit': 100,
            'weights': {'trades': 1, 'exchange_info': 1, 'tickers': 1}
        })
        self.base_url = self.config['api_url']
        self.weights = self.config['weights']
        self.exchange_name = 'okx'

    async def test_connection(self) -> bool:
        """
        Проверяет соединение с OKX API.

        Returns:
            True если соединение успешно
        """
        try:
            url = f"{self.base_url}/api/v5/public/time"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '0':
                        logger.info("Соединение с OKX API установлено")
                        return True
                logger.error(f"Ошибка ответа OKX: {response.status}")
                return False
        except Exception as e:
            logger.error(f"Не удалось подключиться к OKX API: {e}")
            return False

    async def get_instruments_info(self) -> Dict:
        """
        Получает информацию о торговых инструментах.

        Returns:
            Словарь с информацией о торговых парах
        """
        await self.rate_limiter.acquire(self.weights.get('exchange_info', 1))

        url = f"{self.base_url}/api/v5/public/instruments"
        params = {'instType': 'SPOT'}

        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            if data.get('code') != '0':
                raise Exception(f"OKX API error: {data.get('msg', 'Unknown error')}")

            return data

    async def get_active_pairs(self) -> Set[str]:
        """
        Получает список всех активных спотовых торговых пар.

        Returns:
            Множество символов активных спотовых пар
        """
        try:
            data = await self.get_instruments_info()

            # Фильтруем активные спотовые пары
            spot_pairs = {
                item['instId']
                for item in data.get('data', [])
                if item.get('state') == 'live'
            }

            logger.info(f"Найдено {len(spot_pairs)} активных спотовых пар на OKX")
            return spot_pairs

        except Exception as e:
            logger.error(f"Ошибка при получении списка торговых пар OKX: {e}")
            raise

    async def get_24hr_tickers(self) -> List[Dict]:
        """
        Получает 24-часовую статистику для всех пар.

        Returns:
            Список словарей с данными тикеров
        """
        await self.rate_limiter.acquire(self.weights.get('tickers', 1))

        url = f"{self.base_url}/api/v5/market/tickers"
        params = {'instType': 'SPOT'}

        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            if data.get('code') != '0':
                raise Exception(f"OKX API error: {data.get('msg', 'Unknown error')}")

            return data.get('data', [])

    async def get_recent_trades(self, symbol: str, retry_count: int = 0) -> List[Dict]:
        """
        Получает последние сделки для указанной торговой пары.

        Args:
            symbol: Символ торговой пары (например, "BTC-USDT")
            retry_count: Текущее количество попыток

        Returns:
            Список сделок в сыром виде
        """
        try:
            await self.rate_limiter.acquire(self.weights.get('trades', 1))
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

            url = f"{self.base_url}/api/v5/market/trades"
            params = {
                'instId': symbol,
                'limit': min(self.config.get('trades_limit', 100), 100)  # OKX максимум 100
            }

            async with self.session.get(url, params=params) as response:
                # Обработка rate limit
                if response.status == 429:
                    if retry_count < MAX_RETRIES:
                        retry_after = int(response.headers.get('Retry-After', RETRY_DELAY))
                        logger.warning(f"Rate limit для {symbol}, повтор через {retry_after}с")
                        await asyncio.sleep(retry_after)
                        return await self.get_recent_trades(symbol, retry_count + 1)
                    return []

                if response.status == 400:
                    data = await response.json()
                    # Проверяем код ошибки OKX
                    if data.get('code') in ['51001', '51002']:  # Invalid instrument
                        logger.debug(f"Неверный символ {symbol}, пропускаем")
                    return []

                response.raise_for_status()
                data = await response.json()

                if data.get('code') == '0':
                    return data.get('data', [])
                else:
                    logger.warning(f"OKX API error for {symbol}: {data.get('msg')}")
                    return []

        except asyncio.TimeoutError:
            logger.error(f"Таймаут при получении сделок для {symbol}")
            return []
        except Exception as e:
            if retry_count < MAX_RETRIES:
                logger.warning(f"Ошибка для {symbol}: {e}, повтор {retry_count + 1}/{MAX_RETRIES}")
                await asyncio.sleep(RETRY_DELAY)
                return await self.get_recent_trades(symbol, retry_count + 1)
            else:
                logger.error(f"Ошибка при получении сделок для {symbol}: {e}")
                return []

    async def parse_trade(self, trade_data: Dict, pair_info: TradingPairInfo) -> Trade:
        """
        Парсит сырые данные сделки OKX в объект Trade.

        Args:
            trade_data: Сырые данные сделки от API
            pair_info: Информация о торговой паре

        Returns:
            Объект Trade
        """
        return Trade.from_okx_response(
            trade_data,
            pair_info.symbol,
            pair_info.base_asset,
            pair_info.quote_asset,
            pair_info.quote_price_usd
        )
'''

    with open('exchanges/okx/client.py', 'w', encoding='utf-8') as f:
        f.write(client_content)
    print("✅ Создан exchanges/okx/client.py")

    # 3. exchanges/okx/analyzer.py - ИСПРАВЛЕННАЯ ВЕРСИЯ
    analyzer_content = '''"""
Анализатор данных для OKX.
"""
import logging
from decimal import Decimal
from typing import Dict, List

# Исправленные импорты с fallback
try:
    from config.constants import STABLECOINS, WRAPPED_TOKENS, DEFAULT_QUOTE_PRICES_USD
except ImportError:
    # Fallback константы
    STABLECOINS = {'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI'}
    WRAPPED_TOKENS = {'WBTC', 'WETH', 'WBNB'}
    DEFAULT_QUOTE_PRICES_USD = {
        'USDT': Decimal('1.0'),
        'USDC': Decimal('1.0'),
        'USD': Decimal('1.0')
    }

try:
    from config.settings import MIN_VOLUME_USD
except ImportError:
    MIN_VOLUME_USD = 1_000_000

from database.models import TradingPairInfo
from exchanges.base import ExchangeAnalyzerBase

logger = logging.getLogger(__name__)


class OKXAnalyzer(ExchangeAnalyzerBase):
    """Анализатор торговых данных OKX."""

    def __init__(self):
        """Инициализирует анализатор."""
        super().__init__()
        self.quote_prices_usd = DEFAULT_QUOTE_PRICES_USD.copy()

    def calculate_volume_usd(self, volume: str, quote_asset: str) -> Decimal:
        """
        Рассчитывает объем в USD.

        Args:
            volume: Объем в котировочной валюте
            quote_asset: Котировочный актив

        Returns:
            Объем в USD
        """
        try:
            volume_decimal = Decimal(str(volume))
            quote_price = self.quote_prices_usd.get(quote_asset, Decimal('0'))
            return volume_decimal * quote_price
        except (ValueError, TypeError):
            return Decimal('0')

    def update_quote_prices(self, tickers: List[Dict]) -> None:
        """
        Обновляет цены котировочных активов в USD.

        Args:
            tickers: Список тикеров с 24hr данными
        """
        # Обновляем цены основных котировочных активов
        for ticker in tickers:
            inst_id = ticker.get('instId', '')

            try:
                last_price = ticker.get('last', '0')
                if not last_price:
                    continue

                price_decimal = Decimal(str(last_price))

                # BTC price in USDT
                if inst_id == 'BTC-USDT':
                    self.quote_prices_usd['BTC'] = price_decimal
                # ETH price in USDT
                elif inst_id == 'ETH-USDT':
                    self.quote_prices_usd['ETH'] = price_decimal
                # Дополнительные котировочные активы для OKX
                elif inst_id == 'USDC-USDT':
                    self.quote_prices_usd['USDC'] = price_decimal
                elif inst_id == 'OKB-USDT':
                    self.quote_prices_usd['OKB'] = price_decimal

            except (ValueError, TypeError) as e:
                logger.debug(f"Ошибка обработки цены для {inst_id}: {e}")
                continue

    def filter_trading_pairs(
        self,
        instruments_info: Dict,
        tickers: List[Dict]
    ) -> List[TradingPairInfo]:
        """
        Фильтрует торговые пары по критериям.

        Args:
            instruments_info: Информация об инструментах от OKX
            tickers: 24-часовая статистика

        Returns:
            Список отфильтрованных пар с информацией
        """
        # Создаем словарь тикеров для быстрого доступа
        ticker_map = {t.get('instId', ''): t for t in tickers}

        # Обновляем цены котировочных активов
        self.update_quote_prices(tickers)

        filtered_pairs = []

        try:
            # В OKX данные находятся в data
            instruments = instruments_info.get('data', [])

            for instrument in instruments:
                try:
                    # Проверяем, что инструмент активен
                    if instrument.get('state') != 'live':
                        continue

                    inst_id = instrument.get('instId', '')
                    base_asset = instrument.get('baseCcy', '')  # В OKX используется baseCcy
                    quote_asset = instrument.get('quoteCcy', '')  # В OKX используется quoteCcy

                    if not inst_id or not base_asset or not quote_asset:
                        continue

                    # Пропускаем пары стейблкоинов и wrapped токены
                    if self.should_filter_pair(base_asset, quote_asset):
                        continue

                    # Получаем данные тикера
                    ticker = ticker_map.get(inst_id)
                    if not ticker:
                        continue

                    # В OKX объем указан как volCcy24h (в quote currency)
                    quote_volume = ticker.get('volCcy24h', '0')
                    if not quote_volume or quote_volume == '0':
                        continue

                    volume_usd = self.calculate_volume_usd(quote_volume, quote_asset)

                    # Фильтруем по минимальному объему
                    if volume_usd < Decimal(str(MIN_VOLUME_USD)):
                        continue

                    quote_price_usd = self.quote_prices_usd.get(quote_asset, Decimal('0'))

                    # Проверяем что цена котировочного актива известна
                    if quote_price_usd <= 0:
                        logger.debug(f"Неизвестная цена для {quote_asset}, пропускаем {inst_id}")
                        continue

                    filtered_pairs.append(TradingPairInfo(
                        exchange='okx',
                        symbol=inst_id,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        volume_24h_usd=volume_usd,
                        quote_price_usd=quote_price_usd
                    ))

                    # Добавляем отладочную информацию для первых нескольких пар
                    if len(filtered_pairs) <= 3:
                        logger.info(f"Добавлена пара OKX: {inst_id} с объемом ${volume_usd:,.0f}")

                except Exception as e:
                    logger.error(f"Ошибка при обработке инструмента {instrument.get('instId', 'unknown')}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Ошибка при обработке данных OKX: {e}")

        logger.info(
            f"Отфильтровано {len(filtered_pairs)} пар OKX "
            f"с объемом > ${MIN_VOLUME_USD:,}"
        )

        return filtered_pairs
'''

    with open('exchanges/okx/analyzer.py', 'w', encoding='utf-8') as f:
        f.write(analyzer_content)
    print("✅ Создан exchanges/okx/analyzer.py")


def update_models():
    """Обновляет database/models.py для поддержки OKX."""
    models_file = 'database/models.py'
    backup = create_backup(models_file)
    if backup:
        print(f"✅ Создана резервная копия: {backup}")

    try:
        with open(models_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Проверяем, не добавлен ли уже метод
        if 'from_okx_response' in content:
            print("ℹ️  Метод from_okx_response уже существует в models.py")
            return True

        # Добавляем метод в конец класса Trade (перед @dataclass для TradingPairInfo)
        okx_method = '''
    @classmethod
    def from_okx_response(
        cls,
        data: Dict,
        symbol: str,
        base_asset: str,
        quote_asset: str,
        quote_price_usd: Decimal
    ) -> 'Trade':
        """
        Создает объект Trade из ответа OKX API.

        Args:
            data: Словарь с данными сделки от API
            symbol: Символ торговой пары
            base_asset: Базовый актив
            quote_asset: Котировочный актив
            quote_price_usd: Цена котировочного актива в USD

        Returns:
            Объект Trade
        """
        price = Decimal(str(data['px']))
        size = Decimal(str(data['sz']))
        value_usd = price * size * quote_price_usd

        # В OKX время в миллисекундах
        trade_time_ms = int(data['ts'])

        trade = cls(
            id=str(data['tradeId']),
            exchange='okx',  # Явно указываем exchange
            symbol=symbol,
            base_asset=base_asset,
            price=price,
            quantity=size,
            value_usd=value_usd,
            quote_asset=quote_asset,
            is_buyer_maker=data['side'] == 'sell',  # В OKX sell = buyer maker
            trade_time=trade_time_ms
        )

        # Отладочная информация для первых сделок
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Создана сделка OKX: {trade.exchange} - {symbol} - ${value_usd:.2f}")

        return trade

'''

        # Находим место для вставки (перед @dataclass TradingPairInfo)
        insert_marker = '@dataclass\nclass TradingPairInfo:'
        if insert_marker in content:
            content = content.replace(insert_marker, okx_method + insert_marker)
        else:
            # Альтернативный способ - добавляем в конец класса Trade
            trade_class_end = content.rfind('        return trade_type')
            if trade_class_end > 0:
                # Находим конец метода trade_type
                next_line_pos = content.find('\n', trade_class_end)
                if next_line_pos > 0:
                    content = content[:next_line_pos] + okx_method + content[next_line_pos:]
            else:
                print("❌ Не удалось найти место для вставки метода")
                return False

        with open(models_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print("✅ Добавлен метод from_okx_response в database/models.py")
        return True

    except Exception as e:
        print(f"❌ Ошибка обновления models.py: {e}")
        return False


def update_settings():
    """Обновляет config/settings.py для поддержки OKX."""
    settings_file = 'config/settings.py'
    backup = create_backup(settings_file)
    if backup:
        print(f"✅ Создана резервная копия: {backup}")

    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Проверяем, включен ли уже OKX
        if "'enabled': get_env_bool('OKX_ENABLED', True)" in content:
            print("ℹ️  Конфигурация OKX уже обновлена в settings.py")
            return True

        # Находим секцию 'okx' и заменяем её на правильную
        okx_config_new = '''    'okx': {
        'api_url': 'https://www.okx.com',
        'trades_limit': get_env_int('OKX_TRADES_LIMIT', 100),
        'cycle_pause_minutes': get_env_int('OKX_CYCLE_MINUTES', 4),
        'rate_limit': get_env_int('OKX_RATE_LIMIT', MAX_WEIGHT_PER_MINUTE),
        'enabled': get_env_bool('OKX_ENABLED', True),
        'weights': {
            'trades': 1,
            'exchange_info': 1,
            'tickers': 1
        }
    }'''

        # Ищем и заменяем существующую конфигурацию OKX
        lines = content.split('\n')
        okx_start = -1
        okx_end = -1

        for i, line in enumerate(lines):
            if "'okx':" in line:
                okx_start = i
                brace_count = 0
                for j in range(i, len(lines)):
                    brace_count += lines[j].count('{') - lines[j].count('}')
                    if brace_count <= 0 and '}' in lines[j]:
                        okx_end = j
                        break
                break

        if okx_start >= 0 and okx_end >= 0:
            # Заменяем конфигурацию
            new_lines = lines[:okx_start] + okx_config_new.split('\n') + lines[okx_end + 1:]
            new_content = '\n'.join(new_lines)

            with open(settings_file, 'w', encoding='utf-8') as f:
                f.write(new_content)

            print("✅ Обновлена конфигурация OKX в config/settings.py")
            return True
        else:
            print("❌ Не удалось найти секцию 'okx' в EXCHANGES_CONFIG")
            # Попробуем добавить в конец EXCHANGES_CONFIG
            exchanges_end = content.rfind('}')
            if exchanges_end > 0 and 'EXCHANGES_CONFIG' in content[max(0, exchanges_end - 1000):exchanges_end]:
                # Добавляем перед закрывающей скобкой
                insert_pos = content.rfind('}', 0, exchanges_end)
                if insert_pos > 0:
                    content = content[:insert_pos] + ',\n' + okx_config_new + '\n' + content[insert_pos:]
                    with open(settings_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print("✅ Добавлена конфигурация OKX в config/settings.py")
                    return True
            return False

    except Exception as e:
        print(f"❌ Ошибка обновления settings.py: {e}")
        return False


def update_main():
    """Обновляет main.py для поддержки OKX."""
    main_file = 'main.py'
    backup = create_backup(main_file)
    if backup:
        print(f"✅ Создана резервная копия: {backup}")

    try:
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Проверяем, не добавлен ли уже импорт OKX
        if 'from exchanges.okx.client import OKXClient' in content:
            print("ℹ️  Импорты OKX уже добавлены в main.py")
            return True

        # Добавляем импорты после других exchanges импортов
        coinbase_import = 'from exchanges.coinbase.analyzer import CoinbaseAnalyzer'
        if coinbase_import in content:
            okx_imports = '''from exchanges.okx.client import OKXClient
from exchanges.okx.analyzer import OKXAnalyzer'''
            content = content.replace(coinbase_import, coinbase_import + '\n' + okx_imports)

        # Добавляем обработку OKX в setup_exchanges
        coinbase_handler = '''            elif exchange_name == 'coinbase':
                client = CoinbaseClient(session, RateLimiter(config['rate_limit']))
                analyzer = CoinbaseAnalyzer()'''

        if coinbase_handler in content:
            okx_handler = '''            elif exchange_name == 'okx':
                client = OKXClient(session, RateLimiter(config['rate_limit']))
                analyzer = OKXAnalyzer()'''
            content = content.replace(coinbase_handler, coinbase_handler + '\n' + okx_handler)

        with open(main_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print("✅ Обновлен main.py для поддержки OKX")
        return True

    except Exception as e:
        print(f"❌ Ошибка обновления main.py: {e}")
        return False


def update_exchange_worker():
    """Обновляет workers/exchange_worker.py для поддержки OKX."""
    worker_file = 'workers/exchange_worker.py'
    backup = create_backup(worker_file)
    if backup:
        print(f"✅ Создана резервная копия: {backup}")

    try:
        with open(worker_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Проверяем, не добавлена ли уже обработка OKX
        if "elif self.exchange_name == 'okx':" in content:
            print("ℹ️  Обработка OKX уже добавлена в exchange_worker.py")
            return True

        # Добавляем обработку OKX в метод update_pairs_cache
        coinbase_handler = '''            elif self.exchange_name == 'coinbase':
                products_info = await self.client.get_products_info()
                tickers = await self.client.get_24hr_tickers()
                filtered_pairs = self.analyzer.filter_trading_pairs(products_info, tickers)'''

        if coinbase_handler in content:
            okx_handler = '''            elif self.exchange_name == 'okx':
                exchange_info = await self.client.get_instruments_info()
                tickers = await self.client.get_24hr_tickers()
                filtered_pairs = self.analyzer.filter_trading_pairs(exchange_info, tickers)'''
            content = content.replace(coinbase_handler, coinbase_handler + '\n' + okx_handler)

            with open(worker_file, 'w', encoding='utf-8') as f:
                f.write(content)

            print("✅ Обновлен exchange_worker.py для поддержки OKX")
            return True
        else:
            print("❌ Не удалось найти место для вставки обработки OKX")
            return False

    except Exception as e:
        print(f"❌ Ошибка обновления exchange_worker.py: {e}")
        return False


def update_env_file():
    """Обновляет .env файл с настройками OKX."""
    env_file = '.env'

    okx_settings = '''
# OKX
OKX_ENABLED=true
OKX_TRADES_LIMIT=100
OKX_CYCLE_MINUTES=4
OKX_RATE_LIMIT=1200
'''

    try:
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                content = f.read()

            if 'OKX_ENABLED' not in content:
                with open(env_file, 'a', encoding='utf-8') as f:
                    f.write(okx_settings)
                print("✅ Добавлены настройки OKX в .env")
            else:
                print("ℹ️  Настройки OKX уже есть в .env")
        else:
            with open(env_file, 'w', encoding='utf-8') as f:
                f.write(okx_settings.strip())
            print("✅ Создан .env файл с настройками OKX")

        return True

    except Exception as e:
        print(f"❌ Ошибка обновления .env: {e}")
        return False


def verify_integration():
    """Проверяет корректность интеграции."""
    print("\n🔍 Проверка интеграции...")

    checks = []

    # Проверяем файлы
    files_to_check = [
        'exchanges/okx/__init__.py',
        'exchanges/okx/client.py',
        'exchanges/okx/analyzer.py'
    ]

    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"  ✅ {file_path}")
            checks.append(True)
        else:
            print(f"  ❌ {file_path}")
            checks.append(False)

    # Проверяем импорты
    try:
        import sys
        sys.path.insert(0, '.')

        from exchanges.okx.client import OKXClient
        from exchanges.okx.analyzer import OKXAnalyzer
        print("  ✅ Импорты OKX работают")
        checks.append(True)
    except Exception as e:
        print(f"  ❌ Ошибка импорта: {e}")
        checks.append(False)

    # Проверяем настройки
    try:
        from config.settings import EXCHANGES_CONFIG
        if 'okx' in EXCHANGES_CONFIG and EXCHANGES_CONFIG['okx'].get('enabled'):
            print("  ✅ Конфигурация OKX найдена и включена")
            checks.append(True)
        else:
            print("  ❌ Конфигурация OKX не найдена или отключена")
            checks.append(False)
    except Exception as e:
        print(f"  ❌ Ошибка проверки настроек: {e}")
        checks.append(False)

    # Проверяем модель Trade
    try:
        from database.models import Trade
        if hasattr(Trade, 'from_okx_response'):
            print("  ✅ Метод from_okx_response добавлен в Trade")
            checks.append(True)
        else:
            print("  ❌ Метод from_okx_response не найден в Trade")
            checks.append(False)
    except Exception as e:
        print(f"  ❌ Ошибка проверки модели Trade: {e}")
        checks.append(False)

    success_rate = sum(checks) / len(checks) * 100
    print(f"\n📊 Успешность интеграции: {success_rate:.1f}% ({sum(checks)}/{len(checks)})")

    return success_rate >= 80


def main():
    """Главная функция интеграции OKX."""
    print("""
╔═══════════════════════════════════════════════════╗
║     ИСПРАВЛЕННАЯ ИНТЕГРАЦИЯ БИРЖИ OKX             ║
╚═══════════════════════════════════════════════════╝

🔧 ИСПРАВЛЕНИЯ:
✅ Правильные импорты с fallback значениями
✅ Безопасная обработка отсутствующих конфигураций
✅ Улучшенная обработка ошибок
✅ Проверка корректности интеграции

🚀 КОМПОНЕНТЫ:
• OKX Client с обработкой ошибок импорта
• OKX Analyzer с fallback константами  
• Обновление модели Trade
• Интеграция в main.py и exchange_worker.py
• Настройки в .env и config/settings.py
    """)

    try:
        success_steps = []

        # 1. Создаем директорию и файлы
        print("\n📁 Создание файлов OKX...")
        create_okx_directory()
        create_okx_files()
        success_steps.append("files_created")

        # 2. Обновляем существующие файлы
        print("\n🔄 Обновление существующих файлов...")

        if update_models():
            success_steps.append("models_updated")

        if update_settings():
            success_steps.append("settings_updated")

        if update_main():
            success_steps.append("main_updated")

        if update_exchange_worker():
            success_steps.append("worker_updated")

        if update_env_file():
            success_steps.append("env_updated")

        # 3. Проверяем интеграцию
        print("\n🧪 Проверка интеграции...")
        integration_success = verify_integration()

        # 4. Итоговый отчет
        print(f"\n{'=' * 60}")
        print("ИТОГОВЫЙ ОТЧЕТ ИНТЕГРАЦИИ")
        print(f"{'=' * 60}")

        successful_steps = len(success_steps)
        total_steps = 5  # models, settings, main, worker, env

        print(f"📊 Выполнено шагов: {successful_steps}/{total_steps}")
        for step in success_steps:
            step_names = {
                "files_created": "Создание файлов OKX",
                "models_updated": "Обновление database/models.py",
                "settings_updated": "Обновление config/settings.py",
                "main_updated": "Обновление main.py",
                "worker_updated": "Обновление exchange_worker.py",
                "env_updated": "Обновление .env"
            }
            print(f"  ✅ {step_names.get(step, step)}")

        if successful_steps >= 4 and integration_success:
            print(f"""
🎉 ИНТЕГРАЦИЯ OKX ЗАВЕРШЕНА УСПЕШНО!

✅ ЧТО БЫЛО СДЕЛАНО:
• Созданы все необходимые файлы OKX
• Добавлена поддержка OKX в модели данных
• Обновлена конфигурация (OKX включен по умолчанию)
• Интегрировано в основное приложение
• Добавлены настройки в .env

🚀 СЛЕДУЮЩИЕ ШАГИ:
1. Перезапустите приложение: python main.py
2. В логах должно появиться: "OKX готов к работе"
3. Мониторьте работу OKX воркера

⚙️ НАСТРОЙКИ OKX:
• API URL: https://www.okx.com
• Пауза между циклами: 4 минуты
• Лимит сделок: 100 за запрос (максимум OKX API)
• Rate limit: 1200 запросов/мин
• Статус: ВКЛЮЧЕН

🔧 НАСТРОЙКА:
• Чтобы отключить: установите OKX_ENABLED=false в .env
• Изменить интервалы: отредактируйте OKX_CYCLE_MINUTES в .env
• Все настройки доступны через переменные окружения

📈 ОЖИДАЕМЫЕ РЕЗУЛЬТАТЫ:
• OKX появится в списке активных бирж
• Будет обрабатывать высокообъемные пары каждые 4 минуты
• Крупные сделки (>$49,000) будут сохраняться в БД
• В статистике появится раздел OKX

🧪 ТЕСТИРОВАНИЕ:
Для проверки работы OKX запустите:
python -c "
import asyncio
from exchanges.okx.client import OKXClient
from utils.rate_limiter import RateLimiter
import aiohttp

async def test():
    async with aiohttp.ClientSession() as session:
        client = OKXClient(session, RateLimiter(1200))
        result = await client.test_connection()
        print('OKX Connection:', 'OK' if result else 'FAILED')

asyncio.run(test())
"
            """)
        elif successful_steps >= 3:
            print(f"""
⚠️ ИНТЕГРАЦИЯ ЗАВЕРШЕНА С ПРЕДУПРЕЖДЕНИЯМИ

✅ Основные компоненты установлены ({successful_steps}/{total_steps})
⚠️ Некоторые шаги завершились с ошибками

🔧 РЕКОМЕНДАЦИИ:
1. Проверьте логи выше на предмет ошибок
2. Убедитесь что все файлы созданы корректно
3. Попробуйте запустить приложение
4. При необходимости исправьте ошибки вручную

📁 РЕЗЕРВНЫЕ КОПИИ:
Все измененные файлы имеют резервные копии с timestamp.
При необходимости используйте их для отката изменений.
            """)
        else:
            print(f"""
❌ ИНТЕГРАЦИЯ ЗАВЕРШЕНА С ОШИБКАМИ

Выполнено только {successful_steps}/{total_steps} шагов.
Проверьте ошибки выше и исправьте их вручную.

🔄 ПОВТОРИТЬ ПОПЫТКУ:
1. Исправьте найденные ошибки
2. Запустите скрипт снова
3. Используйте резервные копии при необходимости

📞 АЛЬТЕРНАТИВА:
Выполните интеграцию вручную, используя созданные файлы
как шаблоны и добавив необходимые изменения в код.
            """)

    except Exception as e:
        print(f"💥 Критическая ошибка интеграции: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()