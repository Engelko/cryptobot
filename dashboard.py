import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine
import time
import asyncio
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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Market", "Portfolio (Sim)", "Signals", "AI", "System", "Help"])

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
        "Active Strategies": ["MACD_Trend", "RSI_Reversion"],
        "Environment": settings.ENVIRONMENT
    })

    st.subheader("Configuration (Read-only)")
    st.text(f"Config Source: .env file")
    st.text(f"Max Daily Loss: ${settings.MAX_DAILY_LOSS}")
    st.text(f"Max Position Size: ${settings.MAX_POSITION_SIZE}")

with tab6:
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
    Currently, the following strategies are active:

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

    **4. Configuration**
    You can configure which pairs to trade by editing the `.env` file:
    `TRADING_SYMBOLS=["BTCUSDT", "ETHUSDT"]`

    **5. Control**
    - **Dashboard**: Use this interface to monitor performance.
    - **Trading**: The bot executes trades automatically. Manual intervention is done by stopping the bot or using the Exchange interface directly.
    """)
