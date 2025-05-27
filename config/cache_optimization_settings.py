"""
Дополнительные настройки для оптимизации кэширования.
config/cache_optimization_settings.py

Добавьте эти настройки в основной config/settings.py или импортируйте из этого файла.
"""
import os
from typing import Dict, Any


# Функции для безопасного получения переменных окружения
def get_env_int(key: str, default: int) -> int:
    """Безопасно получает integer из переменных окружения."""
    try:
        value = os.getenv(key)
        if value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def get_env_bool(key: str, default: bool) -> bool:
    """Безопасно получает boolean из переменных окружения."""
    value = os.getenv(key, '').lower()
    if value in ('true', '1', 'yes', 'on'):
        return True
    elif value in ('false', '0', 'no', 'off'):
        return False
    return default


def get_env_float(key: str, default: float) -> float:
    """Безопасно получает float из переменных окружения."""
    try:
        value = os.getenv(key)
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


# === ОПТИМИЗИРОВАННЫЕ НАСТРОЙКИ КЭШИРОВАНИЯ ===

# Основные настройки кэша
CACHE_OPTIMIZATION_ENABLED = get_env_bool('CACHE_OPTIMIZATION_ENABLED', True)
MEMORY_CACHE_ENABLED = get_env_bool('MEMORY_CACHE_ENABLED', True)
CACHE_WARMUP_ON_START = get_env_bool('CACHE_WARMUP_ON_START', True)
CACHE_BACKGROUND_UPDATE = get_env_bool('CACHE_BACKGROUND_UPDATE', True)

# Времена жизни кэша (в минутах/часах)
MEMORY_CACHE_TTL_MINUTES = get_env_int('MEMORY_CACHE_TTL_MINUTES', 30)
DB_CACHE_TTL_HOURS = get_env_int('DB_CACHE_TTL_HOURS', 2)
FALLBACK_CACHE_TTL_HOURS = get_env_int('FALLBACK_CACHE_TTL_HOURS', 6)
API_UPDATE_INTERVAL_MINUTES = get_env_int('API_UPDATE_INTERVAL_MINUTES', 60)

# Настройки производительности
MAX_CACHE_SIZE_MB = get_env_int('MAX_CACHE_SIZE_MB', 100)
CACHE_COMPRESSION_ENABLED = get_env_bool('CACHE_COMPRESSION_ENABLED', False)
CACHE_PRELOAD_TOP_PAIRS = get_env_int('CACHE_PRELOAD_TOP_PAIRS', 50)

# Настройки стратегий обновления
CACHE_UPDATE_STRATEGY = os.getenv('CACHE_UPDATE_STRATEGY', 'scheduled')  # scheduled, adaptive, aggressive
CACHE_SMART_INVALIDATION = get_env_bool('CACHE_SMART_INVALIDATION', True)
CACHE_PREDICTIVE_UPDATE = get_env_bool('CACHE_PREDICTIVE_UPDATE', False)

# Настройки мониторинга
CACHE_METRICS_ENABLED = get_env_bool('CACHE_METRICS_ENABLED', True)
CACHE_METRICS_INTERVAL_MINUTES = get_env_int('CACHE_METRICS_INTERVAL_MINUTES', 15)
CACHE_EFFICIENCY_THRESHOLD = get_env_int('CACHE_EFFICIENCY_THRESHOLD', 80)
CACHE_DEBUG_LOGGING = get_env_bool('CACHE_DEBUG_LOGGING', False)

# Пороги для алертов
CACHE_HIT_RATE_WARNING_THRESHOLD = get_env_int('CACHE_HIT_RATE_WARNING_THRESHOLD', 70)
CACHE_HIT_RATE_CRITICAL_THRESHOLD = get_env_int('CACHE_HIT_RATE_CRITICAL_THRESHOLD', 50)
API_CALLS_PER_HOUR_WARNING = get_env_int('API_CALLS_PER_HOUR_WARNING', 10)
API_CALLS_PER_HOUR_CRITICAL = get_env_int('API_CALLS_PER_HOUR_CRITICAL', 20)

