"""
Анализатор данных для Binance.
"""
import logging
from decimal import Decimal
from typing import Dict, List

from config.constants import STABLECOINS, WRAPPED_TOKENS, DEFAULT_QUOTE_PRICES_USD
from config.settings import MIN_VOLUME_USD
from database.models import TradingPairInfo
from exchanges.base import ExchangeAnalyzerBase

logger = logging.getLogger(__name__)


class BinanceAnalyzer(ExchangeAnalyzerBase):
    """Анализатор торговых данных Binance."""

    def __init__(self):
        """Инициализирует анализатор."""
        super().__init__()
        self.quote_prices_usd = DEFAULT_QUOTE_PRICES_USD.copy()

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

    def calculate_volume_usd(self, volume: str, quote_asset: str) -> Decimal:
        """
        Рассчитывает объем в USD.

        Args:
            volume: Объем в котировочной валюте
            quote_asset: Котировочный актив

        Returns:
            Объем в USD
        """
        volume_decimal = Decimal(str(volume))  # Преобразуем в строку сначала
        quote_price = self.quote_prices_usd.get(quote_asset, Decimal('0'))
        return volume_decimal * quote_price

    def update_quote_prices(self, tickers: List[Dict]) -> None:
        """
        Обновляет цены котировочных активов в USD.

        Args:
            tickers: Список тикеров с 24hr данными
        """
        # Обновляем цены основных котировочных активов
        for ticker in tickers:
            symbol = ticker['symbol']

            # BTC price in USDT
            if symbol == 'BTCUSDT':
                self.quote_prices_usd['BTC'] = Decimal(str(ticker['lastPrice']))
            # ETH price in USDT
            elif symbol == 'ETHUSDT':
                self.quote_prices_usd['ETH'] = Decimal(str(ticker['lastPrice']))
            # BNB price in USDT
            elif symbol == 'BNBUSDT':
                self.quote_prices_usd['BNB'] = Decimal(str(ticker['lastPrice']))

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
        # Создаем словарь тикеров для быстрого доступа
        ticker_map = {t['symbol']: t for t in tickers}

        # Обновляем цены котировочных активов
        self.update_quote_prices(tickers)

        filtered_pairs = []

        for symbol_info in exchange_info['symbols']:
            try:
                # Проверяем, что это спотовая пара и она активна
                if (symbol_info['status'] != 'TRADING' or
                    not symbol_info['isSpotTradingAllowed']):
                    continue

                symbol = symbol_info['symbol']
                base_asset = symbol_info['baseAsset']
                quote_asset = symbol_info['quoteAsset']

                # Пропускаем пары стейблкоинов
                if self.is_stablecoin_pair(base_asset, quote_asset):
                    continue

                # Пропускаем wrapped токены
                if self.is_wrapped_token(base_asset):
                    continue

                # Получаем данные тикера
                ticker = ticker_map.get(symbol)
                if not ticker:
                    continue

                # Рассчитываем объем в USD
                quote_volume = ticker.get('quoteVolume', '0')
                volume_usd = self.calculate_volume_usd(quote_volume, quote_asset)

                # Фильтруем по минимальному объему
                if volume_usd < Decimal(str(MIN_VOLUME_USD)):
                    continue

                quote_price_usd = self.quote_prices_usd.get(quote_asset, Decimal('0'))

                filtered_pairs.append(TradingPairInfo(
                    exchange='binance',
                    symbol=symbol,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                    volume_24h_usd=volume_usd,
                    quote_price_usd=quote_price_usd
                ))
            except Exception as e:
                logger.error(f"Ошибка при обработке пары {symbol_info.get('symbol', 'unknown')}: {e}")
                logger.error(f"Тип ошибки: {type(e).__name__}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                continue

        logger.info(
            f"Отфильтровано {len(filtered_pairs)} пар Binance "
            f"с объемом > ${MIN_VOLUME_USD:,}"
        )

        return filtered_pairs