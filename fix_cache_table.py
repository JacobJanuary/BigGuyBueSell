#!/usr/bin/env python3
"""
Скрипт для исправления структуры таблицы trading_pairs_cache.
"""
import asyncio
import logging

from database.manager import DatabaseManager
from config.settings import MYSQL_CONFIG

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def fix_table_structure():
    """Исправляет структуру таблицы trading_pairs_cache."""
    print("🔧 Исправление структуры таблицы trading_pairs_cache...")

    db_manager = DatabaseManager()

    try:
        await db_manager.connect()

        async with db_manager.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # Проверяем текущую структуру
                print("📋 Проверка текущей структуры...")
                await cursor.execute("""
                                     SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH
                                     FROM INFORMATION_SCHEMA.COLUMNS
                                     WHERE TABLE_SCHEMA = %s
                                       AND TABLE_NAME = 'trading_pairs_cache'
                                       AND COLUMN_NAME IN ('base_asset', 'quote_asset')
                                     """, (MYSQL_CONFIG['db'],))

                columns = await cursor.fetchall()

                if not columns:
                    print("❌ Таблица trading_pairs_cache не найдена")
                    return False

                # Показываем текущие размеры
                for column_name, data_type, max_length in columns:
                    print(f"  {column_name}: {data_type}({max_length})")

                # Обновляем размеры колонок
                updates_needed = []
                for column_name, data_type, max_length in columns:
                    if max_length < 20:
                        updates_needed.append(column_name)

                if updates_needed:
                    print(f"🔄 Обновляем колонки: {updates_needed}")

                    for column_name in updates_needed:
                        alter_sql = f"""
                        ALTER TABLE trading_pairs_cache 
                        MODIFY COLUMN {column_name} VARCHAR(20) NOT NULL
                        """
                        await cursor.execute(alter_sql)
                        print(f"  ✅ {column_name}: VARCHAR(10) → VARCHAR(20)")

                    print("🎉 Структура таблицы обновлена!")
                else:
                    print("✅ Структура таблицы уже корректна")

                # Очищаем кэш для безопасности
                await cursor.execute("DELETE FROM trading_pairs_cache")
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    print(f"🧹 Очищен старый кэш ({deleted_count} записей)")

                return True

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return False
    finally:
        await db_manager.close()


async def main():
    """Главная функция."""
    print("=" * 60)
    print("ИСПРАВЛЕНИЕ СТРУКТУРЫ ТАБЛИЦЫ КЭША")
    print("=" * 60)

    success = await fix_table_structure()

    if success:
        print("\n✅ Исправление завершено успешно!")
        print("Теперь можно запускать: python main.py")
    else:
        print("\n❌ Исправление не удалось")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())