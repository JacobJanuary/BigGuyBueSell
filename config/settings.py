"""
Общие настройки проекта для мониторинга крупных сделок.
"""
import os
from typing import Dict, Any
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# MySQL конфигурация
MYSQL_CONFIG: Dict[str, Any] = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'port': int(os.getenv('MYSQL_PORT', 3306)),
    'user': os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'db': os.getenv('MYSQL_DATABASE', 'crypto_db'),
}

# Фильтры для сделок
MIN_VOLUME_USD = 1_000_000  # Минимальный объем торгов за 24 часа
MIN_TRADE_VALUE_USD = 49_000  # Минимальная сумма сделки для вывода

# Rate limit настройки
MAX_CONCURRENT_REQUESTS = 3
MAX_WEIGHT_PER_MINUTE = 1200
DELAY_BETWEEN_REQUESTS = 0.2
RETRY_DELAY = 5
MAX_RETRIES = 3

# Настройки мониторинга
MONITORING_PAUSE_MINUTES = 5  # Пауза между циклами мониторинга
BATCH_SIZE = 30  # Размер батча для обработки пар

# SSL настройки
DISABLE_SSL_VERIFY = os.getenv('DISABLE_SSL_VERIFY', 'false').lower() == 'true'

# Настройки для разных бирж
EXCHANGES_CONFIG = {
    'binance': {
        'api_url': 'https://api.binance.com',
        'trades_limit': 1000,
        'weights': {
            'trades': 10,
            'exchange_info': 20,
            'tickers': 40
        }
    },
    'bybit': {
        'api_url': 'https://api.bybit.com',
        'trades_limit': 60,  # Bybit ограничивает до 60 для спота
        'weights': {
            'trades': 1,
            'exchange_info': 1,
            'tickers': 1
        }
    },
    'okx': {
        'api_url': 'https://www.okx.com',
        'trades_limit': 100,
        'weights': {
            'trades': 1,
            'exchange_info': 1,
            'tickers': 1
        }
    }
}