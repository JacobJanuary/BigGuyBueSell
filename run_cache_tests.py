#!/usr/bin/env python3
"""
Главный скрипт для запуска всех тестов кэширования и анализа проблем.
run_cache_tests.py
"""
import asyncio
import sys
import os
import subprocess
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.append(str(Path(__file__).parent))


def print_header():
    """Выводит заголовок."""
    print("""
    ╔═══════════════════════════════════════════════════╗
    ║      КОМПЛЕКСНАЯ ПРОВЕРКА КЭШИРОВАНИЯ             ║
    ║        И ДИАГНОСТИКА ПРОБЛЕМ                      ║
    ╚═══════════════════════════════════════════════════╝
    """)


def check_dependencies():
    """Проверяет наличие необходимых зависимостей."""
    print("🔍 Проверка зависимостей...")

    required_modules = [
        'asyncio',
        'datetime',
        'decimal',
        'unittest.mock'
    ]

    missing_modules = []

    for module in required_modules:
        try:
            __import__(module)
            print(f"  ✅ {module}")
        except ImportError:
            missing_modules.append(module)
            print(f"  ❌ {module}")

    # Проверяем pytest отдельно
    try:
        import pytest
        print(f"  ✅ pytest")
    except ImportError:
        print(f"  ⚠️  pytest (не обязательно)")

    if missing_modules:
        print(f"\n⚠️  Отсутствуют модули: {', '.join(missing_modules)}")
        return False

    print("✅ Все основные зависимости в порядке\n")
    return True


async def run_cache_analysis():
    """Запускает анализ проблем кэширования."""
    print("📊 АНАЛИЗ ПРОБЛЕМ КЭШИРОВАНИЯ")
    print("=" * 60)

    try:
        # Проверяем существование файла
        if os.path.exists('tests/test_cache_analysis.py'):
            # Импортируем и запускаем анализ
            sys.path.append('tests')
            from tests.test_cache_analysis import run_cache_analysis
            await run_cache_analysis()
            return True
        else:
            print("❌ Файл tests/test_cache_analysis.py не найден")
            return False
    except Exception as e:
        print(f"❌ Ошибка анализа кэширования: {e}")
        return False


async def run_performance_demo():
    """Запускает демонстрацию производительности."""
    print("\n🚀 ДЕМОНСТРАЦИЯ ПРОИЗВОДИТЕЛЬНОСТИ")
    print("=" * 60)

    try:
        if os.path.exists('tests/test_cache_performance.py'):
            sys.path.append('tests')
            from tests.test_cache_performance import demonstrate_cache_problem
            await demonstrate_cache_problem()
            return True
        else:
            print("❌ Файл tests/test_cache_performance.py не найден")
            return False
    except Exception as e:
        print(f"❌ Ошибка демонстрации: {e}")
        return False


def run_unit_tests():
    """Запускает unit тесты."""
    print("\n🧪 UNIT ТЕСТЫ")
    print("=" * 60)

    # Ищем тестовые файлы
    test_files = []
    test_dir = Path('tests')

    if test_dir.exists():
        for file in test_dir.glob('test_*.py'):
            test_files.append(str(file))

    if not test_files:
        print("❌ Тестовые файлы не найдены в папке tests/")
        return False

    print(f"Найдено тестовых файлов: {len(test_files)}")
    for file in test_files:
        print(f"  📄 {file}")

    # Пытаемся запустить pytest
    try:
        result = subprocess.run([
                                    sys.executable, '-m', 'pytest'] + test_files + ['-v', '--tb=short'],
                                capture_output=True, text=True, timeout=120
                                )

        print("\nРЕЗУЛЬТАТЫ UNIT ТЕСТОВ:")
        print(result.stdout)

        if result.stderr:
            print("ПРЕДУПРЕЖДЕНИЯ:")
            print(result.stderr)

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("❌ Таймаут выполнения тестов")
        return False
    except FileNotFoundError:
        print("⚠️  pytest не найден, запускаем тесты напрямую...")

        # Запускаем тесты напрямую через Python
        success_count = 0
        for test_file in test_files:
            try:
                result = subprocess.run([
                    sys.executable, test_file
                ], capture_output=True, text=True, timeout=60)

                if result.returncode == 0:
                    success_count += 1
                    print(f"✅ {test_file}")
                else:
                    print(f"❌ {test_file}")
                    if result.stdout:
                        print(f"   {result.stdout[:200]}...")

            except Exception as e:
                print(f"❌ {test_file}: {e}")

        return success_count == len(test_files)
    except Exception as e:
        print(f"❌ Ошибка запуска тестов: {e}")
        return False


