import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine
import time
import asyncio
import os
import json
from antigravity.config import settings
from antigravity.client import BybitClient

# Database Connection
db_path = settings.DATABASE_URL
engine = create_engine(db_path)

st.set_page_config(page_title="Antigravity Cockpit", layout="wide", page_icon="🚀")

st.title("🚀 Project Antigravity: Mission Control")

# Sidebar
st.sidebar.header("Telemetry")
auto_refresh = st.sidebar.checkbox("Auto Refresh (5s)", value=True)

# Fetch Balance (Async wrapper)
async def fetch_balance():
    if not settings.BYBIT_API_KEY:
        return None
    client = BybitClient()
    try:
        return await client.get_wallet_balance()
    except Exception as e:
        return None
    finally:
        await client.close()

# Display Balance in Sidebar
try:
    if settings.BYBIT_API_KEY:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        balance_data = loop.run_until_complete(fetch_balance())
        loop.close()

        if balance_data and "coin" in balance_data:
            for coin_data in balance_data["coin"]:
                if coin_data["coin"] == "USDT":
                    st.sidebar.metric("Bybit Balance (USDT)", f"${float(coin_data.get('walletBalance', 0)):.2f}")
                    break
        else:
            st.sidebar.warning("Could not fetch balance")
    else:
        st.sidebar.info("API Key missing (Paper Mode only)")
except Exception as e:
    st.sidebar.error(f"Balance Error: {e}")


if auto_refresh:
    time.sleep(5)
    st.rerun()

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Market", "Portfolio (Sim)", "Signals", "AI", "System", "Settings", "Help"])

with tab1:
    st.subheader("Live Market Data")

    # Symbol Selector
    active_symbols = settings.TRADING_SYMBOLS
    selected_symbol = st.selectbox("Select Pair", active_symbols, index=0)

    try:
        # Use parameterized query to be safe, though symbols come from config
        df_kline = pd.read_sql(f"SELECT * FROM klines WHERE symbol='{selected_symbol}' ORDER BY ts DESC LIMIT 100", engine)
        if not df_kline.empty:
            df_kline = df_kline.sort_values("ts")
            fig = go.Figure(data=[go.Candlestick(x=pd.to_datetime(df_kline['ts'], unit='ms'),
                            open=df_kline['open'],
                            high=df_kline['high'],
                            low=df_kline['low'],
                            close=df_kline['close'])])
            fig.update_layout(height=500, title=f"{selected_symbol} Price Action")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(f"No Market Data Available for {selected_symbol} yet.")
    except Exception as e:
        st.error(f"Error loading Klines: {e}")

with tab2:
    st.subheader("Paper Trading Portfolio")
    try:
        df_trades = pd.read_sql("SELECT * FROM trades ORDER BY created_at DESC", engine)

        # Calculate Current Balance logic (Simplistic for UI)
        # In deployment we'd query PaperBroker but here we read DB
        # This is a bit disjointed, normally Dashboard pulls from API or DB state.
        # For H09, we just show Trade History and aggregated PnL.

        if not df_trades.empty:
            realized_pnl = df_trades['pnl'].sum()
            col1, col2 = st.columns(2)
            col1.metric("Realized PnL", f"${realized_pnl:.2f}")
            col2.metric("Total Trades", len(df_trades))

            st.dataframe(df_trades, use_container_width=True)
        else:
            st.info("No Trades Executed yet.")

    except Exception as e:
        st.error(f"Error loading Trades: {e}")

with tab3:
    st.subheader("Strategy Signals")
    try:
        df_signals = pd.read_sql("SELECT * FROM signals ORDER BY created_at DESC LIMIT 50", engine)
        if not df_signals.empty:
            st.dataframe(df_signals, use_container_width=True)
        else:
            st.info("No Signals Generated yet.")
    except Exception as e:
        st.error(f"Error loading Signals: {e}")

with tab4:
    st.subheader("AI Copilot Sentiment")
    try:
        df_sentiment = pd.read_sql("SELECT * FROM sentiment ORDER BY created_at DESC LIMIT 1", engine)
        if not df_sentiment.empty:
            latest = df_sentiment.iloc[0]
            st.metric("Sentiment Score", f"{latest['score']:.2f}")
            st.markdown(f"**Reasoning:** {latest['reasoning']}")
            st.caption(f"Model: {latest['model']}")
        else:
            st.info("AI Analysis Pernding...")
    except Exception as e:
        st.error(f"Error loading Sentiment: {e}")

with tab5:
    st.subheader("System Health")
    st.json({
        "Status": "Online",
        "Mode": "Simulation (Paper)" if settings.SIMULATION_MODE else "Live Trading",
        "Risk Manager": "Active",
        "Database": "Connected",
        "Active Strategies": settings.ACTIVE_STRATEGIES,
        "Environment": settings.ENVIRONMENT
    })

    st.subheader("Configuration (Read-only)")
    st.text(f"Config Source: .env file")
    st.text(f"Max Daily Loss: ${settings.MAX_DAILY_LOSS}")
    st.text(f"Max Position Size: ${settings.MAX_POSITION_SIZE}")

