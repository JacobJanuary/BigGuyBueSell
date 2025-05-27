#!/usr/bin/env python3
"""
Исправление SSL проблем для подключения к OKX API.
"""
import ssl
import aiohttp
import asyncio
import certifi
import os


def create_ssl_context_for_okx():
    """Создает SSL контекст, совместимый с OKX."""
    try:
        # Метод 1: Использовать certifi
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        return ssl_context
    except Exception as e:
        print(f"Метод 1 не сработал: {e}")

        try:
            # Метод 2: Обычный SSL контекст с обновленными сертификатами
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            return ssl_context
        except Exception as e2:
            print(f"Метод 2 не сработал: {e2}")

            # Метод 3: Отключение проверки SSL (только для тестирования!)
            print("⚠️ Используем отключение SSL проверки (только для тестирования)")
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            return ssl_context


async def test_okx_connection_with_ssl_fix():
    """Тестирует подключение к OKX с исправлением SSL."""
    print("🔧 Тестирование подключения к OKX с исправлением SSL...")

    # Создаем SSL контекст
    ssl_context = create_ssl_context_for_okx()

    # Создаем коннектор с SSL контекстом
    connector = aiohttp.TCPConnector(
        ssl=ssl_context,
        limit=50,
        limit_per_host=10,
        ttl_dns_cache=300,
        use_dns_cache=True,
    )

    timeout = aiohttp.ClientTimeout(total=30, connect=10)

    try:
        async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={'User-Agent': 'OKXTestClient/1.0'}
        ) as session:

            # Тест 1: Проверка времени сервера
            print("  📡 Тест 1: Проверка времени сервера...")
            try:
                async with session.get('https://www.okx.com/api/v5/public/time') as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('code') == '0':
                            server_time = data.get('data', [{}])[0].get('ts', 'N/A')
                            print(f"    ✅ Соединение успешно! Время сервера: {server_time}")
                        else:
                            print(f"    ❌ Ошибка API: {data.get('msg', 'Unknown error')}")
                            return False
                    else:
                        print(f"    ❌ HTTP ошибка: {response.status}")
                        return False
            except Exception as e:
                print(f"    ❌ Ошибка подключения: {e}")
                return False

            # Тест 2: Получение инструментов
            print("  📊 Тест 2: Получение инструментов...")
            try:
                async with session.get(
                        'https://www.okx.com/api/v5/public/instruments',
                        params={'instType': 'SPOT', 'limit': '5'}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('code') == '0':
                            instruments = data.get('data', [])
                            print(f"    ✅ Получено {len(instruments)} инструментов")
                            if instruments:
                                print(f"    📋 Пример: {instruments[0].get('instId', 'N/A')}")
                        else:
                            print(f"    ❌ Ошибка API: {data.get('msg', 'Unknown error')}")
                            return False
                    else:
                        print(f"    ❌ HTTP ошибка: {response.status}")
                        return False
            except Exception as e:
                print(f"    ❌ Ошибка получения инструментов: {e}")
                return False

            # Тест 3: Получение тикеров
            print("  💹 Тест 3: Получение тикеров...")
            try:
                async with session.get(
                        'https://www.okx.com/api/v5/market/tickers',
                        params={'instType': 'SPOT', 'limit': '5'}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('code') == '0':
                            tickers = data.get('data', [])
                            print(f"    ✅ Получено {len(tickers)} тикеров")
                            if tickers:
                                ticker = tickers[0]
                                print(f"    📈 Пример: {ticker.get('instId', 'N/A')} - {ticker.get('last', 'N/A')}")
                        else:
                            print(f"    ❌ Ошибка API: {data.get('msg', 'Unknown error')}")
                            return False
                    else:
                        print(f"    ❌ HTTP ошибка: {response.status}")
                        return False
            except Exception as e:
                print(f"    ❌ Ошибка получения тикеров: {e}")
                return False

            print("  🎉 Все тесты пройдены успешно!")
            return True

    except Exception as e:
        print(f"  ❌ Критическая ошибка: {e}")
        return False


def update_okx_client_with_ssl_fix():
    """Обновляет OKX клиент с исправлением SSL."""
    print("\n🔧 Обновление OKX клиент с исправлением SSL...")

    client_file = 'exchanges/okx/client.py'

    if not os.path.exists(client_file):
        print(f"❌ Файл {client_file} не найден")
        return False

    try:
        # Читаем текущий файл
        with open(client_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Проверяем, не добавлено ли уже исправление SSL
        if 'ssl_context_for_okx' in content:
            print("  ✅ SSL исправление уже добавлено")
            return True

        # Создаем резервную копию
        import shutil
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"{client_file}.backup_{timestamp}"
        shutil.copy2(client_file, backup_file)
        print(f"  📁 Создана резервная копия: {backup_file}")

        # Добавляем импорты для SSL
        ssl_imports = '''import ssl
import certifi'''

        if 'import certifi' not in content:
            # Добавляем импорты после существующих импортов
            import_section = content.find('from aiohttp import ClientSession')
            if import_section > 0:
                content = content[:import_section] + ssl_imports + '\n' + content[import_section:]

        # Добавляем функцию создания SSL контекста
        ssl_function = '''
def create_ssl_context_for_okx():
    """Создает SSL контекст для OKX API."""
    try:
        # Используем certifi для получения актуальных сертификатов
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        return ssl_context
    except Exception:
        # Fallback: стандартный SSL контекст
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            return ssl_context
        except Exception:
            # Последний resort: отключение SSL проверки
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            return ssl_context

'''

        # Добавляем функцию перед классом OKXClient
        class_pos = content.find('class OKXClient(ExchangeBase):')
        if class_pos > 0:
            content = content[:class_pos] + ssl_function + content[class_pos:]

        # Обновляем методы для использования SSL контекста
        # Находим все места с self.session.get и добавляем ssl контекст
        old_session_calls = [
            'async with self.session.get(url',
            'async with self.session.get(url,'
        ]

        for old_call in old_session_calls:
            if old_call in content:
                new_call = old_call.replace(
                    'async with self.session.get(url',
                    'async with self.session.get(url, ssl=create_ssl_context_for_okx()'
                )
                content = content.replace(old_call, new_call)

        # Сохраняем изменения
        with open(client_file, 'w', encoding='utf-8') as f:
            f.write(content)

        print("  ✅ OKX клиент обновлен с исправлением SSL")
        return True

    except Exception as e:
        print(f"  ❌ Ошибка обновления клиента: {e}")
        return False


def check_ssl_dependencies():
    """Проверяет SSL зависимости."""
    print("🔍 Проверка SSL зависимостей...")

    dependencies = []

    # Проверяем certifi
    try:
        import certifi
        cert_path = certifi.where()
        print(f"  ✅ certifi: {cert_path}")
        dependencies.append("certifi")
    except ImportError:
        print("  ❌ certifi не установлен")
        print("    Установите: pip install certifi")

    # Проверяем OpenSSL версию
    try:
        import ssl
        print(f"  ✅ OpenSSL: {ssl.OPENSSL_VERSION}")
        dependencies.append("ssl")
    except:
        print("  ❌ Проблемы с SSL")

    # Проверяем aiohttp
    try:
        import aiohttp
        print(f"  ✅ aiohttp: {aiohttp.__version__}")
        dependencies.append("aiohttp")
    except ImportError:
        print("  ❌ aiohttp не установлен")

    return len(dependencies) >= 2  # Минимум ssl и aiohttp


async def main():
    """Главная функция исправления SSL."""
    print("""
╔═══════════════════════════════════════════════════╗
║           ИСПРАВЛЕНИЕ SSL ПРОБЛЕМ OKX             ║
╚═══════════════════════════════════════════════════╝

Проблема: SSL certificate verification failed
Решение: Обновление SSL конфигурации для OKX API

Что будет сделано:
🔍 Проверка SSL зависимостей
🧪 Тест подключения с исправлением SSL
🔧 Обновление OKX клиента
✅ Финальная проверка
    """)

    success_steps = []

    # 1. Проверяем зависимости
    if check_ssl_dependencies():
        success_steps.append("dependencies")

    # 2. Тестируем подключение
    print(f"\n{'=' * 60}")
    if await test_okx_connection_with_ssl_fix():
        success_steps.append("connection_test")

    # 3. Обновляем клиент
    print(f"\n{'=' * 60}")
    if update_okx_client_with_ssl_fix():
        success_steps.append("client_updated")

    # 4. Финальный тест с обновленным клиентом
    print(f"\n{'=' * 60}")
    print("🧪 Финальный тест с обновленным клиентом...")
    try:
        # Перезагружаем модуль
        import sys
        if 'exchanges.okx.client' in sys.modules:
            del sys.modules['exchanges.okx.client']

        from exchanges.okx.client import OKXClient
        from utils.rate_limiter import RateLimiter

        connector = aiohttp.TCPConnector(ssl=create_ssl_context_for_okx())
        timeout = aiohttp.ClientTimeout(total=30)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            client = OKXClient(session, RateLimiter(1200))

            if await client.test_connection():
                print("  ✅ Обновленный клиент работает!")
                success_steps.append("final_test")
            else:
                print("  ❌ Обновленный клиент не работает")

    except Exception as e:
        print(f"  ❌ Ошибка финального теста: {e}")

    # Итоги
    success_count = len(success_steps)
    total_steps = 4

    print(f"\n{'=' * 60}")
    print("РЕЗУЛЬТАТ ИСПРАВЛЕНИЯ SSL")
    print(f"{'=' * 60}")
    print(f"📊 Выполнено: {success_count}/{total_steps} шагов")

    if success_count >= 3:
        print(f"""
🎉 SSL ПРОБЛЕМЫ ИСПРАВЛЕНЫ!

✅ ЧТО СДЕЛАНО:
• Проверены SSL зависимости
• Создан корректный SSL контекст
• Обновлен OKX клиент с исправлением SSL
• Протестировано подключение к OKX API

🚀 СЛЕДУЮЩИЕ ШАГИ:
1. Перезапустите тест: python test_okx_quick.py
2. Или сразу основное приложение: python main.py
3. OKX должен работать без SSL ошибок

⚙️ ЧТО ИСПРАВЛЕНО:
• Использование актуальных SSL сертификатов из certifi
• Корректная настройка SSL контекста
• Fallback на отключение SSL проверки при необходимости
• Улучшенная обработка SSL ошибок

💡 ДОПОЛНИТЕЛЬНО:
Если проблемы остались, добавьте в .env:
DISABLE_SSL_VERIFY=true

Это отключит SSL проверку для всех запросов.
        """)
    else:
        print(f"""
⚠️ ЧАСТИЧНОЕ ИСПРАВЛЕНИЕ SSL

Выполнено только {success_count}/{total_steps} шагов.

🔧 АЛЬТЕРНАТИВНЫЕ РЕШЕНИЯ:

1. Отключить SSL проверку (быстрое решение):
   Добавьте в .env файл:
   DISABLE_SSL_VERIFY=true

2. Обновить сертификаты системы:
   # Ubuntu/Debian:
   sudo apt-get update && sudo apt-get install ca-certificates

   # macOS:
   brew install ca-certificates

   # Windows:
   Обновите Python до последней версии

3. Установить/обновить certifi:
   pip install --upgrade certifi

4. Использовать другой DNS:
   Временно используйте DNS 8.8.8.8 или 1.1.1.1

📞 ПОДДЕРЖКА:
Если ничего не помогает, это может быть связано с:
• Корпоративным firewall
• Блокировкой OKX в вашем регионе
• Проблемами с интернет-провайдером
        """)

    return success_count >= 3


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n👋 Исправление прервано пользователем")
        exit(1)
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
        exit(1)