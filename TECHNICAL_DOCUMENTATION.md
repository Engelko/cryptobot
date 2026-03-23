# Antigravity Crypto Trading Bot - Technical Documentation

## 1. System Overview

### 1.1 Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                     │
├──────────────┬──────────────┬──────────────┬──────────────┤
│   Engine     │  Dashboard   │  Optimizer   │ Settings API │
│   (main.py)  │  (Streamlit) │ (optimizer)  │  (FastAPI)   │
│   Port: N/A  │  Port: 8501  │  Port: N/A   │  Port: 8080  │
└──────────────┴──────────────┴──────────────┴──────────────┘
                          │
                    ┌─────┴─────┐
                    │  SQLite   │
                    │  Database │
                    │ storage/  │
                    └───────────┘
```

### 1.2 Core Components

| Component | Purpose | File |
|-----------|---------|------|
| **Engine** | Main trading logic, strategy execution | `main.py` |
| **Dashboard** | Web UI for monitoring and configuration | `dashboard.py` |
| **Optimizer** | Strategy parameter optimization | `optimizer.py` |
| **Settings API** | REST API for profile management | `settings_api.py` |
| **Risk Manager** | Position sizing, stop-loss, daily limits | `antigravity/risk.py` |
| **Execution** | Order placement via Bybit API | `antigravity/execution.py` |
| **Router** | Strategy signal filtering by market regime | `antigravity/router.py` |

---

## 2. Trading Strategies

### 2.1 Active Strategies (ENABLED)

#### GoldenCross (Trend Following)
- **File**: `antigravity/strategies/trend_improved.py`
- **Logic**: Fast SMA (8) crosses Slow SMA (40) with ADX > 20
- **Stop Loss**: Dynamic, based on 2x ATR
- **Take Profit**: 4x ATR (1:2 Risk/Reward)
- **Risk**: 1% per trade (strategies.yaml)
- **Performance**: 2.8% win rate (poor - position size reduced)
- **Symbols**: BTC, ETH, SOL, ADA, DOGE

#### BollingerRSI (Mean Reversion)
- **File**: `antigravity/strategies/mean_reversion_improved.py`
- **Logic**: Price touches Bollinger Bands + RSI confirmation
- **Filters**: ADX ≥ 15 to avoid ranging markets
- **Risk**: 2% per trade
- **Performance**: 4.1% win rate, Risk/Reward 172:1

#### BBSqueeze (Volatility Breakout)
- **File**: `antigravity/strategies/bb_squeeze.py`
- **Logic**: Bollinger Bands squeeze + momentum
- **Risk**: 2% per trade
- **Performance**: 25% win rate, avg profit $2.00

#### DynamicRiskLeverage
- **File**: `antigravity/strategies/dynamic_risk_leverage.py`
- **Logic**: Multi-timeframe analysis with support/resistance
- **Risk**: Variable based on market conditions (0.5% - 2%)
- **Performance**: 33.3% win rate, Risk/Reward 1.73:1

### 2.2 Disabled Strategies

| Strategy | Status | Reason |
|----------|--------|--------|
| ATRBreakout | ❌ DISABLED | 0% win rate, -$35.25 total loss |
| GridMaster | ❌ DISABLED | High complexity, poor testnet performance |
| Scalping | ❌ DISABLED | Low profitability |

---

## 3. Risk Management System

### 3.1 Cascade Protection Architecture

```
Level 1: Position Stop Loss (-2% per trade)
    ↓
Level 2: Trailing Stop (activates at +2.5% profit)
    ↓
Level 3: Daily Loss Limit ($100 testnet / $20 mainnet)
    ↓
Level 4: Recovery Mode (Equity < 80% → Spot only)
    ↓
