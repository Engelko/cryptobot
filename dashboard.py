import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from sqlalchemy import create_engine, text
import time
import asyncio
import os
import json
import logging
import yaml
import joblib
import lightgbm
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

# Antigravity Imports
from antigravity.config import settings
from antigravity.client import BybitClient
from antigravity.logging import configure_logging
from antigravity.database import db
from antigravity.onchain_analyzer import onchain_analyzer

# ===== CONFIGURATION & SESSION STATE =====
st.set_page_config(
    page_title="Antigravity Mission Control",
    layout="wide",
    page_icon="🚀",
    initial_sidebar_state="expanded"
)

# Load Custom CSS
def load_css():
    css_path = "dashboard_styles.css"
    if os.path.exists(css_path):
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    else:
        st.warning("CSS file not found.")

    # Force viewport meta for mobile scale stability
    st.markdown('<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">', unsafe_allow_html=True)

load_css()

# Database Connection
engine = create_engine(settings.DATABASE_URL)

# Initialize Session State
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# ===== HELPER FUNCTIONS =====

@st.cache_data(ttl=60)
def get_ai_model_info():
    model_path = "storage/ai_model.joblib"
    if os.path.exists(model_path):
        try:
            model = joblib.load(model_path)
            # LightGBM models have feature_name() and feature_importance()
            if hasattr(model, 'feature_name') and hasattr(model, 'feature_importance'):
                features = model.feature_name()
                importances = model.feature_importance(importance_type='gain')
                fi_df = pd.DataFrame({'feature': features, 'importance': importances})
                return fi_df.sort_values('importance', ascending=False).head(10)
        except Exception as e:
            logging.error(f"Failed to load AI model for diagnostics: {e}")
    return pd.DataFrame()

