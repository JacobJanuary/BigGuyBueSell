"""
Исправленный клиент для работы с OKX API.
"""
import asyncio
import logging
import ssl
import certifi
from typing import Dict, List, Set

from aiohttp import ClientSession

# Исправленные импорты с fallback
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


def create_ssl_context_for_okx():
    """Создает SSL контекст для OKX API."""
    try:
        # Используем certifi для получения актуальных сертификатов
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        return ssl_context
    except Exception:
        # Fallback: стандартный SSL контекст
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            return ssl_context
        except Exception:
            # Последний resort: отключение SSL проверки
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            return ssl_context


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
            # ИСПРАВЛЕНО: передаем ssl_context только один раз
            async with self.session.get(url, ssl=create_ssl_context_for_okx()) as response:
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

        # ИСПРАВЛЕНО: передаем ssl_context только один раз
        async with self.session.get(url, params=params, ssl=create_ssl_context_for_okx()) as response:
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

        # ИСПРАВЛЕНО: передаем ssl_context только один раз
        async with self.session.get(url, params=params, ssl=create_ssl_context_for_okx()) as response:
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

            # ИСПРАВЛЕНО: передаем ssl_context только один раз
            async with self.session.get(url, params=params, ssl=create_ssl_context_for_okx()) as response:
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