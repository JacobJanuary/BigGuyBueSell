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
            exchange VARCHAR(20) NOT NULL DEFAULT 'unknown',
            symbol VARCHAR(20) NOT NULL,
            base_asset VARCHAR(10),
            price DECIMAL(20, 8) NOT NULL,
            quantity DECIMAL(20, 8) NOT NULL,
            value_usd DECIMAL(20, 2) NOT NULL,
            quote_asset VARCHAR(10) NOT NULL,
            is_buyer_maker BOOLEAN NOT NULL,
            trade_time DATETIME NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_exchange (exchange),
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

                # Проверяем, есть ли колонка exchange
                check_exchange_column_sql = """
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'large_trades' 
                AND COLUMN_NAME = 'exchange'
                """
                await cursor.execute(check_exchange_column_sql, (MYSQL_CONFIG['db'],))
                result = await cursor.fetchone()

                if result[0] == 0:
                    # Колонки exchange нет, нужно добавить
                    logger.info("Добавляем колонку exchange в существующую таблицу...")
                    await cursor.execute("""
                        ALTER TABLE large_trades 
                        ADD COLUMN exchange VARCHAR(20) NOT NULL DEFAULT 'unknown' AFTER id,
                        ADD INDEX idx_exchange (exchange)
                    """)
                    logger.info("Колонка exchange добавлена")

                # Проверяем, есть ли колонка base_asset
                check_base_asset_column_sql = """
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = %s 
                AND TABLE_NAME = 'large_trades' 
                AND COLUMN_NAME = 'base_asset'
                """
                await cursor.execute(check_base_asset_column_sql, (MYSQL_CONFIG['db'],))
                result = await cursor.fetchone()

                if result[0] == 0:
                    # Колонки base_asset нет, нужно добавить
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
        (id, exchange, symbol, base_asset, price, quantity, value_usd, quote_asset, is_buyer_maker, trade_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        # Проверяем существующие ID (с учетом биржи для уникальности)
        trade_keys = [(trade.exchange, int(trade.id)) for trade in trades]

        # Создаем запрос для проверки существующих комбинаций exchange + id
        check_conditions = []
        check_params = []
        for exchange, trade_id in trade_keys:
            check_conditions.append("(exchange = %s AND id = %s)")
            check_params.extend([exchange, trade_id])

        check_sql = f"SELECT exchange, id FROM large_trades WHERE {' OR '.join(check_conditions)}"

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Получаем существующие комбинации exchange + id
                await cursor.execute(check_sql, check_params)
                existing_keys = {(row[0], row[1]) for row in await cursor.fetchall()}

                # Фильтруем новые сделки
                new_trades = []
                duplicate_count = 0

                for trade in trades:
                    trade_key = (trade.exchange, int(trade.id))
                    if trade_key in existing_keys:
                        duplicate_count += 1
                        logger.debug(
                            f"Дубликат: сделка {trade.exchange}:{trade.symbol} ID:{trade.id} "
                            f"на сумму ${trade.value_usd:,.2f} уже в БД"
                        )
                    else:
                        new_trades.append(trade)

                # Сохраняем только новые сделки
                if new_trades:
                    values = [
                        (
                            int(trade.id),
                            trade.exchange,
                            trade.symbol,
                            trade.base_asset,
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
                            print(f"  НОВАЯ [{trade.exchange.upper()}]: {trade.symbol} ${trade.value_usd:,.2f} "
                                  f"в {trade.trade_datetime.strftime('%H:%M:%S')}")
                        if len(new_trades) > 5:
                            print(f"  ... и еще {len(new_trades) - 5} сделок")

                    return saved_count, duplicate_count
                else:
                    return 0, duplicate_count

    async def get_recent_trades_count(self, hours: int = 24, exchange: Optional[str] = None) -> int:
        """
        Получает количество сделок за последние N часов.

        Args:
            hours: Количество часов
            exchange: Фильтр по бирже (опционально)

        Returns:
            Количество сделок
        """
        if exchange:
            query = """
            SELECT COUNT(*) 
            FROM large_trades 
            WHERE trade_time > DATE_SUB(NOW(), INTERVAL %s HOUR)
            AND exchange = %s
            """
            params = (hours, exchange)
        else:
            query = """
            SELECT COUNT(*) 
            FROM large_trades 
            WHERE trade_time > DATE_SUB(NOW(), INTERVAL %s HOUR)
            """
            params = (hours,)

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def get_statistics(self, exchange: Optional[str] = None) -> dict:
        """
        Получает общую статистику.

        Args:
            exchange: Фильтр по бирже (опционально)

        Returns:
            Словарь со статистикой
        """
        if exchange:
            query = """
            SELECT 
                COUNT(*) as trade_count,
                SUM(value_usd) as total_volume,
                AVG(value_usd) as avg_trade_size,
                MAX(value_usd) as max_trade_size
            FROM large_trades
            WHERE trade_time > DATE_SUB(NOW(), INTERVAL 24 HOUR)
            AND exchange = %s
            """
            params = (exchange,)
        else:
            query = """
            SELECT 
                COUNT(*) as trade_count,
                SUM(value_usd) as total_volume,
                AVG(value_usd) as avg_trade_size,
                MAX(value_usd) as max_trade_size
            FROM large_trades
            WHERE trade_time > DATE_SUB(NOW(), INTERVAL 24 HOUR)
            """
            params = ()

        stats = {}
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                row = await cursor.fetchone()
                if row:
                    stats = {
                        'trade_count': row[0] or 0,
                        'total_volume': float(row[1]) if row[1] else 0,
                        'avg_trade_size': float(row[2]) if row[2] else 0,
                        'max_trade_size': float(row[3]) if row[3] else 0
                    }
        return stats

    async def get_statistics_by_exchange(self) -> dict:
        """
        Получает статистику по каждой бирже отдельно.

        Returns:
            Словарь со статистикой по биржам
        """
        query = """
        SELECT 
            exchange,
            COUNT(*) as trade_count,
            SUM(value_usd) as total_volume,
            AVG(value_usd) as avg_trade_size,
            MAX(value_usd) as max_trade_size
        FROM large_trades
        WHERE trade_time > DATE_SUB(NOW(), INTERVAL 24 HOUR)
        GROUP BY exchange
        ORDER BY total_volume DESC
        """

        stats_by_exchange = {}
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query)
                rows = await cursor.fetchall()
                for row in rows:
                    exchange = row[0]
                    stats_by_exchange[exchange] = {
                        'trade_count': row[1] or 0,
                        'total_volume': float(row[2]) if row[2] else 0,
                        'avg_trade_size': float(row[3]) if row[3] else 0,
                        'max_trade_size': float(row[4]) if row[4] else 0
                    }

        return stats_by_exchange