# Настройки fallback поведения
CACHE_FALLBACK_ENABLED = get_env_bool('CACHE_FALLBACK_ENABLED', True)
CACHE_GRACEFUL_DEGRADATION = get_env_bool('CACHE_GRACEFUL_DEGRADATION', True)
API_FAILURE_CACHE_EXTEND_HOURS = get_env_int('API_FAILURE_CACHE_EXTEND_HOURS', 2)

# Экспериментальные настройки
CACHE_ASYNC_UPDATE = get_env_bool('CACHE_ASYNC_UPDATE', False)
CACHE_LAZY_LOADING = get_env_bool('CACHE_LAZY_LOADING', True)
CACHE_PARTITIONING_ENABLED = get_env_bool('CACHE_PARTITIONING_ENABLED', False)

# === КОНФИГУРАЦИЯ ДЛЯ РАЗНЫХ РЕЖИМОВ ===

# Режим высокой производительности
HIGH_PERFORMANCE_CONFIG = {
    'MEMORY_CACHE_TTL_MINUTES': 60,
    'API_UPDATE_INTERVAL_MINUTES': 120,
    'CACHE_PRELOAD_TOP_PAIRS': 100,
    'CACHE_ASYNC_UPDATE': True,
    'CACHE_PREDICTIVE_UPDATE': True
}

# Режим низкого потребления API
LOW_API_USAGE_CONFIG = {
    'MEMORY_CACHE_TTL_MINUTES': 45,
    'API_UPDATE_INTERVAL_MINUTES': 180,
    'FALLBACK_CACHE_TTL_HOURS': 12,
    'CACHE_GRACEFUL_DEGRADATION': True,
    'API_FAILURE_CACHE_EXTEND_HOURS': 6
}

# Режим отладки
DEBUG_CONFIG = {
    'CACHE_DEBUG_LOGGING': True,
    'CACHE_METRICS_INTERVAL_MINUTES': 5,
    'MEMORY_CACHE_TTL_MINUTES': 10,
    'API_UPDATE_INTERVAL_MINUTES': 30
}


# === ФУНКЦИИ ДЛЯ ПРИМЕНЕНИЯ КОНФИГУРАЦИЙ ===

def apply_config_mode(mode: str) -> Dict[str, Any]:
    """
    Применяет предустановленную конфигурацию.

    Args:
        mode: Режим конфигурации ('high_performance', 'low_api_usage', 'debug')

    Returns:
        Словарь с настройками
    """
    configs = {
        'high_performance': HIGH_PERFORMANCE_CONFIG,
        'low_api_usage': LOW_API_USAGE_CONFIG,
        'debug': DEBUG_CONFIG
    }

    return configs.get(mode, {})


def get_cache_config_summary() -> Dict[str, Any]:
    """
    Возвращает сводку текущей конфигурации кэша.

    Returns:
        Словарь с основными настройками
    """
    return {
        'optimization_enabled': CACHE_OPTIMIZATION_ENABLED,
        'memory_cache_enabled': MEMORY_CACHE_ENABLED,
        'memory_ttl_minutes': MEMORY_CACHE_TTL_MINUTES,
        'api_interval_minutes': API_UPDATE_INTERVAL_MINUTES,
        'db_ttl_hours': DB_CACHE_TTL_HOURS,
        'metrics_enabled': CACHE_METRICS_ENABLED,
        'fallback_enabled': CACHE_FALLBACK_ENABLED,
        'update_strategy': CACHE_UPDATE_STRATEGY
    }


def validate_cache_config() -> List[str]:
    """
    Валидирует конфигурацию кэша и возвращает предупреждения.

    Returns:
        Список предупреждений/ошибок конфигурации
    """
    warnings = []

    if MEMORY_CACHE_TTL_MINUTES > API_UPDATE_INTERVAL_MINUTES:
        warnings.append(
            f"Memory cache TTL ({MEMORY_CACHE_TTL_MINUTES}мин) меньше интервала API обновлений "
            f"({API_UPDATE_INTERVAL_MINUTES}мин) - возможны частые API вызовы"
        )

    if API_UPDATE_INTERVAL_MINUTES < 30:
        warnings.append(
            f"Слишком частые API обновления ({API_UPDATE_INTERVAL_MINUTES}мин) - "
            f"рекомендуется минимум 30 минут"
        )

    if not CACHE_FALLBACK_ENABLED and not MEMORY_CACHE_ENABLED:
        warnings.append(
            "Отключены и memory cache, и fallback - система может быть нестабильной"
        )

    if MAX_CACHE_SIZE_MB > 500:
        warnings.append(
            f"Большой размер кэша ({MAX_CACHE_SIZE_MB}MB) - может влиять на память"
        )

    return warnings