def analyze_current_code():
    """Анализирует текущий код на предмет проблем."""
    print("\n🔍 АНАЛИЗ ТЕКУЩЕГО КОДА")
    print("=" * 60)

    issues_found = []

    # Проверяем существование файлов
    files_to_check = [
        'workers/exchange_worker.py',
        'database/pairs_cache.py',
        'config/settings.py'
    ]

    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"✅ {file_path} найден")

            # Проверяем содержимое на проблемы
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Поиск проблемных паттернов
                if file_path == 'workers/exchange_worker.py':
                    if 'is_cache_fresh' in content and 'get_cached_pairs' in content:
                        fresh_count = content.count('is_cache_fresh')
                        if fresh_count > 1:
                            issues_found.append(
                                f"❌ {file_path}: Множественные проверки is_cache_fresh() ({fresh_count} раз)")

                    if '_quick_cache' not in content and '_cached_pairs' not in content:
                        issues_found.append(f"❌ {file_path}: Отсутствует in-memory кэширование")

                    if 'update_pairs_cache()' in content:
                        # Подсчитываем потенциальные вызовы API
                        api_calls = content.count('await self.client.get_')
                        if api_calls > 3:
                            issues_found.append(f"⚠️  {file_path}: Много потенциальных API вызовов ({api_calls})")

                elif file_path == 'config/settings.py':
                    if 'PAIRS_CACHE_UPDATE_MINUTES' not in content:
                        issues_found.append(f"❌ {file_path}: Отсутствуют оптимизированные настройки кэша")

                    if 'MEMORY_CACHE' not in content:
                        issues_found.append(f"❌ {file_path}: Не настроено in-memory кэширование")

            except Exception as e:
                issues_found.append(f"❌ {file_path}: Ошибка чтения файла - {e}")

        else:
            print(f"❌ {file_path} не найден")
            issues_found.append(f"❌ Отсутствует файл: {file_path}")

    # Проверяем .env файл
    if os.path.exists('.env'):
        print("✅ .env найден")
        try:
            with open('.env', 'r', encoding='utf-8') as f:
                env_content = f.read()

            if 'PAIRS_CACHE_UPDATE_MINUTES' not in env_content:
                issues_found.append("⚠️  .env: Отсутствуют настройки кэширования")
        except Exception as e:
            issues_found.append(f"⚠️  .env: Ошибка чтения - {e}")
    else:
        print("⚠️  .env не найден")
        issues_found.append("⚠️  Отсутствует файл .env")

    # Выводим результаты анализа
    if issues_found:
        print(f"\n🚨 НАЙДЕНО ПРОБЛЕМ: {len(issues_found)}")
        for issue in issues_found:
            print(f"  {issue}")
    else:
        print("\n✅ Серьезных проблем не обнаружено")

    return len(issues_found) == 0


def create_optimization_recommendations():
    """Создает рекомендации по оптимизации."""
    print("\n💡 РЕКОМЕНДАЦИИ ПО ОПТИМИЗАЦИИ")
    print("=" * 60)

    recommendations = [
        {
            'priority': 'КРИТИЧНО',
            'issue': 'Частые API вызовы',
            'solution': 'Применить quick_cache_fix.py',
            'impact': 'Сокращение API вызовов на 90%',
            'effort': 'Низкий (5 минут)'
        },
        {
            'priority': 'ВЫСОКО',
            'issue': 'Повторные проверки кэша',
            'solution': 'Внедрить in-memory кэширование',
            'impact': 'Уменьшение запросов к БД на 80%',
            'effort': 'Средний (30 минут)'
        },
        {
            'priority': 'СРЕДНЕ',
            'issue': 'Отсутствие метрик кэша',
            'solution': 'Использовать optimized_exchange_worker.py',
            'impact': 'Улучшение мониторинга и отладки',
            'effort': 'Средний (1 час)'
        },
        {
            'priority': 'НИЗКО',
            'issue': 'Настройки по умолчанию',
            'solution': 'Настроить cache_optimization_settings.py',
            'impact': 'Тонкая настройка производительности',
            'effort': 'Низкий (15 минут)'
        }
    ]

    for i, rec in enumerate(recommendations, 1):
        priority_icon = {
            'КРИТИЧНО': '🔴',
            'ВЫСОКО': '🟠',
            'СРЕДНЕ': '🟡',
            'НИЗКО': '🟢'
        }[rec['priority']]

        print(f"{i}. {priority_icon} {rec['priority']}")
        print(f"   Проблема: {rec['issue']}")
        print(f"   Решение: {rec['solution']}")
        print(f"   Эффект: {rec['impact']}")
        print(f"   Усилия: {rec['effort']}\n")


