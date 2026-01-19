# ScalpingStrategy (Stochastic Scalping)

## 1. Description
This strategy is designed for **Scalping**, aiming to profit from small price changes in oscillating markets. It uses the **Stochastic Oscillator** to identify potential turning points.

## 2. Working Principle
The strategy monitors the Stochastic %K and %D lines.
*   **BUY Signal:** %K crosses *above* %D while in the Oversold zone.
*   **SELL Signal:** %K crosses *below* %D while in the Overbought zone.

## 3. Mathematical Logic
1.  **Stochastic Oscillator:**
    *   **%K Line:** Current price relative to the High-Low range over $N$ periods.
    *   **%D Line:** SMA of %K.
    *   K Period: 14
    *   D Period: 3

2.  **Zones:**
    *   Overbought: > 80
    *   Oversold: < 20

### Signal Conditions
*   **BUY Signal:**
    *   $K[prev] < D[prev]$ AND $K[curr] > D[curr]$ (Golden Cross)
    *   $K[curr] < 20$ (Oversold condition)

*   **SELL Signal:**
    *   $K[prev] > D[prev]$ AND $K[curr] < D[curr]$ (Death Cross)
    *   $K[curr] > 80$ (Overbought condition)

## 4. Implementation Details
*   **File:** `antigravity/strategies/scalping.py`
*   **Class:** `ScalpingStrategy`
*   **Libraries:** `pandas`, `ta`
*   **Config Class:** `ScalpingConfig`
    *   `k_period`: 14
    *   `d_period`: 3
    *   `overbought`: 80
    *   `oversold`: 20

### Key Methods
*   `_calculate_signal(symbol)`: Computes Stochastic indicators and checks for crossovers in extreme zones.
