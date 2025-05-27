#!/usr/bin/env python3
"""
Быстрое исправление проблем кэширования в ExchangeWorker.
quick_cache_fix.py

Этот скрипт содержит минимальные изменения для немедленного улучшения эффективности кэша.
"""
import os
import shutil
from datetime import datetime

QUICK_FIX_CODE = '''
# === БЫСТРОЕ ИСПРАВЛЕНИЕ ДЛЯ ExchangeWorker ===
# Добавьте в начало метода __init__ класса ExchangeWorker:

# Быстрое исправление кэширования - добавить в __init__
self._quick_cache = None
self._quick_cache_time = None
self._quick_cache_ttl = 1800  # 30 минут в секундах
self._api_cooldown = 3600     # 1 час между API обновлениями
self._last_api_call = None

# === ЗАМЕНИТЕ get_trading_pairs() НА ЭТОТ КОД ===

async def get_trading_pairs(self) -> Optional[List[TradingPairInfo]]:
    """Быстрое исправление с минимальными изменениями для оптимизации кэша."""
    import time

    current_time = time.time()

    # 1. ПРОВЕРЯЕМ БЫСТРЫЙ КЭШЬ (ГЛАВНАЯ ОПТИМИЗАЦИЯ)
    if (self._quick_cache and 
        self._quick_cache_time and
        (current_time - self._quick_cache_time) < self._quick_cache_ttl):

        logger.debug(f"[{self.exchange_name.upper()}] 🚀 Используем быстрый кэш")
        return self._quick_cache

    # 2. ПРОВЕРЯЕМ МОЖНО ЛИ ВЫЗЫВАТЬ API (ПРЕДОТВРАЩЕНИЕ ЧАСТЫХ ВЫЗОВОВ)
    api_allowed = (not self._last_api_call or 
                   (current_time - self._last_api_call) >= self._api_cooldown)

    trading_pairs = None

    try:
        # 3. СНАЧАЛА ПРОБУЕМ БД КЭШЬ
        if not api_allowed:
            # Если API нельзя - используем БД кэш даже если он чуть устарел
            logger.debug(f"[{self.exchange_name.upper()}] API в кулдауне, проверяем БД кэш")

            cache_fresh = await self.pairs_cache.is_cache_fresh(
                self.exchange_name, 
                max_age_hours=3  # Более щадящий TTL
            )

            if cache_fresh:
                trading_pairs = await self.pairs_cache.get_cached_pairs(self.exchange_name)
                if trading_pairs:
                    logger.info(f"[{self.exchange_name.upper()}] 📦 Загружено {len(trading_pairs)} пар из БД кэша")

        # 4. ВЫЗЫВАЕМ API ТОЛЬКО ЕСЛИ НЕОБХОДИМО И РАЗРЕШЕНО
        if not trading_pairs and api_allowed:
            logger.info(f"[{self.exchange_name.upper()}] 🌐 Обновление через API (кулдаун истек)")

            # Обновляем кулдаун ДО вызова API
            self._last_api_call = current_time

            try:
                trading_pairs = await self.update_pairs_cache()
                if trading_pairs:
                    logger.info(f"[{self.exchange_name.upper()}] ✅ API обновление: {len(trading_pairs)} пар")
            except Exception as e:
                logger.error(f"[{self.exchange_name.upper()}] ❌ Ошибка API: {e}")
                # Сбрасываем кулдаун при ошибке для повторной попытки
                self._last_api_call = None

        # 5. FALLBACK - ИСПОЛЬЗУЕМ СТАРЫЙ КЭШЬ ЕСЛИ ЕСТЬ
        if not trading_pairs and self._quick_cache:
            cache_age_hours = (current_time - self._quick_cache_time) / 3600
            logger.warning(
                f"[{self.exchange_name.upper()}] 🔄 Используем устаревший кэш "
                f"(возраст {cache_age_hours:.1f}ч)"
            )
            return self._quick_cache

        # 6. СОХРАНЯЕМ В БЫСТРЫЙ КЭШЬ
        if trading_pairs:
            self._quick_cache = trading_pairs
            self._quick_cache_time = current_time
            logger.debug(f"[{self.exchange_name.upper()}] 💾 Обновлен быстрый кэш")

        return trading_pairs

    except Exception as e:
        logger.error(f"[{self.exchange_name.upper()}] 💥 Ошибка получения пар: {e}")

        # В случае ошибки возвращаем старый кэш если есть
        if self._quick_cache:
            logger.warning(f"[{self.exchange_name.upper()}] 🆘 Возвращаем аварийный кэш")
            return self._quick_cache

        return None

# === ДОПОЛНИТЕЛЬНЫЕ МЕТОДЫ ДЛЯ МОНИТОРИНГА ===

def get_cache_stats(self) -> dict:
    """Получает статистику быстрого кэша."""
    import time
    current_time = time.time()

    if self._quick_cache_time:
        cache_age_minutes = (current_time - self._quick_cache_time) / 60
        cache_valid = cache_age_minutes < (self._quick_cache_ttl / 60)
    else:
        cache_age_minutes = 0
        cache_valid = False

    api_cooldown_remaining = 0
    if self._last_api_call:
        api_cooldown_remaining = max(0, self._api_cooldown - (current_time - self._last_api_call))

    return {
        'cache_size': len(self._quick_cache) if self._quick_cache else 0,
        'cache_age_minutes': cache_age_minutes,
        'cache_valid': cache_valid,
        'api_cooldown_remaining_seconds': api_cooldown_remaining,
        'last_api_call': datetime.fromtimestamp(self._last_api_call).isoformat() if self._last_api_call else None
    }

def force_cache_refresh(self):
    """Принудительно сбрасывает кэш для обновления."""
    self._quick_cache = None
    self._quick_cache_time = None
    self._last_api_call = None
    logger.info(f"[{self.exchange_name.upper()}] 🔄 Кэш принудительно сброшен")
'''


