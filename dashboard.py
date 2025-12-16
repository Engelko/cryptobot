import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from sqlalchemy import create_engine
import time

# Database Connection
db_path = "sqlite:////opt/cryptobot/data.db"
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
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Market", "Portfolio (Sim)", "Signals", "AI", "System"])

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
        "Mode": "Simulation (Paper)",
        "Risk Manager": "Active",
        "Database": "Connected"
    })
