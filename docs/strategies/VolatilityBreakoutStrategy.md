# VolatilityBreakoutStrategy

## 1. Description
This strategy aims to capture explosive moves (breakouts) caused by high volatility. It uses the **ATR (Average True Range)** indicator to define a dynamic channel around the previous closing price. If the price breaks out of this channel, it signals a trend continuation or initiation.

## 2. Working Principle
The strategy calculates a "Breakout Channel" based on volatility.
*   **Upper Bound:** Previous Close + (Multiplier × ATR)
*   **Lower Bound:** Previous Close - (Multiplier × ATR)

*   **BUY Signal:** Price breaks *above* the Upper Bound.
*   **SELL Signal:** Price breaks *below* the Lower Bound.

## 3. Mathematical Logic
1.  **ATR (Average True Range):**
    *   Measures market volatility.
    *   Period: 14 (default)

2.  **Breakout Thresholds:**
    $$ Upper = Close_{prev} + (ATR_{prev} \times Multiplier) $$
    $$ Lower = Close_{prev} - (ATR_{prev} \times Multiplier) $$
    *   Multiplier: 3.0 (default)

### Signal Conditions
*   **BUY Signal:** $Close[curr] > Upper$
*   **SELL Signal:** $Close[curr] < Lower$

## 4. Implementation Details
*   **File:** `antigravity/strategies/volatility.py`
*   **Class:** `VolatilityBreakoutStrategy`
*   **Libraries:** `pandas`, `ta`
*   **Config Class:** `VolatilityConfig`
    *   `atr_period`: 14
    *   `multiplier`: 3.0

### Key Methods
*   `_calculate_signal(symbol)`: Computes ATR, defines bounds, and compares current price to generate signals.
