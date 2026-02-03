-- dashboard_queries.sql
-- Optimized queries for Antigravity Dashboard

-- 1. AI Accuracy by Date (Last 7 days)
-- Calculates average confidence and prediction counts grouped by day
SELECT
    DATE(created_at) as date,
    AVG(confidence) as avg_confidence,
    COUNT(*) as total_predictions
FROM predictions
WHERE created_at >= date('now', '-7 days')
GROUP BY date
ORDER BY date;

-- 2. Strategy Win Rate Heatmap
-- Calculates win rate percentage per strategy and symbol
SELECT
    strategy,
    symbol,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as win_rate,
    COUNT(*) as trade_count
FROM trades
WHERE created_at >= datetime('now', '-7 days')
GROUP BY strategy, symbol;

-- 3. Regime Timeline (15min intervals)
-- Bucketized market regimes for timeline visualization
-- Assumes market_regime_history table exists (to be added)
SELECT
    datetime((strftime('%s', created_at) / 900) * 900, 'unixepoch') as time_bucket,
    symbol,
    regime
FROM market_regime_history
WHERE created_at >= datetime('now', '-24 hours')
ORDER BY time_bucket;

-- 4. Signal Flow Analysis
-- Summarizes how many signals were rejected vs executed
SELECT
    strategy,
    COUNT(*) as total,
    SUM(CASE WHEN reason LIKE '[REJECTED: AI%' THEN 1 ELSE 0 END) as rejected_ai,
    SUM(CASE WHEN reason LIKE '[REJECTED: Risk%' THEN 1 ELSE 0 END) as rejected_risk,
    SUM(CASE WHEN reason LIKE '[REJECTED: Market%' THEN 1 ELSE 0 END) as rejected_router,
    SUM(CASE WHEN reason NOT LIKE '[REJECTED%' THEN 1 ELSE 0 END) as executed
FROM signals
WHERE created_at >= datetime('now', '-48 hours')
GROUP BY strategy;

-- 5. Daily P&L Breakdown (Waterfall)
-- Grouped P&L for the current day
SELECT
    id,
    symbol,
    pnl,
    created_at
FROM trades
WHERE DATE(created_at) = DATE('now')
ORDER BY created_at;
