#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import time
from typing import Any, Dict, List, Optional, Tuple, Union

# --- Константы ---
API_BASE_URL: str = "https://api.exchange.coinbase.com"
# Задержка между API-запросами для соблюдения лимитов (в секундах)
API_REQUEST_DELAY: float = 0.05  # Примерно 3 запроса в секунду
VOLUME_THRESHOLD_USD: float = 1_000_000.0
SIGNIFICANT_TRADE_THRESHOLD_USD: float = 10_000.0
# Максимальное количество сделок для запроса за один раз (согласно документации Coinbase Exchange API)
MAX_TRADES_TO_FETCH: int = 1000
# User-Agent для HTTP запросов
DEFAULT_USER_AGENT: str = "CoinbaseMarketAnalysisScript/1.0"

# --- Глобальный кэш для курсов конвертации в USD ---
# Ключ: код валюты (например, "BTC"), Значение: цена в USD (float)
_conversion_rate_to_usd_cache: Dict[str, float] = {
    "USD": 1.0,
    "USDT": 1.0,  # Приблизительно, используется как прямой эквивалент USD
    "USDC": 1.0,  # Приблизительно, используется как прямой эквивалент USD
    # Можно добавить другие стейблкоины, если они торгуются к USD 1:1 или их курс стабилен
}


# --- Вспомогательные функции ---

def _make_api_request(
        endpoint: str, params: Optional[Dict[str, Union[str, int]]] = None
) -> Optional[Any]:
    """
    Выполняет GET-запрос к API Coinbase Exchange и возвращает JSON-ответ.

    Args:
        endpoint: Конечная точка API (например, "/products").
        params: Опциональный словарь параметров запроса.

    Returns:
        Декодированный JSON-ответ от API или None в случае ошибки.
    """
    url = f"{API_BASE_URL}{endpoint}"
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    try:
        # Добавляем небольшую задержку перед каждым запросом
        time.sleep(API_REQUEST_DELAY)
        response = requests.get(url, params=params, timeout=10, headers=headers)
        response.raise_for_status()  # Вызовет HTTPError для плохих ответов (4XX или 5XX)
        return response.json()
    except requests.exceptions.Timeout:
        print(f"Ошибка: Таймаут при запросе к {url} с параметрами {params}")
    except requests.exceptions.HTTPError as http_err:
        print(f"Ошибка HTTP: {http_err} при запросе к {url} с параметрами {params}")
    except requests.exceptions.RequestException as req_err:
        print(f"Ошибка запроса: {req_err} к {url} с параметрами {params}")
    except ValueError as json_err:  # Обработка ошибок декодирования JSON
        print(f"Ошибка декодирования JSON от {url}: {json_err}")
    return None


def _get_conversion_rate_to_usd(currency_code: str) -> Optional[float]:
    """
    Получает курс конвертации указанной валюты в USD.

    Использует кэш для избежания повторных API-запросов.
    Пытается найти пары CURRENCY-USD, затем CURRENCY-USDT, затем CURRENCY-USDC.

    Args:
        currency_code: Код валюты (например, "BTC", "ETH").

    Returns:
        Курс конвертации в USD или None, если курс не найден.
    """
    if not currency_code:
        return None
    if currency_code in _conversion_rate_to_usd_cache:
        return _conversion_rate_to_usd_cache[currency_code]

    # Основные пары для попытки конвертации
    conversion_targets = ["USD", "USDT", "USDC"]

    for target_stablecoin in conversion_targets:
        pair_id = f"{currency_code}-{target_stablecoin}"
        # print(f"Пытаюсь найти курс для {pair_id}...") # Для отладки
        ticker_data = _make_api_request(f"/products/{pair_id}/ticker")
        if ticker_data and "price" in ticker_data:
            try:
                price = float(ticker_data["price"])
                # Если цель была USDT или USDC, мы принимаем их курс 1:1 к USD для этого фактора
                # То есть, цена CURRENCY-USDT интерпретируется как CURRENCY-USD
                _conversion_rate_to_usd_cache[currency_code] = price
                if target_stablecoin != "USD":
                    print(
                        f"Примечание: Используется курс {pair_id} ({price}) для конвертации {currency_code} в USD-эквивалент."
                    )
                return price
            except ValueError:
                print(
                    f"Предупреждение: Не удалось обработать цену для {pair_id}."
                )
        # else: # Для отладки
        # print(f"Не удалось получить тикер для {pair_id} или отсутствует цена.")

    print(
        f"Предупреждение: Не удалось определить курс конвертации в USD для {currency_code}."
    )
    return None


