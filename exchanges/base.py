"""
Базовый класс для всех бирж.
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Dict, Set, Optional

from aiohttp import ClientSession

from config.constants import STABLECOINS, WRAPPED_TOKENS
from config.settings import MIN_VOLUME_USD
from database.models import Trade, TradingPairInfo
from utils.rate_limiter import RateLimiter


class ExchangeBase(ABC):
    """Абстрактный базовый класс для всех бирж."""

    def __init__(self, session: ClientSession, rate_limiter: RateLimiter):
        """
        Инициализирует базовый класс биржи.

        Args:
            session: Асинхронная HTTP сессия
            rate_limiter: Контроллер rate limits
        """
        self.session = session
        self.rate_limiter = rate_limiter
        self.exchange_name = self.__class__.__name__.replace('Client', '').lower()

    @abstractmethod
    async def get_active_pairs(self) -> Set[str]:
        """
        Получает список всех активных торговых пар.

        Returns:
            Множество символов активных пар
        """
        pass

    @abstractmethod
    async def get_24hr_tickers(self) -> List[Dict]:
        """
        Получает 24-часовую статистику для всех пар.

        Returns:
            Список словарей с данными тикеров
        """
        pass

    @abstractmethod
    async def get_recent_trades(self, symbol: str) -> List[Dict]:
        """
        Получает последние сделки для указанной торговой пары.

        Args:
            symbol: Символ торговой пары

        Returns:
            Список сделок в сыром виде
        """
        pass

    @abstractmethod
    async def parse_trade(self, trade_data: Dict, pair_info: TradingPairInfo) -> Trade:
        """
        Парсит сырые данные сделки в объект Trade.

        Args:
            trade_data: Сырые данные сделки от API
            pair_info: Информация о торговой паре

        Returns:
            Объект Trade
        """
        pass

    async def test_connection(self) -> bool:
        """
        Проверяет соединение с API биржи.

        Returns:
            True если соединение успешно
        """
        try:
            # Каждая биржа должна переопределить этот метод
            # с правильным ping endpoint
            return True
        except Exception:
            return False


class ExchangeAnalyzerBase(ABC):
    """Базовый класс для анализаторов данных бирж."""

    def __init__(self):
        """Инициализирует анализатор."""
        self.exchange_name = self.__class__.__name__.replace('Analyzer', '').lower()
        self.quote_prices_usd: Dict[str, Decimal] = {}

    def is_stablecoin_pair(self, base_asset: str, quote_asset: str) -> bool:
        """
        Проверяет, является ли пара парой стейблкоинов.

        Args:
            base_asset: Базовый актив
            quote_asset: Котировочный актив

        Returns:
            True если оба актива - стейблкоины
        """
        return base_asset in STABLECOINS and quote_asset in STABLECOINS

    def is_wrapped_token(self, asset: str) -> bool:
        """
        Проверяет, является ли токен wrapped токеном.

        Args:
            asset: Название актива

        Returns:
            True если актив - wrapped токен
        """
        return asset in WRAPPED_TOKENS or (asset.startswith('W') and len(asset) > 2)

    def should_filter_pair(self, base_asset: str, quote_asset: str) -> bool:
        """
        Определяет, нужно ли отфильтровать пару.

        Args:
            base_asset: Базовый актив
            quote_asset: Котировочный актив

        Returns:
            True если пару нужно исключить
        """
        # Исключаем пары стейблкоинов
        if self.is_stablecoin_pair(base_asset, quote_asset):
            return True

        # Исключаем wrapped токены
        if self.is_wrapped_token(base_asset):
            return True

        return False

    @abstractmethod
    def filter_trading_pairs(
        self,
        exchange_info: Dict,
        tickers: List[Dict]
    ) -> List[TradingPairInfo]:
        """
        Фильтрует торговые пары по критериям.

        Args:
            exchange_info: Информация о парах
            tickers: 24-часовая статистика

        Returns:
            Список отфильтрованных пар с информацией
        """
        pass

    @abstractmethod
    def calculate_volume_usd(self, volume: str, quote_asset: str) -> Decimal:
        """
        Рассчитывает объем в USD.

        Args:
            volume: Объем в котировочной валюте
            quote_asset: Котировочный актив

        Returns:
            Объем в USD
        """
        pass

    @abstractmethod
    def update_quote_prices(self, tickers: List[Dict]) -> None:
        """
        Обновляет цены котировочных активов в USD.

        Args:
            tickers: Список тикеров с ценами
        """
        pass

    def find_large_trades(
        self,
        trades: List[Trade],
        min_value_usd: Decimal
    ) -> List[Trade]:
        """
        Находит крупные сделки.

        Args:
            trades: Список всех сделок
            min_value_usd: Минимальная сумма сделки в USD

        Returns:
            Список крупных сделок
        """
        return [
            trade for trade in trades
            if trade.value_usd >= min_value_usd
        ]