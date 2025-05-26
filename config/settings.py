"""
Конфигурационный файл с настройками для всех бирж.
"""
import os
from decimal import Decimal

# === ОБЩИЕ НАСТРОЙКИ ===
MIN_TRADE_VALUE_USD = 49000  # Минимальная сумма сделки в USD для сохранения
MIN_VOLUME_USD = 500000      # Минимальный объем торгов пары за 24ч
MONITORING_PAUSE_MINUTES = 5  # Пауза между циклами для Binance
BATCH_SIZE = 50              # Размер батча для обработки пар

# === НАСТРОЙКИ ПАРАЛЛЕЛИЗМА ===
MAX_CONCURRENT_REQUESTS = 10  # Максимум одновременных запросов для Binance
MAX_WEIGHT_PER_MINUTE = 1200  # Лимит весов Binance в минуту

# === НАСТРОЙКИ ПОВТОРНЫХ ЗАПРОСОВ ===
MAX_RETRIES = 3              # Максимум повторных попыток
RETRY_DELAY = 2              # Задержка между повторными попытками (секунды)
DELAY_BETWEEN_REQUESTS = 0.05  # Задержка между запросами (секунды)

# === SSL НАСТРОЙКИ ===
DISABLE_SSL_VERIFY = os.getenv('DISABLE_SSL_VERIFY', 'false').lower() == 'true'

# === КОНФИГУРАЦИЯ БАЗ ДАННЫХ ===
MYSQL_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'port': int(os.getenv('MYSQL_PORT', 3306)),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'db': os.getenv('MYSQL_DATABASE', 'crypto_trades'),
    'charset': 'utf8mb4',
    'connect_timeout': 60,
    'read_timeout': 30,
    'write_timeout': 30,
}

# === КОНФИГУРАЦИЯ БИРЖ ===
EXCHANGES_CONFIG = {
    'binance': {
        'api_url': 'https://api.binance.com',
        'trades_limit': 1000,  # Максимум сделок за запрос
        'rate_limit_per_minute': 1200,  # Вес лимит в минуту
        'weights': {
            'exchange_info': 10,
            'tickers': 40,
            'trades': 1,
        }
    },
    'bybit': {
        'api_url': 'https://api.bybit.com',
        'trades_limit': 60,    # Максимум сделок за запрос (ограничение Bybit)
        'rate_limit_per_second': 10,  # Запросов в секунду (оценочно)
        'weights': {
            'exchange_info': 1,
            'tickers': 1,
            'trades': 1,
        },
        # Агрессивный мониторинг
        'aggressive_mode': {
            'request_delay': 0.05,      # 50ms между запросами
            'max_concurrent_pairs': 5,  # Максимум пар одновременно
            'batch_save_interval': 2,   # Интервал сохранения в секундах
        }
    },
    'coinbase': {
        'api_url': 'https://api.coinbase.com/api/v3/brokerage',
        'trades_limit': 100,   # Максимум сделок за запрос (оценочно)
        'rate_limit_per_second': 10,  # 10 RPS для публичных endpoints
        'weights': {
            'products': 1,
            'trades': 1,
        },
        # Агрессивный мониторинг
        'aggressive_mode': {
            'request_delay': 0.1,       # 100ms между запросами (10 RPS)
            'max_concurrent_pairs': 8,  # Больше пар из-за лучшего лимита
            'batch_save_interval': 3,   # Интервал сохранения в секундах
        }
    }
}

# === ФИЛЬТРЫ ТОРГОВЫХ ПАР ===
# Стейблкоины (не мониторим как базовый актив)
STABLECOINS = {
    'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'USDP', 'USDD', 'FRAX', 'LUSD'
}

# Поддерживаемые котировочные валюты
SUPPORTED_QUOTE_ASSETS = {
    'USDT', 'USDC', 'BTC', 'ETH', 'BNB', 'USD', 'EUR', 'GBP'
}

# Минимальные объемы по котировочным валютам (в USD эквиваленте)
MIN_VOLUMES_BY_QUOTE = {
    'USDT': Decimal('500000'),
    'USDC': Decimal('500000'),
    'BTC': Decimal('200000'),   # Меньше из-за высокой цены BTC
    'ETH': Decimal('300000'),   # Меньше из-за высокой цены ETH
    'USD': Decimal('500000'),   # Coinbase
    'EUR': Decimal('500000'),   # Coinbase EUR пары
    'GBP': Decimal('500000'),   # Coinbase GBP пары
}

# === НАСТРОЙКИ ЛОГИРОВАНИЯ ===
LOG_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': 'crypto_monitor.log',
    'max_bytes': 10 * 1024 * 1024,  # 10MB
    'backup_count': 5,
}

# === УВЕДОМЛЕНИЯ (для будущего расширения) ===
NOTIFICATIONS_CONFIG = {
    'enabled': False,
    'min_trade_value_for_alert': 100000,  # $100k+ сделки для уведомлений
    'channels': {
        'telegram': {
            'enabled': False,
            'bot_token': os.getenv('TELEGRAM_BOT_TOKEN', ''),
            'chat_id': os.getenv('TELEGRAM_CHAT_ID', ''),
        },
        'discord': {
            'enabled': False,
            'webhook_url': os.getenv('DISCORD_WEBHOOK_URL', ''),
        }
    }
}

