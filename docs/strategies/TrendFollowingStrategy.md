# TrendFollowingStrategy (GoldenCross Improved)

## 1. Description
This strategy implements a **Trend Following** logic based on the "Golden Cross" and "Death Cross" concepts, enhanced with an **ADX (Average Directional Index)** filter to avoid trading in sideways markets.

## 2. Working Principle
The strategy monitors Moving Averages (MA) of the price.
*   **Golden Cross (BUY):** When the Fast SMA crosses *above* the Slow SMA.
*   **Death Cross (SELL):** When the Fast SMA crosses *below* the Slow SMA.

To improve reliability, the signal is only valid if the market is trending strongly, which is determined by the ADX indicator.

## 3. Mathematical Logic
The strategy relies on the following indicators calculated over `Kline` data:

1.  **Fast SMA (Simple Moving Average):**
    $$ SMA_{fast} = \frac{\sum_{i=1}^{N} Close_i}{N} $$
    *   Default Period ($N$): 50

2.  **Slow SMA:**
    $$ SMA_{slow} = \frac{\sum_{i=1}^{M} Close_i}{M} $$
    *   Default Period ($M$): 200

3.  **ADX (Average Directional Index):**
    *   Period: 14
    *   Threshold: 25

### Signal Conditions
*   **BUY Signal:**
    *   $SMA_{fast}[prev] \le SMA_{slow}[prev]$ AND $SMA_{fast}[curr] > SMA_{slow}[curr]$ (Crossover)
    *   $Price[curr] > SMA_{fast}[curr]$ (Price Confirmation)
    *   $ADX[curr] > 25$ (Trend Strength Confirmation)

*   **SELL Signal:**
    *   $SMA_{fast}[prev] \ge SMA_{slow}[prev]$ AND $SMA_{fast}[curr] < SMA_{slow}[curr]$ (Crossover)
    *   $Price[curr] < SMA_{fast}[curr]$ (Price Confirmation)
    *   $ADX[curr] > 25$ (Trend Strength Confirmation)

## 4. Implementation Details
*   **File:** `antigravity/strategies/trend_improved.py`
*   **Class:** `GoldenCrossImproved`
*   **Libraries:** `pandas`, `ta` (Technical Analysis Library)
*   **Config Class:** `TrendConfig`
    *   `fast_period`: 50
    *   `slow_period`: 200
    *   `risk_per_trade`: 0.02 (2%)

### Key Methods
*   `on_market_data(event)`: Accumulates kline data and triggers calculation.
*   `generate_signal(...)`: Evaluates the mathematical logic and returns a signal if conditions are met.