def create_quick_fix():
    """Создает и запускает быстрое исправление."""
    print("\n⚡ БЫСТРОЕ ИСПРАВЛЕНИЕ")
    print("=" * 60)

    if os.path.exists('quick_cache_fix.py'):
        print("✅ Файл quick_cache_fix.py уже существует")

        try:
            result = subprocess.run([sys.executable, 'quick_cache_fix.py'],
                                    capture_output=True, text=True, timeout=30)

            if result.stdout:
                print("Вывод quick_cache_fix.py:")
                print(result.stdout)

            return result.returncode == 0
        except Exception as e:
            print(f"❌ Ошибка запуска quick_cache_fix.py: {e}")
            return False
    else:
        print("❌ Файл quick_cache_fix.py не найден")
        print("Создайте его из артефакта quick_cache_fix.py")
        return False


def check_test_files():
    """Проверяет наличие всех необходимых тестовых файлов."""
    print("\n📁 ПРОВЕРКА ФАЙЛОВ ПРОЕКТА")
    print("=" * 60)

    required_files = {
        'tests/test_cache_comprehensive.py': 'Комплексные тесты кэширования',
        'tests/test_cache_analysis.py': 'Анализ проблем кэширования',
        'tests/test_cache_performance.py': 'Тесты производительности',
        'workers/optimized_exchange_worker.py': 'Оптимизированный воркер',
        'config/cache_optimization_settings.py': 'Настройки оптимизации',
        'quick_cache_fix.py': 'Быстрое исправление'
    }

    missing_files = []
    existing_files = []

    for file_path, description in required_files.items():
        if os.path.exists(file_path):
            existing_files.append((file_path, description))
            print(f"✅ {file_path} - {description}")
        else:
            missing_files.append((file_path, description))
            print(f"❌ {file_path} - {description}")

    print(f"\n📊 Статистика файлов:")
    print(f"  Найдено: {len(existing_files)}/{len(required_files)}")
    print(f"  Отсутствует: {len(missing_files)}")

    if missing_files:
        print(f"\n📋 Необходимо создать:")
        for file_path, description in missing_files:
            print(f"  📄 {file_path}")

    return len(missing_files) == 0


