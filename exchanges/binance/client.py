"""
Клиент для работы с Binance API.
"""
import asyncio
import logging
from typing import Dict, List, Set

from aiohttp import ClientSession

from config.settings import EXCHANGES_CONFIG, DELAY_BETWEEN_REQUESTS, RETRY_DELAY, MAX_RETRIES
from database.models import Trade, TradingPairInfo
from exchanges.base import ExchangeBase

logger = logging.getLogger(__name__)


class BinanceClient(ExchangeBase):
    """Асинхронный клиент для работы с Binance API."""

    def __init__(self, session: ClientSession, rate_limiter):
        """
        Инициализирует клиент Binance.

        Args:
            session: Асинхронная HTTP сессия
            rate_limiter: Контроллер rate limits
        """
        super().__init__(session, rate_limiter)
        self.config = EXCHANGES_CONFIG['binance']
        self.base_url = self.config['api_url']
        self.weights = self.config['weights']
        self.exchange_name = 'binance'

    async def test_connection(self) -> bool:
        """
        Проверяет соединение с Binance API.

        Returns:
            True если соединение успешно
        """
        try:
            url = f"{self.base_url}/api/v3/ping"
            async with self.session.get(url) as response:
                response.raise_for_status()
                logger.info("Соединение с Binance API установлено")
                return True
        except Exception as e:
            logger.error(f"Не удалось подключиться к Binance API: {e}")
            return False

    async def get_exchange_info(self) -> Dict:
        """
        Получает информацию о бирже.

        Returns:
            Словарь с информацией о торговых парах
        """
        await self.rate_limiter.acquire(self.weights['exchange_info'])

        url = f"{self.base_url}/api/v3/exchangeInfo"
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
            data = await self.get_exchange_info()

            # Фильтруем только спотовые пары со статусом TRADING
            spot_pairs = {
                symbol['symbol']
                for symbol in data['symbols']
                if symbol['status'] == 'TRADING' and symbol['isSpotTradingAllowed']
            }

            logger.info(f"Найдено {len(spot_pairs)} активных спотовых пар на Binance")
            return spot_pairs

        except Exception as e:
            logger.error(f"Ошибка при получении списка торговых пар Binance: {e}")
            raise

    async def get_24hr_tickers(self) -> List[Dict]:
        """
        Получает 24-часовую статистику для всех пар.

        Returns:
            Список словарей с данными тикеров
        """
        await self.rate_limiter.acquire(self.weights['tickers'])

        url = f"{self.base_url}/api/v3/ticker/24hr"
        async with self.session.get(url) as response:
            response.raise_for_status()
            return await response.json()

    async def get_recent_trades(self, symbol: str, retry_count: int = 0) -> List[Dict]:
        """
        Получает последние сделки для указанной торговой пары.

        Args:
            symbol: Символ торговой пары
            retry_count: Текущее количество попыток

        Returns:
            Список сделок в сыром виде
        """
        try:
            await self.rate_limiter.acquire(self.weights['trades'])
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS)

            url = f"{self.base_url}/api/v3/trades"
            params = {
                'symbol': symbol,
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

                if response.status == 400:
                    error_data = await response.json()
                    if error_data.get('code') == -1121:  # Invalid symbol
                        logger.debug(f"Неверный символ {symbol}, пропускаем")
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
        Парсит сырые данные сделки Binance в объект Trade.

        Args:
            trade_data: Сырые данные сделки от API
            pair_info: Информация о торговой паре

        Returns:
            Объект Trade
        """
        return Trade.from_binance_response(
            trade_data,
            pair_info.symbol,
            pair_info.base_asset,
            pair_info.quote_asset,
            pair_info.quote_price_usd
        )