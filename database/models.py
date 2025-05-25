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
        price: Цена сделки
        quantity: Количество в сделке
        value_usd: Примерная стоимость в USD
        quote_asset: Котировочный актив
        is_buyer_maker: True если покупатель был мейкером
        trade_time: Время сделки (timestamp в миллисекундах)
    """
    id: str  # Строка для совместимости с разными биржами
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
        return (
            int(self.id),  # Binance использует числовые ID
            self.symbol,
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
            symbol=symbol,
            base_asset=base_asset,
            price=price,
            quantity=qty,
            value_usd=value_usd,
            quote_asset=quote_asset,
            is_buyer_maker=data['isBuyerMaker'],
            trade_time=data['time']
        )


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