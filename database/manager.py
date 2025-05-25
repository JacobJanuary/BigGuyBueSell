"""
Менеджер для работы с MySQL базой данных.
"""
import logging
from datetime import datetime
from typing import List, Tuple, Optional

import aiomysql

from config.settings import MYSQL_CONFIG
from database.models import Trade

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер для работы с MySQL базой данных."""

    def __init__(self):
        """Инициализирует менеджер базы данных."""
        self.pool: Optional[aiomysql.Pool] = None

    async def connect(self) -> None:
        """Создает пул соединений с базой данных."""
        try:
            self.pool = await aiomysql.create_pool(
                **MYSQL_CONFIG,
                autocommit=True,
                minsize=1,
                maxsize=10
            )
            logger.info("Подключение к MySQL установлено")
        except Exception as e:
            logger.error(f"Ошибка подключения к MySQL: {e}")
            raise

    async def close(self) -> None:
        """Закрывает пул соединений."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("Соединение с MySQL закрыто")

    async def create_tables(self) -> None:
        """Создает необходимые таблицы, если они не существуют."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS large_trades (
            id BIGINT PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            base_asset VARCHAR(10),
            price DECIMAL(20, 8) NOT NULL,
            quantity DECIMAL(20, 8) NOT NULL,
            value_usd DECIMAL(20, 2) NOT NULL,
            quote_asset VARCHAR(10) NOT NULL,
            is_buyer_maker BOOLEAN NOT NULL,
            trade_time DATETIME NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_symbol (symbol),
            INDEX idx_base_asset (base_asset),
            INDEX idx_value_usd (value_usd),
            INDEX idx_trade_time (trade_time)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Сначала создаем таблицу если не существует
                await cursor.execute(create_table_sql)

                # Проверяем, есть ли колонка base_asset
                check_column_sql = """
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'large_trades' 
                AND COLUMN_NAME = 'base_asset'
                """
                await cursor.execute(check_column_sql, (MYSQL_CONFIG['db'],))
                result = await cursor.fetchone()

                if result[0] == 0:
                    # Колонки нет, нужно добавить
                    logger.info("Добавляем колонку base_asset в существующую таблицу...")
                    await cursor.execute("""
                        ALTER TABLE large_trades 
                        ADD COLUMN base_asset VARCHAR(10) AFTER symbol
                    """)
                    logger.info("Колонка base_asset добавлена")

                logger.info("Таблица large_trades готова к работе")

    async def save_trades(self, trades: List[Trade]) -> Tuple[int, int]:
        """
        Сохраняет сделки в базу данных.

        Args:
            trades: Список сделок для сохранения

        Returns:
            Кортеж (количество новых сделок, количество дубликатов)
        """
        if not trades:
            return 0, 0

        insert_sql = """
        INSERT IGNORE INTO large_trades 
        (id, symbol, base_asset, price, quantity, value_usd, quote_asset, is_buyer_maker, trade_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        # Проверяем существующие ID
        trade_ids = [int(trade.id) for trade in trades]  # Преобразуем в int для Binance
        placeholders = ','.join(['%s'] * len(trade_ids))
        check_sql = f"SELECT id FROM large_trades WHERE id IN ({placeholders})"

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Получаем существующие ID
                await cursor.execute(check_sql, trade_ids)
                existing_ids = {row[0] for row in await cursor.fetchall()}

                # Фильтруем новые сделки
                new_trades = []
                duplicate_count = 0

                for trade in trades:
                    if int(trade.id) in existing_ids:
                        duplicate_count += 1
                        logger.info(
                            f"Дубликат: сделка {trade.symbol} ID:{trade.id} "
                            f"на сумму ${trade.value_usd:,.2f} уже в БД"
                        )
                    else:
                        new_trades.append(trade)

                # Сохраняем только новые сделки
                if new_trades:
                    values = [
                        (
                            int(trade.id),  # Binance использует числовые ID
                            trade.symbol,
                            trade.base_asset,  # Добавляем base_asset
                            float(trade.price),
                            float(trade.quantity),
                            float(trade.value_usd),
                            trade.quote_asset,
                            trade.is_buyer_maker,
                            trade.trade_datetime
                        )
                        for trade in new_trades
                    ]

                    await cursor.executemany(insert_sql, values)
                    saved_count = cursor.rowcount

                    if saved_count > 0:
                        logger.info(f"Сохранено {saved_count} новых сделок в БД")
                        # Выводим информацию о новых сделках
                        for trade in new_trades[:5]:
                            print(f"  НОВАЯ: {trade.symbol} ${trade.value_usd:,.2f} "
                                  f"в {trade.trade_datetime.strftime('%H:%M:%S')}")
                        if len(new_trades) > 5:
                            print(f"  ... и еще {len(new_trades) - 5} сделок")

                    return saved_count, duplicate_count
                else:
                    return 0, duplicate_count

    async def get_recent_trades_count(self, hours: int = 24) -> int:
        """
        Получает количество сделок за последние N часов.

        Args:
            hours: Количество часов

        Returns:
            Количество сделок
        """
        query = """
        SELECT COUNT(*) 
        FROM large_trades 
        WHERE trade_time > DATE_SUB(NOW(), INTERVAL %s HOUR)
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, (hours,))
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def get_statistics(self) -> dict:
        """
        Получает общую статистику.

        Returns:
            Словарь со статистикой
        """
        query = """
        SELECT 
            COUNT(*) as trade_count,
            SUM(value_usd) as total_volume,
            AVG(value_usd) as avg_trade_size,
            MAX(value_usd) as max_trade_size
        FROM large_trades
        WHERE trade_time > DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """

        stats = {}
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query)
                row = await cursor.fetchone()
                if row:
                    stats = {
                        'trade_count': row[0] or 0,
                        'total_volume': float(row[1]) if row[1] else 0,
                        'avg_trade_size': float(row[2]) if row[2] else 0,
                        'max_trade_size': float(row[3]) if row[3] else 0
                    }
        return stats