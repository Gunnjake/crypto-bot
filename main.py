# main.py
import time
import sys
from datetime import datetime, timedelta, UTC

# --- Internal Imports for Core Modules ---
# Architectural Choice: Importing separated modules makes the system clean and maintainable.
# Each module has a single, clear responsibility.
from config import EXCHANGE_CONFIGS, STRATEGY_MODERATE, STRATEGY_AGGRESSIVE, TRADING_WINDOWS
from binance_client import BinanceClient
from binance.exceptions import BinanceAPIException
import strategy
import risk_manager
import trade_logger
import notifier

class TradingBot:
    """
    The main orchestrator class for the trading bot. It initializes all components
    and manages the primary trading loop.
    """
    def __init__(self):
        """
        Initializes the bot, sets up the exchange client, and prepares the state
        for tracking open positions and notification timers.
        """
        self.clients = {}
        self.open_positions = {}
        self.last_notification_time = time.time() - 86400  # Set to 24 hours ago to ensure first run sends notification

        print("Initializing Binance client...")
        # Creates an instance of our dedicated Binance client
        client_instance = BinanceClient(EXCHANGE_CONFIGS['binance']['products'])
        if client_instance and client_instance.client:
            print("Binance client initialized successfully.")
            self.clients['binance'] = client_instance
            # Design Choice: Position state is initialized to CLOSED for all assets.
            # The bot will verify the true state from the trade log later.
            self.open_positions['binance'] = {p: False for p in EXCHANGE_CONFIGS['binance']['products']}
        else:
            print("Failed to initialize Binance client.")

    def resync_client_time(self):
        """
        Design Choice (Defensive Programming): This method synchronizes the client's clock with the
        Binance server's clock. This is crucial to prevent the common `APIError -1021`
        which occurs due to clock drift between the client and server.
        """
        print("\n--- Performing time synchronization with Binance server... ---")
        try:
            client = self.clients.get('binance')
            if not client or not client.client:
                print("Time Sync Failed: Binance client not available.")
                return

            server_time = client.client.get_server_time()['serverTime']
            local_time = int(time.time() * 1000)
            
            # The python-binance library uses this offset for all subsequent signed API calls
            time_offset = server_time - local_time
            client.client.timestamp_offset = time_offset
            
            print(f"Time synchronized successfully. Offset is {time_offset} ms.")
        except Exception as e:
            print(f"Could not sync time with Binance server: {e}")

    def run(self):
        """
        The main entry point that starts the infinite trading loop.
        """
        if not self.clients:
            print("No exchanges initialized. Exiting.")
            sys.exit(1)
        print(f"Starting Bot on {', '.join(self.clients.keys())}...")
        
        while True:
            try:
                # Sync time at the start of every loop to ensure continued alignment
                self.resync_client_time()

                # Run scheduled, non-trading tasks like daily summaries
                self.run_scheduled_tasks()
                
                # Execute the core trading logic
                self.run_strategy_cycle()
                
                print("\n===== Full Cycle Complete. Sleeping for 60 seconds... =====")
                time.sleep(60)

            # Architectural Choice: Specific handling for known, recoverable API errors.
            except BinanceAPIException as e:
                if e.code == -1021:
                    print(f"TIMESTAMP ERROR: {e}. This should have been prevented by resync. Pausing before retry.")
                    time.sleep(60)
                    continue
                else:
                    # For unknown critical errors, notify and exit to prevent further issues.
                    print(f"A critical Binance API error occurred: {e}")
                    notifier.send_error_notification(str(e))
                    sys.exit(1)
            # General catch-all for any other unexpected errors.
            except Exception as e:
                print(f"A critical error occurred in the main loop: {e}")
                notifier.send_error_notification(str(e))
                sys.exit(1)

    def run_scheduled_tasks(self):
        """
        Handles tasks that run on a schedule, like the daily notification summary.
        This is kept separate from the trading logic for clarity.
        """
        if (time.time() - self.last_notification_time) > 86400: # 24 hours
            print("\n--- Performing Daily Task: Sending 24-Hour Status Notification ---")
            try:
                client = self.clients.get('binance')
                if client:
                    balances, current_total_value = client.get_enriched_balances()
                    
                    # Read historical data to calculate 24h change
                    daily_log = trade_logger.read_log(trade_logger.DAILY_BALANCE_LOG_FILE)
                    previous_total_value = 0
                    if not daily_log.empty:
                        # Ensure we get the value from the PREVIOUS day, not today's log entry
                        previous_day_log = daily_log[daily_log['date'] != datetime.now().strftime('%Y-%m-%d')]
                        if not previous_day_log.empty:
                            previous_total_value = previous_day_log['total_portfolio_value_usdt'].iloc[-1]

                    notifier.send_daily_summary(current_total_value, previous_total_value, balances)
                    
                    if not trade_logger.has_logged_today():
                        trade_logger.log_daily_balance(current_total_value)

                    self.last_notification_time = time.time() # Reset timer
            except Exception as e:
                print(f"Failed to send daily notification: {e}")

    def run_strategy_cycle(self):
        """
        Determines which trading strategy to use based on the current time (UTC)
        and then iterates through each configured asset to process its logic.
        """
        now = datetime.now(UTC)
        current_hour_utc = now.hour
        
        # Design Choice: Time-based strategy switching.
        # This allows the bot to adapt its behavior to expected market conditions at different times.
        if current_hour_utc in TRADING_WINDOWS['stop_hours']:
            print(f"\n--- In STOPPED trading window. Pausing until the next hour. ---")
            return
        elif current_hour_utc in TRADING_WINDOWS['aggressive_hours']:
            active_strategy = STRATEGY_AGGRESSIVE
            print(f"\n--- In SUPER AGGRESSIVE trading window (Hour {current_hour_utc} UTC). ---")
        else:
            active_strategy = STRATEGY_MODERATE
            print(f"\n--- In MODERATE trading window (Hour {current_hour_utc} UTC). ---")

        for exchange, client in self.clients.items():
            print(f"\n===== Processing Strategy on {exchange.upper()} =====")
            # Perform a portfolio-level risk check before analyzing any individual assets.
            is_safe, _ = risk_manager.check_portfolio_risk(client)
            for product_id in EXCHANGE_CONFIGS[exchange]['products']:
                self.process_symbol(exchange, client, product_id, is_safe, active_strategy)
                time.sleep(2) # Small delay to avoid API rate limiting

    def process_symbol(self, exchange, client, product_id, portfolio_safe, strategy_params):
        """
        This is the core logic for a single trading asset (e.g., BTCUSDT).
        It fetches data, calculates indicators, checks risk, and generates a signal.
        """
        # Asset-specific risk check (the "BTC Canary" failsafe)
        if exchange == 'binance' and 'BTC' in product_id:
            if not risk_manager.check_binance_btc_balance(client):
                print("!!! BTC FAILSAFE: All BTC trading is paused. !!!")
                return 

        print(f"\n----- Analyzing {product_id} with {strategy_params['granularity']} data -----")
        
        # 1. Fetch Data
        klines = client.get_historic_rates(product_id, strategy_params['granularity'])
        df_raw = strategy.process_raw_klines(klines)
        
        # 2. Calculate Indicators
        df_with_indicators = strategy.calculate_indicators(df_raw, strategy_params)
        if df_with_indicators is None or df_with_indicators.empty: return
        
        # 3. Determine Current Position State
        # Design Choice (Statelessness): The bot reads the log to know if it's in a trade.
        # This makes it resilient to restarts. It doesn't need to remember its state in memory.
        log_symbol = f"{exchange}_{product_id}"
        last_buy = trade_logger.get_last_buy_for_symbol(log_symbol)
        self.open_positions[exchange][product_id] = last_buy is not None
        print(f"Position Status: {'OPEN' if self.open_positions[exchange][product_id] else 'CLOSED'}")
        
        # 4. Check for Market Crash
        if risk_manager.check_market_crash(df_with_indicators): return
        
        # 5. Generate Signal
        signal, reason = strategy.generate_signal(df_with_indicators, strategy_params)
        print(f"Signal: {signal} ({reason})")
        
        # 6. Execute Trade based on signal and state
        if signal == 'BUY' and not self.open_positions[exchange][product_id] and portfolio_safe:
            self.execute_buy(exchange, client, product_id)
        elif signal == 'SELL' and self.open_positions[exchange][product_id]:
            self.execute_sell(exchange, client, product_id, last_buy)

    def execute_buy(self, exchange, client, product_id):
        """Handles the logic for placing a limit buy order."""
        from config import TRADE_AMOUNT_USDT, LIMIT_ORDER_OFFSET
        price = client.get_current_price(product_id)
        if not price: return
        
        quantity = TRADE_AMOUNT_USDT / price
        limit_price = price * (1 - LIMIT_ORDER_OFFSET) # Place order slightly below market to ensure fill
        order_details = client.place_limit_order(product_id, 'buy', quantity, limit_price)
        
        if order_details and order_details.get('order_id'):
            trade_logger.log_trade(symbol=f"{exchange}_{product_id}", side='BUY', price=order_details['price'], quantity=order_details['quantity'], cost=order_details.get('cost', 0), commission=order_details.get('commission', 0), order_id=order_details['order_id'])
            self.open_positions[exchange][product_id] = True

    def execute_sell(self, exchange, client, product_id, last_buy):
        """Handles the logic for placing a limit sell order and calculating P&L."""
        from config import LIMIT_ORDER_OFFSET
        base_currency = product_id.replace(EXCHANGE_CONFIGS[exchange]['quote_currency'], '')
        balance = client.get_asset_balance(base_currency)
        
        if balance and balance > 0:
            price = client.get_current_price(product_id)
            if not price: return
            limit_price = price * (1 + LIMIT_ORDER_OFFSET) # Place order slightly above market
            order_details = client.place_limit_order(product_id, 'sell', balance, limit_price)
            
            if order_details and order_details.get('order_id'):
                # Calculate Profit and Loss for this specific trade
                buy_cost = float(last_buy['cost'])
                sell_value = order_details.get('cost', 0)
                net_pnl = sell_value - buy_cost
                trade_logger.log_trade(symbol=f"{exchange}_{product_id}", side='SELL', price=order_details['price'], quantity=balance, cost=sell_value, commission=order_details.get('commission', 0), order_id=order_details['order_id'], pnl=net_pnl)
                self.open_positions[exchange][product_id] = False

if __name__ == '__main__':
    bot = TradingBot()
    bot.run()