# --- Основные функции API ---

def get_tradable_spot_pairs() -> List[Dict[str, Any]]:
    """
    Получает список всех торгуемых спотовых пар с Coinbase.

    Фильтрует продукты по типу "SPOT" и статусу "online".

    Returns:
        Список словарей, где каждый словарь представляет торговую пару.
        Пустой список, если произошла ошибка или пары не найдены.
    """
    print("Получение списка всех торгуемых спотовых пар...")
    products_data = _make_api_request("/products")
    if not products_data:
        return []

    spot_pairs: List[Dict[str, Any]] = []
    for product in products_data:
        # Coinbase Exchange API использует 'id' (e.g., BTC-USD), 'base_currency', 'quote_currency'.
        # Поле 'status' должно быть 'online'.
        # Поле 'product_type' (если есть) или аналогичное для определения спота.
        # В Coinbase Pro API это было просто. В новом Exchange API структура похожа.
        # Если product_type нет, можно смотреть на формат id или другие признаки.
        # Однако, обычно /products возвращает и так спотовые рынки, если не указано иное.
        # Будем считать, что основные пары это спот, и проверим статус.
        # Некоторые API могут иметь поле `type: "spot"` или `product_type: "SPOT"`.
        # Для Coinbase Exchange API, обычно достаточно `status == "online"` и не `auction_mode`.
        is_spot = True  # Предполагаем, что /products возвращает в основном спот
        if 'product_type' in product and product['product_type'].lower() != 'spot':
            is_spot = False
        elif 'type' in product and product['type'].lower() != 'spot':  # Альтернативное поле
            is_spot = False

        if (
                is_spot and
                product.get("status") == "online" and
                not product.get("trading_disabled", False) and
                not product.get("auction_mode", False)  # Исключаем аукционы
        ):
            spot_pairs.append(product)

    print(f"Найдено {len(spot_pairs)} активных спотовых пар.")
    return spot_pairs


def get_product_24h_volume_usd(
        product: Dict[str, Any]
) -> Optional[float]:
    """
    Определяет объем торгов для указанной пары за последние 24 часа в USD.

    Args:
        product: Словарь с информацией о продукте (торговой паре),
                 должен содержать 'id' и 'quote_currency'.

    Returns:
        Объем торгов в USD за 24 часа или None, если не удалось рассчитать.
    """
    product_id = product["id"]
    quote_currency = product["quote_currency"]

    ticker_data = _make_api_request(f"/products/{product_id}/ticker")
    if not ticker_data or "volume" not in ticker_data or "price" not in ticker_data:
        # print(f"Не удалось получить данные тикера для {product_id}.") # Слишком много логов
        return None

    try:
        volume_in_base_currency = float(ticker_data["volume"])
        # 'price' в тикере - это последняя цена сделки, используем ее для оценки объема
        last_price_in_quote_currency = float(ticker_data["price"])
    except ValueError:
        print(
            f"Ошибка конвертации данных объема/цены для {product_id}: {ticker_data}"
        )
        return None

    volume_in_quote_currency = volume_in_base_currency * last_price_in_quote_currency

    conversion_rate = _get_conversion_rate_to_usd(quote_currency)
    if conversion_rate is None:
        # print(f"Не удалось получить курс конвертации для {quote_currency} (пара {product_id}).")
        return None

    volume_in_usd = volume_in_quote_currency * conversion_rate
    return volume_in_usd


def get_recent_trades(
        product_id: str, limit: int = MAX_TRADES_TO_FETCH
) -> List[Dict[str, Any]]:
    """
    Запрашивает последние сделки для указанной торговой пары.

    Args:
        product_id: Идентификатор торговой пары (например, "BTC-USD").
        limit: Максимальное количество сделок для запроса.

    Returns:
        Список словарей, где каждый словарь представляет сделку.
        Пустой список в случае ошибки или отсутствия сделок.
    """
    print(f"Запрос последних {limit} сделок для {product_id}...")
    trades_data = _make_api_request(
        f"/products/{product_id}/trades", params={"limit": limit}
    )
    return trades_data if trades_data else []