async def main():
    """Главная функция."""
    print_header()

    # Проверяем зависимости
    if not check_dependencies():
        print("❌ Не удается продолжить из-за отсутствующих зависимостей")
        return

    print("Выберите режим тестирования:")
    print("1. 🔍 Полный анализ (все тесты + анализ кода)")
    print("2. 📊 Только анализ проблем кэширования")
    print("3. 🚀 Только демонстрация производительности")
    print("4. 🧪 Только unit тесты")
    print("5. 🔍 Только анализ текущего кода")
    print("6. ⚡ Запустить быстрое исправление")
    print("7. 💡 Показать рекомендации")
    print("8. 📁 Проверить наличие файлов")
    print("9. 🏗️  Создать отсутствующие директории")

    try:
        choice = input("\nВведите номер (1-9): ").strip()
    except KeyboardInterrupt:
        print("\n👋 Выход по запросу пользователя")
        return

    results = {}

    if choice == "1":
        # Полный анализ
        print("\n🔍 ЗАПУСК ПОЛНОГО АНАЛИЗА...")

        # 1. Проверка файлов
        print("\n" + "=" * 60)
        results['files_check'] = check_test_files()

        # 2. Анализ кода
        print("\n" + "=" * 60)
        results['code_analysis'] = analyze_current_code()

        # 3. Unit тесты
        print("\n" + "=" * 60)
        results['unit_tests'] = run_unit_tests()

        # 4. Анализ проблем кэширования
        print("\n" + "=" * 60)
        try:
            results['cache_analysis'] = await run_cache_analysis()
        except Exception as e:
            print(f"❌ Ошибка анализа кэширования: {e}")
            results['cache_analysis'] = False

        # 5. Демонстрация производительности
        print("\n" + "=" * 60)
        try:
            results['performance_demo'] = await run_performance_demo()
        except Exception as e:
            print(f"❌ Ошибка демонстрации: {e}")
            results['performance_demo'] = False

        # 6. Рекомендации
        create_optimization_recommendations()

    elif choice == "2":
        try:
            results['cache_analysis'] = await run_cache_analysis()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            results['cache_analysis'] = False

    elif choice == "3":
        try:
            results['performance_demo'] = await run_performance_demo()
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            results['performance_demo'] = False

    elif choice == "4":
        results['unit_tests'] = run_unit_tests()

    elif choice == "5":
        results['code_analysis'] = analyze_current_code()

    elif choice == "6":
        results['quick_fix'] = create_quick_fix()

    elif choice == "7":
        create_optimization_recommendations()
        results['recommendations'] = True

    elif choice == "8":
        results['files_check'] = check_test_files()

    elif choice == "9":
        print("\n🏗️  СОЗДАНИЕ ДИРЕКТОРИЙ")
        print("=" * 60)

        directories = ['tests', 'workers', 'config']

        for directory in directories:
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                    print(f"✅ Создана директория: {directory}")
                except Exception as e:
                    print(f"❌ Ошибка создания {directory}: {e}")
            else:
                print(f"✅ Директория существует: {directory}")

        print(f"\n📋 Следующие шаги:")
        print("1. Скопируйте содержимое артефактов в соответствующие файлы")
        print("2. Запустите снова этот скрипт для проверки")
        results['directories_created'] = True

    else:
        print("❌ Неверный выбор")
        return

    # Итоговый отчет
    print(f"\n{'=' * 80}")
    print("ИТОГОВЫЙ ОТЧЕТ")
    print(f"{'=' * 80}")

    if results:
        passed_tests = sum(1 for result in results.values() if result is True)
        total_tests = len([r for r in results.values() if r is not None])

        print(f"📊 Выполнено проверок: {total_tests}")
        print(f"✅ Успешных: {passed_tests}")
        print(f"❌ Неуспешных: {total_tests - passed_tests}")

        # Детальные результаты
        for test_name, result in results.items():
            if result is True:
                print(f"  ✅ {test_name}")
            elif result is False:
                print(f"  ❌ {test_name}")
            else:
                print(f"  ℹ️  {test_name}")

    # Следующие шаги
    print(f"\n📋 СЛЕДУЮЩИЕ ШАГИ:")

    code_issues = not results.get('code_analysis', True)
    performance_issues = not results.get('performance_demo', True)
    files_missing = not results.get('files_check', True)

    if files_missing:
        print("1. 📁 Создайте отсутствующие файлы из артефактов")
        print("2. 🔄 Перезапустите этот скрипт для повторной проверки")
    elif code_issues or performance_issues:
        print("1. 🔧 Примените быстрое исправление: python quick_cache_fix.py")
        print("2. 📈 Мониторьте улучшения производительности")
        print("3. ⚙️  Настройте параметры кэширования в .env")
        print("4. 🔄 Перезапустите приложение и проверьте логи")
    else:
        print("✅ Система работает оптимально!")
        print("💡 Рекомендуется периодический мониторинг метрик кэша")

    print(f"\n📁 ФАЙЛЫ ДЛЯ СОЗДАНИЯ (если отсутствуют):")
    missing_files = [
        "tests/test_cache_comprehensive.py",
        "tests/test_cache_analysis.py",
        "tests/test_cache_performance.py",
        "workers/optimized_exchange_worker.py",
        "config/cache_optimization_settings.py",
        "quick_cache_fix.py"
    ]

    for file in missing_files:
        if not os.path.exists(file):
            print(f"  📄 {file} - создайте из соответствующего артефакта")

    print(f"\n🎯 ОЖИДАЕМЫЕ УЛУЧШЕНИЯ ПОСЛЕ ПРИМЕНЕНИЯ ИСПРАВЛЕНИЙ:")
    print("  • Сокращение API вызовов на 80-90%")
    print("  • Ускорение отклика в 5-10 раз")
    print("  • Снижение нагрузки на биржи")
    print("  • Повышение стабильности системы")

    print(f"\n📖 ДОКУМЕНТАЦИЯ:")
    print("  • quick_cache_fix.py - для немедленного улучшения")
    print("  • optimized_exchange_worker.py - для полной замены")
    print("  • cache_optimization_settings.py - для тонкой настройки")

    print(f"\n👋 Анализ завершен!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Выход по запросу пользователя")
    except Exception as e:
        print(f"\n💥 Критическая ошибка: {e}")
        print("Попробуйте запустить отдельные тесты вручную")