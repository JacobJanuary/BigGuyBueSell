"""
Менеджер кэша торговых пар для оптимизации API запросов.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from decimal import Decimal

import aiomysql

from config.settings import MYSQL_CONFIG, MIN_VOLUME_USD
from database.models import TradingPairInfo

logger = logging.getLogger(__name__)


class PairsCacheManager:
    """Менеджер для кэширования информации о торговых парах."""

    def __init__(self, pool: aiomysql.Pool):
        """
        Инициализирует менеджер кэша.

        Args:
            pool: Пул соединений с базой данных
        """
        self.pool = pool

    async def create_table(self) -> None:
        """Создает таблицу кэша торговых пар, если она не существует."""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS trading_pairs_cache (
            id INT AUTO_INCREMENT PRIMARY KEY,
            exchange VARCHAR(20) NOT NULL,
            symbol VARCHAR(50) NOT NULL,
            base_asset VARCHAR(20) NOT NULL,
            quote_asset VARCHAR(20) NOT NULL,
            volume_24h_usd DECIMAL(20, 2) NOT NULL,
            quote_price_usd DECIMAL(20, 8) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            
            UNIQUE KEY unique_exchange_symbol (exchange, symbol),
            INDEX idx_exchange (exchange),
            INDEX idx_volume (volume_24h_usd),
            INDEX idx_last_updated (last_updated),
            INDEX idx_active (is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(create_table_sql)

                # Проверяем и обновляем структуру существующей таблицы
                await self._ensure_column_sizes(cursor)

                logger.info("Таблица trading_pairs_cache готова к работе")

    async def _ensure_column_sizes(self, cursor) -> None:
        """Обеспечивает правильные размеры колонок в существующей таблице."""
        try:
            # Проверяем текущие размеры колонок
            check_columns_sql = """
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'trading_pairs_cache' 
            AND COLUMN_NAME IN ('base_asset', 'quote_asset')
            """
            await cursor.execute(check_columns_sql)
            columns = await cursor.fetchall()

            columns_to_update = []
            for column_name, data_type, max_length in columns:
                if column_name in ['base_asset', 'quote_asset'] and max_length < 20:
                    columns_to_update.append(column_name)

            # Обновляем размеры колонок если нужно
            if columns_to_update:
                logger.info(f"Обновляем размеры колонок: {columns_to_update}")
                for column_name in columns_to_update:
                    alter_sql = f"""
                    ALTER TABLE trading_pairs_cache 
                    MODIFY COLUMN {column_name} VARCHAR(20) NOT NULL
                    """
                    await cursor.execute(alter_sql)
                logger.info("Размеры колонок обновлены")

        except Exception as e:
            logger.warning(f"Не удалось проверить/обновить размеры колонок: {e}")
            # Продолжаем работу, возможно таблица уже имеет правильную структуру

    async def is_cache_fresh(self, exchange: str, max_age_hours: int = 1) -> bool:
        """
        Проверяет, актуален ли кэш для указанной биржи.

        Args:
            exchange: Название биржи
            max_age_hours: Максимальный возраст кэша в часах

        Returns:
            True если кэш актуален
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        check_sql = """
        SELECT COUNT(*) 
        FROM trading_pairs_cache 
        WHERE exchange = %s 
        AND last_updated > %s 
        AND is_active = TRUE
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(check_sql, (exchange, cutoff_time))
                result = await cursor.fetchone()
                count = result[0] if result else 0

                logger.debug(f"Кэш {exchange}: найдено {count} актуальных записей")
                return count > 0

    async def get_cached_pairs(self, exchange: str) -> List[TradingPairInfo]:
        """
        Получает список активных торговых пар из кэша.

        Args:
            exchange: Название биржи

        Returns:
            Список торговых пар из кэша
        """
        select_sql = """
        SELECT symbol, base_asset, quote_asset, volume_24h_usd, quote_price_usd
        FROM trading_pairs_cache 
        WHERE exchange = %s 
        AND is_active = TRUE 
        AND volume_24h_usd >= %s
        ORDER BY volume_24h_usd DESC
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(select_sql, (exchange, MIN_VOLUME_USD))
                rows = await cursor.fetchall()

                pairs = []
                for row in rows:
                    symbol, base_asset, quote_asset, volume_24h_usd, quote_price_usd = row
                    pairs.append(TradingPairInfo(
                        exchange=exchange,
                        symbol=symbol,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        volume_24h_usd=Decimal(str(volume_24h_usd)),
                        quote_price_usd=Decimal(str(quote_price_usd))
                    ))

                logger.info(f"Загружено {len(pairs)} пар {exchange.upper()} из кэша")
                return pairs

    def _sanitize_asset_name(self, asset_name: str, max_length: int = 20) -> str:
        """
        Безопасно обрезает название актива до допустимой длины.

        Args:
            asset_name: Название актива
            max_length: Максимальная длина

        Returns:
            Обрезанное название актива
        """
        if not asset_name:
            return ""

        # Обрезаем до максимальной длины
        if len(asset_name) > max_length:
            logger.warning(f"Актив '{asset_name}' слишком длинный, обрезаем до '{asset_name[:max_length]}'")
            return asset_name[:max_length]

        return asset_name

    async def update_pairs_cache(self, exchange: str, pairs: List[TradingPairInfo]) -> Tuple[int, int, int]:
        """
        Обновляет кэш торговых пар для указанной биржи.

        Args:
            exchange: Название биржи
            pairs: Список торговых пар для сохранения

        Returns:
            Кортеж (добавлено, обновлено, деактивировано)
        """
        if not pairs:
            logger.warning(f"Нет пар для обновления кэша {exchange}")
            return 0, 0, 0

        # SQL для вставки/обновления
        upsert_sql = """
        INSERT INTO trading_pairs_cache 
        (exchange, symbol, base_asset, quote_asset, volume_24h_usd, quote_price_usd, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, TRUE)
        ON DUPLICATE KEY UPDATE
            base_asset = VALUES(base_asset),
            quote_asset = VALUES(quote_asset), 
            volume_24h_usd = VALUES(volume_24h_usd),
            quote_price_usd = VALUES(quote_price_usd),
            is_active = TRUE,
            last_updated = CURRENT_TIMESTAMP
        """

        # SQL для деактивации старых пар
        deactivate_sql = """
        UPDATE trading_pairs_cache 
        SET is_active = FALSE 
        WHERE exchange = %s 
        AND symbol NOT IN ({})
        AND is_active = TRUE
        """.format(','.join(['%s'] * len(pairs)))

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Получаем статистику до обновления
                await cursor.execute(
                    "SELECT COUNT(*) FROM trading_pairs_cache WHERE exchange = %s AND is_active = TRUE",
                    (exchange,)
                )
                old_count = (await cursor.fetchone())[0]

                # Подготавливаем данные с безопасным обрезанием
                values = []
                for pair in pairs:
                    try:
                        # Безопасно обрезаем названия активов
                        base_asset = self._sanitize_asset_name(pair.base_asset)
                        quote_asset = self._sanitize_asset_name(pair.quote_asset)

                        values.append((
                            exchange,
                            pair.symbol,
                            base_asset,
                            quote_asset,
                            float(pair.volume_24h_usd),
                            float(pair.quote_price_usd)
                        ))
                    except Exception as e:
                        logger.error(f"Ошибка подготовки данных для пары {pair.symbol}: {e}")
                        continue

                if not values:
                    logger.error(f"Не удалось подготовить данные для {exchange}")
                    return 0, 0, 0

                # Вставляем/обновляем пары
                await cursor.executemany(upsert_sql, values)
                upserted_count = cursor.rowcount

                # Деактивируем пары, которых нет в новом списке
                symbols = [pair.symbol for pair in pairs]
                deactivate_params = [exchange] + symbols
                await cursor.execute(deactivate_sql, deactivate_params)
                deactivated_count = cursor.rowcount

                # Получаем финальную статистику
                await cursor.execute(
                    "SELECT COUNT(*) FROM trading_pairs_cache WHERE exchange = %s AND is_active = TRUE",
                    (exchange,)
                )
                new_count = (await cursor.fetchone())[0]

                added_count = max(0, new_count - old_count)
                updated_count = min(upserted_count, old_count)

                logger.info(
                    f"Кэш {exchange.upper()} обновлен: "
                    f"добавлено {added_count}, обновлено {updated_count}, "
                    f"деактивировано {deactivated_count}, итого активных {new_count}"
                )

                return added_count, updated_count, deactivated_count

    async def get_cache_stats(self, exchange: Optional[str] = None) -> dict:
        """
        Получает статистику по кэшу торговых пар.

        Args:
            exchange: Название биржи (если None, то по всем биржам)

        Returns:
            Словарь со статистикой
        """
        if exchange:
            stats_sql = """
            SELECT 
                COUNT(*) as total_pairs,
                COUNT(CASE WHEN is_active = TRUE THEN 1 END) as active_pairs,
                AVG(volume_24h_usd) as avg_volume,
                MAX(last_updated) as last_update
            FROM trading_pairs_cache 
            WHERE exchange = %s
            """
            params = (exchange,)
        else:
            stats_sql = """
            SELECT 
                COUNT(*) as total_pairs,
                COUNT(CASE WHEN is_active = TRUE THEN 1 END) as active_pairs,
                AVG(volume_24h_usd) as avg_volume,
                MAX(last_updated) as last_update
            FROM trading_pairs_cache
            """
            params = ()

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(stats_sql, params)
                row = await cursor.fetchone()

                if row:
                    return {
                        'total_pairs': row[0] or 0,
                        'active_pairs': row[1] or 0,
                        'avg_volume': float(row[2]) if row[2] else 0,
                        'last_update': row[3]
                    }
                else:
                    return {
                        'total_pairs': 0,
                        'active_pairs': 0,
                        'avg_volume': 0,
                        'last_update': None
                    }

    async def cleanup_old_cache(self, days_old: int = 7) -> int:
        """
        Удаляет старые записи из кэша.

        Args:
            days_old: Возраст записей для удаления (в днях)

        Returns:
            Количество удаленных записей
        """
        cutoff_date = datetime.now() - timedelta(days=days_old)

        cleanup_sql = """
        DELETE FROM trading_pairs_cache 
        WHERE last_updated < %s 
        AND is_active = FALSE
        """

        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(cleanup_sql, (cutoff_date,))
                deleted_count = cursor.rowcount

                if deleted_count > 0:
                    logger.info(f"Удалено {deleted_count} старых записей из кэша")

                return deleted_count