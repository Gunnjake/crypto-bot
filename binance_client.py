# binance_client.py
import math
import traceback
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import BINANCE_TLD, EXCHANGE_CONFIGS
from trade_logger import get_last_buy_for_symbol

# Architectural Choice: API Abstraction Layer.
# This class encapsulates all direct interaction with the Binance API.
# The main bot logic doesn't need to know the specifics of Binance's API endpoints;
# it just calls methods like `get_current_price()`. This makes the code cleaner and
# would make it easier to add another exchange in the future.
class BinanceClient:
    def __init__(self, symbols):
        """
        Initializes the client, securely loads API keys from environment variables,
        and pre-loads exchange information for the specified trading symbols.
        """
        self.client = None
        try:
            # Design Choice (Security): API keys are loaded from environment variables,
            # never hard-coded, to prevent credential exposure.
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_API_SECRET')

            if not api_key or not api_secret:
                raise ValueError("API Key or Secret not found in environment variables.")

            self.client = Client(api_key, api_secret, tld=BINANCE_TLD)
            self.client.ping() # Verify connectivity
            print("Successfully connected to Binance.us API.")
            self.symbol_info = {}
            self._load_symbol_info(symbols)
        except Exception as e:
            print(f"Error connecting to Binance.us. Full error details below:")
            traceback.print_exc()
            self.client = None

    def _load_symbol_info(self, symbols):
        """
        Private method to fetch and store exchange-specific rules for each trading pair,
        such as minimum order size ('step_size') and price precision ('tick_size').
        This is crucial for placing valid orders.
        """
        if not self.client: return
        print("Loading Binance.us exchange information for symbols...")
        exchange_info = self.client.get_exchange_info()
        for s in symbols:
            info = next((item for item in exchange_info['symbols'] if item['symbol'] == s), None)
            if info:
                self.symbol_info[s] = {
                    'tick_size': float(next(f['tickSize'] for f in info['filters'] if f['filterType'] == 'PRICE_FILTER')),
                    'step_size': float(next(f['stepSize'] for f in info['filters'] if f['filterType'] == 'LOT_SIZE'))
                }
        print("Binance.us exchange information loaded.")

    def get_enriched_balances(self):
        """
        Design Choice (Data Enrichment): Instead of just returning raw balance data,
        this method enriches it with calculated, useful information like the current
        USD value, unrealized P&L, and 24-hour performance for each asset.
        """
        if not self.client: return [], 0
        raw_balances = self.client.get_account()['balances']
        enriched_balances = []
        total_portfolio_value = 0
        
        quote_currency = EXCHANGE_CONFIGS['binance']['quote_currency']

        for balance in raw_balances:
            asset, free = balance['asset'], float(balance['free'])
            if free > 0:
                usd_value = 0
                unrealized_pnl, unrealized_pnl_pct = 0, 0
                pnl_24h, pnl_24h_pct = 0, 0
                
                if asset == quote_currency:
                    usd_value = free
                else:
                    symbol = f"{asset}{quote_currency}"
                    price = self.get_current_price(symbol)
                    if price:
                        usd_value = free * price
                        
                        # Calculate unrealized P&L based on the last buy price from the log
                        last_buy = get_last_buy_for_symbol(f"binance_{symbol}")
                        if last_buy is not None:
                            cost_basis = float(last_buy['cost'])
                            unrealized_pnl = usd_value - cost_basis
                            if cost_basis > 0:
                                unrealized_pnl_pct = (unrealized_pnl / cost_basis) * 100
                        
                        # Calculate 24-hour P&L using ticker data
                        ticker_info = self.get_24hr_ticker(symbol)
                        if ticker_info:
                            price_change_percent = float(ticker_info.get('priceChangePercent', 0))
                            # Back-calculate the value from 24h ago
                            cost_basis_24h = usd_value / (1 + price_change_percent / 100) if (100 + price_change_percent) != 0 else usd_value
                            pnl_24h = usd_value - cost_basis_24h
                            pnl_24h_pct = price_change_percent
                
                # Append all calculated data to the balance object
                balance['usd_value'] = usd_value
                balance['unrealized_pnl'] = unrealized_pnl
                balance['unrealized_pnl_pct'] = unrealized_pnl_pct
                balance['pnl_24h'] = pnl_24h
                balance['pnl_24h_pct'] = pnl_24h_pct
                enriched_balances.append(balance)
                total_portfolio_value += usd_value

        enriched_balances.sort(key=lambda x: x['asset'] != quote_currency)
        return enriched_balances, total_portfolio_value
        
    def get_24hr_ticker(self, symbol):
        """Fetches the 24-hour price change statistics for a symbol."""
        if not self.client: return None
        try:
            return self.client.get_ticker(symbol=symbol)
        except Exception: return None
        
    def get_asset_balance(self, asset):
        """Retrieves the available balance for a single asset."""
        if not self.client: return 0.0
        try:
            return float(self.client.get_asset_balance(asset=asset)['free'])
        except Exception as e:
            print(f"Error fetching balance for {asset} from Binance: {e}"); return 0.0

    def get_current_price(self, symbol):
        """Gets the most recent trade price for a symbol."""
        if not self.client: return None
        try:
            return float(self.client.get_symbol_ticker(symbol=symbol)['price'])
        except Exception: return None
            
    def get_historic_rates(self, symbol, interval):
        """Fetches historical k-line (candlestick) data for a symbol."""
        if not self.client: return None
        try:
            return self.client.get_historical_klines(symbol, interval, "3 days ago UTC")
        except Exception as e:
            print(f"Error fetching historical data for {symbol} from Binance: {e}"); return None

    def place_limit_order(self, symbol, side, quantity, price):
        """
        Places a limit order on the exchange, first rounding the quantity and price
        to meet the exchange's specific rules.
        """
        if not self.client: return None
        if symbol not in self.symbol_info:
            print(f"ERROR: Cannot place order for {symbol}, missing exchange symbol info."); return None
        try:
            # Round values to be compliant with Binance API rules
            rounded_quantity = self._round_quantity_to_step(symbol, quantity)
            if rounded_quantity <= 0: 
                print(f"WARN: Quantity for {symbol} is zero after rounding. Skipping order."); return None
            rounded_price = self._round_price_to_tick(symbol, price)
            
            print(f"Placing Binance LIMIT {side} order: {rounded_quantity} {symbol} at {rounded_price}")
            
            order = self.client.create_order(symbol=symbol, side=side, type=Client.ORDER_TYPE_LIMIT, timeInForce=Client.TIME_IN_FORCE_GTC, quantity=rounded_quantity, price=f'{rounded_price:.8f}')
            
            return self._parse_order_response(order)
        except Exception as e:
            print(f"An error occurred placing Binance limit order for {symbol}: {e}"); return None
            
    def calculate_total_portfolio_value(self):
        """A simple helper method to get the total portfolio value in USDT."""
        if not self.client: return 0.0
        _, total_value = self.get_enriched_balances()
        return total_value

    def _parse_order_response(self, order_response):
        """Private method to standardize the response from a filled order."""
        if not order_response or 'fills' not in order_response or not order_response['fills']: return None
        fills = order_response['fills']
        total_quantity = sum(float(fill['qty']) for fill in fills)
        total_cost = sum(float(fill['qty']) * float(fill['price']) for fill in fills)
        avg_price = total_cost / total_quantity if total_quantity > 0 else 0
        total_commission = sum(float(fill.get('commission', 0)) for fill in fills)
        return {'order_id': order_response['orderId'], 'price': avg_price, 'quantity': total_quantity, 'cost': total_cost, 'commission': total_commission}

    def _round_price_to_tick(self, symbol, price):
        """Rounds a price down to the nearest valid tick size."""
        if not symbol in self.symbol_info: return price
        tick_size = self.symbol_info[symbol]['tick_size']
        return round(math.floor(price / tick_size) * tick_size, 8)

    def _round_quantity_to_step(self, symbol, quantity):
        """Rounds a quantity down to the nearest valid step size."""
        if not symbol in self.symbol_info: return quantity
        step_size = self.symbol_info[symbol]['step_size']
        return round(math.floor(quantity / step_size) * step_size, 8)
