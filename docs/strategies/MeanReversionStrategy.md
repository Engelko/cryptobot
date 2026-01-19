# MeanReversionStrategy (BollingerRSI Improved)

## 1. Description
This strategy is based on the **Mean Reversion** principle, assuming that prices tend to return to their average. It combines **Bollinger Bands** (to identify overextended price moves) and **RSI** (Relative Strength Index) to confirm oversold/overbought conditions.

## 2. Working Principle
The strategy looks for price reversals at the edges of the Bollinger Bands.
*   **BUY Signal:** Price drops below the Lower Bollinger Band AND RSI indicates "Oversold".
*   **SELL Signal:** Price rises above the Upper Bollinger Band AND RSI indicates "Overbought".

It includes a **Cooldown** mechanism to prevent duplicate signals in short succession.

## 3. Mathematical Logic
The strategy uses the following indicators:

1.  **Bollinger Bands:**
    *   $Middle Band = SMA(Close, 20)$
    *   $Upper Band = Middle Band + (2 \times StdDev)$
    *   $Lower Band = Middle Band - (2 \times StdDev)$
    *   Period: 20, StdDev: 2.0

2.  **RSI (Relative Strength Index):**
    *   Period: 14
    *   Oversold Threshold: 30
    *   Overbought Threshold: 70

### Signal Conditions
*   **BUY Signal:**
    *   $Price[curr] < Lower Band$
    *   $RSI[curr] < 30$

*   **SELL Signal:**
    *   $Price[curr] > Upper Band$
    *   $RSI[curr] > 70$

### Filters
*   **Cooldown:** A new signal for the same symbol cannot be generated within 300 seconds (5 minutes) of the previous one.

## 4. Implementation Details
*   **File:** `antigravity/strategies/mean_reversion_improved.py`
*   **Class:** `BollingerRSIImproved`
*   **Libraries:** `pandas`, `ta`
*   **Config Class:** `MeanReversionConfig`
    *   `rsi_period`: 14
    *   `bb_period`: 20
    *   `bb_std`: 2.0
    *   `rsi_oversold`: 30
    *   `rsi_overbought`: 70

### Key Methods
*   `on_market_data(event)`: Processes `KlineEvent`, updates buffers, and calculates indicators.
*   `generate_signal(...)`: Checks if price is outside bands and RSI thresholds are met, enforcing cooldown.
