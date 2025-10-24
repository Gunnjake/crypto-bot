# config.py
import os

# --- API Configurations ---
BINANCE_TLD = 'us'

# --- Notification Configuration ---
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', 'YOUR_WEBHOOK_URL_HERE')

# --- Trading Parameters ---
EXCHANGE_CONFIGS = {
    'binance': {
        'client_class': 'BinanceClient',
        'products': ['BTCUSDT', 'ETHUSDT', 'ADAUSDT', 'SOLUSDT', 'DOGEUSDT', 'SHIBUSDT'],
        'quote_currency': 'USDT',
        'fee_rate': 0.001 
    }
}

# --- Shared Trading Parameters ---
TRADE_AMOUNT_USDT = 15.00
LIMIT_ORDER_OFFSET = 0.0001 

# --- Strategy Profiles ---
STRATEGY_MODERATE = {
    'granularity': '1h',
    'short_sma': 8,
    'long_sma': 21,
    'rsi_period': 14,
    'rsi_overbought': 75,
    'rsi_oversold': 25
}

STRATEGY_AGGRESSIVE = {
    'granularity': '1m',
    'short_sma': 5,
    'long_sma': 13,
    'rsi_period': 9,
    'rsi_overbought': 80,
    'rsi_oversold': 20
}

# --- Time-Based Strategy Windows (UTC Hours) ---
TRADING_WINDOWS = {
    'aggressive_hours': list(range(3, 7)),
    'stop_hours': [2, 7, 23]
}

# --- Risk Management Parameters ---
SAFE_PORTFOLIO_VALUE_THRESHOLD = 200.00
MARKET_CRASH_THRESHOLD_PERCENT = -10.0
BINANCE_BTC_MIN_VALUE = 50.00 

# --- Logging & Dashboard ---
TRADE_LOG_FILE = 'trade_log.csv'
DAILY_BALANCE_LOG_FILE = 'daily_balance.csv'
DASHBOARD_REFRESH_RATE = 30000 # Refresh rate in milliseconds (e.g., 30000 = 30 seconds)

# --- ADDED: Set the minimum dollar value for a coin to appear in the notification ---
NOTIFICATION_BALANCE_THRESHOLD = 0.00 # Set to 0.0 to show all coins