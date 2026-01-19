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

# Configure logging for dashboard
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
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Market", "Strategies", "Live Portfolio", "Signals", "System", "Settings", "Diagnostics"])

with tab1:
    st.subheader("Market Regimes & Data")

    col_m1, col_m2 = st.columns([1, 3])

    with col_m1:
        st.markdown("### Regime Detection")
        try:
            df_regime = pd.read_sql("SELECT * FROM market_regime ORDER BY updated_at DESC", engine)
            if not df_regime.empty:
                # Deduplicate, keep latest per symbol
                df_regime = df_regime.drop_duplicates(subset=['symbol'], keep='first')

                for _, row in df_regime.iterrows():
                    regime = row['regime']
                    color = "grey"
                    if "TRENDING" in regime: color = "green"
                    if "RANGING" in regime: color = "blue"
                    if "VOLATILE" in regime: color = "red"

                    st.markdown(f"**{row['symbol']}**")
                    st.markdown(f":{color}[{regime}]")
                    st.caption(f"ADX: {row['adx']:.1f} | Vol: {row['volatility']:.2f}%")
                    st.divider()
            else:
                st.info("No regime data yet.")
        except Exception as e:
            st.error(f"DB Error: {e}")

    with col_m2:
        # Symbol Selector
        active_symbols = settings.TRADING_SYMBOLS
        selected_symbol = st.selectbox("Select Pair", active_symbols, index=0)

        try:
            from sqlalchemy import text
            query = text("SELECT * FROM klines WHERE symbol=:symbol ORDER BY ts DESC LIMIT 100")
            df_kline = pd.read_sql(query, engine, params={"symbol": selected_symbol})

            if not df_kline.empty:
                df_kline = df_kline.sort_values("ts")
                ts_series = pd.to_datetime(df_kline['ts'], unit='ms', utc=True)

                fig = go.Figure(data=[go.Candlestick(x=ts_series,
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
    st.subheader("Strategy Configuration")

    # Load YAML Configuration
    yaml_config = load_strategies_config()
    strategies_config = yaml_config.get("strategies", {})

    # Display Active Strategies Summary
    active_list = [k for k, v in strategies_config.items() if v.get("enabled", False)]
    if active_list:
        st.success(f"Active Strategies: {', '.join(active_list)}")
    else:
        st.warning("No strategies enabled.")

    st.divider()

    # Edit Configuration
    with st.form("strat_config_form"):
        st.markdown("### Manage Strategies")
        updated_strategies = {}

        # Iterate through strategies
        for strat_key, strat_conf in strategies_config.items():
            with st.expander(f"{strat_conf.get('name', strat_key.title())} ({'ON' if strat_conf.get('enabled') else 'OFF'})"):

                # Enable Toggle
                is_enabled = st.checkbox("Enabled", value=strat_conf.get("enabled", False), key=f"en_{strat_key}")
                strat_conf["enabled"] = is_enabled

                # Dynamic Fields based on existing keys
                # We skip 'enabled' and 'name' as they are handled or fixed
                col1, col2 = st.columns(2)
                keys = list(strat_conf.keys())
                for i, key in enumerate(keys):
                    if key in ["enabled", "name"]: continue

                    val = strat_conf[key]
                    val_type = type(val)

                    # Split into columns
                    curr_col = col1 if i % 2 == 0 else col2

                    with curr_col:
                        if val_type == bool:
                            strat_conf[key] = st.checkbox(key, value=val, key=f"{strat_key}_{key}")
                        elif val_type == int:
                            strat_conf[key] = st.number_input(key, value=val, step=1, key=f"{strat_key}_{key}")
                        elif val_type == float:
                            strat_conf[key] = st.number_input(key, value=val, format="%.4f", key=f"{strat_key}_{key}")
                        else:
                            strat_conf[key] = st.text_input(key, value=str(val), key=f"{strat_key}_{key}")

            updated_strategies[strat_key] = strat_conf

        submitted = st.form_submit_button("Save Strategy Changes")
        if submitted:
            yaml_config["strategies"] = updated_strategies
            if save_strategies_config(yaml_config):
                st.success("Strategies saved! Restart application to apply changes.")
            else:
                st.error("Failed to save.")

with tab3:
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
                wb = 0.0
                mb = 0.0
                upnl = 0.0
                # Unified vs Standard logic
                if "totalWalletBalance" in balance:
                    wb = float(balance.get("totalWalletBalance", 0))
                    mb = float(balance.get("totalMarginBalance", 0))
                    upnl = float(balance.get("totalPerpUPL", 0)) or float(balance.get("totalUnrealisedPnl", 0))
                elif "coin" in balance:
                    for c in balance["coin"]:
                        if c.get("coin") == "USDT":
                            wb = float(c.get("walletBalance", 0))
                            upnl = float(c.get("unrealisedPnl", 0))
                            mb = float(c.get("equity", 0))
                            break

                c1, c2, c3 = st.columns(3)
                c1.metric("Wallet Balance", f"${wb:.2f}")
                c2.metric("Margin Balance", f"${mb:.2f}")
                c3.metric("Unrealized PnL", f"${upnl:.2f}", delta=f"{upnl:.2f}")
                st.divider()

            # 1. Open Positions
            st.markdown("### Open Positions")
            if positions:
                pos_data = []
                for p in positions:
                    pos_data.append({
                        "Symbol": p.get("symbol"),
                        "Side": p.get("side"),
                        "Size": p.get("size"),
                        "Entry": p.get("avgPrice"),
                        "Mark": p.get("markPrice"),
                        "UPnL": p.get("unrealisedPnl"),
                        "Lev": p.get("leverage")
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

            # 3. Closed PnL
            st.markdown("### Recent Trades (Closed PnL)")
            if history:
                hist_data = []
                for h in history:
                    hist_data.append({
                        "Symbol": h.get("symbol"),
                        "Side": h.get("side"),
                        "Qty": h.get("qty"),
                        "Exit Price": h.get("avgExitPrice"),
                        "PnL": h.get("closedPnl"),
                        "Time": pd.to_datetime(int(h.get("updatedTime")), unit="ms")
                    })
                st.dataframe(pd.DataFrame(hist_data), use_container_width=True)
            else:
                st.info("No History")

        except Exception as e:
            st.error(f"Failed to fetch data: {e}")

with tab4:
    st.subheader("Strategy Signals")
    try:
        df_signals = pd.read_sql("SELECT * FROM signals ORDER BY created_at DESC LIMIT 50", engine)
        if not df_signals.empty:
            # Highlight Rejections
            def highlight_rejected(row):
                if "[REJECTED" in str(row['reason']):
                    return ['background-color: #ffcccc'] * len(row)
                return [''] * len(row)

            st.dataframe(df_signals.style.apply(highlight_rejected, axis=1), use_container_width=True)
        else:
            st.info("No Signals Generated yet.")
    except Exception as e:
        st.error(f"Error loading Signals: {e}")

with tab5:
    st.subheader("System Health")

    st.json({
        "Mode": "Simulation (Paper)" if settings.SIMULATION_MODE else "Live Trading",
        "Market Type": getattr(settings, "DEFAULT_MARKET_TYPE", "linear"),
        "Risk Manager": "Active",
        "Database": "Connected",
        "Environment": settings.ENVIRONMENT
    })

    st.subheader("Risk State")
    try:
        df_risk = pd.read_sql("SELECT * FROM risk_state", engine)
        st.dataframe(df_risk)
    except:
        st.warning("Could not load risk state")

with tab6:
    st.subheader("Global Settings (.env)")

    with st.form("global_config_form"):
        current_symbols = settings.TRADING_SYMBOLS
        if isinstance(current_symbols, list):
            current_symbols_str = ", ".join(current_symbols)
        else:
            current_symbols_str = str(current_symbols)

        new_symbols_str = st.text_input("Trading Symbols", value=current_symbols_str)
        new_max_daily = st.number_input("Max Daily Loss", value=float(settings.MAX_DAILY_LOSS))
        new_max_pos = st.number_input("Max Position Size", value=float(settings.MAX_POSITION_SIZE))

        submitted = st.form_submit_button("Save Global Settings")

        if submitted:
            # Update .env logic (Simplified)
            try:
                env_path = ".env"
                if not os.path.exists(env_path):
                    with open(env_path, "w") as f: f.write("")

                with open(env_path, "r") as f: lines = f.readlines()

                config_map = {
                    "TRADING_SYMBOLS": f'"{new_symbols_str}"',
                    "MAX_DAILY_LOSS": str(new_max_daily),
                    "MAX_POSITION_SIZE": str(new_max_pos)
                }

                new_lines = []
                for line in lines:
                    key = line.split("=")[0].strip()
                    if key in config_map:
                        new_lines.append(f"{key}={config_map[key]}\n")
                        del config_map[key]
                    else:
                        new_lines.append(line)

                for k, v in config_map.items():
                    new_lines.append(f"{k}={v}\n")

                with open(env_path, "w") as f: f.writelines(new_lines)
                st.success("Saved! Restart required.")
            except Exception as e:
                st.error(f"Error saving .env: {e}")

with tab7:
    st.subheader("System Diagnostics")

    # Logs
    if st.button("Refresh Logs"):
        st.rerun()

    log_file = "storage/antigravity.log"
    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as f:
                lines = f.readlines()[-50:]
                st.code("".join(lines))
        except:
            st.error("Log read error")
    else:
        st.warning("No log file found.")
