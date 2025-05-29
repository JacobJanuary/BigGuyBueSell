#!/usr/bin/env python3
"""
Утилиты для управления кэшем торговых пар.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from database.manager import DatabaseManager
from database.pairs_cache import PairsCacheManager
from config.settings import MYSQL_CONFIG

logger = logging.getLogger(__name__)


class CacheManagementTool:
    """Инструмент для управления кэшем торговых пар."""

    def __init__(self):
        """Инициализирует инструмент управления кэшем."""
        self.db_manager = None
        self.pairs_cache = None

    async def connect(self):
        """Подключается к базе данных."""
        self.db_manager = DatabaseManager()
        await self.db_manager.connect()
        self.pairs_cache = PairsCacheManager(self.db_manager.pool)

    async def disconnect(self):
        """Отключается от базы данных."""
        if self.db_manager:
            await self.db_manager.close()

    async def show_cache_status(self, exchange: Optional[str] = None):
        """
        Показывает статус кэша.

        Args:
            exchange: Название биржи (если None, показывает все)
        """
        print("📊 СТАТУС КЭША ТОРГОВЫХ ПАР")
        print("=" * 60)

        if exchange:
            exchanges = [exchange]
        else:
            # Получаем список всех бирж в кэше
            async with self.db_manager.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT DISTINCT exchange FROM trading_pairs_cache")
                    rows = await cursor.fetchall()
                    exchanges = [row[0] for row in rows] if rows else []

        if not exchanges:
            print("❌ Кэш пуст")
            return

        for exchange_name in exchanges:
            stats = await self.pairs_cache.get_cache_stats(exchange_name)
            is_fresh = await self.pairs_cache.is_cache_fresh(exchange_name, 1)

            print(f"\n🏦 {exchange_name.upper()}:")
            print(f"  Всего пар: {stats['total_pairs']}")
            print(f"  Активных: {stats['active_pairs']}")
            print(f"  Средний объем: ${stats['avg_volume']:,.0f}")
            print(f"  Последнее обновление: {stats['last_update']}")
            print(f"  Статус: {'🟢 Актуален' if is_fresh else '🔴 Устарел'}")

    async def clear_cache(self, exchange: Optional[str] = None):
        """
        Очищает кэш.

        Args:
            exchange: Название биржи (если None, очищает все)
        """
        if exchange:
            sql = "DELETE FROM trading_pairs_cache WHERE exchange = %s"
            params = (exchange,)
            print(f"Очистка кэша для {exchange.upper()}...")
        else:
            sql = "DELETE FROM trading_pairs_cache"
            params = ()
            print("Очистка всего кэша...")

        async with self.db_manager.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(sql, params)
                deleted_count = cursor.rowcount
                print(f"✅ Удалено {deleted_count} записей")

    async def cleanup_old_cache(self, days: int = 7):
        """
        Удаляет старые записи из кэша.

        Args:
            days: Возраст записей для удаления
        """
        print(f"Очистка записей старше {days} дней...")
        deleted_count = await self.pairs_cache.cleanup_old_cache(days)
        print(f"✅ Удалено {deleted_count} старых записей")

    async def force_update_cache(self, exchange: str):
        """
        Принудительно помечает кэш как устаревший.

        Args:
            exchange: Название биржи
        """
        old_date = datetime.now() - timedelta(hours=25)  # Делаем старше 1 дня

        sql = """
              UPDATE trading_pairs_cache
              SET last_updated = %s
              WHERE exchange = %s \
              """

        async with self.db_manager.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(sql, (old_date, exchange))
                updated_count = cursor.rowcount
                print(f"✅ Помечено {updated_count} записей {exchange.upper()} как устаревшие")

    async def export_cache(self, exchange: Optional[str] = None, filename: Optional[str] = None):
        """
        Экспортирует кэш в CSV файл.

        Args:
            exchange: Название биржи (если None, экспортирует все)
            filename: Имя файла (если None, генерирует автоматически)
        """
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            exchange_suffix = f"_{exchange}" if exchange else "_all"
            filename = f"trading_pairs_cache{exchange_suffix}_{timestamp}.csv"

        if exchange:
            sql = """
                  SELECT exchange, \
                         symbol, \
                         base_asset, \
                         quote_asset, \
                         volume_24h_usd,
                         quote_price_usd, \
                         is_active, \
                         last_updated
                  FROM trading_pairs_cache
                  WHERE exchange = %s
                  ORDER BY volume_24h_usd DESC \
                  """
            params = (exchange,)
        else:
            sql = """
                  SELECT exchange, \
                         symbol, \
                         base_asset, \
                         quote_asset, \
                         volume_24h_usd,
                         quote_price_usd, \
                         is_active, \
                         last_updated
                  FROM trading_pairs_cache
                  ORDER BY exchange, volume_24h_usd DESC \
                  """
            params = ()

        async with self.db_manager.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(sql, params)
                rows = await cursor.fetchall()

        if not rows:
            print("❌ Нет данных для экспорта")
            return

        # Записываем в CSV
        with open(filename, 'w', encoding='utf-8') as f:
            # Заголовок
            f.write("exchange,symbol,base_asset,quote_asset,volume_24h_usd,quote_price_usd,is_active,last_updated\n")

            # Данные
            for row in rows:
                f.write(','.join(str(field) for field in row) + '\n')

        print(f"✅ Экспортировано {len(rows)} записей в {filename}")


async def main():
    """Главная функция для CLI управления кэшем."""
    import sys

    if len(sys.argv) < 2:
        print("""
Утилита управления кэшем торговых пар

Использование:
  python -m utils.cache_management status [биржа]     # Показать статус кэша
  python -m utils.cache_management clear [биржа]      # Очистить кэш
  python -m utils.cache_management cleanup [дни]      # Удалить старые записи
  python -m utils.cache_management force-update биржа # Пометить как устаревший
  python -m utils.cache_management export [биржа]     # Экспорт в CSV

Примеры:
  python -m utils.cache_management status
  python -m utils.cache_management status binance
  python -m utils.cache_management clear binance
  python -m utils.cache_management cleanup 30
  python -m utils.cache_management force-update coinbase
        """)
        return

    command = sys.argv[1]
    tool = CacheManagementTool()

    try:
        await tool.connect()

        if command == 'status':
            exchange = sys.argv[2] if len(sys.argv) > 2 else None
            await tool.show_cache_status(exchange)

        elif command == 'clear':
            exchange = sys.argv[2] if len(sys.argv) > 2 else None
            await tool.clear_cache(exchange)

        elif command == 'cleanup':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
            await tool.cleanup_old_cache(days)

        elif command == 'force-update':
            if len(sys.argv) < 3:
                print("❌ Укажите название биржи")
                return
            exchange = sys.argv[2]
            await tool.force_update_cache(exchange)

        elif command == 'export':
            exchange = sys.argv[2] if len(sys.argv) > 2 else None
            await tool.export_cache(exchange)

        else:
            print(f"❌ Неизвестная команда: {command}")

    finally:
        await tool.disconnect()


if __name__ == "__main__":
    asyncio.run(main())