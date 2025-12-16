# Project Antigravity (Hummingbot V2 Refactor)

## Overview
This repository contains the refactored "Project Antigravity" trading bot, now built on the **Hummingbot V2 Framework**.

## Architecture
- **Engine**: Hummingbot (Dockerized)
- **Controllers**: Custom Strategy Logic located in `controllers/`
    - `macd_controller.py`: MACD Trend Strategy
    - `rsi_controller.py`: RSI Reversion Strategy
    - `ai_copilot.py`: AI Sentiment Analysis
- **Loader**: `scripts/antigravity_loader.py` initializes the V2 Strategy with these controllers.
- **Dashboard**: Hummingbot Dashboard for monitoring.

## Migration Notes
- The custom `aiohttp` engine has been replaced by Hummingbot's robust `bybit_perpetual` connector.
- Strategies are now V2 Controllers, allowing independent execution and configuration.
- Risk management is handled by Hummingbot's `TripleBarrierConf` and `PositionExecutor`.

## Setup
1. **Configuration**:
   Copy `.env.example` to `.env` and fill in your API keys.
   ```env
   BYBIT_API_KEY=...
   BYBIT_API_SECRET=...
   LLM_API_KEY=...
   ```

2. **Run**:
   ```bash
   docker-compose up -d
   ```

3. **Monitor**:
   Access the dashboard at `http://localhost:8501`.

4. **Management**:
   - To stop: `docker-compose down`
   - To attach to HB console: `docker attach antigravity-engine`
