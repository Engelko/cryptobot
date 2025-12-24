# Antigravity Trading Bot 🚀

A high-performance asynchronous algorithmic trading engine built for Bybit V5 API.

## Features
- **Event-Driven Architecture**: Low latency signal processing.
- **Multi-Strategy Support**: Run MACD, RSI, and ML models concurrently.
- **Risk Management**: Real-time position sizing and drawdown protection.
- **Live Dashboard**: Streamlit-based monitoring UI with Diagnostics.
- **Diagnostics**: Real-time logs, manual order testing, and strategy verification.
- **Multi-Asset**: Supports trading multiple pairs (BTC, ETH, SOL, XRP, ADA, DOGE) simultaneously.

---

## 🚀 Getting Started (Zero to Hero)

### 1. Prerequisites
- Python 3.10 or higher
- A Bybit Account (Testnet or Mainnet) with API Keys.

### 2. Installation

Clone the repository and enter the directory:
```bash
git clone <repository_url>
cd cryptobot
```

Install the required dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configuration

Create your configuration file from the template:
```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in your details:
- `BYBIT_API_KEY` & `BYBIT_API_SECRET`: Your exchange keys.
- `TRADING_SYMBOLS`: List of coins, e.g., `["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT"]`.
- `SIMULATION_MODE`: Set to `False` for real trading, `True` for paper trading.
- `TZ`: Your timezone (default `Europe/Moscow`).

### 4. Running the Bot

**Start the Trading Engine (The Bot):**
This process runs in the background, analyzes data, and executes trades.
```bash
python main.py
```
*You should see logs indicating "system_startup" and "strategy_engine_started".*

**Start the Dashboard (The UI):**
Open a new terminal window and run:
```bash
streamlit run dashboard.py
```
*Access the dashboard at http://localhost:8501*

---

## 🛠 Diagnostics & Debugging

If the bot isn't behaving as expected, use the **Diagnostics** tab in the Dashboard or run these scripts:

1.  **Check Strategy Logic:**
    Verifies if your strategies would have generated signals on historical data.
    ```bash
    python check_strategies.py
    ```

2.  **Verify API Connection:**
    ```bash
    python verify_api.py
    ```

3.  **Verify WebSocket Feed:**
    ```bash
    python verify_ws.py
    ```

For a deep dive into how the bot works, read [BOT_LOGIC.md](BOT_LOGIC.md).

## Docker Deployment (Optional)

Alternatively, you can run everything in Docker containers:
```bash
docker-compose up -d --build
```
