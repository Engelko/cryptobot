# DynamicRiskLeverageStrategy

## 1. Description
This is an advanced strategy that does not rely on a single indicator but performs a comprehensive **Market Analysis** to determine the entry type, trend direction, and risk parameters. It dynamically adjusts the **Leverage** and **Position Size** based on the confidence score of the setup.

## 2. Working Principle
The strategy aggregates data from Trend, Support/Resistance, Volume, and Technical Indicators (RSI, MACD) to calculate a "Score".
*   **Score Calculation:** Points are added for bullish factors and subtracted for bearish factors.
*   **Entry Types:**
    *   **Type A (High Confidence):** Score $\ge 6$. Uses High Leverage (e.g., 2.5x - 9x depending on config), Higher Risk %.
    *   **Type B (Medium Confidence):** Score $\ge 2$. Moderate Leverage/Risk.
    *   **Type C (Weak Confidence):** Score $\ge -1$. Low Leverage/Risk.

## 3. Mathematical Logic
### Components Analysis
1.  **Trend:**
    *   Analyzes Fast/Slow EMA relationship and Price position.
    *   Calculates `Trend Strength` (0-1).
2.  **Levels:**
    *   Finds Support/Resistance using local swing highs/lows.
    *   Scores based on distance to support (Buy) or resistance (Sell).
3.  **Volume:**
    *   Compares current volume to Volume MA.
4.  **Indicators:**
    *   RSI Zones (Neutral is preferred for trend following entries).
    *   MACD Cross status.

### Risk & Sizing
*   **Position Sizing:**
    $$ Qty = \frac{MaxPosSize \times Risk\%}{Price \times StopDist\%} $$
    *   *Note:* The quantity is clamped to `MaxPosSize` and scaled by available balance.
*   **Stop Loss:** $1.5 \times ATR$
*   **Take Profit:** Dynamic levels (1.5R, 3R, 5R) based on Entry Type.

## 4. Implementation Details
*   **File:** `antigravity/strategies/dynamic_risk_leverage.py`
*   **Class:** `DynamicRiskLeverageStrategy`
*   **Config Class:** `DynamicRiskLeverageConfig`
    *   Defines leverage tiers (`high_risk_leverage`, etc.) and risk percentages (`type_a_risk`, etc.).

### Key Methods
*   `_analyze_market(symbol)`: The brain of the strategy. Returns a `MarketAnalysis` object containing the score and recommendation.
*   `_determine_entry_type(...)`: Maps the analysis score to Type A/B/C.
*   `_generate_signal(...)`: Converts the analysis into a trading `Signal` with precise Stop Loss, Take Profit, and Quantity.
