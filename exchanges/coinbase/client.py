"""
Клиент для работы с Coinbase Exchange API.
"""
import asyncio
import logging
from typing import Dict, List, Set

from aiohttp import ClientSession

from config.settings import EXCHANGES_CONFIG, DELAY_BETWEEN_REQUESTS, RETRY_DELAY, MAX_RETRIES
from database.models import Trade, TradingPairInfo
from exchanges.base import ExchangeBase

logger = logging.getLogger(__name__)


class CoinbaseClient(ExchangeBase):
    """Асинхронный клиент для работы с Coinbase Exchange API."""

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
            url = f"{self.base_url}/time"
            async with self.session.get(url) as response:
                if response.status == 200:
                    logger.info("Соединение с Coinbase API установлено")
                    return True
                logger.error(f"Ошибка ответа Coinbase: {response.status}")
                return False
        except Exception as e:
            logger.error(f"Не удалось подключиться к Coinbase API: {e}")
            return False

    async def get_products_info(self) -> Dict:
        """
        Получает информацию о всех продуктах (торговых парах).

        Returns:
            Список словарей с информацией о торговых парах
        """
        await self.rate_limiter.acquire(self.weights['exchange_info'])

        url = f"{self.base_url}/products"
        async with self.session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    async def get_active_pairs(self) -> Set[str]:
        """
        Получает список всех активных спотовых торговых пар.

        Returns:
            Множество символов активных спотовых пар
        """
        try:
            products = await self.get_products_info()

            # Фильтруем только спотовые пары со статусом online
            spot_pairs = {
                product['id']
                for product in products
                if (product.get('status') == 'online' and
                    not product.get('trading_disabled', False) and
                    not product.get('auction_mode', False) and
                    product.get('product_type', '').lower() in ['spot', ''])
            }

            logger.info(f"Найдено {len(spot_pairs)} активных спотовых пар на Coinbase")
            return spot_pairs

        except Exception as e:
            logger.error(f"Ошибка при получении списка торговых пар Coinbase: {e}")
            raise

    async def get_product_ticker(self, product_id: str) -> Dict:
        """
        Получает тикер для конкретной торговой пары.

        Args:
            product_id: Идентификатор продукта (например, "BTC-USD")

        Returns:
            Словарь с данными тикера
        """
        await self.rate_limiter.acquire(self.weights['tickers'])

        url = f"{self.base_url}/products/{product_id}/ticker"
        async with self.session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    async def get_24hr_tickers(self) -> List[Dict]:
        """
        Получает 24-часовую статистику для всех пар.

        Returns:
            Список словарей с данными тикеров
        """
        try:
            products = await self.get_products_info()
            tickers = []

            # Получаем тикеры для активных пар
            for product in products:
                if (product.get('status') == 'online' and
                    not product.get('trading_disabled', False)):
                    try:
                        ticker = await self.get_product_ticker(product['id'])
                        # Добавляем информацию о продукте к тикеру
                        ticker['product_info'] = product
                        tickers.append(ticker)
                    except Exception as e:
                        logger.debug(f"Ошибка получения тикера для {product['id']}: {e}")
                        continue

            return tickers

        except Exception as e:
            logger.error(f"Ошибка при получении тикеров Coinbase: {e}")
            raise

    async def get_recent_trades(self, symbol: str, retry_count: int = 0) -> List[Dict]:
        """
        Получает последние сделки для указанной торговой пары.

        Args:
            symbol: Символ торговой пары (например, "BTC-USD")
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
                if response.status in [429, 418]:  # Rate limit errors
                    if retry_count < MAX_RETRIES:
                        retry_after = int(response.headers.get('Retry-After', RETRY_DELAY))
                        logger.warning(f"Rate limit для {symbol}, повтор через {retry_after}с")
                        await asyncio.sleep(retry_after)
                        return await self.get_recent_trades(symbol, retry_count + 1)
                    else:
                        return []

                if response.status == 404:
                    logger.debug(f"Продукт {symbol} не найден, пропускаем")
                    return []

                if response.status == 400:
                    logger.debug(f"Неверный запрос для {symbol}, пропускаем")
                    return []

                response.raise_for_status()
                return await response.json()

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