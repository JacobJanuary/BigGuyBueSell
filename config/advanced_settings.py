# Настройки для экстремальных нагрузок
EXTREME_MODE = {
    'binance': {
        'cycle_pause_minutes': 2,
        'batch_size': 50,
        'max_concurrent': 5
    },
    'bybit': {
        'cycle_pause_minutes': 1,
        'batch_size': 20,
        'max_concurrent': 3
    },
    'coinbase': {
        'cycle_pause_minutes': 10,
        'batch_size': 15,
        'max_concurrent': 2
    }
}

# Настройки для медленных сетей
SLOW_NETWORK_MODE = {
    'default_timeout': 60,
    'retry_delays': [10, 30, 60],
    'max_retries': 5
}