# === ПАТЧ ДЛЯ ДОБАВЛЕНИЯ В ОСНОВНОЙ settings.py ===

SETTINGS_PATCH = '''
# === ДОБАВЬТЕ В config/settings.py ===

# Импорт оптимизированных настроек кэширования
try:
    from .cache_optimization_settings import (
        CACHE_OPTIMIZATION_ENABLED,
        MEMORY_CACHE_ENABLED,
        MEMORY_CACHE_TTL_MINUTES,
        API_UPDATE_INTERVAL_MINUTES,
        DB_CACHE_TTL_HOURS,
        CACHE_METRICS_ENABLED,
        CACHE_FALLBACK_ENABLED,
        get_cache_config_summary,
        validate_cache_config
    )

    # Выводим сводку конфигурации при отладке
    if LOG_LEVEL == 'DEBUG':
        print("🔧 Конфигурация оптимизированного кэширования:")
        config_summary = get_cache_config_summary()
        for key, value in config_summary.items():
            print(f"  {key}: {value}")

        # Проверяем конфигурацию
        config_warnings = validate_cache_config()
        if config_warnings:
            print("⚠️  Предупреждения конфигурации кэша:")
            for warning in config_warnings:
                print(f"  - {warning}")
        else:
            print("✅ Конфигурация кэша корректна")

except ImportError:
    # Fallback значения если модуль недоступен
    CACHE_OPTIMIZATION_ENABLED = True
    MEMORY_CACHE_ENABLED = True
    MEMORY_CACHE_TTL_MINUTES = 30
    API_UPDATE_INTERVAL_MINUTES = 60
    DB_CACHE_TTL_HOURS = 2
    CACHE_METRICS_ENABLED = True
    CACHE_FALLBACK_ENABLED = True
    print("⚠️  Используются базовые настройки кэша")
'''


def print_integration_instructions():
    """Выводит инструкции по интеграции."""
    print("""
╔═══════════════════════════════════════════════════╗
║       ИНСТРУКЦИИ ПО ИНТЕГРАЦИИ НАСТРОЕК           ║
╚═══════════════════════════════════════════════════╝

1. 📁 СОЗДАНИЕ ФАЙЛА
   Сохраните этот файл как: config/cache_optimization_settings.py

2. 🔧 ОБНОВЛЕНИЕ settings.py
   Добавьте в конец файла config/settings.py:

   # Импорт оптимизированных настроек кэширования
   from .cache_optimization_settings import *

3. 🌐 НАСТРОЙКА .env
   Добавьте в .env файл:

   # Оптимизация кэширования
   CACHE_OPTIMIZATION_ENABLED=true
   MEMORY_CACHE_ENABLED=true
   MEMORY_CACHE_TTL_MINUTES=30
   API_UPDATE_INTERVAL_MINUTES=60
   CACHE_METRICS_ENABLED=true
   CACHE_FALLBACK_ENABLED=true

4. 🧪 ПРОВЕРКА
   Запустите: python config/cache_optimization_settings.py

5. 🔄 ПРИМЕНЕНИЕ
   Перезапустите приложение для применения настроек

📊 МОНИТОРИНГ ЭФФЕКТИВНОСТИ:
   - Следите за логами на предмет сообщений о кэше
   - Проверяйте метрики hit_rate (должен быть >80%)
   - Контролируйте количество API вызовов в час (<10)
    """)


if __name__ == "__main__":
    print("🔧 Анализ конфигурации оптимизированного кэширования")
    print("=" * 60)

    # Показываем текущую конфигурацию
    config = get_cache_config_summary()
    print("\n📋 Текущая конфигурация:")
    for key, value in config.items():
        print(f"  {key}: {value}")

    # Проверяем на предупреждения
    warnings = validate_cache_config()
    if warnings:
        print(f"\n⚠️  Предупреждения ({len(warnings)}):")
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("\n✅ Конфигурация корректна")

    # Показываем инструкции
    print_integration_instructions()