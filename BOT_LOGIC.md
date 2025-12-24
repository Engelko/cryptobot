# Logic and Working Principle of Antigravity Bot

## 1. Architecture Overview

Project Antigravity is an asynchronous, event-driven crypto trading bot designed for the Bybit Exchange (V5 API). It separates concerns into distinct modules to ensure reliability, scalability, and ease of debugging.

### Core Components:

*   **Engine (`main.py`, `antigravity/engine.py`):** The central nervous system. It initializes the bot, manages the lifecycle of strategies, and coordinates data flow.
*   **Event Bus (`antigravity/event.py`):** An asynchronous messaging system. Components publish events (e.g., `MarketDataEvent`, `Signal`) that subscribers (Strategies, Execution Manager) listen to. This decouples the modules.
*   **Strategies (`antigravity/strategies/`):** The brain. They receive market data and generate buy/sell signals based on technical indicators (RSI, MACD).
*   **Risk Manager (`antigravity/risk.py`):** The safety valve. It validates every signal against predefined limits (Max Daily Loss, Position Size) before execution.
*   **Execution Manager (`antigravity/execution.py`):** The hands. It routes orders to either a `PaperBroker` (simulation) or `RealBroker` (live Bybit API).
*   **Database (`antigravity/database.py`):** SQLite storage for historical data (klines), signals, trades, and logs.
*   **Dashboard (`dashboard.py`):** A Streamlit-based web interface for monitoring, diagnostics, and manual control.

---

## 2. Data Flow & Logic

The bot operates in an infinite loop (event loop), processing data in real-time.

### Step 1: Data Ingestion (WebSocket)
*   The bot connects to Bybit's WebSocket feed (`antigravity/websocket_client.py`).
*   It subscribes to `kline.1.{symbol}` topics for all configured symbols.
*   When a new candle (kline) closes, it publishes a `KlineEvent` to the Event Bus.

### Step 2: Strategy Processing
*   The `StrategyEngine` listens for `KlineEvent`.
*   It saves the candle to the database (`data.db`) for history.
*   It forwards the event to all active strategies (e.g., `MACD_Trend`, `RSI_Reversion`).
*   **Strategy Logic:**
    *   **RSI:** Calculates RSI (14 periods). If RSI < 30 (Oversold), generates a `BUY` signal. If RSI > 70 (Overbought), generates a `SELL` signal.
    *   **MACD:** Calculates MACD line and Signal line. If MACD crosses above Signal, `BUY`. If below, `SELL`.

### Step 3: Signal Validation (Risk Management)
*   If a strategy generates a signal, it is passed to the `RiskManager`.
*   **Checks:**
    1.  **Max Daily Loss:** Have we lost more than allowed today?
    2.  **Position Size:** Is the trade too big?
*   **Outcome:**
    *   **Accepted:** The signal proceeds to execution.
    *   **Rejected:** The signal is saved to the DB with a reason (e.g., `[REJECTED: Risk Limit]`) so you can see it in the Dashboard, but no trade is placed.

### Step 4: Execution
*   The `ExecutionManager` receives accepted signals.
*   **Simulation Mode:** Updates a virtual balance and saves a "PAPER" trade to the DB.
*   **Live Mode:**
    1.  Checks available USDT balance on Bybit (`BybitClient`).
    2.  Calculates trade size (`min(MAX_POSITION_SIZE, Available Balance)`).
    3.  Sends a Market Order to Bybit via API.
    4.  Logs the result (Order ID or Error).

---

## 3. Configuration

All settings are managed via the `.env` file or the Dashboard "Settings" tab.

*   **TRADING_SYMBOLS:** List of coins to trade (e.g., `["BTCUSDT", "ETHUSDT"]`).
*   **ACTIVE_STRATEGIES:** Which logic to use.
*   **RISK PARAMETERS:** `MAX_DAILY_LOSS`, `MAX_POSITION_SIZE`.
*   **TZ:** Timezone (default `Europe/Moscow`).

---

## 4. Diagnostics & Debugging

If the bot is not trading, use the **Diagnostics** tab in the Dashboard:

1.  **Real-time Logs:** View internal logs to see errors (e.g., API connection issues) or status updates (`signal_accepted`).
2.  **Ping Log:** Verify that logging is working.
3.  **Manual Order Test:** Try to place a small manual order. If this fails, your API keys are wrong or you lack permissions.
4.  **Check Strategies Script:** Run `python check_strategies.py` in the terminal to backtest strategies against your local data and see if signals *should* have occurred.

---

## 5. File Structure

*   `main.py`: Entry point for the trading bot.
*   `dashboard.py`: Entry point for the web UI.
*   `antigravity/`: Source code package.
    *   `client.py`: Bybit API wrapper (handles V5 API details like `settleCoin`).
    *   `engine.py`: Core logic loop.
    *   `strategies/`: Strategy implementations.
*   `data.db`: Local SQLite database.
*   `antigravity.log`: Log file (viewable in Dashboard).
