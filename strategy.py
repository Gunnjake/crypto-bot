# strategy.py
import pandas as pd

# Architectural Choice: Decoupled Strategy Module.
# This file contains the "brains" of the trading logic. It is completely
# independent of any specific exchange. It simply takes in price data (a DataFrame)
# and strategy parameters, then outputs a signal. This makes it highly reusable
# and easy to test or modify in isolation.

def calculate_indicators(df, params):
    """
    Calculates technical indicators based on the provided DataFrame and parameters.

    Args:
        df (pd.DataFrame): DataFrame with historical price data (must include a 'close' column).
        params (dict): A dictionary containing the parameters for the indicators,
                       e.g., {'short_sma': 8, 'long_sma': 21, 'rsi_period': 14}.

    Returns:
        pd.DataFrame: The original DataFrame with new columns for each calculated indicator.
    """
    if df is None: return None
    
    # Extract parameters for clarity
    short_sma_period = params['short_sma']
    long_sma_period = params['long_sma']
    rsi_period = params['rsi_period']

    # Calculate Simple Moving Averages (SMAs)
    df[f'SMA_{short_sma_period}'] = df['close'].rolling(window=short_sma_period).mean()
    df[f'SMA_{long_sma_period}'] = df['close'].rolling(window=long_sma_period).mean()
    
    # Calculate Relative Strength Index (RSI)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss
    rs = rs.fillna(0) # Avoid division by zero if loss is 0
    df[f'RSI_{rsi_period}'] = 100 - (100 / (1 + rs))
    
    return df

def generate_signal(df, params):
    """
    Generates a 'BUY', 'SELL', or 'HOLD' signal based on the calculated indicators
    and the rules defined in the strategy parameters.

    Args:
        df (pd.DataFrame): DataFrame with pre-calculated indicators.
        params (dict): A dictionary with strategy rules, e.g., {'rsi_overbought': 75}.

    Returns:
        tuple: A (str, str) tuple containing the signal ('BUY', 'SELL', 'HOLD') and the reason.
    """
    # Define column names dynamically from parameters for flexibility
    short_sma_col = f"SMA_{params['short_sma']}"
    long_sma_col = f"SMA_{params['long_sma']}"
    rsi_col = f"RSI_{params['rsi_period']}"
    
    # --- Pre-computation Checks ---
    if df is None or len(df) < params['long_sma']: return 'HOLD', "Not enough data"
    if not all(col in df.columns for col in [short_sma_col, long_sma_col, rsi_col]): return 'HOLD', "Indicator columns missing"
    
    # Get the last two data points for crossover comparison
    last_row, prev_row = df.iloc[-1], df.iloc[-2]

    if pd.isna(last_row[short_sma_col]) or pd.isna(last_row[long_sma_col]): return 'HOLD', "Indicators still calculating"

    # --- BUY Signal Logic ---
    # Condition 1: The short-term SMA has just crossed above the long-term SMA ("Golden Cross").
    sma_cross_over = prev_row[short_sma_col] <= prev_row[long_sma_col] and last_row[short_sma_col] > last_row[long_sma_col]
    # Condition 2 (Confirmation): The RSI is not in the "overbought" territory.
    rsi_confirm_buy = last_row[rsi_col] < params['rsi_overbought']
    
    if sma_cross_over and rsi_confirm_buy:
        return 'BUY', "Golden Cross + RSI Confirmation"

    # --- SELL Signal Logic ---
    # Condition 1: The short-term SMA has just crossed below the long-term SMA ("Death Cross").
    sma_cross_under = prev_row[short_sma_col] >= prev_row[long_sma_col] and last_row[short_sma_col] < last_row[long_sma_col]
    # Condition 2 (Aggressive Sell): The RSI indicates the asset is "overbought".
    rsi_is_overbought = last_row[rsi_col] > params['rsi_overbought']
    
    # The bot will sell if either condition is met.
    if rsi_is_overbought:
        return 'SELL', f"Aggressive Sell: RSI Overbought ({last_row[rsi_col]:.2f})"
    if sma_cross_under:
        return 'SELL', "Death Cross"
        
    # If no conditions are met, hold the current position.
    return 'HOLD', "No signal"

def process_raw_klines(klines_json):
    """
    A utility function to convert the raw JSON response for historical data from the
    Binance API into a clean, properly typed pandas DataFrame.

    Args:
        klines_json (list): The raw list of lists from the API.

    Returns:
        pd.DataFrame: A formatted DataFrame ready for indicator calculation.
    """
    if not klines_json: return None
    # Define columns based on Binance API documentation
    df = pd.DataFrame(klines_json, columns=['time','open','high','low','close','volume','close_time','quote_asset_volume','number_of_trades','taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore'])
    # Convert key columns to numeric types for calculations
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    # Convert timestamp to a readable datetime object
    df['time'] = pd.to_datetime(df['time'], unit='ms')
    df = df.sort_values('time').reset_index(drop=True)
    return df
