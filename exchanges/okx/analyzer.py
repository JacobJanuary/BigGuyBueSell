"""
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
