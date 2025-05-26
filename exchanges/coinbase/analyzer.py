"""
Анализатор данных для Coinbase.
"""
import logging
from decimal import Decimal
from typing import Dict, List

from config.constants import STABLECOINS, WRAPPED_TOKENS, DEFAULT_QUOTE_PRICES_USD
from config.settings import MIN_VOLUME_USD
from database.models import TradingPairInfo
from exchanges.base import ExchangeAnalyzerBase

logger = logging.getLogger(__name__)


class CoinbaseAnalyzer(ExchangeAnalyzerBase):
    """Анализатор торговых данных Coinbase."""

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
            tickers: Список тикеров с данными
        """
        # Обновляем цены основных котировочных активов
        for ticker in tickers:
            product_info = ticker.get('product_info', {})
            product_id = product_info.get('id', '')

            try:
                last_price = ticker.get('price', '0')
                if not last_price:
                    continue

                price_decimal = Decimal(str(last_price))

                # BTC price in USD
                if product_id == 'BTC-USD':
                    self.quote_prices_usd['BTC'] = price_decimal
                # ETH price in USD
                elif product_id == 'ETH-USD':
                    self.quote_prices_usd['ETH'] = price_decimal
                # Дополнительные котировочные активы
                elif product_id == 'BTC-USDT':
                    self.quote_prices_usd['BTC'] = price_decimal
                elif product_id == 'ETH-USDT':
                    self.quote_prices_usd['ETH'] = price_decimal

            except (ValueError, TypeError) as e:
                logger.debug(f"Ошибка обработки цены для {product_id}: {e}")
                continue

    def _get_conversion_rate_to_usd(self, currency_code: str) -> Decimal:
        """
        Получает курс конвертации указанной валюты в USD.

        Args:
            currency_code: Код валюты (например, "BTC", "ETH")

        Returns:
            Курс конвертации в USD
        """
        if not currency_code:
            return Decimal('0')

        return self.quote_prices_usd.get(currency_code, Decimal('0'))

    def filter_trading_pairs(
        self,
        products_info: List[Dict],
        tickers: List[Dict]
    ) -> List[TradingPairInfo]:
        """
        Фильтрует торговые пары по критериям.

        Args:
            products_info: Информация о продуктах
            tickers: Тикеры с данными

        Returns:
            Список отфильтрованных пар с информацией
        """
        # Создаем словарь тикеров для быстрого доступа
        ticker_map = {}
        for ticker in tickers:
            product_info = ticker.get('product_info', {})
            product_id = product_info.get('id')
            if product_id:
                ticker_map[product_id] = ticker

        # Обновляем цены котировочных активов
        self.update_quote_prices(tickers)

        filtered_pairs = []

        for product in products_info:
            try:
                # Проверяем, что продукт активен
                if (product.get('status') != 'online' or
                    product.get('trading_disabled', False) or
                    product.get('auction_mode', False)):
                    continue

                product_id = product['id']
                base_asset = product['base_currency']
                quote_asset = product['quote_currency']

                # Пропускаем пары стейблкоинов и wrapped токены
                if self.should_filter_pair(base_asset, quote_asset):
                    continue

                # Получаем данные тикера
                ticker = ticker_map.get(product_id)
                if not ticker:
                    continue

                # Рассчитываем объем в USD
                # В Coinbase объем в тикере указан как volume (24h в базовой валюте)
                volume_24h = ticker.get('volume', '0')
                price = ticker.get('price', '0')

                try:
                    volume_decimal = Decimal(str(volume_24h))
                    price_decimal = Decimal(str(price))

                    # Объем в котировочной валюте
                    quote_volume = volume_decimal * price_decimal

                    # Конвертируем в USD
                    volume_usd = self.calculate_volume_usd(str(quote_volume), quote_asset)

                except (ValueError, TypeError):
                    logger.debug(f"Ошибка расчета объема для {product_id}")
                    continue

                # Фильтруем по минимальному объему
                if volume_usd < Decimal(str(MIN_VOLUME_USD)):
                    continue

                quote_price_usd = self._get_conversion_rate_to_usd(quote_asset)

                # Проверяем что цена котировочного актива известна
                if quote_price_usd <= 0:
                    logger.debug(f"Неизвестная цена для {quote_asset}, пропускаем {product_id}")
                    continue

                filtered_pairs.append(TradingPairInfo(
                    exchange='coinbase',  # Явно указываем название биржи
                    symbol=product_id,
                    base_asset=base_asset,
                    quote_asset=quote_asset,
                    volume_24h_usd=volume_usd,
                    quote_price_usd=quote_price_usd
                ))

                # Добавляем отладочную информацию для первых нескольких пар
                if len(filtered_pairs) <= 3:
                    logger.info(f"Добавлена пара Coinbase: {product_id} с объемом ${volume_usd:,.0f}")

            except Exception as e:
                logger.error(f"Ошибка при обработке продукта {product.get('id', 'unknown')}: {e}")
                continue

        logger.info(
            f"Отфильтровано {len(filtered_pairs)} пар Coinbase "
            f"с объемом > ${MIN_VOLUME_USD:,}"
        )

        return filtered_pairs