async def fetch_bybit_data():
    client = BybitClient()
    try:
        tasks = [
            client.get_wallet_balance(coin="USDT"),
            client.get_positions(category="linear"),
            client.get_open_orders(category="linear")
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
    finally:
        await client.close()

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def get_risk_state():
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT * FROM risk_state LIMIT 1")).fetchone()
            if res:
                # Handle both tuple and mapping result
                if hasattr(res, '_mapping'):
                    return res._mapping
                return res
    except Exception:
        pass
    return None

def get_trading_mode(equity_ratio: float, consecutive_losses: int) -> str:
    if equity_ratio < settings.EMERGENCY_THRESHOLD:
        return "EMERGENCY"
    if equity_ratio < 0.80 or consecutive_losses >= 2:
        return "RECOVERY"
    return "NORMAL"

# ===== CONFIG PERSISTENCE =====
def save_yaml_config(new_config):
    try:
        with open("strategies.yaml", "w") as f:
            yaml.dump(new_config, f, default_flow_style=False)
        return True
    except Exception as e:
        st.error(f"Failed to save strategies.yaml: {e}")
        return False

def update_env_file(updates: Dict[str, Any]):
    try:
        env_path = ".env"
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()

        # Parse existing keys
        env_dict = {}
        for line in lines:
            if "=" in line and not line.startswith("#"):
                key, val = line.split("=", 1)
                env_dict[key.strip()] = val.strip()

        # Apply updates
        for k, v in updates.items():
            if isinstance(v, list):
                env_dict[k] = json.dumps(v)
            else:
                env_dict[k] = str(v)

        # Write back
        with open(env_path, "w") as f:
            for k, v in env_dict.items():
                f.write(f"{k}={v}\n")
        return True
    except Exception as e:
        st.error(f"Failed to update .env: {e}")
        return False

# ===== DATA FETCHING =====
bybit_results = run_async(fetch_bybit_data())
balance_raw = bybit_results[0] if not isinstance(bybit_results[0], Exception) else {}
positions_raw = bybit_results[1] if not isinstance(bybit_results[1], Exception) else []
orders_raw = bybit_results[2] if not isinstance(bybit_results[2], Exception) else []

# Parse Balance
equity = 0.0
wallet_balance = 0.0
upnl = 0.0
if balance_raw:
    if "totalWalletBalance" in balance_raw:
        wallet_balance = float(balance_raw.get("totalWalletBalance", 0))
        equity = float(balance_raw.get("totalEquity", wallet_balance))
        upnl = float(balance_raw.get("totalPerpUPL", 0))
    elif "coin" in balance_raw:
        for c in balance_raw["coin"]:
            if c.get("coin") == "USDT":
                wallet_balance = float(c.get("walletBalance", 0))
                equity = float(c.get("equity", wallet_balance))
                upnl = float(c.get("unrealisedPnl", 0))
                break

equity_ratio = equity / settings.INITIAL_DEPOSIT if settings.INITIAL_DEPOSIT > 0 else 1.0
risk_state = get_risk_state()
consecutive_losses = risk_state["consecutive_loss_days"] if risk_state and "consecutive_loss_days" in risk_state else 0
mode = get_trading_mode(equity_ratio, consecutive_losses)

# ===== LEVEL 1: CRITICAL STATUS BAR (STICKY) =====
st.markdown(f"""
<div class="sticky-header">
    <div style="display: flex; align-items: center; gap: 20px;">
        <span style="font-size: 20px; font-weight: 700; color: #FAFAFA;">ANTIGRAVITY <span style="color: #3B82F6;">v2.0</span></span>
        <div class="mode-container">
            <div class="mode-badge mode-normal {'active' if mode == 'NORMAL' else ''}" title="Equity >= 80%">NORMAL</div>
            <div class="mode-badge mode-recovery {'active' if mode == 'RECOVERY' else ''}" title="Equity < 80% or 2+ Loss Days">RECOVERY</div>
            <div class="mode-badge mode-emergency {'active' if mode == 'EMERGENCY' else ''}" title="Equity < 50%">EMERGENCY</div>
        </div>
    </div>
    <div style="display: flex; align-items: center; gap: 40px;">
        <div style="text-align: right;">
            <div style="font-size: 10px; color: #9CA3AF; text-transform: uppercase;">Equity Ratio</div>
            <div style="font-size: 18px; font-weight: 700; color: {'#10B981' if equity_ratio >= 0.8 else '#F59E0B' if equity_ratio >= 0.5 else '#EF4444'}">
                {equity_ratio:.1%}
            </div>
        </div>
        <div style="text-align: right;">
            <div style="font-size: 10px; color: #9CA3AF; text-transform: uppercase;">Total Equity</div>
            <div style="font-size: 18px; font-weight: 700;">${equity:,.2f}</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Alert Ticker
try:
    df_recent_signals = pd.read_sql("SELECT created_at, reason FROM signals ORDER BY created_at DESC LIMIT 5", engine)
    alerts = []
    for _, row in df_recent_signals.iterrows():
        time_str = row['created_at'].split()[1][:5] if isinstance(row['created_at'], str) else row['created_at'].strftime("%H:%M")
        reason = row['reason']
        icon = "🚨" if "[REJECTED" in reason else "✅" if "accepted" in reason.lower() else "⚠️"
        alerts.append(f"<span class='alert-item'>{icon} {time_str} - {reason}</span>")

    alert_html = "".join(alerts) if alerts else "<span class='alert-item'>🛰️ System Online - Awaiting Signals...</span>"
    st.markdown(f"""
    <div class="alert-ticker-container">
        <div class="alert-ticker-content">
            {alert_html} {alert_html}
        </div>
    </div>
    """, unsafe_allow_html=True)
except Exception:
    st.markdown("<div class='alert-ticker-container'>Ticker Unavailable</div>", unsafe_allow_html=True)

# Main Dashboard Layout
col_gauge, col_main = st.columns([1, 4])

with col_gauge:
    # Equity Gauge
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = equity_ratio * 100,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Equity Status (%)", 'font': {'size': 16}},
        number = {'suffix': "%", 'font': {'size': 24}},
        gauge = {
            'axis': {'range': [0, 150], 'tickwidth': 1},
            'bar': {'color': "#3B82F6"},
            'bgcolor': "rgba(0,0,0,0)",
            'borderwidth': 2,
            'bordercolor': "#30363D",
            'steps': [
                {'range': [0, 50], 'color': '#EF4444'},
                {'range': [50, 80], 'color': '#F59E0B'},
                {'range': [80, 120], 'color': '#10B981'},
                {'range': [120, 150], 'color': '#60A5FA'}
            ],
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': 100
            }
        }
    ))
    fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor="rgba(0,0,0,0)", font={'color': "#FAFAFA"})
    st.plotly_chart(fig_gauge, use_container_width=True)

    # Sidebar Metrics (Secondary)
    st.sidebar.markdown("### System Controls")
    refresh_rate = st.sidebar.select_slider("Auto-Refresh (sec)", options=[5, 10, 30, 60], value=10)
    if st.sidebar.button("Manual Refresh"):
        st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("### Active Strategies")
    try:
        with open("strategies.yaml", "r") as f:
            yaml_config = yaml.safe_load(f).get("strategies", {})

        active_env = settings.ACTIVE_STRATEGIES
        if isinstance(active_env, str):
            active_env = [s.strip() for s in active_env.split(",")]

        # Mapping for display
        mapping = {
            "trend_following": ["MACD_Trend", "GoldenCross", "TrendFollowing"],
            "mean_reversion": ["RSI_Reversion", "BollingerRSI", "MeanReversion"],
            "volatility_breakout": ["ATRBreakout", "VolatilityBreakout"],
            "scalping": ["StochScalp", "Scalping"],
            "bb_squeeze": ["BBSqueeze"],
            "grid": ["GridMaster", "Grid"],
            "dynamic_risk_leverage": ["DynamicRiskLeverage"],
            "spot_recovery": ["SpotRecovery"]
        }

        for key, env_names in mapping.items():
            conf = yaml_config.get(key, {})

            # Match logic in main.py: .env takes precedence if not empty
            if active_env and (isinstance(active_env, list) and len(active_env) > 0 or isinstance(active_env, str) and len(active_env) > 0):
                is_active = False
                for name in env_names:
                    if name in active_env:
                        is_active = True
                        break
            else:
                is_active = conf.get("enabled", False)

            # Special case for SpotRecovery which is always on in the engine but conditional in execution
            if key == "spot_recovery":
                is_active = True

            if is_active:
                st.sidebar.markdown(f"✅ **{key.replace('_', ' ').title()}**")
            else:
                st.sidebar.markdown(f"⚪ {key.replace('_', ' ').title()}")
    except Exception as e:
        st.sidebar.error(f"Error loading strategies: {e}")

    st.sidebar.divider()
    st.sidebar.markdown("### Bot Parameters")
    st.sidebar.json({
        "Max Daily Loss": f"${settings.MAX_DAILY_LOSS}",
        "Max Pos Size": f"${settings.MAX_POSITION_SIZE}",
        "Max Leverage": f"{settings.MAX_LEVERAGE}x",
        "Stop Loss": f"{settings.STOP_LOSS_PCT*100}%"
    })

with col_main:
    tabs = st.tabs(["🎯 Risk", "🤖 AI & Strategies", "📊 Market", "💼 Portfolio", "⚙️ Settings"])

    # ===== TAB 1: RISK MANAGEMENT =====
    with tabs[0]:
        r_col1, r_col2 = st.columns([2, 1])

        with r_col1:
            st.markdown("#### Cascade Stops Architecture")
            # Flowchart Logic
            daily_loss_val = risk_state["daily_loss"] if risk_state else 0.0
            daily_loss_pct = (daily_loss_val / settings.MAX_DAILY_LOSS) * 100 if settings.MAX_DAILY_LOSS > 0 else 0

            # Cascading levels status
            l1_status = "Active" if mode != "EMERGENCY" else "Triggered"
            l2_status = "Active" if mode != "EMERGENCY" else "Triggered"
            l3_status = "Warning" if daily_loss_pct > 70 else "Active" if daily_loss_val > 0 else "Standby"
            l4_status = "Triggered" if mode == "RECOVERY" else "Standby"
            l5_status = "Triggered" if mode == "EMERGENCY" else "Standby"

            def get_color(status):
                return {"Active": "#10B981", "Warning": "#F59E0B", "Triggered": "#EF4444", "Standby": "#9CA3AF"}[status]

            st.markdown(f"""
            <div style="display: flex; flex-direction: column; gap: 10px; padding: 20px; background: #1E2128; border-radius: 12px; border: 1px solid #30363D;">
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; border-radius: 6px; background: rgba(16, 185, 129, 0.1); border-left: 4px solid {get_color(l1_status)};">
                    <span><b>Level 1: Position Stop Loss</b> (-{settings.STOP_LOSS_PCT*100}%)</span>
                    <span style="color: {get_color(l1_status)}; font-weight: bold;">{l1_status}</span>
                </div>
                <div style="text-align: center; color: #4B5563;">↓</div>
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; border-radius: 6px; background: rgba(16, 185, 129, 0.1); border-left: 4px solid {get_color(l2_status)};">
                    <span><b>Level 2: Trailing Stop</b> (+{settings.TRAILING_STOP_TRIGGER*100}% Profit Trigger)</span>
                    <span style="color: {get_color(l2_status)}; font-weight: bold;">{l2_status}</span>
                </div>
                <div style="text-align: center; color: #4B5563;">↓</div>
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; border-radius: 6px; background: rgba(245, 158, 11, 0.1); border-left: 4px solid {get_color(l3_status)};">
                    <span><b>Level 3: Daily Loss Limit</b> (${settings.MAX_DAILY_LOSS}/day)</span>
                    <span style="color: {get_color(l3_status)}; font-weight: bold;">{f"${daily_loss_val:.2f} Used" if daily_loss_val > 0 else l3_status}</span>
                </div>
                <div style="text-align: center; color: #4B5563;">↓</div>
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; border-radius: 6px; background: rgba(239, 68, 68, 0.1); border-left: 4px solid {get_color(l4_status)};">
                    <span><b>Level 4: Recovery Mode</b> (Spot Only DCA < 80%)</span>
                    <span style="color: {get_color(l4_status)}; font-weight: bold;">{l4_status}</span>
                </div>
                <div style="text-align: center; color: #4B5563;">↓</div>
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; border-radius: 6px; background: rgba(239, 68, 68, 0.2); border-left: 4px solid {get_color(l5_status)};">
                    <span><b>Level 5: Emergency Stop</b> (Equity < 50%)</span>
                    <span style="color: {get_color(l5_status)}; font-weight: bold;">{l5_status}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with r_col2:
            st.markdown("#### Daily Loss Progress")
            fig_progress = go.Figure(go.Indicator(
                mode = "gauge+number",
                value = daily_loss_val,
                domain = {'x': [0, 1], 'y': [0, 1]},
                title = {'text': "Used Loss Limit ($)"},
                gauge = {
                    'axis': {'range': [0, settings.MAX_DAILY_LOSS]},
                    'bar': {'color': "#EF4444" if daily_loss_pct > 80 else "#F59E0B"},
                    'steps': [
                        {'range': [0, settings.MAX_DAILY_LOSS], 'color': "#30363D"}
                    ],
                    'threshold': {
                        'line': {'color': "white", 'width': 2},
                        'value': settings.MAX_DAILY_LOSS
                    }
                }
            ))
            fig_progress.update_layout(height=200, margin=dict(l=20, r=20, t=40, b=20), paper_bgcolor="rgba(0,0,0,0)", font={'color': "#FAFAFA"})
            st.plotly_chart(fig_progress, use_container_width=True)

            st.metric("Consecutive Loss Days", consecutive_losses, delta=None)

        st.markdown("#### Position Risk Matrix")
        if positions_raw:
            pos_processed = []
            for p in positions_raw:
                symbol = p.get("symbol")
                side = p.get("side")
                entry = float(p.get("avgPrice", 0))
                mark = float(p.get("markPrice", 0))

                # SL Calculation
                sl_pct = settings.STOP_LOSS_PCT
                sl_price = entry * (1 - sl_pct) if side == "Buy" else entry * (1 + sl_pct)
                dist_to_sl = (mark - sl_price) / sl_price if side == "Buy" else (sl_price - mark) / sl_price

                pos_processed.append({
                    "Symbol": symbol,
                    "Side": side,
                    "Entry": entry,
                    "Mark": mark,
                    "UPnL": f"${float(p.get('unrealisedPnl', 0)):.2f}",
                    "SL Price": sl_price,
                    "SL Distance": dist_to_sl,
                    "Leverage": f"{p.get('leverage')}x"
                })

            df_pos = pd.DataFrame(pos_processed)

            def color_sl_dist(val):
                color = '#10B981' # green
                if val < 0.01: color = '#EF4444' # red
                elif val < 0.03: color = '#F59E0B' # yellow
                return f'color: {color}'

            st.dataframe(
                df_pos.style.format({"SL Distance": "{:.2%}"}).applymap(color_sl_dist, subset=['SL Distance']),
                use_container_width=True
            )
        else:
            st.info("No active positions to monitor.")

    # ===== TAB 2: AI & STRATEGIES =====
    with tabs[1]:
        ai_col1, ai_col2 = st.columns(2)

        with ai_col1:
            st.markdown("#### AI Prediction Performance")
            try:
                df_preds = pd.read_sql("""
                    SELECT DATE(created_at) as date, AVG(confidence) as avg_conf, COUNT(*) as count
                    FROM predictions GROUP BY date ORDER BY date DESC LIMIT 7
                """, engine)

                if df_preds.empty:
                    st.info("📡 **Waiting for AI signals...** No prediction data found in database.")
                else:
                    fig_ai = px.line(df_preds, x='date', y='avg_conf', title='Avg Confidence Trend', markers=True)
                    fig_ai.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_ai, use_container_width=True)

            except Exception as e:
                st.error(f"Prediction Query Error: {e}")

            st.markdown("#### Confidence Distribution")
            try:
                df_conf = pd.read_sql("SELECT confidence FROM predictions ORDER BY created_at DESC LIMIT 200", engine)
                if not df_conf.empty:
                    fig_dist = px.histogram(df_conf, x="confidence", nbins=20, title="Prediction Confidence")
                    fig_dist.add_vline(x=0.6, line_dash="dash", line_color="red", annotation_text="Acceptance Zone")
                    fig_dist.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_dist, use_container_width=True)
                else:
                    st.caption("No distribution data available.")
            except Exception:
                pass

        with ai_col2:
            st.markdown("#### AI Feature Importance (Top 10)")
            fi_df = get_ai_model_info()
            if not fi_df.empty:
                fig_fi = px.bar(fi_df, y='feature', x='importance', orientation='h', title='Global Model Feature Impact')
                fig_fi.update_layout(height=400, yaxis={'categoryorder':'total ascending'}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_fi, use_container_width=True)
            else:
                st.info("AI Model file not found in storage/ai_model.joblib or incompatible format.")

            st.markdown("#### On-chain Indicators")
            if not settings.MESSARI_API_KEY or not settings.COINGECKO_API_KEY:
                st.info("💡 **On-chain data missing.**")
                if not settings.MESSARI_API_KEY:
                    st.write("- Set `MESSARI_API_KEY` in `.env` for Exchange Flows.")
                if not settings.COINGECKO_API_KEY:
                    st.write("- Set `COINGECKO_API_KEY` in `.env` for Volume Spike Detection.")
            else:
                # Real on-chain data fetch
                o_c1, o_c2 = st.columns(2)
                netflow = onchain_analyzer.get_netflow()
                fear_greed = onchain_analyzer.get_fear_greed()

                nf_delta = "Outflow (Bullish)" if netflow < 0 else "Inflow (Bearish)"
                fg_delta = "Fear (Bullish)" if fear_greed < 40 else "Greed (Bearish)" if fear_greed > 70 else "Neutral"

                o_c1.metric("Exchange Netflow", f"{netflow:.1f} BTC", delta=nf_delta, delta_color="normal" if netflow < 0 else "inverse")
                o_c2.metric("Fear & Greed Index", f"{fear_greed}", delta=fg_delta, delta_color="normal" if fear_greed < 40 else "inverse")

                st.progress(onchain_analyzer.get_score(), text=f"Sentiment Score: {onchain_analyzer.get_score():.2f}")

            st.markdown("#### Whale Alerts Feed")
            if not settings.COINGECKO_API_KEY:
                 st.caption("CoinGecko API key required in .env for Volume Spike detection.")
            else:
                 whale_safe = onchain_analyzer.is_whale_safe()
                 if not whale_safe:
                     st.error("🐋 **Whale Activity Detected!** Trading paused.")
                 else:
                     st.success("🐋 **Whale activity within normal range.**")
                 st.info("Using Volume Spike detection via CoinGecko")

        st.markdown("#### Strategy Performance Heatmap")
        try:
            df_heatmap = pd.read_sql("""
                SELECT strategy, symbol,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate
                FROM trades WHERE created_at >= datetime('now', '-7 days') AND pnl != 0
                GROUP BY strategy, symbol
            """, engine)

            if df_heatmap.empty:
                st.info("📉 **No trade data available.** Win rate heatmap will appear after first successful trades.")
            else:
                pivot = df_heatmap.pivot_table(index='symbol', columns='strategy', values='win_rate', aggfunc='mean').fillna(0)
                fig_heat = px.imshow(pivot, text_auto=True, color_continuous_scale='RdYlGn', labels=dict(color="Win Rate %"))
                st.plotly_chart(fig_heat, use_container_width=True)

        except Exception as e:
            st.error(f"Heatmap Error: {e}")

    # ===== TAB 3: MARKET DATA =====
    with tabs[2]:
        m_col1, m_col2 = st.columns([1, 3])

        with m_col1:
            st.markdown("#### Current Regimes")
            try:
                df_regime = pd.read_sql("SELECT * FROM market_regime ORDER BY updated_at DESC", engine)
                if not df_regime.empty:
                    for _, row in df_regime.iterrows():
                        reg = row['regime']
                        color = "#10B981" if "TRENDING" in reg else "#3B82F6" if "RANGING" in reg else "#EF4444"
                        st.markdown(f"""
                        <div style="padding: 10px; border-radius: 8px; border-left: 5px solid {color}; background: #1E2128; margin-bottom: 10px;">
                            <div style="font-size: 14px; font-weight: bold;">{row['symbol']}</div>
                            <div style="font-size: 12px; color: {color};">{reg}</div>
                            <div style="font-size: 10px; color: #9CA3AF;">ADX: {row['adx']:.1f} | ATR: {row['volatility']:.2f}</div>
                        </div>
                        """, unsafe_allow_html=True)
            except Exception:
                pass

        with m_col2:
            st.markdown("#### Regime Timeline (Last 24h)")
            try:
                df_hist = pd.read_sql("""
                    SELECT created_at, symbol, regime FROM market_regime_history
                    WHERE created_at >= datetime('now', '-24 hours') ORDER BY created_at ASC
                """, engine)
                if not df_hist.empty:
                    fig_timeline = px.line(df_hist, x='created_at', y='regime', color='symbol', title="Regime Shifts Over Time")
                    st.plotly_chart(fig_timeline, use_container_width=True)
                else:
                    st.info("Market history is being collected. Data will appear here shortly.")
            except Exception:
                st.info("Regime history tracking enabled. Waiting for first updates.")

            # Dual Axis ADX/Volatility
            st.markdown("#### ADX & Volatility Dynamics")
            # Logic for selecting symbol...
            selected_symbol = st.selectbox("Symbol Analysis", settings.TRADING_SYMBOLS, index=0)
            try:
                df_metrics = pd.read_sql(text("""
                    SELECT created_at, adx, volatility FROM market_regime_history
                    WHERE symbol = :symbol AND created_at >= datetime('now', '-24 hours')
                """), engine, params={"symbol": selected_symbol})
                if not df_metrics.empty:
                    fig_dual = go.Figure()
                    fig_dual.add_trace(go.Scatter(x=df_metrics['created_at'], y=df_metrics['adx'], name="ADX (Trend Strength)", line=dict(color='#10B981')))
                    fig_dual.add_trace(go.Scatter(x=df_metrics['created_at'], y=df_metrics['volatility'], name="Volatility (ATR)", yaxis="y2", line=dict(color='#3B82F6')))
                    fig_dual.update_layout(
                        yaxis=dict(title="ADX"),
                        yaxis2=dict(title="ATR", overlaying="y", side="right"),
                        height=400, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
                    )
                    st.plotly_chart(fig_dual, use_container_width=True)
            except Exception:
                pass

    # ===== TAB 4: PORTFOLIO & DATA =====
    with tabs[3]:
        p_col1, p_col2 = st.columns(2)

        with p_col1:
            st.markdown("#### Daily P&L Waterfall")
            try:
                df_pnl = pd.read_sql(text("SELECT pnl, symbol, created_at FROM trades WHERE DATE(created_at) = DATE('now') AND pnl != 0"), engine)

                if df_pnl.empty:
                    st.info("💸 **No closed trades today.**")
                else:
                    fig_water = go.Figure(go.Waterfall(
                        name = "Daily P&L", orientation = "v",
                        measure = ["relative"] * len(df_pnl) + ["total"],
                        x = [f"{row['symbol']} #{i}" for i, row in df_pnl.iterrows()] + ["NET"],
                        y = list(df_pnl['pnl']) + [df_pnl['pnl'].sum()],
                        connector = {"line":{"color":"rgb(63, 63, 63)"}},
                    ))
                    fig_water.update_layout(title = "Today's Profit Path", height=350, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_water, use_container_width=True)
            except Exception as e:
                st.error(f"Waterfall Error: {e}")

        with p_col2:
            st.markdown("#### Signal Flow Sankey")
            try:
                df_sig_flow = pd.read_sql("""
                    SELECT strategy, reason FROM signals WHERE created_at >= datetime('now', '-24 hours')
                """, engine)
                if not df_sig_flow.empty:
                    # Categorize reasons
                    def categorize(reason):
                        if "[REJECTED: AI" in reason: return "AI Filter"
                        if "[REJECTED: Risk" in reason: return "Risk Manager"
                        if "[REJECTED: Market" in reason: return "Strategy Router"
                        if "[REJECTED:" in reason: return "Rejected (Other)"
                        return "Executed"

                    df_sig_flow['target'] = df_sig_flow['reason'].apply(categorize)

                    # Prepare Sankey Data
                    strategies = sorted(df_sig_flow['strategy'].unique().tolist())
                    targets = ["AI Filter", "Risk Manager", "Strategy Router", "Rejected (Other)", "Executed"]
                    all_labels = strategies + targets

                    label_map = {label: i for i, label in enumerate(all_labels)}

                    sources = []
                    s_targets = []
                    values = []

                    for strat in strategies:
                        strat_data = df_sig_flow[df_sig_flow['strategy'] == strat]
                        counts = strat_data['target'].value_counts()
                        for target, count in counts.items():
                            sources.append(label_map[strat])
                            s_targets.append(label_map[target])
                            values.append(int(count))

                    fig_sankey = go.Figure(data=[go.Sankey(
                        node = dict(
                          pad = 15,
                          thickness = 20,
                          line = dict(color = "black", width = 0.5),
                          label = all_labels,
                          color = "#3B82F6"
                        ),
                        link = dict(
                          source = sources,
                          target = s_targets,
                          value = values
                        ))])

                    fig_sankey.update_layout(title_text="Signal Processing Path", font_size=10, height=350)
                    st.plotly_chart(fig_sankey, use_container_width=True)
                else:
                    st.info("No signal data in the last 24h.")
            except Exception as e:
                st.error(f"Sankey Error: {e}")

        st.markdown("#### Recent Trade Log")
        try:
            df_trades = pd.read_sql("SELECT * FROM trades ORDER BY created_at DESC LIMIT 50", engine)
            st.dataframe(df_trades, use_container_width=True)
        except Exception:
            pass

    # ===== TAB 5: SETTINGS & SYSTEM =====
    with tabs[4]:
        st.subheader("Global System Configuration")

        # Load current YAML for editing
        try:
            with open("strategies.yaml", "r") as f:
                current_yaml = yaml.safe_load(f)
        except Exception:
            current_yaml = {"strategies": {}}

        with st.form("settings_form"):
            st.markdown("#### 🌍 General Limits (.env)")
            c1, c2 = st.columns(2)
            new_symbols = c1.text_area("Trading Symbols (JSON list)", value=json.dumps(settings.TRADING_SYMBOLS))
            new_leverage = c2.number_input("Max Leverage (Global Cap)", value=settings.MAX_LEVERAGE, min_value=1.0, max_value=20.0, step=0.5)
            new_daily_loss = c1.number_input("Max Daily Loss ($)", value=settings.MAX_DAILY_LOSS, min_value=1.0)
            new_pos_size = c2.number_input("Max Position Size ($)", value=settings.MAX_POSITION_SIZE, min_value=1.0)
            new_initial_deposit = c1.number_input("Initial Deposit ($) for Drawdown", value=settings.INITIAL_DEPOSIT)

            st.divider()
            st.markdown("#### 🎯 Strategy Risk Settings (strategies.yaml)")

            # Create a column for each strategy's risk
            strat_keys = ["trend_following", "mean_reversion", "volatility_breakout", "scalping", "bb_squeeze", "grid"]
            new_risks = {}

            # Split into two columns for better layout
            sc1, sc2 = st.columns(2)
            for i, key in enumerate(strat_keys):
                target_col = sc1 if i % 2 == 0 else sc2

                # Get current risk or default to 0.02
                strat_data = current_yaml.get("strategies", {}).get(key, {})
                current_risk = strat_data.get("risk_per_trade", 0.02)

                label = f"{key.replace('_', ' ').title()} Risk (%)"
                # Use percentage for easier UI (0.02 -> 2.0%)
                new_risk_pct = target_col.slider(label, 0.1, 20.0, float(current_risk * 100.0), 0.1, help=f"Risk per trade for {key}")
                new_risks[key] = new_risk_pct / 100.0

            # Special case for DynamicRiskLeverage
            drl_data = current_yaml.get("strategies", {}).get("dynamic_risk_leverage", {})
            drl_max_risk = drl_data.get("max_risk_per_trade", 0.02)
            drl_risk = sc1.slider("DynamicRiskLeverage Max Risk (%)", 0.1, 20.0, float(drl_max_risk * 100.0), 0.1)
            new_risks["dynamic_risk_leverage"] = drl_risk / 100.0

            st.divider()
            submit_col1, submit_col2 = st.columns([1, 1])
            if submit_col1.form_submit_button("💾 Save All Changes"):
                # 1. Update YAML
                for key, risk_val in new_risks.items():
                    if key in current_yaml["strategies"]:
                        if key == "dynamic_risk_leverage":
                            current_yaml["strategies"][key]["max_risk_per_trade"] = risk_val
                        else:
                            current_yaml["strategies"][key]["risk_per_trade"] = risk_val

                yaml_success = save_yaml_config(current_yaml)

                # 2. Update .env
                env_updates = {
                    "TRADING_SYMBOLS": json.loads(new_symbols),
                    "MAX_LEVERAGE": new_leverage,
                    "MAX_DAILY_LOSS": new_daily_loss,
                    "MAX_POSITION_SIZE": new_pos_size,
                    "INITIAL_DEPOSIT": new_initial_deposit
                }
                env_success = update_env_file(env_updates)

                if yaml_success and env_success:
                    st.success("✅ Configuration saved! Please restart the bot to apply changes.")
                    st.balloons()
                else:
                    st.error("❌ Some changes could not be saved.")

        st.divider()
        st.subheader("Diagnostics")
        d_c1, d_c2 = st.columns(2)
        if d_c1.button("Clear Cache"):
            st.cache_data.clear()
            st.success("Cache Cleared!")

        if d_c2.button("Run Connection Test"):
            try:
                test_client = BybitClient()
                run_async(test_client.get_server_time())
                st.success("Bybit API: Connected")
            except Exception as e:
                st.error(f"Bybit API: Failed - {e}")

# Bottom Info
st.divider()
st.caption(f"Antigravity Dashboard | System Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC | Refreshing in {refresh_rate}s")

# Auto-Refresh Logic
if st.session_state.last_refresh + timedelta(seconds=refresh_rate) < datetime.now():
    st.session_state.last_refresh = datetime.now()
    st.rerun()
