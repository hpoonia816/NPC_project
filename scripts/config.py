import os

# Binance API Configuration
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')  # Leave empty, will be set via .env
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')

# Hummingbot Configuration
TRADING_PAIR = "BTC-USDT"
ORDER_AMOUNT = 0.01
SPREAD_PERCENT = 0.005  # 0.5%

# Logging Configuration
LOG_CONFIG = {
    'version': 1,
    'handlers': {
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'bot.log',
            'level': 'INFO'
        }
    },
    'root': {
        'handlers': ['file'],
        'level': 'INFO'
    }
}