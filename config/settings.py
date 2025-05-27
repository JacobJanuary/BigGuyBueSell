"""
Исправленные настройки проекта для мониторинга крупных сделок.
"""
import os
from typing import Dict, Any
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

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

# MySQL конфигурация
MYSQL_CONFIG: Dict[str, Any] = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'port': get_env_int('MYSQL_PORT', 3306),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'db': os.getenv('MYSQL_DATABASE', 'crypto_db'),
}

# Основные настройки
MIN_VOLUME_USD = get_env_int('MIN_VOLUME_USD', 1_000_000)
MIN_TRADE_VALUE_USD = get_env_int('MIN_TRADE_VALUE_USD', 49_000)
MAX_CONCURRENT_REQUESTS = get_env_int('MAX_CONCURRENT_REQUESTS', 3)
MAX_WEIGHT_PER_MINUTE = get_env_int('MAX_WEIGHT_PER_MINUTE', 1200)
DELAY_BETWEEN_REQUESTS = float(os.getenv('DELAY_BETWEEN_REQUESTS', '0.2'))
RETRY_DELAY = get_env_int('RETRY_DELAY', 5)
MAX_RETRIES = get_env_int('MAX_RETRIES', 3)
# Настройки кэша торговых пар
PAIRS_CACHE_UPDATE_MINUTES = get_env_int('PAIRS_CACHE_UPDATE_MINUTES', 60)  # Интервал обновления кэша
PAIRS_CACHE_TTL_HOURS = get_env_int('PAIRS_CACHE_TTL_HOURS', 2)  # Время жизни кэша
PAIRS_CACHE_CLEANUP_DAYS = get_env_int('PAIRS_CACHE_CLEANUP_DAYS', 7)  # Очистка старых записей

MONITORING_PAUSE_MINUTES = get_env_int('MONITORING_PAUSE_MINUTES', 5)
BATCH_SIZE = get_env_int('BATCH_SIZE', 30)
STATS_REPORT_MINUTES = get_env_int('STATS_REPORT_MINUTES', 10)
HEALTH_CHECK_MINUTES = get_env_int('HEALTH_CHECK_MINUTES', 15)
DISABLE_SSL_VERIFY = get_env_bool('DISABLE_SSL_VERIFY', False)
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# Конфигурация бирж
EXCHANGES_CONFIG = {
    'binance': {
        'api_url': 'https://api.binance.com',
        'trades_limit': get_env_int('BINANCE_TRADES_LIMIT', 1000),
        'cycle_pause_minutes': get_env_int('BINANCE_CYCLE_MINUTES', 5),
        'rate_limit': get_env_int('BINANCE_RATE_LIMIT', MAX_WEIGHT_PER_MINUTE),
        'enabled': get_env_bool('BINANCE_ENABLED', True),
        'weights': {
            'trades': 10,
            'exchange_info': 20,
            'tickers': 40
        }
    },
    'bybit': {
        'api_url': 'https://api.bybit.com',
        'trades_limit': get_env_int('BYBIT_TRADES_LIMIT', 60),
        'cycle_pause_minutes': get_env_int('BYBIT_CYCLE_MINUTES', 3),
        'rate_limit': get_env_int('BYBIT_RATE_LIMIT', MAX_WEIGHT_PER_MINUTE),
        'enabled': get_env_bool('BYBIT_ENABLED', True),
        'weights': {
            'trades': 1,
            'exchange_info': 1,
            'tickers': 1
        }
    },
    'coinbase': {
        'api_url': 'https://api.exchange.coinbase.com',
        'trades_limit': get_env_int('COINBASE_TRADES_LIMIT', 1000),
        'cycle_pause_minutes': get_env_int('COINBASE_CYCLE_MINUTES', 7),
        'rate_limit': get_env_int('COINBASE_RATE_LIMIT', 600),
        'enabled': get_env_bool('COINBASE_ENABLED', True),
        'weights': {
            'trades': 1,
            'exchange_info': 1,
            'tickers': 1
        }
    },
    'okx': {
        'api_url': 'https://www.okx.com',
        'trades_limit': get_env_int('OKX_TRADES_LIMIT', 100),
        'cycle_pause_minutes': get_env_int('OKX_CYCLE_MINUTES', 4),
        'rate_limit': get_env_int('OKX_RATE_LIMIT', MAX_WEIGHT_PER_MINUTE),
        'enabled': get_env_bool('OKX_ENABLED', True),  # ← ВАЖНО: True!
        'weights': {
            'trades': 1,
            'exchange_info': 1,
            'tickers': 1
        }
    }
}

# Отладочная информация
if LOG_LEVEL == 'DEBUG':
    print("🔧 Загруженные настройки:")
    print(f"  MySQL: {MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']}")
    print(f"  SSL проверка: {'отключена' if DISABLE_SSL_VERIFY else 'включена'}")
    for exchange, config in EXCHANGES_CONFIG.items():
        if config['enabled']:
            print(f"  {exchange.upper()}: пауза {config['cycle_pause_minutes']}мин, лимит {config['rate_limit']}/мин")
        else:
            print(f"  {exchange.upper()}: ОТКЛЮЧЕН")

# =================== ОПТИМИЗАЦИЯ КЭШИРОВАНИЯ ===================

# Основные настройки кэширования
CACHE_OPTIMIZATION_ENABLED = get_env_bool('CACHE_OPTIMIZATION_ENABLED', True)
MEMORY_CACHE_ENABLED = get_env_bool('MEMORY_CACHE_ENABLED', True)
MEMORY_CACHE_TTL_MINUTES = get_env_int('MEMORY_CACHE_TTL_MINUTES', 30)
API_UPDATE_INTERVAL_MINUTES = get_env_int('API_UPDATE_INTERVAL_MINUTES', 60)
DB_CACHE_TTL_HOURS = get_env_int('DB_CACHE_TTL_HOURS', 2)

# Настройки мониторинга кэша
CACHE_METRICS_ENABLED = get_env_bool('CACHE_METRICS_ENABLED', True)
CACHE_FALLBACK_ENABLED = get_env_bool('CACHE_FALLBACK_ENABLED', True)
CACHE_DEBUG_LOGGING = get_env_bool('CACHE_DEBUG_LOGGING', False)

# Пороги для оптимизации
CACHE_HIT_RATE_WARNING_THRESHOLD = get_env_int('CACHE_HIT_RATE_WARNING_THRESHOLD', 70)
API_CALLS_PER_HOUR_WARNING = get_env_int('API_CALLS_PER_HOUR_WARNING', 10)

if LOG_LEVEL == 'DEBUG':
    print("🚀 Настройки оптимизированного кэширования загружены")

# ============================================================
