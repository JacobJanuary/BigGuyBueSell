"""
Клиент для работы с Bybit API v5.
"""
import asyncio
import logging
from typing import Dict, List, Set

from aiohttp import ClientSession

from config.settings import EXCHANGES_CONFIG, DELAY_BETWEEN_REQUESTS, RETRY_DELAY, MAX_RETRIES
from database.models import Trade, TradingPairInfo
from exchanges.base import ExchangeBase

logger = logging.getLogger(__name__)


class BybitClient(ExchangeBase):
    """Асинхронный клиент для работы с Bybit API v5."""

    def __init__(self, session: ClientSession, rate_limiter):
        """
        Инициализирует клиент Bybit.

        Args:
            session: Асинхронная HTTP сессия
            rate_limiter: Контроллер rate limits
        """
        super().__init__(session, rate_limiter)
        self.config = EXCHANGES_CONFIG['bybit']
        self.base_url = self.config['api_url']
        self.weights = self.config['weights']

    async def test_connection(self) -> bool:
        """
        Проверяет соединение с Bybit API.

        Returns:
            True если соединение успешно
        """
        try:
            url = f"{self.base_url}/v5/market/time"
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('retCode') == 0:
                        logger.info("Соединение с Bybit API установлено")
                        return True
                logger.error(f"Ошибка ответа Bybit: {response.status}")
                return False
        except Exception as e:
            logger.error(f"Не удалось подключиться к Bybit API: {e}")
            return False

    async def get_instruments_info(self) -> Dict:
        """
        Получает информацию о торговых инструментах.

        Returns:
            Словарь с информацией о торговых парах
        """
        await self.rate_limiter.acquire(self.weights['exchange_info'])

        url = f"{self.base_url}/v5/market/instruments-info"
        params = {'category': 'spot'}

        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            if data.get('retCode') != 0:
                raise Exception(f"Bybit API error: {data.get('retMsg', 'Unknown error')}")

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
                item['symbol']
                for item in data['result']['list']
                if item['status'] == 'Trading'
            }

            logger.info(f"Найдено {len(spot_pairs)} активных спотовых пар на Bybit")
            return spot_pairs

        except Exception as e:
            logger.error(f"Ошибка при получении списка торговых пар Bybit: {e}")
            raise

    async def get_24hr_tickers(self) -> List[Dict]:
        """
        Получает 24-часовую статистику для всех пар.

        Returns:
            Список словарей с данными тикеров
        """
        await self.rate_limiter.acquire(self.weights['tickers'])

        url = f"{self.base_url}/v5/market/tickers"
        params = {'category': 'spot'}

        async with self.session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            if data.get('retCode') != 0:
                raise Exception(f"Bybit API error: {data.get('retMsg', 'Unknown error')}")

            return data['result']['list']

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

            url = f"{self.base_url}/v5/market/recent-trade"
            # Bybit ограничивает до 60 сделок за запрос для спота
            params = {
                'category': 'spot',
                'symbol': symbol,
                'limit': min(self.config['trades_limit'], 60)
            }

            async with self.session.get(url, params=params) as response:
                # Обработка rate limit (403 в Bybit)
                if response.status == 403:
                    if retry_count < MAX_RETRIES:
                        logger.warning(f"Rate limit для {symbol}, повтор через {RETRY_DELAY}с")
                        await asyncio.sleep(RETRY_DELAY)
                        return await self.get_recent_trades(symbol, retry_count + 1)
                    return []

                if response.status == 400:
                    data = await response.json()
                    # 10001 - Invalid symbol в Bybit
                    if data.get('retCode') == 10001:
                        logger.debug(f"Неверный символ {symbol}, пропускаем")
                    return []

                response.raise_for_status()
                data = await response.json()

                if data.get('retCode') == 0:
                    return data['result']['list']
                else:
                    logger.warning(f"Bybit API error for {symbol}: {data.get('retMsg')}")
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
        Парсит сырые данные сделки Bybit в объект Trade.

        Args:
            trade_data: Сырые данные сделки от API
            pair_info: Информация о торговой паре

        Returns:
            Объект Trade
        """
        from decimal import Decimal

        price = Decimal(str(trade_data['price']))
        size = Decimal(str(trade_data['size']))
        value_usd = price * size * pair_info.quote_price_usd

        return Trade(
            id=str(trade_data['execId']),  # В Bybit используется execId как уникальный ID
            symbol=pair_info.symbol,
            base_asset=pair_info.base_asset,
            price=price,
            quantity=size,
            value_usd=value_usd,
            quote_asset=pair_info.quote_asset,
            is_buyer_maker=trade_data['side'] == 'Sell',  # В Bybit Sell = buyer maker
            trade_time=int(trade_data['time'])  # Bybit возвращает время в миллисекундах
        )