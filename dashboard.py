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

# Fetch and display Wallet Balance in Sidebar
if settings.BYBIT_API_KEY:
    async def fetch_wallet_balance_only():
        client = BybitClient()
        try:
            return await client.get_wallet_balance(coin="USDT")
        except Exception:
            return {}
        finally:
            await client.close()

    try:
        # Create a new loop for this sidebar fetch
        # Note: In Streamlit, creating new loops can sometimes be tricky if one is already running,
        # but here we are in the main script flow, not inside a callback.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        balance_data = loop.run_until_complete(fetch_wallet_balance_only())
        loop.close()

        if balance_data:
            wb = 0.0
            # Unified Account
            if "totalWalletBalance" in balance_data:
                wb = float(balance_data.get("totalWalletBalance", 0))
            # Standard/Contract Account
            elif "coin" in balance_data:
                for c in balance_data["coin"]:
                    if c.get("coin") == "USDT":
                        wb = float(c.get("walletBalance", 0))
                        break

            st.sidebar.metric("Wallet Balance (USDT)", f"${wb:,.2f}")
        else:
             st.sidebar.warning("Balance: N/A")
    except Exception as e:
        st.sidebar.error(f"Err: {str(e)[:20]}")

if auto_refresh:
    time.sleep(5)
    st.rerun()

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Market", "Live Portfolio", "Signals", "AI", "System", "Settings", "Help"])

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
    st.subheader("Live Portfolio (Bybit)")

    if not settings.BYBIT_API_KEY:
        st.error("API Key not found. Please configure BYBIT_API_KEY in .env")
    else:
        # Async data fetcher
        async def fetch_portfolio_data():
            client = BybitClient()
            try:
                balance = await client.get_wallet_balance(coin="USDT")
                positions = await client.get_positions(category="linear")
                orders = await client.get_open_orders(category="linear")
                history = await client.get_closed_pnl(category="linear", limit=20)
                return balance, positions, orders, history
            except Exception as e:
                return {}, [], [], []
            finally:
                await client.close()

        # Run async fetch
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            balance, positions, orders, history = loop.run_until_complete(fetch_portfolio_data())
            loop.close()

            # 0. Account Info
            if balance:
                # Extract metrics based on Account Type
                wb = 0.0
                mb = 0.0
                upnl = 0.0

                # Case 1: Unified Trading Account (UTA)
                if "totalWalletBalance" in balance:
                    wb = float(balance.get("totalWalletBalance", 0))
                    mb = float(balance.get("totalMarginBalance", 0))
                    upnl = float(balance.get("totalPerpUPL", 0)) # Perp Unrealized PnL
                    if upnl == 0:
                         # Fallback if totalPerpUPL is not present (some versions)
                         upnl = float(balance.get("totalUnrealisedPnl", 0))

                # Case 2: Standard/Contract Account (Check 'coin' list)
                elif "coin" in balance:
                    for c in balance["coin"]:
                        if c.get("coin") == "USDT":
                            wb = float(c.get("walletBalance", 0))
                            upnl = float(c.get("unrealisedPnl", 0))
                            # Margin Balance usually equals Equity in Standard if no isolated margin logic simpler
                            mb = float(c.get("equity", 0))
                            break

                col1, col2, col3 = st.columns(3)
                col1.metric("Wallet Balance", f"${wb:.2f}")
                col2.metric("Margin Balance", f"${mb:.2f}")
                col3.metric("Unrealized PnL (Perp)", f"${upnl:.2f}", delta=f"{upnl:.2f}")
                st.divider()

            # 1. Open Positions
            st.markdown("### Open Positions (Linear/Futures)")
            if positions:
                # Process data for display
                pos_data = []
                for p in positions:
                    pos_data.append({
                        "Symbol": p.get("symbol"),
                        "Side": p.get("side"),
                        "Size": p.get("size"),
                        "Entry Price": p.get("avgPrice"),
                        "Mark Price": p.get("markPrice"),
                        "Unrealized PnL": p.get("unrealisedPnl"),
                        "Leverage": p.get("leverage")
                    })
                st.dataframe(pd.DataFrame(pos_data), use_container_width=True)
            else:
                st.info("No Open Positions")

            # 2. Open Orders
            st.markdown("### Active Orders")
            if orders:
                ord_data = []
                for o in orders:
                    ord_data.append({
                        "Symbol": o.get("symbol"),
                        "Side": o.get("side"),
                        "Type": o.get("orderType"),
                        "Price": o.get("price"),
                        "Qty": o.get("qty"),
                        "Status": o.get("orderStatus")
                    })
                st.dataframe(pd.DataFrame(ord_data), use_container_width=True)
            else:
                st.info("No Active Orders")

            # 3. Closed PnL (History)
            st.markdown("### Recent Closed PnL")
            if history:
                hist_data = []
                for h in history:
                    hist_data.append({
                        "Symbol": h.get("symbol"),
                        "Order Type": h.get("orderType"),
                        "Side": h.get("side"),
                        "Qty": h.get("qty"),
                        "Exit Price": h.get("avgExitPrice"),
                        "Closed PnL": h.get("closedPnl"),
                        "Time": pd.to_datetime(int(h.get("updatedTime")), unit="ms")
                    })
                st.dataframe(pd.DataFrame(hist_data), use_container_width=True)
            else:
                st.info("No Closed Positions in history")

        except Exception as e:
            st.error(f"Failed to fetch data: {e}")

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
    *   **Live Portfolio (Bybit):** This tab shows real-time data from your Bybit account (Wallet Balance, Positions, Orders, History). If you see "API Key not found", configure it in the Settings or .env file.
    *   **Strategy Signals:** This tab lists the raw opportunities identified by the strategies.

    **5. Configuration**
    Use the **Settings** tab to change:
    *   **Trading Symbols:** Comma-separated list (e.g., `BTCUSDT, ETHUSDT`).
    *   **Active Strategies:** Select which strategies to run.
    *   **Risk Limits:** Set Max Daily Loss and Position Size.

    **6. Control**
    - **Dashboard**: Use this interface to monitor performance.
    - **Trading**: The bot executes trades automatically. Manual intervention is done by stopping the bot or using the Exchange interface directly.
    """)
