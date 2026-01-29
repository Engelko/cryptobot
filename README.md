# Antigravity Trading Bot 🚀

A high-performance asynchronous algorithmic trading engine built for Bybit V5 API.

## Features
- **Event-Driven Architecture**: Low latency signal processing.
- **Multi-Strategy Support**: Run MACD, RSI, and ML models concurrently.
- **Risk Management**: Real-time position sizing and drawdown protection.
- **Live Dashboard**: Streamlit-based monitoring UI with Diagnostics.
- **Diagnostics**: Real-time logs, manual order testing, and strategy verification.
- **Multi-Asset**: Supports trading multiple pairs (BTC, ETH, SOL, XRP, ADA, DOGE) simultaneously.

---

## 🇷🇺 Установка и запуск (Ubuntu 22.04 + Docker)

Подробная инструкция по развертыванию бота на чистом сервере Ubuntu 22.04 с использованием Docker Compose.

### Шаг 1: Подготовка сервера

Обновите систему и установите необходимые пакеты (Git, Docker, Docker Compose):

```bash
# Обновление списка пакетов
sudo apt update && sudo apt upgrade -y

# Установка Git, Curl и необходимых утилит
sudo apt install -y git curl ca-certificates gnupg lsb-release

# Установка Docker (официальный скрипт установки)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Добавление текущего пользователя в группу docker (чтобы не писать sudo каждый раз)
sudo usermod -aG docker $USER

# Применение изменений групп (или перезайдите в систему)
newgrp docker
```

### Шаг 2: Установка проекта

Склонируйте репозиторий и перейдите в папку проекта:

```bash
git clone https://github.com/Engelko/cryptobot.git
cd cryptobot
```

### Шаг 3: Настройка конфигурации

Создайте файл настроек `.env` из примера:

```bash
cp .env.example .env
```

Отредактируйте файл `.env` с помощью редактора `nano`:

```bash
nano .env
```

**Что нужно изменить:**
1.  `BYBIT_API_KEY` и `BYBIT_API_SECRET`: Вставьте ваши API ключи от Bybit.
2.  `BYBIT_TESTNET`: Установите `False` для реальной торговли или `True` для Тестнета.
3.  `TRADING_SYMBOLS`: Список монет для торговли (например, `["BTCUSDT","ETHUSDT"]`).
4.  `SIMULATION_MODE`: `False` для подключения к бирже.

*Для сохранения в nano нажмите `Ctrl+O`, `Enter`, затем `Ctrl+X` для выхода.*

### Шаг 4: Запуск через Docker Compose

Запустите сборку и старт контейнеров в фоновом режиме:

```bash
docker compose up -d --build
```

**Проверка статуса:**
```bash
docker compose ps
```
Вы должны увидеть два запущенных сервиса: `antigravity-engine` и `antigravity-dashboard`.

### Шаг 5: Использование

1.  **Дашборд (Панель управления):**
    Откройте в браузере: `http://<IP-ВАШЕГО-СЕРВЕРА>:8501`

    *Здесь вы можете видеть баланс, активные позиции, графики и логи.*

2.  **Управление стратегиями:**
    Настройки стратегий находятся в файле `strategies.yaml`.

    *Важно:* Благодаря настройке Docker, вы можете редактировать этот файл прямо на сервере, и изменения подхватятся при перезапуске бота, либо менять их прямо через интерфейс Дашборда (вкладка "Strategies").

3.  **Просмотр логов:**

    Логи торгового движка:
    ```bash
    docker compose logs -f engine
    ```

    Логи дашборда:
    ```bash
    docker compose logs -f dashboard
    ```

4.  **Остановка бота:**
    ```bash
    docker compose down
    ```

---

## 🚀 Getting Started (English / Local Dev)

### 1. Prerequisites
- Python 3.10 or higher
- A Bybit Account (Testnet or Mainnet) with API Keys.

### 2. Installation

Clone the repository and enter the directory:
```bash
git clone <repository_url>
cd cryptobot
```

Install the required dependencies:
```bash
pip install -r requirements.txt
```

### 3. Configuration

Create your configuration file from the template:
```bash
cp .env.example .env
```

Open `.env` in a text editor and fill in your details:
- `BYBIT_API_KEY` & `BYBIT_API_SECRET`: Your exchange keys.
- `TRADING_SYMBOLS`: List of coins, e.g., `["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT"]`.
- `SIMULATION_MODE`: Set to `False` for real trading, `True` for paper trading.
- `TZ`: Your timezone (default `Europe/Moscow`).

### 4. Running the Bot

**Start the Trading Engine (The Bot):**
This process runs in the background, analyzes data, and executes trades.
```bash
python main.py
```
*You should see logs indicating "system_startup" and "strategy_engine_started".*

**Start the Dashboard (The UI):**
Open a new terminal window and run:
```bash
streamlit run dashboard.py
```
*Access the dashboard at http://localhost:8501*

---

## 🛠 Diagnostics & Debugging

If the bot isn't behaving as expected, use the **Diagnostics** tab in the Dashboard or run these scripts:

1.  **Check Strategy Logic:**
    Verifies if your strategies would have generated signals on historical data.
    ```bash
    python check_strategies.py
    ```

2.  **Verify API Connection:**
    ```bash
    python verify_api.py
    ```

3.  **Verify WebSocket Feed:**
    ```bash
    python verify_ws.py
    ```

For a deep dive into how the bot works, read [BOT_LOGIC.md](BOT_LOGIC.md).