def create_backup():
    """Создает резервную копию существующего файла."""
    original_file = 'workers/exchange_worker.py'

    if not os.path.exists(original_file):
        print(f"❌ Файл {original_file} не найден")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_file = f'workers/exchange_worker_backup_{timestamp}.py'

    try:
        shutil.copy2(original_file, backup_file)
        print(f"✅ Создана резервная копия: {backup_file}")
        return backup_file
    except Exception as e:
        print(f"❌ Ошибка создания резервной копии: {e}")
        return None


def apply_quick_fix():
    """Применяет быстрое исправление к файлу ExchangeWorker."""
    print("🔧 ПРИМЕНЕНИЕ БЫСТРОГО ИСПРАВЛЕНИЯ")
    print("=" * 50)

    # 1. Создаем резервную копию
    backup_file = create_backup()
    if not backup_file:
        print("❌ Не удалось создать резервную копию. Остановка.")
        return False

    # 2. Читаем оригинальный файл
    original_file = 'workers/exchange_worker.py'
    try:
        with open(original_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        return False

    # 3. Проверяем, не применялось ли исправление ранее
    if '_quick_cache' in content:
        print("ℹ️  Быстрое исправление уже было применено")
        return True

    # 4. Ищем место для вставки в __init__
    init_marker = 'def __init__('
    init_pos = content.find(init_marker)

    if init_pos == -1:
        print("❌ Не найден метод __init__ в ExchangeWorker")
        return False

    # Ищем конец __init__ метода (начало следующего метода или конец класса)
    lines = content[init_pos:].split('\n')
    init_end_line = 0

    for i, line in enumerate(lines[1:], 1):  # Пропускаем строку с def __init__
        if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
            # Найден следующий метод или конец класса
            init_end_line = i
            break
        elif line.strip().startswith('def ') and not line.startswith('        '):
            # Найден следующий метод класса
            init_end_line = i
            break

    if init_end_line == 0:
        init_end_line = len(lines)

    # 5. Вставляем код быстрого исправления
    init_code = '''
        # === БЫСТРОЕ ИСПРАВЛЕНИЕ КЭШИРОВАНИЯ ===
        self._quick_cache = None
        self._quick_cache_time = None
        self._quick_cache_ttl = 1800  # 30 минут
        self._api_cooldown = 3600     # 1 час между API обновлениями
        self._last_api_call = None

        # Добавляем в конец существующего __init__
        logger.info(f"[{self.exchange_name.upper()}] 🚀 Быстрое исправление кэша активировано")
'''

    # Вставляем в конец __init__
    init_section = '\n'.join(lines[:init_end_line - 1])
    rest_section = '\n'.join(lines[init_end_line - 1:])

    new_init_section = init_section + init_code + '\n'
    new_content_part = content[:init_pos] + new_init_section + rest_section

    # 6. Заменяем метод get_trading_pairs
    get_pairs_marker = 'async def get_trading_pairs('
    get_pairs_pos = new_content_part.find(get_pairs_marker)

    if get_pairs_pos == -1:
        print("❌ Не найден метод get_trading_pairs")
        return False

    # Находим конец метода get_trading_pairs
    lines_after_method = new_content_part[get_pairs_pos:].split('\n')
    method_end_line = 0

    for i, line in enumerate(lines_after_method[1:], 1):
        if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
            if line.strip().startswith('async def ') or line.strip().startswith('def '):
                method_end_line = i
                break

    if method_end_line == 0:
        method_end_line = len(lines_after_method)

    # Создаем новый метод get_trading_pairs
    new_method = '''    async def get_trading_pairs(self) -> Optional[List[TradingPairInfo]]:
        """Быстрое исправление с оптимизацией кэша."""
        import time

        current_time = time.time()

        # Проверяем быстрый кэш
        if (self._quick_cache and 
            self._quick_cache_time and
            (current_time - self._quick_cache_time) < self._quick_cache_ttl):

            logger.debug(f"[{self.exchange_name.upper()}] 🚀 Используем быстрый кэш")
            return self._quick_cache

        # Проверяем API кулдаун
        api_allowed = (not self._last_api_call or 
                       (current_time - self._last_api_call) >= self._api_cooldown)

        trading_pairs = None

        try:
            # Пробуем БД кэш если API в кулдауне
            if not api_allowed:
                cache_fresh = await self.pairs_cache.is_cache_fresh(
                    self.exchange_name, max_age_hours=3
                )

                if cache_fresh:
                    trading_pairs = await self.pairs_cache.get_cached_pairs(self.exchange_name)
                    if trading_pairs:
                        logger.info(f"[{self.exchange_name.upper()}] 📦 БД кэш: {len(trading_pairs)} пар")

            # API обновление если разрешено
            if not trading_pairs and api_allowed:
                logger.info(f"[{self.exchange_name.upper()}] 🌐 API обновление")
                self._last_api_call = current_time

                try:
                    trading_pairs = await self.update_pairs_cache()
                    if trading_pairs:
                        logger.info(f"[{self.exchange_name.upper()}] ✅ API: {len(trading_pairs)} пар")
                except Exception as e:
                    logger.error(f"[{self.exchange_name.upper()}] ❌ API ошибка: {e}")
                    self._last_api_call = None

            # Fallback к старому кэшу
            if not trading_pairs and self._quick_cache:
                cache_age_hours = (current_time - self._quick_cache_time) / 3600
                logger.warning(
                    f"[{self.exchange_name.upper()}] 🔄 Устаревший кэш ({cache_age_hours:.1f}ч)"
                )
                return self._quick_cache

            # Сохраняем в быстрый кэш
            if trading_pairs:
                self._quick_cache = trading_pairs
                self._quick_cache_time = current_time

            return trading_pairs

        except Exception as e:
            logger.error(f"[{self.exchange_name.upper()}] 💥 Ошибка: {e}")
            return self._quick_cache if self._quick_cache else None
'''

    # Собираем финальный контент
    before_method = new_content_part[:get_pairs_pos]
    after_method = '\n'.join(lines_after_method[method_end_line:])

    final_content = before_method + new_method + '\n' + after_method

    # 7. Сохраняем изменения
    try:
        with open(original_file, 'w', encoding='utf-8') as f:
            f.write(final_content)

        print("✅ Быстрое исправление применено успешно!")
        print(f"📁 Резервная копия: {backup_file}")
        return True

    except Exception as e:
        print(f"❌ Ошибка записи файла: {e}")

        # Восстанавливаем из резервной копии
        try:
            shutil.copy2(backup_file, original_file)
            print("🔄 Файл восстановлен из резервной копии")
        except:
            pass

        return False


def show_quick_fix_info():
    """Показывает информацию о быстром исправлении."""
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║              БЫСТРОЕ ИСПРАВЛЕНИЕ                  ║
    ║           ПРОБЛЕМ КЭШИРОВАНИЯ                     ║
    ╚═══════════════════════════════════════════════════╝

    🎯 ЦЕЛЬ: Немедленно сократить API вызовы на 90%

    🔧 ЧТО ДЕЛАЕТ:
    • Добавляет in-memory кэш на 30 минут
    • Устанавливает кулдаун API на 1 час
    • Использует более щадящий БД кэш (3 часа)
    • Добавляет fallback к устаревшему кэшу

    ⚡ ОЖИДАЕМЫЙ ЭФФЕКТ:
    • API вызовы: с каждого цикла → раз в час
    • Время отклика: уменьшается в 10+ раз
    • Стабильность: повышается при недоступности API

    ⚠️  ВАЖНО:
    • Создается резервная копия перед изменениями
    • Можно откатить изменения в любой момент
    • Работает с существующим кодом без конфликтов

    📋 ПОСЛЕ ПРИМЕНЕНИЯ:
    1. Перезапустите приложение
    2. Проверьте логи на сообщения "🚀 Быстрое исправление"
    3. Мониторьте сокращение API вызовов
    """)


def create_env_patch():
    """Создает патч для .env файла."""
    env_patch = """
# === ДОБАВЬТЕ В .env ДЛЯ БЫСТРОГО ИСПРАВЛЕНИЯ ===
# Оптимизация кэша (базовые настройки)
PAIRS_CACHE_UPDATE_MINUTES=60
PAIRS_CACHE_TTL_HOURS=3
MONITORING_PAUSE_MINUTES=5

# Лог уровень для отладки (опционально)
# LOG_LEVEL=DEBUG
"""

    env_file = '.env'
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if 'PAIRS_CACHE_UPDATE_MINUTES' not in content:
            with open(env_file, 'a', encoding='utf-8') as f:
                f.write(env_patch)
            print("✅ Настройки добавлены в .env")
        else:
            print("ℹ️  Настройки уже есть в .env")
    else:
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_patch.strip())
        print("✅ Создан .env с базовыми настройками")


def main():
    """Главная функция скрипта."""
    show_quick_fix_info()

    print("\nВыберите действие:")
    print("1. 🔧 Применить быстрое исправление")
    print("2. 📋 Показать код для ручного применения")
    print("3. ⚙️  Создать/обновить .env настройки")
    print("4. ℹ️  Показать инструкции")
    print("5. 🚪 Выход")

    try:
        choice = input("\nВведите номер (1-5): ").strip()
    except KeyboardInterrupt:
        print("\n👋 Выход")
        return

    if choice == "1":
        print("\n🔧 Применение быстрого исправления...")
        success = apply_quick_fix()
        if success:
            print("""
✅ ИСПРАВЛЕНИЕ ПРИМЕНЕНО УСПЕШНО!

📋 Следующие шаги:
1. Перезапустите приложение: python main.py
2. Проверьте логи на сообщения с 🚀
3. Мониторьте сокращение API вызовов

🔄 Для отката используйте резервную копию в workers/
            """)
        else:
            print("❌ Не удалось применить исправление")

    elif choice == "2":
        print("\n📋 КОД ДЛЯ РУЧНОГО ПРИМЕНЕНИЯ:")
        print("=" * 60)
        print(QUICK_FIX_CODE)
        print("=" * 60)
        print("Скопируйте код выше и вставьте в workers/exchange_worker.py")

    elif choice == "3":
        print("\n⚙️  Обновление .env настроек...")
        create_env_patch()

    elif choice == "4":
        show_quick_fix_info()

    elif choice == "5":
        print("👋 Выход")

    else:
        print("❌ Неверный выбор")


if __name__ == "__main__":
    main()