# --- Основной цикл ---

def main() -> None:
    """
    Главная функция скрипта.
    """
    print("Запуск скрипта анализа рынка Coinbase...")
    tradable_pairs = get_tradable_spot_pairs()

    if not tradable_pairs:
        print("Не найдено ни одной активной спотовой пары. Завершение работы.")
        return

    print(f"\nАнализ объема торгов для {len(tradable_pairs)} пар:")
    high_volume_products_info: List[Tuple[Dict[str, Any], float]] = []  # (product, conversion_rate_for_quote_to_usd)

    for i, product in enumerate(tradable_pairs):
        product_id = product["id"]
        print(f"Обработка пары {i + 1}/{len(tradable_pairs)}: {product_id}...")

        volume_usd = get_product_24h_volume_usd(product)
        if volume_usd is not None:
            print(f"  Объем торгов для {product_id} за 24ч: ${volume_usd:,.2f} USD")
            if volume_usd > VOLUME_THRESHOLD_USD:
                # Получаем курс конвертации еще раз, т.к. get_product_24h_volume_usd его не возвращает
                # Это немного неэффективно, но _get_conversion_rate_to_usd кэширует результат.
                # Либо get_product_24h_volume_usd должен возвращать и курс.
                # Для простоты оставим так, кэш поможет.
                conversion_rate = _get_conversion_rate_to_usd(product["quote_currency"])
                if conversion_rate:  # Должен быть, раз volume_usd рассчитан
                    high_volume_products_info.append((product, conversion_rate))
                    print(
                        f"  ---> {product_id} добавлен в список для анализа сделок (объем ${volume_usd:,.0f} > ${VOLUME_THRESHOLD_USD:,.0f})"
                    )
        else:
            print(f"  Не удалось определить объем в USD для {product_id}.")

        # Небольшая пауза между обработкой пар, чтобы не нагружать API сверх меры,
        # если _get_conversion_rate_to_usd делает несколько вызовов.
        # time.sleep(0.1) # Дополнительно к задержке в _make_api_request

    if not high_volume_products_info:
        print("\nНе найдено пар с объемом торгов выше порога. Завершение работы.")
        return

    print(
        f"\nАнализ сделок для {len(high_volume_products_info)} пар с высоким объемом:"
    )
    for product_info in high_volume_products_info:
        product, quote_to_usd_rate = product_info
        product_id = product["id"]
        base_currency = product["base_currency"]
        quote_currency = product["quote_currency"]

        recent_trades = get_recent_trades(product_id)
        if not recent_trades:
            print(f"  Нет недавних сделок для {product_id} или произошла ошибка.")
            continue

        print(f"  Найдены значительные сделки для {product_id} (выше ${SIGNIFICANT_TRADE_THRESHOLD_USD:,.0f} USD):")
        found_significant_trades = False
        for trade in recent_trades:
            try:
                trade_price = float(trade["price"])
                trade_size = float(trade["size"])
                trade_value_in_quote_currency = trade_price * trade_size

                trade_value_usd = trade_value_in_quote_currency * quote_to_usd_rate

                if trade_value_usd > SIGNIFICANT_TRADE_THRESHOLD_USD:
                    found_significant_trades = True
                    print(
                        f"    - Время: {trade['time']}, Сторона: {trade['side'].upper()}, "
                        f"Цена: {trade_price:.2f} {quote_currency}, "
                        f"Размер: {trade_size:.8f} {base_currency}, "
                        f"Стоимость: ~${trade_value_usd:,.2f} USD"
                    )
            except ValueError:
                print(f"    Ошибка конвертации данных для сделки: {trade}")
            except KeyError as e:
                print(f"    Отсутствует ожидаемое поле {e} в данных сделки: {trade}")

        if not found_significant_trades:
            print(f"    Значительных сделок не найдено для {product_id}.")

    print("\nАнализ завершен.")


if __name__ == "__main__":
    main()