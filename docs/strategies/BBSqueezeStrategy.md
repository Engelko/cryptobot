# BBSqueezeStrategy (Bollinger Band Squeeze)

## 1. Description
This strategy identifies periods of low volatility (consolidation) followed by a breakout. It uses the relationship between **Bollinger Bands** and **Keltner Channels** to detect the "Squeeze" state, and **Momentum** to determine the direction of the breakout.

## 2. Working Principle
*   **Squeeze ON:** When the Bollinger Bands (volatility based on StdDev) contract and move *inside* the Keltner Channels (volatility based on ATR). This indicates extremely low volatility.
*   **Squeeze Release (Fire):** When the Bollinger Bands expand and move *outside* the Keltner Channels.
*   **Direction:** Determined by the price momentum (change in price).

## 3. Mathematical Logic
1.  **Bollinger Bands (BB):**
    *   Basis: 20 SMA
    *   Width: $\pm 2.0 \times StdDev$

2.  **Keltner Channels (KC):**
    *   Basis: 20 EMA
    *   Width: $\pm 1.5 \times ATR$

3.  **Momentum:**
    *   $Momentum = Price[curr] - Price[curr - 12]$ (12-period simple momentum)

### Logic Flow
1.  **Check Squeeze:**
    *   $SqueezeOn = (BB_{upper} < KC_{upper})$ AND $(BB_{lower} > KC_{lower})$
2.  **State Tracking:**
    *   If $SqueezeOn$ is True -> Mark state `was_squeezed = True`.
3.  **Signal Fire:**
    *   If `was_squeezed` is True AND $SqueezeOn$ becomes False (The squeeze "breaks"):
        *   If $Momentum > 0$ -> **BUY**
        *   If $Momentum < 0$ -> **SELL**
        *   Reset `was_squeezed = False`.

## 4. Implementation Details
*   **File:** `antigravity/strategies/bb_squeeze.py`
*   **Class:** `BBSqueezeStrategy`
*   **Libraries:** `pandas`, `ta`
*   **Config Class:** `BBSqueezeConfig`
    *   `bb_period`: 20
    *   `bb_std`: 2.0
    *   `keltner_multiplier`: 1.5
    *   `momentum_period`: 12

### Key Methods
*   `_calculate_signal(symbol)`: Manages the squeeze state and triggers signals upon state transition (release).
