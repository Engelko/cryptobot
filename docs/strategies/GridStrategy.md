# GridStrategy (GridMaster Improved)

## 1. Description
The **GridMasterImproved** strategy implements a Grid Trading system. It places buy and sell orders at regular intervals within a defined price range. It aims to profit from market volatility by "buying low and selling high" within the grid. It includes dynamic range calculation based on ATR.

## 2. Working Principle
1.  **Initialization:** The strategy defines a trading range (Upper/Lower Price) and divides it into $N$ levels.
2.  **Range Setup:**
    *   **Manual:** Defined in config (`lower_price`, `upper_price`).
    *   **Dynamic:** Calculated using ATR around current price ($Price \pm \sigma \times ATR$).
3.  **Order Placement:**
    *   When initialized, it conceptually places orders at every level.
    *   If Price < Level -> Place SELL (actually, this logic depends on position, but in this implementation, it sets signals relative to current price).
    *   *Implementation Note:* The strategy emits signals to place limit orders.
4.  **Execution:**
    *   When a level is hit (Filled):
        *   If a BUY order fills at Level $X$, the strategy immediately places a SELL order at Level $X+1$ (Take Profit).
        *   If a SELL order fills at Level $Y$, the strategy places a BUY order at Level $Y-1$.

## 3. Mathematical Logic
*   **Grid Step Size:**
    $$ Step = \frac{Upper - Lower}{Levels} $$
*   **Grid Levels:**
    $$ Price_i = Lower + (i \times Step) $$
    where $i = 0 ... Levels$

*   **Dynamic Range (if used):**
    $$ Lower = Price_{curr} - (2.0 \times ATR) $$
    $$ Upper = Price_{curr} + (2.0 \times ATR) $$

### Logic Flow
*   **Wait for Price to enter range.**
*   **On Order Fill:**
    *   Map `order_id` to `grid_index`.
    *   Calculate Target Index (Index + 1 for Buys, Index - 1 for Sells).
    *   Emit Signal for the counter-order.

## 4. Implementation Details
*   **File:** `antigravity/strategies/grid_improved.py`
*   **Class:** `GridMasterImproved`
*   **State Management:** Maintains `grid_states` dictionary per symbol containing levels, active orders, and initialization status. Persistence via `save_state()`.
*   **Config Class:** `GridConfig`
    *   `lower_price`, `upper_price`: Manual bounds.
    *   `grid_levels`: Number of grids (default 10).
    *   `amount_per_grid`: Quantity per order.

### Key Methods
*   `set_dynamic_range(...)`: Auto-calculates bounds.
*   `on_market_data(event)`: Handles initialization and places initial grid.
*   `on_order_update(event)`: Crucial method. Detects fills and triggers the "Flip" (placing the counter-order).