# === МОНИТОРИНГ И СТАТИСТИКА ===
MONITORING_CONFIG = {
    'stats_interval': 30,           # Интервал вывода статистики (секунды)
    'health_check_interval': 300,   # Интервал проверки здоровья системы (секунды)
    'max_memory_usage_mb': 1024,    # Максимальное использование памяти (MB)
    'cleanup_old_trades_days': 30,  # Удалять сделки старше N дней (0 = не удалять)
}

# === ЦЕНЫ КОТИРОВОЧНЫХ АКТИВОВ (по умолчанию) ===
DEFAULT_QUOTE_PRICES_USD = {
    'USDT': Decimal('1.0'),
    'USDC': Decimal('1.0'),
    'BUSD': Decimal('1.0'),
    'DAI': Decimal('1.0'),
    'USD': Decimal('1.0'),
    'EUR': Decimal('1.1'),     # Примерная цена EUR/USD
    'GBP': Decimal('1.25'),    # Примерная цена GBP/USD
    # Цены BTC, ETH, BNB будут обновляться динамически
}

# === КОНВЕРСИЯ СИМВОЛОВ ===
SYMBOL_CONVERSIONS = {
    # Конверсия из внутреннего формата в формат биржи
    'coinbase': {
        'BTCUSDT': 'BTC-USD',
        'ETHUSDT': 'ETH-USD',
        'SOLUSDT': 'SOL-USD',
        'ADAUSDT': 'ADA-USD',
        'DOGEUSDT': 'DOGE-USD',
        'MATICUSDT': 'MATIC-USD',
        'AVAXUSDT': 'AVAX-USD',
        'DOTUSDT': 'DOT-USD',
        'LINKUSDT': 'LINK-USD',
        'UNIUSDT': 'UNI-USD',
    },
    # Bybit и Binance используют одинаковый формат
    'bybit': {},
    'binance': {},
}

# === РЕЖИМЫ РАБОТЫ ===
OPERATION_MODES = {
    'development': {
        'min_trade_value_usd': 10000,    # Меньшая сумма для тестирования
        'max_concurrent_pairs': 3,       # Меньше пар для тестирования
        'log_level': 'DEBUG',
        'save_all_trades': True,         # Сохранять все сделки для анализа
    },
    'production': {
        'min_trade_value_usd': MIN_TRADE_VALUE_USD,
        'max_concurrent_pairs': 10,
        'log_level': 'INFO',
        'save_all_trades': False,        # Только крупные сделки
    }
}

# Текущий режим (можно переключать через переменную окружения)
CURRENT_MODE = os.getenv('CRYPTO_MONITOR_MODE', 'production').lower()
if CURRENT_MODE in OPERATION_MODES:
    MODE_CONFIG = OPERATION_MODES[CURRENT_MODE]
else:
    MODE_CONFIG = OPERATION_MODES['production']

# === БЕЗОПАСНОСТЬ ===
SECURITY_CONFIG = {
    'max_request_retries': MAX_RETRIES,
    'request_timeout': 30,              # Таймаут запроса в секундах
    'connection_pool_size': 150,        # Размер пула соединений
    'connection_pool_per_host': 50,     # Соединений на хост
    'enable_request_logging': False,    # Логировать все HTTP запросы
    'rate_limit_buffer': 0.1,          # Буфер для rate limits (10%)
}

# === ПРОИЗВОДИТЕЛЬНОСТЬ ===
PERFORMANCE_CONFIG = {
    'database_pool_size': 10,           # Размер пула соединений с БД
    'batch_insert_size': 100,           # Размер батча для вставки в БД
    'memory_cache_size': 10000,         # Размер кэша в памяти (записей)
    'gc_interval': 3600,                # Интервал сборки мусора (секунды)
    'optimize_queries': True,           # Оптимизировать SQL запросы
}

# === ОТЛАДКА И ПРОФИЛИРОВАНИЕ ===
DEBUG_CONFIG = {
    'enabled': os.getenv('DEBUG', 'false').lower() == 'true',
    'profile_performance': False,       # Профилировать производительность
    'log_sql_queries': False,          # Логировать SQL запросы
    'save_raw_responses': False,       # Сохранять сырые ответы API
    'mock_mode': False,                # Режим эмуляции (без реальных запросов)
}

# === EXPORT ВСЕХ НАСТРОЕК ===
__all__ = [
    'MIN_TRADE_VALUE_USD', 'MIN_VOLUME_USD', 'MONITORING_PAUSE_MINUTES',
    'BATCH_SIZE', 'MAX_CONCURRENT_REQUESTS', 'MAX_WEIGHT_PER_MINUTE',
    'MAX_RETRIES', 'RETRY_DELAY', 'DELAY_BETWEEN_REQUESTS',
    'DISABLE_SSL_VERIFY', 'MYSQL_CONFIG', 'EXCHANGES_CONFIG',
    'STABLECOINS', 'SUPPORTED_QUOTE_ASSETS', 'MIN_VOLUMES_BY_QUOTE',
    'LOG_CONFIG', 'NOTIFICATIONS_CONFIG', 'MONITORING_CONFIG',
    'DEFAULT_QUOTE_PRICES_USD', 'SYMBOL_CONVERSIONS', 'OPERATION_MODES',
    'CURRENT_MODE', 'MODE_CONFIG', 'SECURITY_CONFIG', 'PERFORMANCE_CONFIG',
    'DEBUG_CONFIG'
]