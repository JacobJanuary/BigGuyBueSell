"""
Модели данных для торговых сделок.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional


@dataclass
class Trade:
    """
    Представление торговой сделки.

    Attributes:
        id: Уникальный идентификатор сделки
        exchange: Название биржи
        symbol: Символ торговой пары
        base_asset: Базовый актив
        price: Цена сделки
        quantity: Количество в сделке
        value_usd: Примерная стоимость в USD
        quote_asset: Котировочный актив
        is_buyer_maker: True если покупатель был мейкером
        trade_time: Время сделки (timestamp в миллисекундах)
    """
    id: str  # Строка для совместимости с разными биржами
    exchange: str  # Название биржи
    symbol: str
    base_asset: str
    price: Decimal
    quantity: Decimal
    value_usd: Decimal
    quote_asset: str
    is_buyer_maker: bool
    trade_time: int

    @property
    def trade_datetime(self) -> datetime:
        """Возвращает время сделки как datetime объект."""
        return datetime.fromtimestamp(self.trade_time / 1000)

    @property
    def trade_type(self) -> str:
        """Возвращает тип сделки (Покупка/Продажа)."""
        return 'Продажа' if self.is_buyer_maker else 'Покупка'

    def to_db_values(self) -> tuple:
        """Преобразует объект в кортеж значений для БД."""
        # Для более надежной работы с ID разных типов
        try:
            # Пытаемся преобразовать в int
            trade_id = int(self.id) if self.id.isdigit() else hash(self.id) % (2**63 - 1)
        except (ValueError, AttributeError):
            # Если не получается, используем хеш
            trade_id = hash(str(self.id)) % (2**63 - 1)

        return (
            trade_id,
            self.exchange,  # Это поле должно содержать правильное значение
            self.symbol,
            self.base_asset,
            float(self.price),
            float(self.quantity),
            float(self.value_usd),
            self.quote_asset,
            self.is_buyer_maker,
            self.trade_datetime
        )

    @classmethod
    def from_binance_response(
        cls,
        data: Dict,
        symbol: str,
        base_asset: str,
        quote_asset: str,
        quote_price_usd: Decimal
    ) -> 'Trade':
        """
        Создает объект Trade из ответа Binance API.

        Args:
            data: Словарь с данными сделки от API
            symbol: Символ торговой пары
            base_asset: Базовый актив
            quote_asset: Котировочный актив
            quote_price_usd: Цена котировочного актива в USD

        Returns:
            Объект Trade
        """
        price = Decimal(str(data['price']))
        qty = Decimal(str(data['qty']))
        value_usd = price * qty * quote_price_usd

        return cls(
            id=str(data['id']),
            exchange='binance',
            symbol=symbol,
            base_asset=base_asset,
            price=price,
            quantity=qty,
            value_usd=value_usd,
            quote_asset=quote_asset,
            is_buyer_maker=data['isBuyerMaker'],
            trade_time=data['time']
        )

    @classmethod
    def from_bybit_response(
        cls,
        data: Dict,
        symbol: str,
        base_asset: str,
        quote_asset: str,
        quote_price_usd: Decimal
    ) -> 'Trade':
        """
        Создает объект Trade из ответа Bybit API.

        Args:
            data: Словарь с данными сделки от API
            symbol: Символ торговой пары
            base_asset: Базовый актив
            quote_asset: Котировочный актив
            quote_price_usd: Цена котировочного актива в USD

        Returns:
            Объект Trade
        """
        price = Decimal(str(data['price']))
        size = Decimal(str(data['size']))
        value_usd = price * size * quote_price_usd

        return cls(
            id=str(data['execId']),
            exchange='bybit',
            symbol=symbol,
            base_asset=base_asset,
            price=price,
            quantity=size,
            value_usd=value_usd,
            quote_asset=quote_asset,
            is_buyer_maker=data['side'] == 'Sell',  # В Bybit Sell = buyer maker
            trade_time=int(data['time'])
        )

    @classmethod
    def from_coinbase_response(
        cls,
        data: Dict,
        symbol: str,
        base_asset: str,
        quote_asset: str,
        quote_price_usd: Decimal
    ) -> 'Trade':
        """
        Создает объект Trade из ответа Coinbase API.

        Args:
            data: Словарь с данными сделки от API
            symbol: Символ торговой пары
            base_asset: Базовый актив
            quote_asset: Котировочный актив
            quote_price_usd: Цена котировочного актива в USD

        Returns:
            Объект Trade
        """
        price = Decimal(str(data['price']))
        size = Decimal(str(data['size']))
        value_usd = price * size * quote_price_usd

        # В Coinbase время в ISO формате, конвертируем в timestamp
        from dateutil.parser import parse
        trade_datetime = parse(data['time'])
        trade_time_ms = int(trade_datetime.timestamp() * 1000)

        trade = cls(
            id=str(data['trade_id']),
            exchange='coinbase',  # Явно указываем exchange
            symbol=symbol,
            base_asset=base_asset,
            price=price,
            quantity=size,
            value_usd=value_usd,
            quote_asset=quote_asset,
            is_buyer_maker=data['side'] == 'sell',  # В Coinbase sell = buyer maker
            trade_time=trade_time_ms
        )

        # Отладочная информация для первых сделок
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"Создана сделка Coinbase: {trade.exchange} - {symbol} - ${value_usd:.2f}")

        return trade


@dataclass
class TradingPairInfo:
    """Информация о торговой паре."""
    exchange: str
    symbol: str
    base_asset: str
    quote_asset: str
    volume_24h_usd: Decimal
    quote_price_usd: Decimal

    @property
    def is_active(self) -> bool:
        """Проверяет, активна ли пара (есть объем торгов)."""
        return self.volume_24h_usd > Decimal('0')