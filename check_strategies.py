import pandas as pd
import json
import asyncio
from sqlalchemy import create_engine
from antigravity.config import settings
from antigravity.strategies.rsi import RSIStrategy
from antigravity.strategies.macd import MACDStrategy
import ta

# Database Connection
db_path = settings.DATABASE_URL
engine = create_engine(db_path)

def analyze_rsi(df, period=14, oversold=30, overbought=70):
    print(f"\n--- Analyzing RSI Strategy (Period={period}, Buy<{oversold}, Sell>{overbought}) ---")

    # Calculate RSI
    rsi_indicator = ta.momentum.RSIIndicator(close=df["close"], window=period)
    df["rsi"] = rsi_indicator.rsi()

    min_rsi = df["rsi"].min()
    max_rsi = df["rsi"].max()

    print(f"Data range: {len(df)} candles")
    print(f"Min RSI found: {min_rsi:.2f}")
    print(f"Max RSI found: {max_rsi:.2f}")

    # Check for signals
    buy_signals = df[df["rsi"] < oversold]
    sell_signals = df[df["rsi"] > overbought]

    print(f"Potential BUY signals (RSI < {oversold}): {len(buy_signals)}")
    if not buy_signals.empty:
        print("Last 3 BUY signals:")
        print(buy_signals[["ts", "close", "rsi"]].tail(3))

    print(f"Potential SELL signals (RSI > {overbought}): {len(sell_signals)}")
    if not sell_signals.empty:
        print("Last 3 SELL signals:")
        print(sell_signals[["ts", "close", "rsi"]].tail(3))

def analyze_macd(df):
    print(f"\n--- Analyzing MACD Strategy (12, 26, 9) ---")

    # Calculate MACD
    macd = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_diff"] = macd.macd_diff()

    # Crossovers
    # Buy: Cross up (Previous diff < 0 and Current diff > 0)
    # Sell: Cross down (Previous diff > 0 and Current diff < 0)
    df["prev_diff"] = df["macd_diff"].shift(1)

    buy_signals = df[(df["prev_diff"] < 0) & (df["macd_diff"] > 0)]
    sell_signals = df[(df["prev_diff"] > 0) & (df["macd_diff"] < 0)]

    print(f"Potential BUY signals (Crossover UP): {len(buy_signals)}")
    if not buy_signals.empty:
        print("Last 3 BUY signals:")
        print(buy_signals[["ts", "close", "macd", "macd_signal"]].tail(3))

    print(f"Potential SELL signals (Crossover DOWN): {len(sell_signals)}")
    if not sell_signals.empty:
        print("Last 3 SELL signals:")
        print(sell_signals[["ts", "close", "macd", "macd_signal"]].tail(3))

def main():
    # Get symbols
    symbols = settings.TRADING_SYMBOLS
    if isinstance(symbols, str):
         symbols = symbols.split(",")

    for symbol in symbols:
        symbol = symbol.strip()
        print(f"\n==================================================")
        print(f"Checking Symbol: {symbol}")
        print(f"==================================================")

        try:
            query = f"SELECT * FROM klines WHERE symbol='{symbol}' ORDER BY ts ASC"
            df = pd.read_sql(query, engine)

            if df.empty:
                print("No data found in database for this symbol.")
                continue

            # Convert ts to datetime for readability
            df["ts_date"] = pd.to_datetime(df["ts"], unit="ms")
            print(f"Loaded {len(df)} candles. Time range: {df['ts_date'].min()} to {df['ts_date'].max()}")

            analyze_rsi(df)
            analyze_macd(df)

        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")

if __name__ == "__main__":
    main()
