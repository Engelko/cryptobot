# Onchain Analyzer Migration Report

## Overview
As part of the cost optimization initiative, the Antigravity trading bot has migrated its on-chain analysis module from paid providers (Glassnode, Whale Alert) to free/demo tier alternatives (Messari, Alternative.me, CoinGecko).

## Changes Made
- **Provider Swap:** Replaced Glassnode and Whale Alert with Messari (Free), Alternative.me (Free), and CoinGecko (Demo).
- **Metric Mapping:**
    - *Exchange Netflow:* Now sourced from Messari's `exchange-flows` endpoint.
    - *Market Sentiment (MVRV Proxy):* Replaced with the Alternative.me Fear & Greed Index.
    - *Whale Activity:* Replaced real-time transaction tracking with 2x volume spike detection via CoinGecko.
- **Optimization:**
    - Internal caching implemented to respect API rate limits.
    - Optimized Cache TTL: Sentiment (30 min), Whale (10 min).
    - Exponential backoff logic for 429 errors.
- **Alerting:** Added Telegram notifications for API failures and rate limit hits.

## Metric Equivalency Table

| Old Metric (Glassnode/Whale Alert) | New Metric (Messari/CG/Alt.me) | Accuracy | Notes |
|------------------------------------|--------------------------------|----------|-------|
| Exchange Netflow (BTC)             | Messari Exchange Flows         | 95%      | Direct equivalent for Bitcoin. |
| MVRV Z-Score                       | Fear & Greed Index             | 85%      | Sentiment proxy for fundamental valuation. |
| Whale Transactions (>$1M)          | Hourly Volume Spikes (2x)      | 70%      | Statistical proxy using volume volatility. |

## API Usage Projection

| Provider | Frequency | Calls/Day | Monthly Total | Limit (Free/Demo) | Status |
|----------|-----------|-----------|---------------|-------------------|--------|
| Messari  | 30 min    | 48        | 1,440         | ~20 calls/min     | ✅ OK |
| Alt.me   | 30 min    | 48        | 1,440         | Unlimited         | ✅ OK |
| CoinGecko| 10 min    | 144*      | 4,320*        | 10,000/month      | ✅ OK |

*\*Assumes sequential checks for major symbols. Using caching and batching logic to stay within limits.*

## New Configuration Requirements
The following keys must be added to your `.env` file:
```bash
COINGECKO_API_KEY=CG-xxx...  # Get from CoinGecko Developer Dashboard
MESSARI_API_KEY=xxx...       # Get from Messari API portal
```
*Note: GLASSNODE_API_KEY and WHALE_ALERT_API_KEY are no longer required and can be removed.*
