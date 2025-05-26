#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

# --- Константы для OKX ---
OKX_API_BASE_URL: str = "https://www.okx.com"
# Задержка между API-запросами для соблюдения лимитов OKX (10 req/sec)
OKX_API_REQUEST_DELAY: float = 0.11  # ~9 запросов в секунду
VOLUME_THRESHOLD_USD: float = 1_000_000.0
SIGNIFICANT_TRADE_THRESHOLD_USD: float = 20_000.0
# Максимальное количество сделок для запроса за один раз для OKX (для недавних сделок)
OKX_MAX_TRADES_TO_FETCH: int = 100
# User-Agent для HTTP запросов
DEFAULT_USER_AGENT: str = "OKXMarketAnalysisScript/1.0"

# --- Глобальный кэш для курсов конвертации в USD (может быть разделен между скриптами, если запускать их в одной сессии) ---
_okx_conversion_rate_to_usd_cache: Dict[str, float] = {
    "USD": 1.0,
    "USDT": 1.0,  # USDT принимается как эквивалент USD
    "USDC": 1.0,  # USDC также принимается как эквивалент USD
}


# --- Вспомогательные функции для OKX ---

def _make_okx_api_request(
        endpoint: str, params: Optional[Dict[str, Union[str, int]]] = None
) -> Optional[Any]:
    """
    Выполняет GET-запрос к API OKX и возвращает данные из JSON-ответа.

    Args:
        endpoint: Конечная точка API (например, "/api/v5/public/instruments").
        params: Опциональный словарь параметров запроса.

    Returns:
        Поле 'data' из декодированного JSON-ответа от API или None в случае ошибки.
    """
    url = f"{OKX_API_BASE_URL}{endpoint}"
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    try:
        time.sleep(OKX_API_REQUEST_DELAY)
        response = requests.get(url, params=params, timeout=10, headers=headers)
        response.raise_for_status()
        response_json = response.json()

        if response_json.get("code") == "0":  # '0' означает успех для OKX API
            return response_json.get("data")
        else:
            print(
                f"Ошибка OKX API для {url} (Код: {response_json.get('code')}): {response_json.get('msg')}"
            )
            return None
    except requests.exceptions.Timeout:
        print(f"Ошибка: Таймаут при запросе к {url} с параметрами {params}")
    except requests.exceptions.HTTPError as http_err:
        print(f"Ошибка HTTP: {http_err} при запросе к {url} с параметрами {params}")
    except requests.exceptions.RequestException as req_err:
        print(f"Ошибка запроса: {req_err} к {url} с параметрами {params}")
    except ValueError as json_err:  # Обработка ошибок декодирования JSON
        print(f"Ошибка декодирования JSON от {url}: {json_err}")
    return None


def _get_okx_conversion_rate_to_usd(currency_code: str) -> Optional[float]:
    """
    Получает курс конвертации указанной валюты в USD, используя API OKX.

    Предпочитает конвертацию через USDT, затем USDC, затем USD.
    Использует кэш для избежания повторных API-запросов.

    Args:
        currency_code: Код валюты (например, "BTC", "ETH").

    Returns:
        Курс конвертации в USD или None, если курс не найден.
    """
    if not currency_code:
        return None
    if currency_code in _okx_conversion_rate_to_usd_cache:
        return _okx_conversion_rate_to_usd_cache[currency_code]

    # Приоритетные стабильные монеты для конвертации на OKX
    stablecoin_targets = ["USDT", "USDC", "USD"]

    for target_stable in stablecoin_targets:
        pair_id = f"{currency_code}-{target_stable}"
        # Запрос тикера для пары CURRENCY-TARGET_STABLE
        # API OKX возвращает список даже для одного тикера
        ticker_data_list = _make_okx_api_request(
            endpoint="/api/v5/market/ticker", params={"instId": pair_id}
        )

        if ticker_data_list and isinstance(ticker_data_list, list) and len(ticker_data_list) > 0:
            ticker_info = ticker_data_list[0]
            if 'last' in ticker_info and ticker_info['last']:  # Проверяем, что 'last' не пустая строка
                try:
                    price = float(ticker_info['last'])
                    # Цена CURRENCY/TARGET_STABLE. Принимаем TARGET_STABLE как 1 USD.
                    _okx_conversion_rate_to_usd_cache[currency_code] = price
                    if target_stable != "USD":  # Не логируем для прямой пары к USD
                        print(
                            f"Примечание OKX: Используется курс {pair_id} ({price}) для конвертации {currency_code} в USD-эквивалент."
                        )
                    return price
                except ValueError:
                    print(
                        f"Предупреждение OKX: Не удалось обработать цену для {pair_id} из {ticker_info}"
                    )
            # else: # отладка
            #     print(f"Предупреждение OKX: Отсутствует поле 'last' или оно пустое для {pair_id} в {ticker_info}")

    print(
        f"Предупреждение OKX: Не удалось определить курс конвертации в USD для {currency_code}."
    )
    return None