Level 5: Emergency Stop (Equity < 50% → Full halt)
```

### 3.2 Position Sizing Formula

```python
target_size = min(
    balance * risk_per_trade,           # Risk-based
    max_position_size,                   # Absolute limit
    daily_loss_left / stop_loss_pct      # Daily budget
)
```

### 3.3 Key Risk Parameters

| Parameter | Testnet | Mainnet Conservative | Mainnet Aggressive |
|-----------|---------|---------------------|-------------------|
| Max Daily Loss | $100 | $20 | $50 |
| Max Position Size | $100 | $30 | $75 |
| Max Single Trade Loss | $15 | $10 | $15 |
| Stop Loss | 2% | 2% | 2.5% |
| Take Profit | 6% | 6% | 6% |
| Max Leverage | 2x | 1.5x | 3x |
| Risk per Trade | 1% | 1% | 1.5% |

### 3.4 Blacklists

**Symbol Blacklist** (hardcoded in `risk.py`):
- XRPUSDT: Systematic losses (-$60.79)

**Session Blacklist** (UTC hours):
- Testnet: [16, 17, 18, 19, 20, 21, 22, 23] (American session)
- Mainnet Conservative: [16-23]
- Mainnet Aggressive: [17-22]

---

## 4. Trading Profiles System

### 4.1 Profile Structure

Located in: `antigravity/profiles.py`

```python
@dataclass
class TradingProfile:
    name: str                          # Profile identifier
    is_testnet: bool                   # Testnet or mainnet
    
    # Risk Parameters
    max_spread: float                  # Max allowed spread (10% testnet)
    max_leverage: float                # Max leverage cap
    max_daily_loss: float              # Daily loss limit
    max_position_size: float           # Max $ per position
    max_single_trade_loss: float       # Max loss per trade
    stop_loss_pct: float               # SL percentage
    take_profit_pct: float             # TP percentage
    
    # Time Filters
    session_blacklist: list            # Blocked trading hours
    min_hold_time: int                 # Min seconds before SL
    cooldown_after_loss: int           # Seconds after loss
    
    # Feature Flags
    enable_spread_check: bool          # Check orderbook spread
    spread_multiplier: float           # Multiplier for testnet
    enable_spot_mode_for_volatile: bool # Convert futures to spot
    enable_regime_filter: bool         # Filter by market regime
```

### 4.2 Profile Switching

**Via Web UI**:
1. Open http://localhost:8501
2. Go to Settings tab
3. Select profile from dropdown
4. Click "Применить профиль"
5. Bot restarts automatically in 5 seconds

**Via API**:
```bash
curl -X POST http://localhost:8080/api/profile/switch \
  -H "Content-Type: application/json" \
  -d '{"profile": "mainnet_conservative", "restart": true}'
```

---

## 5. Database Schema

### 5.1 Tables

**trades**:
```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    symbol VARCHAR,
    side VARCHAR,
    price FLOAT,
    quantity FLOAT,
    value FLOAT,
    pnl FLOAT,
    strategy VARCHAR,
    execution_type VARCHAR,
    created_at DATETIME
);
```

**signals**:
```sql
CREATE TABLE signals (
    id INTEGER PRIMARY KEY,
    strategy VARCHAR,
    symbol VARCHAR,
    type VARCHAR,
    price FLOAT,
    reason TEXT,
    created_at DATETIME
);
```

**market_regime**:
```sql
CREATE TABLE market_regime (
    symbol VARCHAR PRIMARY KEY,
    regime VARCHAR,  -- TRENDING_UP, TRENDING_DOWN, RANGING, VOLATILE
    adx FLOAT,
    volatility FLOAT,
    updated_at DATETIME
);
```

### 5.2 Key Metrics Queries

**Daily PnL**:
```sql
SELECT date(created_at), SUM(pnl), COUNT(*)
FROM trades
GROUP BY date(created_at);
```

**Strategy Performance**:
```sql
SELECT strategy, 
       SUM(pnl) as total_pnl,
       AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
       AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss,
       100.0 * SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) / COUNT(*) as win_rate
FROM trades
GROUP BY strategy;
```

---

## 6. Execution Flow

### 6.1 Signal Generation → Order Execution

```
1. Strategy generates signal (GoldenCross, BollingerRSI, etc.)
   ↓
2. Strategy Router filters by market regime
   - Grid: Only RANGING markets
   - Trend: Only TRENDING_UP/DOWN or VOLATILE
   - Mean Reversion: Block against strong trend
   ↓
3. Risk Manager validates:
   - Blacklist check
   - Session filter (UTC hour blacklist)
   - Daily loss limit
   - Position sizing
   - Single trade loss limit
   ↓
4. Order Execution:
   - Liquidity check (spread, depth)
   - Set leverage
   - Place market order
   - Set stop-loss
   - Create take-profit orders
   ↓
5. Position Monitoring:
   - Track unrealized PnL
   - Cascade stop management
   - Emergency exit if needed
```

### 6.2 Stop Loss Logic

**Critical Fix Applied** (commit c50f5db):
```python
# OLD (BUG): Risk Manager overwrites strategy SL
signal.stop_loss = signal.price * (1 - sl_pct)

# NEW (FIXED): Preserve strategy ATR-based SL
if not hasattr(signal, 'stop_loss') or signal.stop_loss <= 0:
    signal.stop_loss = signal.price * (1 - sl_pct)
