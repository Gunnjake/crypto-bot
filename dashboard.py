# dashboard.py
from flask import Flask, render_template, jsonify
import pandas as pd
from collections import deque
from datetime import datetime
import os
import time # <-- Import the time module
from trade_logger import read_log
from config import DASHBOARD_REFRESH_RATE, EXCHANGE_CONFIGS
from binance_client import BinanceClient

app = Flask(__name__)
clients = {}
portfolio_history = {}

def resync_client_time(client):
    """
    Gets the server time from Binance and applies the offset to the client
    to prevent timestamp-related API errors.
    """
    if not client or not client.client:
        print("Time Sync Failed: Client not available.")
        return
    try:
        server_time = client.client.get_server_time()['serverTime']
        local_time = int(time.time() * 1000)
        time_offset = server_time - local_time
        client.client.timestamp_offset = time_offset
        print(f"Dashboard client time synchronized successfully. Offset is {time_offset} ms.")
    except Exception as e:
        print(f"Could not sync dashboard client time with Binance server: {e}")

def initialize_clients():
    global clients, portfolio_history
    api_key = os.getenv('BINANCE_API_KEY')
    if api_key:
        client_instance = BinanceClient(EXCHANGE_CONFIGS['binance']['products'])
        if client_instance and client_instance.client:
            # --- FIX: Sync the time right after creating the client ---
            resync_client_time(client_instance)
            clients['binance'] = client_instance
    
    portfolio_history = {exchange: deque(maxlen=1440) for exchange in clients.keys()}
    print(f"Initialized dashboard clients for: {', '.join(clients.keys())}")


@app.route('/')
def binance_dashboard():
    return render_template('dashboard.html', refresh_rate=DASHBOARD_REFRESH_RATE)

@app.route('/data/binance')
def dashboard_data():
    exchange_name = 'binance'
    if exchange_name not in clients:
        return jsonify({'error': 'Binance client not initialized'}), 404
        
    client = clients[exchange_name]
    if not client or not client.client:
        return jsonify({'error': f'Could not connect to {exchange_name} API.'}), 500

    live_balances_enriched, total_portfolio_value = client.get_enriched_balances()

    if total_portfolio_value > 0:
        portfolio_history[exchange_name].append({'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'value': total_portfolio_value})
    
    total_unrealized_pnl = sum(b.get('unrealized_pnl', 0) for b in live_balances_enriched)
    total_cost_basis = total_portfolio_value - total_unrealized_pnl
    total_unrealized_pct = (total_unrealized_pnl / total_cost_basis) * 100 if total_cost_basis > 0 else 0

    trade_df = read_log('trade_log.csv')
    exchange_trade_df = pd.DataFrame()
    if not trade_df.empty:
        exchange_trade_df = trade_df[trade_df['symbol'].str.startswith(f"{exchange_name}_")]

    if not exchange_trade_df.empty:
        exchange_trade_df['pnl'] = pd.to_numeric(exchange_trade_df['pnl'], errors='coerce').fillna(0)
    realized_pnl = exchange_trade_df['pnl'].sum()
    
    win_rate, total_sells = 0, 0
    if not exchange_trade_df.empty:
        sells = exchange_trade_df[exchange_trade_df['side'] == 'SELL']
        if not sells.empty:
            total_sells = len(sells)
            profitable_sells = sells[sells['pnl'] > 0]
            win_rate = (len(profitable_sells) / total_sells) * 100 if total_sells > 0 else 0
            
    return jsonify({
        'live_metrics': {
            'portfolio_value': f"${total_portfolio_value:,.2f}",
            'unrealized_pnl': f"${total_unrealized_pnl:,.2f}",
            'unrealized_pct': f"{total_unrealized_pct:.2f}%"
        },
        'performance_metrics': {
            'realized_pnl': f"${realized_pnl:,.2f}",
            'win_rate': f"{win_rate:.2f}%",
            'total_trades': total_sells
        },
        'live_balances': live_balances_enriched,
        'live_history': list(portfolio_history.get(exchange_name, []))
    })

if __name__ == '__main__':
    initialize_clients()
    print(f"Dashboard starting... Open http://127.0.0.1:5001 in your browser.")
    app.run(debug=True, port=5001, use_reloader=False)