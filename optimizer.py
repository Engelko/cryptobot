import asyncio
import yaml
import pandas as pd
import numpy as np
import ta
import os
from antigravity.database import db
from antigravity.logging import get_logger, configure_logging
from antigravity.config import settings
from antigravity.ai_agent import ai_agent

logger = get_logger("optimizer")

CONFIG_PATH = "strategies.yaml"

async def run_optimization():
    configure_logging()
    logger.info("optimizer_started")

    while True:
        try:
            symbols = settings.TRADING_SYMBOLS
            if isinstance(symbols, str):
                symbols = [symbols]

            for symbol in symbols:
                logger.info("optimizing_symbol", symbol=symbol)
                # Fetch last 7 days of 1h klines
                query = f"SELECT * FROM klines WHERE symbol='{symbol}' AND interval='1' ORDER BY ts DESC LIMIT {7*24}"
                df = pd.read_sql(query, db.engine)
                if df.empty or len(df) < 50:
                    continue

                df = df.sort_values('ts').reset_index(drop=True)

                # 1. Optimize Trend Following (Golden Cross) with Walk-Forward
                best_trend = walk_forward_optimize_trend(df)

                # 2. Optimize Mean Reversion (RSI) with Walk-Forward
                best_mr = walk_forward_optimize_mr(df)

                # 3. Update Config
                update_config(best_trend, best_mr)

                # 4. Train AI Model
                # Fetch last 90 days for training
                query_long = f"SELECT * FROM klines WHERE symbol='{symbol}' ORDER BY ts DESC LIMIT {90*24*4}" # 15m candles approx
                df_long = pd.read_sql(query_long, db.engine)
                if not df_long.empty:
                    ai_agent.train(df_long.iloc[::-1])

            logger.info("optimization_round_complete")

        except Exception as e:
            logger.error("optimization_failed", error=str(e))

        await asyncio.sleep(86400) # Run once every 24h

def backtest_trend(df, fast, slow):
    df = df.copy()
    df['f'] = ta.trend.sma_indicator(df['close'], window=fast)
    df['s'] = ta.trend.sma_indicator(df['close'], window=slow)
    df['pos'] = np.where(df['f'] > df['s'], 1, -1)
    df['ret'] = df['close'].pct_change() * df['pos'].shift(1)
    if df['ret'].std() == 0 or np.isnan(df['ret'].std()): return 0
    return (df['ret'].mean() / df['ret'].std()) * np.sqrt(24*365)

def backtest_mr(df, p, ob, os_val):
    df = df.copy()
    df['rsi'] = ta.momentum.rsi(df['close'], window=p)
    df['pos'] = 0
    df.loc[df['rsi'] < os_val, 'pos'] = 1
    df.loc[df['rsi'] > ob, 'pos'] = -1
    df['ret'] = df['close'].pct_change() * df['pos'].shift(1)
    if df['ret'].std() == 0 or np.isnan(df['ret'].std()): return 0
    return (df['ret'].mean() / df['ret'].std()) * np.sqrt(24*365)

def walk_forward_optimize_trend(df, windows=3):
    n = len(df)
    step = n // (windows + 1)
    params = []
    for f in [8, 12, 16, 20]:
        for s in [40, 50, 60, 100]:
            params.append((f, s))

    results = []
    for f, s in params:
        sharpes = []
        for i in range(windows):
            chunk = df.iloc[i*step : (i+2)*step]
            sharpes.append(backtest_trend(chunk, f, s))
        results.append({"f": f, "s": s, "sharpe": np.mean(sharpes)})

    best = max(results, key=lambda x: x["sharpe"])
    return {"fast": best["f"], "slow": best["s"], "sharpe": best["sharpe"]}

def walk_forward_optimize_mr(df, windows=3):
    n = len(df)
    step = n // (windows + 1)
    params = []
    for p in [10, 14, 18]:
        for ob in [65, 70, 75]:
            for os_val in [25, 30, 35]:
                params.append((p, ob, os_val))

    results = []
    for p, ob, os_val in params:
        sharpes = []
        for i in range(windows):
            chunk = df.iloc[i*step : (i+2)*step]
            sharpes.append(backtest_mr(chunk, p, ob, os_val))
        results.append({"p": p, "ob": ob, "os": os_val, "sharpe": np.mean(sharpes)})

    best = max(results, key=lambda x: x["sharpe"])
    return {"rsi_period": best["p"], "overbought": best["ob"], "oversold": best["os"], "sharpe": best["sharpe"]}

def update_config(trend, mr):
    if not os.path.exists(CONFIG_PATH): return
    with open(CONFIG_PATH, 'r') as f:
        conf = yaml.safe_load(f)

    # Update Trend Following
    if 'trend_following' in conf['strategies']:
        conf['strategies']['trend_following']['fast_period'] = trend['fast']
        conf['strategies']['trend_following']['slow_period'] = trend['slow']
        if trend['sharpe'] < 1.0:
            # conf['strategies']['trend_following']['enabled'] = False # As per requirements
            logger.info("trend_sharpe_low", sharpe=trend['sharpe'])

    # Update Mean Reversion
    if 'mean_reversion' in conf['strategies']:
        conf['strategies']['mean_reversion']['rsi_period'] = mr['rsi_period']
        conf['strategies']['mean_reversion']['rsi_overbought'] = mr['overbought']
        conf['strategies']['mean_reversion']['rsi_oversold'] = mr['oversold']
        if mr['sharpe'] < 1.0:
            # conf['strategies']['mean_reversion']['enabled'] = False
            logger.info("mr_sharpe_low", sharpe=mr['sharpe'])

    with open(CONFIG_PATH, 'w') as f:
        yaml.safe_dump(conf, f)
    logger.info("strategies_updated_with_optimal_params")

if __name__ == "__main__":
    asyncio.run(run_optimization())
