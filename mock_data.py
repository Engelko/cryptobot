import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def get_mock_regime_data():
    return pd.DataFrame({
        "symbol": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"],
        "regime": ["TRENDING_UP", "RANGING", "VOLATILE", "TRENDING_DOWN"],
        "adx": [32.5, 18.2, 45.8, 28.1],
        "volatility": [2.5, 1.2, 5.8, 3.1],
        "updated_at": [datetime.now()] * 4
    })

def get_mock_predictions():
    dates = pd.date_range(end=datetime.now(), periods=100, freq='H')
    return pd.DataFrame({
        "created_at": dates,
        "symbol": ["BTCUSDT"] * 100,
        "prediction_value": np.random.choice([0, 1], 100),
        "confidence": np.random.uniform(0.5, 0.95, 100),
        "features": ['{"regime": "TRENDING_UP"}'] * 100
    })

def get_mock_trades():
    strategies = ["GridMaster", "BollingerRSI", "GoldenCross", "AI_Filter"]
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    data = []
    for _ in range(50):
        side = np.random.choice(["BUY", "SELL"])
        pnl = np.random.uniform(-20, 50) if side == "SELL" else 0
        data.append({
            "symbol": np.random.choice(symbols),
            "strategy": np.random.choice(strategies),
            "side": side,
            "price": np.random.uniform(30000, 60000),
            "quantity": np.random.uniform(0.01, 0.1),
            "pnl": pnl,
            "created_at": datetime.now() - timedelta(days=np.random.randint(0, 7), hours=np.random.randint(0, 24))
        })
    return pd.DataFrame(data)

def get_mock_signals():
    reasons = [
        "Trend following",
        "[REJECTED: AI Low Conf] 0.55",
        "[REJECTED: Risk Limit] Daily loss hit",
        "[REJECTED: Market Regime] Volatile",
        "RSI Oversold"
    ]
    data = []
    for i in range(20):
        data.append({
            "strategy": np.random.choice(["GridMaster", "BollingerRSI"]),
            "symbol": "BTCUSDT",
            "type": np.random.choice(["BUY", "SELL"]),
            "price": 50000 + i*10,
            "reason": np.random.choice(reasons),
            "created_at": datetime.now() - timedelta(minutes=i*15)
        })
    return pd.DataFrame(data)

def get_mock_onchain():
    return {
        "netflow": -1250.5,
        "mvrv": 1.45,
        "whales": [
            {"time": "12:34", "msg": "800 BTC moved from Binance to Cold Wallet"},
            {"time": "11:20", "msg": "1,200 BTC moved to Coinbase"},
            {"time": "10:05", "msg": "Whale Alert: 5,000,000 USDT minted"}
        ]
    }
