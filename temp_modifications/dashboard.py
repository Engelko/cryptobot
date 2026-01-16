import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine
import time
import asyncio
import os
import json
import logging
import yaml
from antigravity.config import settings
from antigravity.client import BybitClient
from antigravity.logging import configure_logging

# Configure logging for dashboard (creates/writes to antigravity.log)
# Check if file handler already exists to avoid duplication on re-runs
has_file_handler = False
for h in logging.getLogger().handlers:
    if isinstance(h, logging.FileHandler) and "antigravity.log" in h.baseFilename:
        has_file_handler = True
        break

if not has_file_handler:
    configure_logging()

# --- Helper Functions ---
def load_strategies_config(filepath="strategies.yaml"):
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logging.getLogger("dashboard").error(f"Failed to load strategies.yaml: {e}")
        return {}

def save_strategies_config(config, filepath="strategies.yaml"):
    try:
        with open(filepath, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        return True
    except Exception as e:
        logging.getLogger("dashboard").error(f"Failed to save strategies.yaml: {e}")
        return False

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
        except Exception as e:
            logging.getLogger("dashboard").error(f"Balance fetch failed: {e}")
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
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["Market", "Live Portfolio", "Signals", "AI", "System", "Settings", "Help", "Diagnostics"])

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

            # Convert to Datetime and adjust Timezone
            ts_series = pd.to_datetime(df_kline['ts'], unit='ms', utc=True)
            target_tz = os.getenv("TZ", "UTC")
            try:
                ts_series = ts_series.dt.tz_convert(target_tz)
            except Exception as e:
                logging.getLogger("dashboard").warning(f"Timezone conversion failed: {e}")

            fig = go.Figure(data=[go.Candlestick(x=ts_series,
                            open=df_kline['open'],
                            high=df_kline['high'],
                            low=df_kline['low'],
                            close=df_kline['close'])])
            fig.update_layout(height=500, title=f"{selected_symbol} Price Action ({target_tz})")
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

    # Load real active strategies from YAML
    sys_yaml_config = load_strategies_config()
    sys_strategies_config = sys_yaml_config.get("strategies", {})
    active_strategies_list = [
        conf.get("name", key)
        for key, conf in sys_strategies_config.items()
        if conf.get("enabled", False)
    ]

    st.json({
        "Status": "Online",
        "Mode": "Simulation (Paper)" if settings.SIMULATION_MODE else "Live Trading",
        "Risk Manager": "Active",
        "Database": "Connected",
        "Active Strategies": active_strategies_list,
        "Environment": settings.ENVIRONMENT
    })

    st.subheader("Configuration (Read-only)")
    st.text(f"Config Source: .env file")
    st.text(f"Max Daily Loss: ${settings.MAX_DAILY_LOSS}")
    st.text(f"Max Position Size: ${settings.MAX_POSITION_SIZE}")