# --- Основные функции API для OKX ---

def get_tradable_spot_pairs_okx() -> List[Dict[str, Any]]:
    """
    Получает список всех торгуемых спотовых пар с OKX.

    Фильтрует инструменты по instType="SPOT" и state="live".

    Returns:
        Список словарей, где каждый словарь представляет торговую пару (инструмент).
        Пустой список, если произошла ошибка или пары не найдены.
    """
    print("OKX: Получение списка всех торгуемых спотовых пар...")
    instruments_data = _make_okx_api_request(
        endpoint="/api/v5/public/instruments", params={"instType": "SPOT"}
    )

    if not instruments_data or not isinstance(instruments_data, list):
        return []

    spot_pairs: List[Dict[str, Any]] = []
    for instrument in instruments_data:
        if instrument.get("state") == "live":
            spot_pairs.append(instrument)

    print(f"OKX: Найдено {len(spot_pairs)} активных спотовых пар.")
    return spot_pairs


def get_product_24h_volume_usd_okx(
        product: Dict[str, Any]
) -> Optional[float]:
    """
    Определяет объем торгов для указанной пары OKX за последние 24 часа в USD.

    Args:
        product: Словарь с информацией об инструменте (торговой паре),
                 должен содержать 'instId' и 'quoteCcy'.

    Returns:
        Объем торгов в USD за 24 часа или None, если не удалось рассчитать.
    """
    product_id = product["instId"]
    quote_currency = product["quoteCcy"]

    # API OKX возвращает список даже для одного тикера
    ticker_data_list = _make_okx_api_request(
        endpoint="/api/v5/market/ticker", params={"instId": product_id}
    )

    if not ticker_data_list or not isinstance(ticker_data_list, list) or len(ticker_data_list) == 0:
        # print(f"OKX: Не удалось получить данные тикера для {product_id}.") # Слишком много логов
        return None

    ticker_info = ticker_data_list[0]

    if "volCcy24h" not in ticker_info or not ticker_info["volCcy24h"]:
        # print(f"OKX: Отсутствует или пустое поле 'volCcy24h' для {product_id}.")
        return None

    try:
        # volCcy24h - объем в валюте котировки
        volume_in_quote_currency = float(ticker_info["volCcy24h"])
    except ValueError:
        print(
            f"Ошибка OKX: конвертации объема для {product_id}: {ticker_info['volCcy24h']}"
        )
        return None

    conversion_rate = _get_okx_conversion_rate_to_usd(quote_currency)
    if conversion_rate is None:
        # print(f"OKX: Не удалось получить курс конвертации для {quote_currency} (пара {product_id}).")
        return None

    volume_in_usd = volume_in_quote_currency * conversion_rate
    return volume_in_usd


def get_recent_trades_okx(
        inst_id: str, limit: int = OKX_MAX_TRADES_TO_FETCH
) -> List[Dict[str, Any]]:
    """
    Запрашивает последние сделки для указанной торговой пары OKX.

    Args:
        inst_id: Идентификатор торговой пары (например, "BTC-USDT").
        limit: Максимальное количество сделок для запроса.

    Returns:
        Список словарей, где каждый словарь представляет сделку.
        Пустой список в случае ошибки или отсутствия сделок.
    """
    print(f"OKX: Запрос последних {limit} сделок для {inst_id}...")
    trades_data = _make_okx_api_request(
        endpoint="/api/v5/market/trades", params={"instId": inst_id, "limit": limit}
    )
    return trades_data if trades_data and isinstance(trades_data, list) else []


