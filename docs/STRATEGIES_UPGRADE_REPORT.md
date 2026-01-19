# Strategies Upgrade Report

## 1. Overview
The trading system has been upgraded to a **Futures-First** architecture with native support for **Market Regimes** and **Risk Management**. The system now filters signals based on the current market environment (Trend vs. Range) and accounts for estimated fees before executing trades.

**Key Improvements:**
*   **Market Regime Detection:** Automatically identifies Trending, Ranging, and Volatile markets.
*   **Strategy Router:** Blocks strategies that are incompatible with the current regime (e.g., Grid in strong trends).
*   **Fee Awareness:** Estimates execution costs (Maker/Taker) and logs them; Risk Manager reserves buffer for fees.
*   **Safety Mechanisms:** "Kill Switch" for Grid Strategy to prevent deep drawdowns.
*   **Unified Execution:** Support for "Linear" (Futures) and "Spot" modes (architecture ready).

## 2. Architecture Upgrades

### Market Regime Detector (`antigravity/market_regime.py`)
*   Uses ADX (Trend Strength), EMA Slope (Direction), and ATR (Volatility).
*   Classifies market into: `TRENDING_UP`, `TRENDING_DOWN`, `RANGING`, `VOLATILE`.

### Strategy Router (`antigravity/router.py`)
*   Acts as a gatekeeper for signals.
*   **Trend Strategies:** Only allowed in `TRENDING` regimes. Counter-trend signals blocked.
*   **Grid Strategies:** Only allowed in `RANGING` regimes. Blocked if ADX > 25.
*   **Volatility Strategies:** Allowed in `VOLATILE` or Strong Trend.

### Risk & Fees (`antigravity/risk.py`, `antigravity/fees.py`)
*   **FeeConfig:** Centralized fee schedule (Default: Bybit Linear Futures 0.02%/0.055%).
*   **RiskManager:** Now reserves 1% of balance as a "Fee Buffer" when calculating max position size.
*   **RealBroker:** Logs estimated fees for every trade.

## 3. Strategy Specific Changes

### Grid Strategy (`GridMasterImproved`)
*   **Critical Upgrade:** Added **Kill Switch**.
*   **Logic:** If price drops 5% below the Grid Lower Limit, the strategy triggers a `SELL` signal to close all positions.
*   **Why:** Prevents "holding the bag" in a crashing market, which is the #1 killer of Grid bots.
*   **Regime:** Restricted to `RANGING` markets by the Router.

### Trend Following (`GoldenCrossImproved`)
*   **Upgrade:** Added Dynamic **Stop Loss** and **Take Profit**.
*   **Logic:**
    *   Stop Loss: 2.0 * ATR from entry.
    *   Take Profit: 4.0 * ATR from entry (Risk:Reward 1:2).
*   **Why:** Protects capital during false breakouts and secures profits in strong trends.
*   **Regime:** Restricted to `TRENDING` markets by the Router.

### Other Strategies
*   All strategies now benefit from the global **Risk Manager** checks (Max Daily Loss, Max Position Size).
*   All strategies are subject to **Fee Estimation** in the execution layer.

## 4. Practical Recommendations

### Recommended Combinations

**1. The "All-Weather" Portfolio:**
*   **Active:** `TrendFollowing` + `MeanReversion` (or `Grid`)
*   **Why:** The Strategy Router will automatically toggle between them.
    *   When ADX > 25: Trend Following is active, Grid is blocked.
    *   When ADX < 20: Grid is active, Trend Following is blocked.
*   **Risk:** Ensure `MAX_POSITION_SIZE` allows for one strategy to be fully invested.

**2. Conservative Growth:**
*   **Active:** `TrendFollowing` only.
*   **Why:** Trend following has the highest expectancy in crypto. The new Stop Loss protects against chop.

**3. Cash Flow (High Risk):**
*   **Active:** `GridMasterImproved`.
*   **Condition:** Only enable on stable pairs (e.g., ADAUSDT, XRPUSDT) during known ranging periods.
*   **Safety:** The new Kill Switch limits catastrophic loss.

### Bybit Testnet Setup
*   **Fees:** Configured for Standard Non-VIP (0.055% Taker).
*   **Leverage:** Logic supports dynamic leverage (default 1x if not specified).
*   **Mode:** Defaults to `linear` (USDT Perpetual).

## 5. Verification

To verify the upgrades:
1.  **Regime Detection:** Run `python verify_fix.py` (or similar script) and check logs for `market_regime` entries.
2.  **Router:** Attempt to run Grid in a Trending market (simulate high ADX) and verify `signal_rejected_by_router` log.
3.  **Kill Switch:** Manually manipulate price in a test script below Grid Lower Limit and verify `Grid Kill Switch` signal.
