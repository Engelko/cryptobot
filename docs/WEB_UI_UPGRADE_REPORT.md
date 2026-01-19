# Web UI Upgrade Report

## 1. Overview
The Dashboard (`dashboard.py`) has been completely rewritten to reflect the new "Futures-First" and "Regime-Aware" architecture. It now provides visibility into the AI's decision-making process (Strategy Router), market conditions (Regime Detection), and Risk Management.

## 2. Key Changes

### New Tab Structure
The dashboard is now organized into functional areas:
1.  **Market:** Focuses on *context*. Shows the detected Regime (Trend/Range/Vol) and Price Action.
2.  **Strategies:** The *control center*. List of all 7 strategies with individual toggles and configuration.
3.  **Live Portfolio:** Real-time data from Bybit Futures (Linear).
4.  **Signals:** A log of all generated signals, including those **BLOCKED** by the Strategy Router or Risk Manager (highlighted in red).
5.  **System:** Health checks, Risk State, and Environment info.
6.  **Settings:** Global configuration (API Keys, Risk Limits).
7.  **Diagnostics:** Logs and connection tests.

### Regime & Router Visualization
*   **Market Tab:** Displays the current Regime for each symbol (e.g., `BTCUSDT: TRENDING_UP`).
*   **Signals Tab:** Signals blocked by the Router (e.g., "Grid blocked in Uptrend") are explicitly shown and highlighted, providing transparency into *why* a trade wasn't taken.

### Risk & Fees
*   **Live Portfolio:** Shows Unrealized PnL and Margin Balance.
*   **System:** Displays current Risk State (Daily Loss tracking).

## 3. Usage Guide

### Scenario 1: All-Weather Trading
1.  Go to **Strategies** tab.
2.  Enable `TrendFollowing` AND `MeanReversion`.
3.  **Behavior:**
    *   When Market is `TRENDING`, the Router allows Trend signals and blocks MeanReversion.
    *   When Market is `RANGING`, the Router allows MeanReversion and blocks Trend.
4.  **Monitor:** Check the **Signals** tab to see the Router automatically filtering signals.

### Scenario 2: High Volatility Protection
1.  Enable `ScalpingStrategy`.
2.  **Safety:** If the detected regime switches to `VOLATILE` (High ATR), the strategy will automatically stop generating signals to prevent slippage losses.

### Scenario 3: Manual Override
*   Use the **Settings** tab to change `Trading Symbols` or `Risk Limits` on the fly.
*   Use **Strategies** tab to disable any strategy immediately.

## 4. Verification
To verify the UI:
1.  Run the bot: `python main.py`
2.  Run the dashboard: `streamlit run dashboard.py`
3.  Navigate to **Market** to see the Regime.
4.  Navigate to **Strategies** to toggle strategies.
