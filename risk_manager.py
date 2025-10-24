# risk_manager.py
from config import SAFE_PORTFOLIO_VALUE_THRESHOLD, MARKET_CRASH_THRESHOLD_PERCENT, BINANCE_BTC_MIN_VALUE

# Architectural Choice: Decoupled Risk Module.
# All safety checks are consolidated in this file. This makes the risk management
# strategy explicit and easy to audit or modify. The main loop simply calls these
# functions without needing to know the implementation details.

def check_portfolio_risk(client):
    """
    Performs a high-level check on the total portfolio value. If the value falls
    below a pre-defined threshold from the config, it signals to pause all new BUY trades.

    Args:
        client: An instance of the exchange client (e.g., BinanceClient).

    Returns:
        tuple: (bool, float) indicating if the portfolio is safe and the current total value.
    """
    total_value = client.calculate_total_portfolio_value()
    if total_value < SAFE_PORTFOLIO_VALUE_THRESHOLD:
        print(f"!!! RISK WARNING: Portfolio value ({total_value:.2f}) is below safe threshold. Pausing all buys.")
        return False, total_value
    return True, total_value

def check_market_crash(df):
    """
    Checks for a single, sharp price drop for a specific asset. It compares the
    last two closing prices in the historical data.

    Args:
        df (pd.DataFrame): The DataFrame for a single asset with historical data.

    Returns:
        bool: True if a crash is detected, False otherwise.
    """
    if df is None or df.empty or len(df) < 2: return False
    
    last_close = df.iloc[-1]['close']
    prev_close = df.iloc[-2]['close']

    if prev_close == 0: return False # Avoid division by zero
    
    price_change_percent = ((last_close - prev_close) / prev_close) * 100
    
    # Check if the drop exceeds the configured threshold
    if price_change_percent < MARKET_CRASH_THRESHOLD_PERCENT:
        print(f"!!! MARKET CRASH DETECTED: {df.name} dropped {price_change_percent:.2f}%. Pausing. !!!")
        return True
    return False

def check_binance_btc_balance(client):
    """
    A custom, asset-specific risk rule. Acts as a "canary in the coal mine."
    It halts all BTC trading if the total USD value of BTC held on Binance falls
    below a configured minimum, potentially indicating an issue or a major sell-off.

    Args:
        client: An instance of the BinanceClient.

    Returns:
        bool: True if the BTC balance is above the safe threshold, False otherwise.
    """
    btc_balance = client.get_asset_balance('BTC')
    btc_price = client.get_current_price('BTCUSDT')
    if btc_price is None:
        print("Could not get BTC price on Binance, cannot perform BTC balance check.")
        return False # Fail safe if we can't get the price
    
    btc_value = btc_balance * btc_price
    print(f"--- Checking Binance BTC value (${btc_value:,.2f}) against threshold (${BINANCE_BTC_MIN_VALUE:,.2f}) ---")
    if btc_value < BINANCE_BTC_MIN_VALUE:
        return False
    return True