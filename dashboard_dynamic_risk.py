import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timezone, timedelta
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antigravity.performance_tracker import PerformanceTracker
from antigravity.strategies.dynamic_risk_leverage import DynamicRiskLeverageStrategy, EntryType, TrendDirection
from antigravity.strategies.config import DynamicRiskLeverageConfig
from antigravity.database import db

st.set_page_config(
    page_title="Dynamic Risk Leverage Dashboard",
    page_icon="📊",
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
<style>
.metric-card {
    background-color: #f0f2f6;
    padding: 20px;
    border-radius: 10px;
    margin: 10px 0;
}
.success { color: #0f5132; }
.warning { color: #664d03; }
.danger { color: #842029; }
.info { color: #084298; }
</style>
""", unsafe_allow_html=True)

def load_performance_data():
    """Load performance data from database"""
    try:
        # This would connect to your actual database
        # For now, return mock data
        tracker = PerformanceTracker()
        
        # Add some mock trades for demonstration
        from antigravity.performance_tracker import Trade, TradeResult
        import uuid
        
        mock_trades = [
            {
                "id": str(uuid.uuid4()),
                "symbol": "BTCUSDT",
                "entry_type": "A",
                "signal_type": "BUY",
                "entry_price": 45000.0,
                "entry_time": datetime.now(timezone.utc) - timedelta(hours=24),
                "quantity": 0.001,
                "leverage": 9.0,
                "stop_loss": 44500.0,
                "exit_price": 46500.0,
                "exit_time": datetime.now(timezone.utc) - timedelta(hours=20),
                "result": TradeResult.WIN,
                "pnl": 180.0
            },
            {
                "id": str(uuid.uuid4()),
                "symbol": "ETHUSDT",
                "entry_type": "B",
                "signal_type": "SELL",
                "entry_price": 3200.0,
                "entry_time": datetime.now(timezone.utc) - timedelta(hours=18),
                "quantity": 0.01,
                "leverage": 6.0,
                "stop_loss": 3250.0,
                "exit_price": 3100.0,
                "exit_time": datetime.now(timezone.utc) - timedelta(hours=15),
                "result": TradeResult.WIN,
                "pnl": 60.0
            },
            {
                "id": str(uuid.uuid4()),
                "symbol": "SOLUSDT",
                "entry_type": "C",
                "signal_type": "BUY",
                "entry_price": 120.0,
                "entry_time": datetime.now(timezone.utc) - timedelta(hours=12),
                "quantity": 0.1,
                "leverage": 2.5,
                "stop_loss": 118.0,
                "exit_price": 119.0,
                "exit_time": datetime.now(timezone.utc) - timedelta(hours=10),
                "result": TradeResult.LOSS,
                "pnl": -2.5
            }
        ]
        
        for trade_data in mock_trades:
            trade = Trade(
                id=trade_data["id"],
                symbol=trade_data["symbol"],
                entry_type=trade_data["entry_type"],
                signal_type=trade_data["signal_type"],
                entry_price=trade_data["entry_price"],
                entry_time=trade_data["entry_time"],
                quantity=trade_data["quantity"],
                leverage=trade_data["leverage"],
                stop_loss=trade_data["stop_loss"]
            )
            
            if trade_data.get("exit_price"):
                tracker.close_trade(
                    trade.id,
                    trade_data["exit_price"],
                    trade_data["exit_time"]
                )
            else:
                tracker.add_trade(trade)
        
        return tracker
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return PerformanceTracker()

def create_metric_card(title, value, delta=None, color="info"):
    """Create a styled metric card"""
    color_classes = {
        "success": "success",
        "warning": "warning", 
        "danger": "danger",
        "info": "info"
    }
    
    delta_str = f" {delta}" if delta else ""
    
    st.markdown(f"""
    <div class="metric-card">
        <h3 style="margin: 0; color: #6c757d;">{title}</h3>
        <p style="font-size: 2rem; margin: 10px 0; color: #212529; font-weight: bold;">
            {value}
            <span style="font-size: 1rem; color: #6c757d;">{delta_str}</span>
        </p>
    </div>
    """, unsafe_allow_html=True)

def main():
    st.title("🚀 Dynamic Risk Leverage Strategy Dashboard")
    st.markdown("---")
    
    # Sidebar for configuration
    st.sidebar.header("⚙️ Configuration")
    
    # Time period selector
    time_period = st.sidebar.selectbox(
        "Time Period",
        ["Last 7 days", "Last 30 days", "Last 90 days", "All time"],
        index=1
    )
    
    # Load data
    tracker = load_performance_data()
    summary = tracker.get_summary_report()
    
    # Main dashboard tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview", 
        "💼 Recent Trades", 
        "📈 Performance Metrics", 
        "🎯 Entry Analysis", 
        "⚙️ Strategy Settings"
    ])
    
    with tab1:
        st.header("📊 Strategy Overview")
        
        # Key metrics in columns
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            create_metric_card(
                "Total P&L", 
                f"${summary['total_pnl']:.2f}",
                f"({summary['total_fees']:.2f} fees)",
                "success" if summary['total_pnl'] > 0 else "danger"
            )
        
        with col2:
            create_metric_card(
                "Win Rate", 
                f"{summary['win_rate']:.1f}%",
                f"{summary['total_wins']}/{summary['total_trades']} trades",
                "success" if summary['win_rate'] >= 55 else "warning"
            )
        
        with col3:
            create_metric_card(
                "Profit Factor", 
                f"{summary['profit_factor']:.2f}",
                "",
                "success" if summary['profit_factor'] >= 1.5 else "warning"
            )
        
        with col4:
            create_metric_card(
                "Active Positions", 
                f"{summary['current_positions']}",
                "",
                "info"
            )
        
        # Additional metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            create_metric_card(
                "Avg Win/Loss Ratio",
                f"{summary['average_win_loss_ratio']:.2f}",
                "",
                "success" if summary['average_win_loss_ratio'] >= 1.5 else "warning"
            )
        
        with col2:
            create_metric_card(
                "Max Consecutive Wins",
                f"{summary['max_consecutive_wins']}",
                "",
                "success"
            )
        
        with col3:
            create_metric_card(
                "Max Consecutive Losses", 
                f"{summary['max_consecutive_losses']}",
                "",
                "danger" if summary['max_consecutive_losses'] >= 3 else "warning"
            )
        
        # Entry Type Performance
        st.subheader("🎯 Performance by Entry Type")
        
        entry_stats = summary['entry_type_stats']
        
        fig = go.Figure()
        
        categories = ['Type A', 'Type B', 'Type C']
        win_rates = []
        total_pnls = []
        
        for entry_type in categories:
            stats = entry_stats.get(entry_type, {})
            total = stats['total']
            wins = stats['wins']
            win_rate = (wins / total * 100) if total > 0 else 0
            win_rates.append(win_rate)
            total_pnls.append(stats['pnl'])
        
        fig.add_trace(go.Bar(
            name='Win Rate %',
            x=categories,
            y=win_rates,
            yaxis='y',
            marker_color='lightblue'
        ))
        
        fig.add_trace(go.Bar(
            name='Total P&L ($)',
            x=categories,
            y=total_pnls,
            yaxis='y2',
            marker_color='lightgreen'
        ))
        
        fig.update_layout(
            title='Entry Type Performance Comparison',
            xaxis_title='Entry Type',
            yaxis=dict(
                title='Win Rate (%)',
                range=[0, 100]
            ),
            yaxis2=dict(
                title='P&L ($)',
                overlaying='y',
                side='right'
            ),
            barmode='group'
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.header("💼 Recent Trades")
        
        # Get recent trades
        recent_trades = tracker.get_recent_trades(days=30)
        
        if recent_trades:
            # Convert to DataFrame for display
            trades_data = []
            for trade in recent_trades:
                trades_data.append({
                    "Symbol": trade.symbol,
                    "Entry Type": trade.entry_type,
                    "Signal": trade.signal_type,
                    "Entry Price": f"${trade.entry_price:.2f}",
                    "Exit Price": f"${trade.exit_price:.2f}" if trade.exit_price else "Open",
                    "Leverage": f"{trade.leverage:.1f}x",
                    "Result": trade.result.value if trade.result else "Open",
                    "P&L": f"${trade.pnl:.2f}" if trade.pnl else "$0.00",
                    "Entry Time": trade.entry_time.strftime("%Y-%m-%d %H:%M"),
                    "Exit Time": trade.exit_time.strftime("%Y-%m-%d %H:%M") if trade.exit_time else "-"
                })
            
            df_trades = pd.DataFrame(trades_data)
            
            # Color coding for results
            def highlight_results(val):
                if val == "WIN":
                    return 'background-color: #d4edda'
                elif val == "LOSS":
                    return 'background-color: #f8d7da'
                elif val == "BREAKEVEN":
                    return 'background-color: #fff3cd'
                return ''
            
            styled_df = df_trades.style.applymap(highlight_results, subset=['Result'])
            st.dataframe(styled_df, use_container_width=True)
            
        else:
            st.info("No recent trades found.")
    
    with tab3:
        st.header("📈 Performance Metrics")
        
        # Time series of P&L
        st.subheader("📊 P&L Over Time")
        
        # This would require historical P&L data
        # For now, show a mock chart
        dates = pd.date_range(start=datetime.now() - timedelta(days=30), end=datetime.now(), freq='D')
        cumulative_pnl = [100 * i + (i % 3 - 1) * 20 for i in range(len(dates))]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=cumulative_pnl,
            mode='lines+markers',
            name='Cumulative P&L',
            line=dict(color='blue', width=2)
        ))
        
        fig.update_layout(
            title='Cumulative P&L - Last 30 Days',
            xaxis_title='Date',
            yaxis_title='P&L ($)'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Drawdown chart
        st.subheader("📉 Drawdown Analysis")
        
        # Calculate drawdown from cumulative P&L
        peak = cumulative_pnl[0]
        drawdowns = []
        for pnl in cumulative_pnl:
            peak = max(peak, pnl)
            drawdown = (peak - pnl) / peak * 100 if peak > 0 else 0
            drawdowns.append(drawdown)
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=drawdowns,
            mode='lines+markers',
            name='Drawdown %',
            fill='tonexty',
            line=dict(color='red', width=2)
        ))
        
        fig.update_layout(
            title='Drawdown Over Time',
            xaxis_title='Date',
            yaxis_title='Drawdown (%)'
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    with tab4:
        st.header("🎯 Entry Analysis")
        
        # Entry type distribution
        st.subheader("📊 Entry Type Distribution")
        
        entry_counts = {k: v['total'] for k, v in entry_stats.items()}
        
        fig = px.pie(
            values=list(entry_counts.values()),
            names=list(entry_counts.keys()),
            title="Distribution of Entry Types"
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Entry quality metrics
        st.subheader("📋 Entry Quality Metrics")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Type A (High Confidence)**")
            if entry_stats.get('A', {}).get('total', 0) > 0:
                a_stats = entry_stats['A']
                st.metric("Total Trades", a_stats['total'])
                st.metric("Win Rate", f"{(a_stats['wins']/a_stats['total']*100):.1f}%")
                st.metric("Total P&L", f"${a_stats['pnl']:.2f}")
            else:
                st.info("No Type A trades yet")
        
        with col2:
            st.markdown("**Type B (Medium Confidence)**")
            if entry_stats.get('B', {}).get('total', 0) > 0:
                b_stats = entry_stats['B']
                st.metric("Total Trades", b_stats['total'])
                st.metric("Win Rate", f"{(b_stats['wins']/b_stats['total']*100):.1f}%")
                st.metric("Total P&L", f"${b_stats['pnl']:.2f}")
            else:
                st.info("No Type B trades yet")
        
        # Type C metrics
        st.markdown("**Type C (Low Confidence)**")
        if entry_stats.get('C', {}).get('total', 0) > 0:
            c_stats = entry_stats['C']
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Trades", c_stats['total'])
            with col2:
                st.metric("Win Rate", f"{(c_stats['wins']/c_stats['total']*100):.1f}%")
            with col3:
                st.metric("Total P&L", f"${c_stats['pnl']:.2f}")
        else:
            st.info("No Type C trades yet")
    
    with tab5:
        st.header("⚙️ Strategy Configuration")
        
        st.subheader("Current Settings")
        
        # Display current configuration (would load from actual strategy)
        config_data = {
            "Risk Management": {
                "Max Risk per Trade": "2%",
                "Daily Loss Limit": "5%",
                "High Risk Leverage": "2.5x",
                "Medium Risk Leverage": "6.0x",
                "Low Risk Leverage": "9.0x"
            },
            "Entry Types": {
                "Type A Risk": "1.5%",
                "Type B Risk": "1.2%", 
                "Type C Risk": "0.5%"
            },
            "Technical Indicators": {
                "EMA Fast": "20",
                "EMA Slow": "50",
                "RSI Period": "14",
                "MACD Fast": "12",
                "MACD Slow": "26",
                "Volume MA Period": "20"
            }
        }
        
        for category, settings in config_data.items():
            with st.expander(f"📋 {category}"):
                for setting, value in settings.items():
                    st.write(f"**{setting}:** {value}")
        
        # Strategy status
        st.subheader("🟢 Strategy Status")
        
        status_col1, status_col2 = st.columns(2)
        
        with status_col1:
            st.success("✅ Strategy is Active")
            st.info("🔄 Last signal: 2 hours ago")
            st.success("✅ All systems operational")
        
        with status_col2:
            st.info("📊 Market conditions: Normal")
            st.warning("⚠️ Daily loss: 2.3% (limit: 5%)")
            st.success("✅ No consecutive losses")

if __name__ == "__main__":
    main()