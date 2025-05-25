"""
Анализатор данных для Bybit.
"""
import logging
from decimal import Decimal
from typing import Dict, List

from config.constants import STABLECOINS, WRAPPED_TOKENS, DEFAULT_QUOTE_PRICES_USD
from config.settings import MIN_VOLUME_USD
from database.models import TradingPairInfo
from exchanges.base import ExchangeAnalyzerBase

logger = logging.getLogger(__name__)


class BybitAnalyzer(ExchangeAnalyzerBase):
    """Анализатор торговых данных Bybit."""

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
        volume_decimal = Decimal(str(volume))
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
            # BNB price in USDT (Bybit может не иметь BNB)
            elif symbol == 'BNBUSDT':
                self.quote_prices_usd['BNB'] = Decimal(str(ticker['lastPrice']))
            # Дополнительные котировочные активы для Bybit
            elif symbol == 'USDCUSDT':
                self.quote_prices_usd['USDC'] = Decimal(str(ticker['lastPrice']))

    def filter_trading_pairs(
            self,
            instruments_info: Dict,
            tickers: List[Dict]
    ) -> List[TradingPairInfo]:
        """
        Фильтрует торговые пары по критериям.

        Args:
            instruments_info: Информация об инструментах от Bybit
            tickers: 24-часовая статистика

        Returns:
            Список отфильтрованных пар с информацией
        """
        # Создаем словарь тикеров для быстрого доступа
        ticker_map = {t['symbol']: t for t in tickers}

        # Обновляем цены котировочных активов
        self.update_quote_prices(tickers)

        filtered_pairs = []

        try:
            # В Bybit данные находятся в result.list
            instruments = instruments_info.get('result', {}).get('list', [])

            for instrument in instruments:
                try:
                    # Проверяем, что инструмент активен
                    if instrument.get('status') != 'Trading':
                        continue

                    symbol = instrument['symbol']
                    base_asset = instrument['baseCoin']  # В Bybit используется baseCoin
                    quote_asset = instrument['quoteCoin']  # В Bybit используется quoteCoin

                    # Пропускаем пары стейблкоинов
                    if self.should_filter_pair(base_asset, quote_asset):
                        continue

                    # Получаем данные тикера
                    ticker = ticker_map.get(symbol)
                    if not ticker:
                        continue

                    # В Bybit объем указан как turnover24h (в quote currency)
                    quote_volume = ticker.get('turnover24h', '0')
                    volume_usd = self.calculate_volume_usd(quote_volume, quote_asset)

                    # Фильтруем по минимальному объему
                    if volume_usd < Decimal(str(MIN_VOLUME_USD)):
                        continue

                    quote_price_usd = self.quote_prices_usd.get(quote_asset, Decimal('0'))

                    # Проверяем что цена котировочного актива известна
                    if quote_price_usd <= 0:
                        logger.debug(f"Неизвестная цена для {quote_asset}, пропускаем {symbol}")
                        continue

                    filtered_pairs.append(TradingPairInfo(
                        exchange='bybit',
                        symbol=symbol,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        volume_24h_usd=volume_usd,
                        quote_price_usd=quote_price_usd
                    ))

                except Exception as e:
                    logger.error(f"Ошибка при обработке инструмента {instrument.get('symbol', 'unknown')}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Ошибка при обработке данных Bybit: {e}")

        logger.info(
            f"Отфильтровано {len(filtered_pairs)} пар Bybit "
            f"с объемом > ${MIN_VOLUME_USD:,}"
        )

        return filtered_pairs