```

GoldenCross sets SL at `price - 2*ATR` (below entry for BUY).
Risk Manager only sets SL if strategy didn't provide one.

---

## 7. Configuration Files

### 7.1 .env (Environment Variables)

```bash
# Exchange
BYBIT_API_KEY=your_key_here
BYBIT_API_SECRET=your_secret_here
BYBIT_TESTNET=True  # or False for mainnet

# Trading
TRADING_SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT","ADAUSDT","DOGEUSDT"]
ACTIVE_STRATEGIES=["GoldenCross","BollingerRSI","BBSqueeze","DynamicRiskLeverage"]

# Risk Limits
MAX_LEVERAGE=2.0
MAX_DAILY_LOSS=100.0
MAX_POSITION_SIZE=100.0
MAX_SINGLE_TRADE_LOSS=15.0
STOP_LOSS_PCT=0.02
TAKE_PROFIT_PCT=0.06

# Database
DATABASE_URL=sqlite:///storage/data.db
```

### 7.2 strategies.yaml

```yaml
strategies:
  trend_following:
    name: GoldenCross
    enabled: true
    fast_period: 8
    slow_period: 40
    leverage: 1.0
    risk_per_trade: 0.01  # Reduced from 0.02
    
  mean_reversion:
    name: BollingerRSI
    enabled: true
    bb_period: 20
    bb_std: 2.0
    rsi_period: 10
    rsi_overbought: 65
    rsi_oversold: 25
    leverage: 1.0
    risk_per_trade: 0.02
    
  volatility_breakout:
    name: ATRBreakout
    enabled: false  # DISABLED - poor performance
```

### 7.3 storage/current_profile.json

```json
{"profile": "testnet"}
```

Valid values: `testnet`, `mainnet_conservative`, `mainnet_aggressive`

---

## 8. Docker Setup

### 8.1 Services

**docker-compose.yml**:
```yaml
services:
  engine:
    build: .
    container_name: antigravity-engine
    command: python main.py
    volumes:
      - ./storage:/app/storage
      - ./.env:/app/.env
      - ./strategies.yaml:/app/strategies.yaml
      - ./antigravity:/app/antigravity  # Hot reload
      
  dashboard:
    build: .
    container_name: antigravity-dashboard
    command: streamlit run dashboard.py
    ports:
      - "8501:8501"
      
  settings-api:
    build: .
    container_name: antigravity-settings-api
    command: python settings_api.py
    ports:
      - "8080:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # Container control
```

### 8.2 Useful Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker logs -f antigravity-engine
docker logs -f antigravity-dashboard

# Restart specific service
docker-compose restart engine

# Full rebuild
docker-compose down && docker-compose up -d --build

# Access database
python3 -c "import sqlite3; conn = sqlite3.connect('storage/data.db'); ..."
```

---

## 9. Known Issues & Solutions

### 9.1 Fixed Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **SL above entry price** | Risk Manager overwrites strategy SL | Preserve strategy SL if set (commit c50f5db) |
| **Spread 27% rejected** | Testnet orderbook anomalies | Apply spread_multiplier=10.0 for testnet |
| **QTY=0 for ETH** | Testnet price formatting bug | Add minimum qty enforcement per symbol |
| **Only ADAUSDT trades** | Session filter + regime filter blocking | Disable regime_filter for testnet |

### 9.2 ETHUSDT Specific

**Testnet Issue**: Price formatting shows ETH at $144,709 (should be ~$2,700)
- **Impact**: Position sizing calculates QTY=0
- **Solution**: Added min_qty enforcement (0.01 ETH minimum)
- **Mainnet**: Should work normally with real prices

**Performance**: ETH shows -$41.03 total loss
- Main losses from ATRBreakout (now disabled)
- Keep monitoring in mainnet before blacklisting

### 9.3 Current Warnings

```
filter_sideways_market  # DynamicRiskLeverage filtering non-trending markets
[EXECUTION ERROR] [10001] StopLoss set for Buy position should lower than base_price
# ^ Fixed in latest commit - SL now set correctly below entry
```

---

## 10. API Reference

### 10.1 Settings API Endpoints

Base URL: `http://localhost:8080`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/profiles` | GET | List all available profiles |
| `/api/profile/current` | GET | Get current active profile |
| `/api/profile/switch` | POST | Switch profile with auto-restart |
| `/api/bot/status` | GET | Get container statuses |
| `/api/bot/restart` | POST | Restart all containers |

### 10.2 Example API Calls

```bash
# Get all profiles
curl http://localhost:8080/api/profiles

