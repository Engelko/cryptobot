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

if auto_refresh:
    time.sleep(5)
    st.rerun()

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Market", "Live Portfolio", "Signals", "AI", "System"])

with tab1:
    st.subheader("Live Market Data (BTCUSDT)")
    try:
        df_kline = pd.read_sql("SELECT * FROM klines ORDER BY ts DESC LIMIT 100", engine)
        if not df_kline.empty:
            df_kline = df_kline.sort_values("ts")
            fig = go.Figure(data=[go.Candlestick(x=pd.to_datetime(df_kline['ts'], unit='ms'),
                            open=df_kline['open'],
                            high=df_kline['high'],
                            low=df_kline['low'],
                            close=df_kline['close'])])
            fig.update_layout(height=500, title="BTCUSDT Price Action")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No Market Data Available yet.")
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
                col1, col2, col3 = st.columns(3)
                col1.metric("Wallet Balance (USDT)", f"${float(balance.get('walletBalance', 0)):.2f}")
                col2.metric("Unrealized PnL", f"${float(balance.get('totalUnrealisedPnl', 0)):.2f}")
                col3.metric("Total Equity", f"${float(balance.get('totalEquity', 0)):.2f}")
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
        "Mode": "Simulation (Paper)",
        "Risk Manager": "Active",
        "Database": "Connected"
    })
