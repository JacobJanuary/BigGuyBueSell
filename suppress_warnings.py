"""
Файл для полного подавления предупреждений MySQL.
Импортируйте его в начале main файла: import suppress_warnings
"""
import warnings
import logging
import sys

# Полное подавление всех предупреждений
warnings.simplefilter("ignore")

# Конкретные фильтры для MySQL/aiomysql
warnings.filterwarnings('ignore', message='.*Data truncated.*')
warnings.filterwarnings('ignore', message='.*truncated.*')
warnings.filterwarnings('ignore', category=UserWarning, module='aiomysql')

# Подавление логгеров
logging.getLogger('aiomysql').setLevel(logging.ERROR)
logging.getLogger('pymysql').setLevel(logging.ERROR)

# Попытка подавить pymysql warnings
try:
    import pymysql

    warnings.filterwarnings('ignore', category=pymysql.Warning)
    # Дополнительно отключаем показ предупреждений в pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass


# Переопределяем sys.stderr для подавления предупреждений aiomysql
class SuppressedStderr:
    def __init__(self, original_stderr):
        self.original_stderr = original_stderr

    def write(self, text):
        # Подавляем строки с предупреждениями о truncated data
        if ('Data truncated' not in text and
                'Warning:' not in text and
                'truncated' not in text.lower()):
            self.original_stderr.write(text)

    def flush(self):
        self.original_stderr.flush()

    def __getattr__(self, name):
        return getattr(self.original_stderr, name)


# Заменяем stderr только для предупреждений
original_stderr = sys.stderr
sys.stderr = SuppressedStderr(original_stderr)

print("🔇 Предупреждения MySQL полностью подавлены")