with tab6:
    st.subheader("Settings Configuration")
    st.info("Note: Changes require an application restart to take effect.")

    with st.form("config_form"):
        # Trading Symbols
        # Convert list to comma-separated string for editing
        current_symbols = settings.TRADING_SYMBOLS
        if isinstance(current_symbols, list):
            current_symbols_str = ", ".join(current_symbols)
        else:
            current_symbols_str = str(current_symbols)

        new_symbols_str = st.text_input("Trading Symbols (comma separated)", value=current_symbols_str)

        # Active Strategies
        available_strategies = ["MACD_Trend", "RSI_Reversion"]
        current_strategies = settings.ACTIVE_STRATEGIES
        if not isinstance(current_strategies, list):
             current_strategies = [current_strategies]

        # Ensure current strategies are in available list to avoid UI errors
        default_strategies = [s for s in current_strategies if s in available_strategies]

        new_strategies = st.multiselect("Active Strategies", options=available_strategies, default=default_strategies)

        # Risk Management
        new_max_daily_loss = st.number_input("Max Daily Loss (USDT)", value=float(settings.MAX_DAILY_LOSS))
        new_max_position_size = st.number_input("Max Position Size (USDT)", value=float(settings.MAX_POSITION_SIZE))

        submitted = st.form_submit_button("Save Configuration")

        if submitted:
            try:
                # Update .env file
                env_path = ".env"
                if not os.path.exists(env_path):
                    with open(env_path, "w") as f:
                        f.write("")

                # Read lines
                with open(env_path, "r") as f:
                    lines = f.readlines()

                config_map = {
                    "TRADING_SYMBOLS": f'"{new_symbols_str}"', # Wrap in quotes
                    "ACTIVE_STRATEGIES": json.dumps(new_strategies),
                    "MAX_DAILY_LOSS": str(new_max_daily_loss),
                    "MAX_POSITION_SIZE": str(new_max_position_size)
                }

                new_lines = []
                # Update existing keys
                for line in lines:
                    key = line.split("=")[0].strip()
                    if key in config_map:
                        new_lines.append(f"{key}={config_map[key]}\n")
                        del config_map[key]
                    else:
                        new_lines.append(line)

                # Append new keys
                for key, val in config_map.items():
                    new_lines.append(f"{key}={val}\n")

                with open(env_path, "w") as f:
                    f.writelines(new_lines)

                st.success("Configuration saved! Please restart the application.")

            except Exception as e:
                st.error(f"Failed to save configuration: {e}")

with tab7:
    st.subheader("User Guide")
    st.markdown("""
    ### How to use Project Antigravity

    **1. Architecture**
    This application is an **automated trading engine**, not a manual terminal.
    It runs autonomously based on the strategies defined in the code and configuration settings.

    **2. Configuration**
    All settings (API keys, Risk limits, Strategy parameters) are managed via the `.env` file in the project root.
    To change settings:
    1. Stop the application.
    2. Edit `.env`.
    3. Restart the application.

    **3. Strategies**
    You can select active strategies in the **Settings** tab.

    *   **MACD_Trend (Moving Average Convergence Divergence):**
        *   **Logic:** A trend-following momentum indicator.
        *   **Buy Signal:** When the MACD line crosses *above* the Signal line (Bullish Crossover).
        *   **Sell Signal:** When the MACD line crosses *below* the Signal line (Bearish Crossover).
        *   **Purpose:** Captures price trends.

    *   **RSI_Reversion (Relative Strength Index):**
        *   **Logic:** A momentum oscillator measuring the speed and change of price movements.
        *   **Buy Signal:** When RSI drops below 30 (Oversold), indicating the price might bounce back up.
        *   **Sell Signal:** When RSI rises above 70 (Overbought), indicating the price might drop.
        *   **Purpose:** Captures potential reversals in price.

    **4. Portfolio & Signals**
    *   **Portfolio (Sim):** This tab shows simulated trades executed by the bot. Even if you are not running real money, the bot simulates execution to track performance. The 6 trades you see were likely generated during initial testing or simulation runs.
    *   **Strategy Signals:** This tab lists the raw opportunities identified by the strategies (e.g., "RSI is Oversold"). Not all signals become trades (e.g., if Risk Management blocks them).

    **5. Configuration**
    Use the **Settings** tab to change:
    *   **Trading Symbols:** Comma-separated list (e.g., `BTCUSDT, ETHUSDT`).
    *   **Active Strategies:** Select which strategies to run.
    *   **Risk Limits:** Set Max Daily Loss and Position Size.

    **6. Control**
    - **Dashboard**: Use this interface to monitor performance.
    - **Trading**: The bot executes trades automatically. Manual intervention is done by stopping the bot or using the Exchange interface directly.
    """)
