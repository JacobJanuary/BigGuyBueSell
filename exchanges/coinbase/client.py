"""
Клиент для работы с Coinbase Advanced Trade API.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Set

from aiohttp import ClientSession

from config.settings import EXCHANGES_CONFIG, DELAY_BETWEEN_REQUESTS, RETRY_DELAY, MAX_RETRIES
from database.models import Trade, TradingPairInfo
from exchanges.base import ExchangeBase

logger = logging.getLogger(__name__)


class CoinbaseClient(ExchangeBase):
    """Асинхронный клиент для работы с Coinbase Advanced Trade API."""

    def __init__(self, session: ClientSession, rate_limiter):
        """
        Инициализирует клиент Coinbase.

        Args:
            session: Асинхронная HTTP сессия
            rate_limiter: Контроллер rate limits
        """
        super().__init__(session, rate_limiter)
        self.config = EXCHANGES_CONFIG['coinbase']
        self.base_url = self.config['api_url']
        self.weights = self.config['weights']
        self.exchange_name = 'coinbase'

    async def test_connection(self) -> bool:
        """
        Проверяет соединение с Coinbase API.

        Returns:
            True если соединение успешно
        """
        try:
            url = f"{self.base_url}/products"
            async with self.session.get(url) as response:
                if response.status == 200:
                    logger.info("Соединение с Coinbase API установлено")
                    return True
                else:
                    logger.error(f"Ошибка ответа Coinbase: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Не удалось подключиться к Coinbase API: {e}")
            return False

    async def get_products(self) -> Dict:
        """
        Получает информацию о продуктах.

        Returns:
            Словарь с информацией о торговых продуктах
        """
        await self.rate_limiter.acquire(self.weights['products'])

        url = f"{self.base_url}/products"
        async with self.session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    async def get_active_pairs(self) -> Set[str]:
        """
        Получает список всех активных торговых пар.

        Returns:
            Множество символов активных пар
        """
        try:
            data = await self.get_products()

            # Получаем активные продукты
            if isinstance(data, dict) and 'products' in data:
                products = data['products']
            elif isinstance(data, list):
                products = data
            else:
                products = []

            active_pairs = set()
            for product in products:
                # Проверяем что продукт активен
                if (product.get('status', '').upper() in ['ONLINE', 'ACTIVE'] and
                        not product.get('trading_disabled', False)):

                    symbol = product.get('product_id', '')
                    if symbol:
                        active_pairs.add(symbol)

            logger.info(f"Найдено {len(active_pairs)} активных пар на Coinbase")
            return active_pairs

        except Exception as e:
            logger.error(f"Ошибка при получении списка торговых пар Coinbase: {e}")
            raise

    async def get_24hr_tickers(self) -> List[Dict]:
        """
        Получает 24-часовую статистику для всех пар.

        Note: Coinbase Advanced Trade не имеет единого endpoint для всех тикеров,
        поэтому возвращаем пустой список. Статистика берется из продуктов.

        Returns:
            Пустой список (статистика берется из products)
        """
        return []

    async def get_recent_trades(self, symbol: str, retry_count: int = 0) -> List[Dict]:
        """
        Получает последние сделки для указанной торговой пары.

        Args:
            symbol: Символ торговой пары в формате Coinbase (BTC-USD)
            retry_count: Текущее количество попыток

        Returns:
            Список сделок в сыром виде
        """
        try:
            await self.rate_limiter.acquire(self.weights['trades'])
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

            url = f"{self.base_url}/products/{symbol}/trades"
            params = {
                'limit': self.config['trades_limit']
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 429:  # Rate limit
                    if retry_count < MAX_RETRIES:
                        logger.warning(f"Rate limit для {symbol}, повтор через {RETRY_DELAY}с")
                        await asyncio.sleep(RETRY_DELAY)
                        return await self.get_recent_trades(symbol, retry_count + 1)
                    else:
                        return []

                if response.status == 400:
                    error_data = await response.text()
                    logger.debug(f"Неверный символ {symbol}, пропускаем: {error_data}")
                    return []

                response.raise_for_status()
                data = await response.json()

                # Coinbase может возвращать trades в разных форматах
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and 'trades' in data:
                    return data['trades']
                else:
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
        Парсит сырые данные сделки Coinbase в объект Trade.

        Args:
            trade_data: Сырые данные сделки от API
            pair_info: Информация о торговой паре

        Returns:
            Объект Trade
        """
        return Trade.from_coinbase_response(
            trade_data,
            pair_info.symbol,
            pair_info.base_asset,
            pair_info.quote_asset,
            pair_info.quote_price_usd
        )

    def convert_symbol_to_coinbase(self, internal_symbol: str) -> str:
        """
        Конвертирует внутренний символ в формат Coinbase.

        Args:
            internal_symbol: Символ в формате BTCUSDT

        Returns:
            Символ в формате Coinbase (BTC-USD)
        """
        # Импортируем из настроек конверсии
        from config.settings import SYMBOL_CONVERSIONS

        coinbase_conversions = SYMBOL_CONVERSIONS.get('coinbase', {})

        # Если есть прямая конверсия
        if internal_symbol in coinbase_conversions:
            return coinbase_conversions[internal_symbol]

        # Автоматическая конверсия
        conversions = {
            'USDT': 'USD',
            'USDC': 'USD'
        }

        for old_quote, new_quote in conversions.items():
            if internal_symbol.endswith(old_quote):
                base = internal_symbol[:-len(old_quote)]
                return f"{base}-{new_quote}"

        # Стандартные паттерны
        if len(internal_symbol) == 6:
            return f"{internal_symbol[:3]}-{internal_symbol[3:]}"
        elif len(internal_symbol) == 7:
            return f"{internal_symbol[:4]}-{internal_symbol[4:]}"

        return internal_symbol

    def convert_symbol_from_coinbase(self, coinbase_symbol: str) -> str:
        """
        Конвертирует символ Coinbase в наш внутренний формат.

        Args:
            coinbase_symbol: Символ в формате BTC-USD

        Returns:
            Символ в нашем формате (BTCUSDT)
        """
        if '-' in coinbase_symbol:
            parts = coinbase_symbol.split('-')
            if len(parts) == 2:
                base, quote = parts
                # Конвертируем USD обратно в USDT для единообразия
                if quote == 'USD':
                    quote = 'USDT'
                return f"{base}{quote}"

        return coinbase_symbol.replace('-', '')