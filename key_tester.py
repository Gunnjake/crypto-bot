# key_tester.py
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Design Choice: A simple, standalone utility script.
# This script's purpose is to provide a quick and easy way to diagnose
# connection or authentication issues without running the entire complex bot.
# It helps isolate problems related to API keys or network connectivity.

print("--- Starting API Key Test ---")

# 1. Load keys from environment variables, consistent with the main application.
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_API_SECRET')

# 2. Check if the keys were actually loaded from the terminal session.
if not api_key or not api_secret:
    print("\n❌ ERROR: API keys not found in environment variables.")
    print("Please set them in your terminal before running the script.")
    exit()

print(f"✅ API Key loaded, starts with: {api_key[:5]}...")
print("Attempting to connect to Binance.us...")

# 3. Attempt a signed API call to get account information.
# This is a reliable way to test if the keys are valid and have the correct permissions.
try:
    client = Client(api_key, api_secret, tld='us')
    account_info = client.get_account()

    print("\n✅ --- SUCCESS! --- ✅")
    print("Your API keys and connection are working correctly.")

# Catch specific API errors from the Binance library for more informative feedback.
except BinanceAPIException as e:
    print("\n❌ --- CONNECTION FAILED --- ❌")
    print("The Binance API returned a specific error:")
    print(f"    Error Code: {e.code}")
    print(f"    Error Message: {e.message}")

# Catch any other exceptions (e.g., network issues).
except Exception as e:
    print("\n❌ --- AN UNEXPECTED ERROR OCCURRED --- ❌")
    print(f"    Error Details: {e}")