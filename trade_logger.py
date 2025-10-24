# trade_logger.py
import pandas as pd
import os
from datetime import datetime
from config import TRADE_LOG_FILE, DAILY_BALANCE_LOG_FILE

# Architectural Choice: Dedicated Logging Module.
# This module handles all interactions with the file system for logging purposes.
# It ensures consistent formatting and provides helper functions to query the logs,
# abstracting the file I/O operations from the main bot logic.

def log_trade(symbol, side, price, quantity, cost, commission, order_id, pnl=0):
    """
    Appends a new record of a completed trade to the trade log CSV file.

    Args:
        symbol (str): The trading pair (e.g., 'binance_BTCUSDT').
        side (str): 'BUY' or 'SELL'.
        price (float): The average fill price of the trade.
        quantity (float): The amount of the asset traded.
        cost (float): The total value of the trade in quote currency (e.g., USDT).
        commission (float): The fee paid for the trade.
        order_id (str): The unique ID from the exchange.
        pnl (float, optional): The calculated profit or loss for SELL trades. Defaults to 0.
    """
    log_entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'order_id': order_id,
        'symbol': symbol,
        'side': side.upper(),
        'price': price,
        'quantity': quantity,
        'cost': cost,
        'commission': commission,
        'pnl': pnl
    }
    file_exists = os.path.isfile(TRADE_LOG_FILE)
    df = pd.DataFrame([log_entry])
    df.to_csv(TRADE_LOG_FILE, mode='a', header=not file_exists, index=False)
    print(f"Logged {side.upper()} trade {order_id}: {quantity:.6f} {symbol} at {price:.2f}. P&L: {pnl:.4f}")

def log_daily_balance(total_value):
    """
    Appends a new record of the total portfolio value at the end of the day.
    """
    log_entry = {'date': datetime.now().strftime('%Y-%m-%d'), 'total_portfolio_value_usdt': total_value}
    file_exists = os.path.isfile(DAILY_BALANCE_LOG_FILE)
    df = pd.DataFrame([log_entry])
    df.to_csv(DAILY_BALANCE_LOG_FILE, mode='a', header=not file_exists, index=False)
    print(f"Logged Daily Balance: {total_value:.2f} USDT")

def read_log(file_path=TRADE_LOG_FILE):
    """
    Safely reads a log file into a pandas DataFrame. If the file doesn't exist,
    it creates it with the correct headers.
    """
    if not os.path.isfile(file_path):
        # Create the file with headers if it's missing
        if "daily" in file_path:
            pd.DataFrame(columns=['date', 'total_portfolio_value_usdt']).to_csv(file_path, index=False)
        else:
            pd.DataFrame(columns=['timestamp', 'order_id', 'symbol', 'side', 'price', 'quantity', 'cost', 'commission', 'pnl']).to_csv(file_path, index=False)
    try:
        return pd.read_csv(file_path)
    except Exception as e:
        print(f"An unexpected error occurred while reading {file_path}: {e}"); return pd.DataFrame()

def get_last_buy_for_symbol(symbol):
    """
    Design Choice (State Management): This function determines if there is an "open"
    position for a given symbol. It does this by checking if the last recorded trade
    for that symbol was a BUY. This is the core of the bot's stateless design.

    Args:
        symbol (str): The symbol to check (e.g., 'binance_BTCUSDT').

    Returns:
        pd.Series or None: The row of the last buy trade if it's an open position, otherwise None.
    """
    log_df = read_log()
    if log_df.empty: return None
    
    symbol_df = log_df[log_df['symbol'] == symbol]
    last_buy = symbol_df[symbol_df['side'] == 'BUY'].tail(1)
    last_sell = symbol_df[symbol_df['side'] == 'SELL'].tail(1)

    # An open position exists if there is a 'BUY' and no subsequent 'SELL'
    if last_buy.empty or (not last_sell.empty and pd.to_datetime(last_sell['timestamp'].iloc[0]) > pd.to_datetime(last_buy['timestamp'].iloc[0])):
        return None
        
    return last_buy.iloc[0]

def has_logged_today():
    """Checks if the daily balance has already been logged for the current day."""
    if not os.path.isfile(DAILY_BALANCE_LOG_FILE): return False
    df = read_log(DAILY_BALANCE_LOG_FILE)
    if df.empty: return False
    # Compare the date of the last log entry with today's date
    return df['date'].iloc[-1] == datetime.now().strftime('%Y-%m-%d')
