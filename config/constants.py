"""
Константы для фильтрации токенов и пар.
"""

# Стейблкоины для исключения
STABLECOINS = {
    'USDT', 'USDC', 'BUSD', 'TUSD', 'USDP', 'USDD', 'GUSD',
    'FRAX', 'LUSD', 'USTC', 'ALUSD', 'CUSD', 'CEUR', 'EUROC',
    'AGEUR', 'AEUR', 'STEUR', 'EURS', 'EURT', 'EURC', 'PAX',
    'FDUSD', 'PYUSD', 'USDB', 'USDJ', 'USDX', 'USDQ', 'TRIBE',
    'XUSD', 'DAI', 'USDN', 'USDZ', 'HUSD', 'UST', 'MUSD',
    'SUSD', 'USDK', 'USDH', 'USDS', 'USDEX', 'FLEXUSD', 'USDE'
}

# Wrapped токены для исключения
WRAPPED_TOKENS = {
    'WBTC', 'WETH', 'WBNB', 'WBETH', 'WBCH', 'WLTC', 'WZEC',
    'WMATIC', 'WAVAX', 'WFTM', 'WONE', 'WCRO', 'WNEAR', 'WKAVA',
    'WXRP', 'WADA', 'WDOT', 'WSOL', 'WTRX', 'WEOS', 'WXLM',
    'WALGO', 'WICP', 'WEGLD', 'WXTZ', 'WFIL', 'WAXL', 'WFLOW',
    'WMINA', 'WGLMR', 'WKLAY', 'WRUNE', 'WZIL', 'WAR', 'WROSE',
    'WVET', 'WQTUM', 'WNEO', 'WHBAR', 'WZRX', 'WBAT', 'WENJ',
    'WCHZ', 'WMANA', 'WGRT', 'W1INCH', 'WCOMP', 'WSNX', 'WCRV',
    'WTON', 'WDOGE', 'WSHIB', 'WLINK', 'WUNI', 'WAAVE', 'WMAKER'
}

# Цены основных котировочных активов в USD (по умолчанию)
from decimal import Decimal

DEFAULT_QUOTE_PRICES_USD = {
    'USDT': Decimal('1.0'),
    'USDC': Decimal('1.0'),
    'BUSD': Decimal('1.0'),
    'FDUSD': Decimal('1.0'),
    'DAI': Decimal('1.0'),
    'TUSD': Decimal('1.0'),
}