# Switch to mainnet
curl -X POST http://localhost:8080/api/profile/switch \
  -H "Content-Type: application/json" \
  -d '{"profile": "mainnet_conservative", "restart": true}'

# Check status
curl http://localhost:8080/api/bot/status
```

---

## 11. Performance Analysis

### 11.1 Current Stats (Last 7 Days)

```
Total PnL: -$47.55 (292 trades)
Win Rate: 16.4%
Daily Average: -$6.79

By Strategy:
- ATRBreakout: -$35.25 (DISABLED)
- RiskManager_Emergency: -$24.92
- GoldenCross: -$4.16 (position size reduced)
- BollingerRSI: +$9.61
- BBSqueeze: +$3.98

By Symbol:
- ETHUSDT: -$41.03 (ATRBreakout losses)
- SOLUSDT: -$14.46
- XRPUSDT: +$0.82
- DOGEUSDT: +$1.81
- ADAUSDT: +$5.32

By Session (UTC):
- American (16-24): -$57.76 (NOW BLOCKED)
- European (8-16): -$32.58
- Asian (0-8): -$28.96
```

### 11.2 Risk/Reward Analysis

| Strategy | Win Rate | Avg Win | Avg Loss | R/R Ratio |
|----------|----------|---------|----------|-----------|
| RiskManager_Emergency | 40.9% | $0.71 | $2.35 | 0.30 ❌ |
| GoldenCross | 2.8% | $1.30 | $4.68 | 0.28 ❌ |
| DynamicRiskLeverage | 33.3% | $0.93 | $0.54 | 1.73 ✅ |
| BollingerRSI | 4.1% | $3.21 | $0.02 | 172.12 ✅ |
| BBSqueeze | 25.0% | $1.99 | N/A | N/A |

---

## 12. Development Guidelines

### 12.1 Adding New Strategy

1. Create file in `antigravity/strategies/`
2. Inherit from `BaseStrategy`
3. Implement `generate_signal()` method
4. Add to `strategies.yaml`
5. Add to `ACTIVE_STRATEGIES` in `.env`
6. Register in `main.py` strategy loader

### 12.2 Modifying Risk Parameters

1. Edit `antigravity/profiles.py`
2. Update all three profiles (testnet, mainnet_conservative, mainnet_aggressive)
3. Restart containers: `docker-compose restart`
4. Changes take effect immediately (no rebuild needed)

### 12.3 Testing Changes

```bash
# Run in testnet first
BYBIT_TESTNET=True

# Monitor logs
docker logs -f antigravity-engine | grep -E "signal|trade|pnl"

# Check recent trades
python3 -c "
import sqlite3
conn = sqlite3.connect('storage/data.db')
cursor = conn.execute('SELECT * FROM trades ORDER BY created_at DESC LIMIT 10')
for row in cursor:
    print(row)
"
```

---

## 13. Troubleshooting

### 13.1 Bot not trading

1. Check if session is blocked: `current_hour in profile.session_blacklist`
2. Check spread check: `spread > max_spread * spread_multiplier`
3. Check regime filter: `profile.enable_regime_filter`
4. Check daily loss limit: `current_daily_loss >= max_daily_loss`
5. Check strategy signals: `docker logs antigravity-engine | grep signal`

### 13.2 Orders rejected

```
[EXECUTION ERROR] [10001] StopLoss set for Buy position should lower than base_price
→ Fixed: SL now calculated correctly below entry price

[EXECUTION ERROR] [30209] order price is lower than minimum
→ Price precision issue - check _format_price() for symbol

[REJECTED: Risk Limit] Daily loss limit reached
→ Wait for UTC reset or increase MAX_DAILY_LOSS
```

### 13.3 Emergency Procedures

**Stop all trading immediately**:
```bash
docker-compose down
```

**Close all positions manually**:
```python
# In settings_api.py or separate script
from antigravity.client import BybitClient
client = BybitClient()
# Get positions and close them
```

---

## 14. Version History

| Date | Commit | Changes |
|------|--------|---------|
| 2026-02-18 | c50f5db | Fix SL overwrite bug, update profile params, block American session |
| 2026-02-18 | 246534b | Add Testnet/Mainnet profile system with web UI |
| 2026-02-17 | 0793d10 | Security hardening and risk management improvements |

---

## 15. Contact & Support

- **Repository**: https://github.com/Engelko/cryptobot
- **Dashboard**: http://localhost:8501
- **Settings API**: http://localhost:8080
- **Logs**: `docker logs antigravity-engine`

---

**Last Updated**: 2026-02-18  
**Version**: 2.0  
**Profile**: Testnet (ready for Mainnet Conservative)