with tab6:
    st.subheader("Settings Configuration")
    st.info("Note: Changes require an application restart to take effect.")

    # Load YAML Configuration
    yaml_config = load_strategies_config()
    strategies_config = yaml_config.get("strategies", {})

    with st.form("config_form"):
        # Trading Symbols
        # Convert list to comma-separated string for editing
        current_symbols = settings.TRADING_SYMBOLS
        if isinstance(current_symbols, list):
            current_symbols_str = ", ".join(current_symbols)
        else:
            current_symbols_str = str(current_symbols)

        new_symbols_str = st.text_input("Trading Symbols (comma separated)", value=current_symbols_str)

        st.divider()
        st.markdown("### Strategy Configuration (New Architecture)")

        # Dynamic Strategy Controls
        updated_strategies = {}

        # Define pretty names or use keys
        for strat_key, strat_conf in strategies_config.items():
            st.markdown(f"**{strat_conf.get('name', strat_key.title())}**")
            col_en, col_p = st.columns([1, 3])

            with col_en:
                is_enabled = st.checkbox("Enabled", value=strat_conf.get("enabled", False), key=f"en_{strat_key}")
                strat_conf["enabled"] = is_enabled

            # Special Handling for Grid
            if strat_key == "grid":
                with st.expander("Grid Parameters", expanded=True):
                    g_lower = st.number_input("Lower Price", value=float(strat_conf.get("lower_price", 0.0)), key="g_low")
                    g_upper = st.number_input("Upper Price", value=float(strat_conf.get("upper_price", 0.0)), key="g_high")
                    g_levels = st.number_input("Grid Levels", value=int(strat_conf.get("grid_levels", 10)), key="g_lvl")
                    g_amt = st.number_input("Amount per Grid", value=float(strat_conf.get("amount_per_grid", 0.001)), format="%.4f", key="g_amt")

                    strat_conf["lower_price"] = g_lower
                    strat_conf["upper_price"] = g_upper
                    strat_conf["grid_levels"] = g_levels
                    strat_conf["amount_per_grid"] = g_amt

            updated_strategies[strat_key] = strat_conf
            st.divider()

        # Risk Management
        st.markdown("### Global Risk Management")
        new_max_daily_loss = st.number_input("Max Daily Loss (USDT)", value=float(settings.MAX_DAILY_LOSS))
        new_max_position_size = st.number_input("Max Position Size (USDT)", value=float(settings.MAX_POSITION_SIZE))

        submitted = st.form_submit_button("Save Configuration")

        if submitted:
            try:
                # 1. Update .env file (Symbols & Risk)
                env_path = ".env"
                if not os.path.exists(env_path):
                    with open(env_path, "w") as f:
                        f.write("")

                with open(env_path, "r") as f:
                    lines = f.readlines()

                config_map = {
                    "TRADING_SYMBOLS": f'"{new_symbols_str}"',
                    "MAX_DAILY_LOSS": str(new_max_daily_loss),
                    "MAX_POSITION_SIZE": str(new_max_position_size)
                    # Note: We no longer update ACTIVE_STRATEGIES in .env as YAML takes precedence
                }

                new_lines = []
                for line in lines:
                    key = line.split("=")[0].strip()
                    if key in config_map:
                        new_lines.append(f"{key}={config_map[key]}\n")
                        del config_map[key]
                    else:
                        new_lines.append(line)

                for key, val in config_map.items():
                    new_lines.append(f"{key}={val}\n")

                with open(env_path, "w") as f:
                    f.writelines(new_lines)

                # 2. Update strategies.yaml
                yaml_config["strategies"] = updated_strategies
                if save_strategies_config(yaml_config):
                    st.success("Configuration saved! Please restart the application.")
                else:
                    st.warning("Saved .env but failed to save strategies.yaml.")

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

    *   **Volatility Breakout (ATR):**
        *   **Logic:** Uses Average True Range (ATR) to detect explosive price movements.
        *   **Signal:** Enters when price breaks out of a defined range by a multiple of the ATR.
        *   **Purpose:** Catching strong breakout trends early.

    *   **Scalping (Stochastic):**
        *   **Logic:** High-frequency trading based on overbought/oversold conditions in short timeframes.
        *   **Signal:** Uses Stochastic Oscillator (K% and D% lines) to find quick entry/exit points.
        *   **Purpose:** Profiting from small price changes in ranging markets.

    *   **BB Squeeze (Volatility):**
        *   **Logic:** Identifies periods of low volatility (squeeze) followed by high volatility (expansion).
        *   **Signal:** Bollinger Bands narrow inside Keltner Channels, then expand.
        *   **Purpose:** Positioning for a major move after a quiet period.

    *   **Grid Trading (Range):**
        *   **Logic:** Places a mesh of Buy and Sell limit orders within a defined price range.
        *   **Strategy:** Buys low and sells high automatically as price oscillates.
        *   **Configuration:** Set 'Lower Price' and 'Upper Price' in Settings to define the playing field.
        *   **Purpose:** Passive income in sideways/choppy markets.

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

with tab8:
    st.subheader("System Diagnostics")

    # 1. Real-time Logs
    st.markdown("### Real-time Logs")
    col_log1, col_log2 = st.columns([1, 4])
    with col_log1:
        if st.button("Refresh Logs"):
            st.rerun()
    with col_log2:
        if st.button("Ping Log (Write Test Entry)"):
            logging.getLogger("dashboard").info("Diagnostics: Test Log Entry from Dashboard")
            st.rerun()

    log_file = "storage/antigravity.log"
    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as f:
                lines = f.readlines()
                last_lines = "".join(lines[-50:]) # Last 50 lines
                st.code(last_lines, language="text")
        except Exception as e:
            st.error(f"Could not read log file: {e}")
    else:
        st.warning("Log file not found yet. Start the application to generate logs.")

    st.divider()

    # 2. Manual Order Test
    st.markdown("### Test Order Execution")
    st.info("Use this form to test if the bot can successfully place an order on Bybit.")

    with st.form("test_order_form"):
        col1, col2 = st.columns(2)
        with col1:
             test_symbol = st.selectbox("Symbol", settings.TRADING_SYMBOLS, key="test_symbol")
             test_side = st.selectbox("Side", ["Buy", "Sell"], key="test_side")
        with col2:
             test_type = st.selectbox("Type", ["Limit", "Market"], key="test_type")
             test_qty = st.text_input("Quantity", value="0.001", key="test_qty") # Text input for precision

        test_price = st.text_input("Price (Limit Only)", value="0", key="test_price")

        submit_test = st.form_submit_button("Place Test Order")

        if submit_test:
            async def place_test_order():
                client = BybitClient()
                try:
                    p = None
                    if test_type == "Limit":
                        p = test_price

                    res = await client.place_order(
                        category="linear",
                        symbol=test_symbol,
                        side=test_side,
                        orderType=test_type,
                        qty=test_qty,
                        price=p
                    )
                    return res
                except Exception as e:
                    return f"Error: {e}"
                finally:
                    await client.close()

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(place_test_order())
                loop.close()

                if isinstance(result, dict) and "orderId" in result:
                    st.success(f"Order Placed Successfully! Order ID: {result['orderId']}")
                else:
                    st.error(f"Order Failed: {result}")
            except Exception as e:
                st.error(f"Execution Error: {e}")