# --- Основной цикл для OKX ---

def main_okx() -> None:
    """
    Главная функция скрипта для OKX.
    """
    print("Запуск скрипта анализа рынка OKX...")
    _okx_conversion_rate_to_usd_cache.clear()  # Очищаем кеш на случай повторных запусков в одной сессии
    _okx_conversion_rate_to_usd_cache.update({  # Восстанавливаем базовые значения
        "USD": 1.0, "USDT": 1.0, "USDC": 1.0,
    })

    tradable_pairs = get_tradable_spot_pairs_okx()

    if not tradable_pairs:
        print("OKX: Не найдено ни одной активной спотовой пары. Завершение работы.")
        return

    print(f"\nOKX: Анализ объема торгов для {len(tradable_pairs)} пар:")
    high_volume_products_info: List[Tuple[Dict[str, Any], float]] = []

    for i, product in enumerate(tradable_pairs):
        product_id = product["instId"]
        print(f"OKX: Обработка пары {i + 1}/{len(tradable_pairs)}: {product_id}...")

        volume_usd = get_product_24h_volume_usd_okx(product)
        if volume_usd is not None:
            print(f"  OKX: Объем торгов для {product_id} за 24ч: ${volume_usd:,.2f} USD")
            if volume_usd > VOLUME_THRESHOLD_USD:
                conversion_rate = _get_okx_conversion_rate_to_usd(product["quoteCcy"])
                if conversion_rate:
                    high_volume_products_info.append((product, conversion_rate))
                    print(
                        f"  ---> OKX: {product_id} добавлен в список для анализа сделок (объем ${volume_usd:,.0f} > ${VOLUME_THRESHOLD_USD:,.0f})"
                    )
        else:
            print(f"  OKX: Не удалось определить объем в USD для {product_id}.")

    if not high_volume_products_info:
        print("\nOKX: Не найдено пар с объемом торгов выше порога. Завершение работы.")
        return

    print(
        f"\nOKX: Анализ сделок для {len(high_volume_products_info)} пар с высоким объемом:"
    )
    for product_info in high_volume_products_info:
        product, quote_to_usd_rate = product_info
        product_id = product["instId"]
        base_currency = product["baseCcy"]
        quote_currency = product["quoteCcy"]

        recent_trades = get_recent_trades_okx(product_id)
        if not recent_trades:
            print(f"  OKX: Нет недавних сделок для {product_id} или произошла ошибка.")
            continue

        print(
            f"  OKX: Найдены значительные сделки для {product_id} (выше ${SIGNIFICANT_TRADE_THRESHOLD_USD:,.0f} USD):")
        found_significant_trades = False
        for trade in recent_trades:
            try:
                trade_price = float(trade["px"])
                trade_size = float(trade["sz"])
                trade_value_in_quote_currency = trade_price * trade_size

                trade_value_usd = trade_value_in_quote_currency * quote_to_usd_rate

                if trade_value_usd > SIGNIFICANT_TRADE_THRESHOLD_USD:
                    found_significant_trades = True
                    # Конвертация времени из миллисекунд
                    trade_time_ms = int(trade["ts"])
                    trade_datetime = datetime.fromtimestamp(trade_time_ms / 1000.0)

                    print(
                        f"    - Время: {trade_datetime.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}Z, "
                        f"Сторона: {trade['side'].upper()}, "
                        f"Цена: {trade_price:.8f} {quote_currency}, "  # Цены могут иметь много знаков
                        f"Размер: {trade_size:.8f} {base_currency}, "
                        f"Стоимость: ~${trade_value_usd:,.2f} USD"
                    )
            except ValueError as e:
                print(f"    OKX: Ошибка конвертации данных для сделки ({e}): {trade}")
            except KeyError as e:
                print(f"    OKX: Отсутствует ожидаемое поле {e} в данных сделки: {trade}")

        if not found_significant_trades:
            print(f"    OKX: Значительных сделок не найдено для {product_id}.")

    print("\nOKX: Анализ завершен.")


if __name__ == "__main__":
    main_okx()