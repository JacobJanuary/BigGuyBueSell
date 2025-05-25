"""
SSL утилиты для обхода проблем с сертификатами.
"""
import logging
import ssl

try:
    import certifi
    HAS_CERTIFI = True
except ImportError:
    HAS_CERTIFI = False

logger = logging.getLogger(__name__)


def create_ssl_context(verify_ssl: bool = True) -> ssl.SSLContext:
    """
    Создает SSL контекст с настройками для обхода проблем с сертификатами.

    Args:
        verify_ssl: Проверять ли SSL сертификаты

    Returns:
        Настроенный SSL контекст
    """
    if verify_ssl:
        ssl_context = ssl.create_default_context()
        try:
            if HAS_CERTIFI:
                ssl_context.load_verify_locations(certifi.where())
        except Exception:
            logger.warning("Не удалось загрузить сертификаты из certifi")
    else:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        logger.warning("SSL проверка отключена! Используйте только для отладки.")

    return ssl_context