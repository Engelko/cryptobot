# Project Antigravity 🚀

Algorithmic Trading Engine for Bybit (V5 API).

## Architecture
- **Engine**: Asyncio-based core with Event Bus (`event.py`, `engine.py`).
- **Strategies**: MACD, RSI (`strategies/`).
- **AI Copilot**: LLM-based Market Sentiment Analysis.
- **Risk Manager**: Hard limits on Daily Loss and Position Size.
- **Dashboard**: Streamlit UI for monitoring.
- **Execution**: Paper Trading (Sim Mode) enabled by default.

## Usage

### 1. Configuration
Ensure `.env` is present with API Keys and Settings.

### 2. Run with Docker
\`\`\`bash
docker-compose up -d --build
\`\`\`

### 3. Access Dashboard
Navigate to \`http://<SERVER_IP>:8501\`.

## Development
- Logs: \`tail -f audit.log\`
- Manual Run: \`python main.py\`
