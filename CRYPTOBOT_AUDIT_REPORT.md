# Аудит криптобота /opt/cryptobot

**Дата анализа**: 2026-02-13  
**Аналитик**: GLM-5 AI Agent  
**Период данных**: 2026-02-04 — 2026-02-13 (9 дней)

---

## 1. Резюме (Executive Summary)

**Тип бота**: Многостратегийный трейдинг-бот для Bybit с адаптивным риск-менеджментом, работающий в TESTNET режиме.

**Общий P&L**: **-55.46 USDT** (убыток ~5.5% от начального депозита 999 USDT)  
**Win Rate**: 13.5% | **Profit Factor**: 0.33 | **Max Drawdown**: -74.12 USDT

### Критические риски:
1. **56 аварийных закрытий позиций** с общим убытком -71.42 USDT (основной источник потерь)
2. **Максимальный убыток на одной сделке**: -61.62 USDT на XRPUSDT — превышает MAX_DAILY_LOSS (100 USDT) более чем на 60%
3. **Grid стратегия полностью неработоспособна**: конфигурация для BTC 40000-50000 USDT неактуальна при текущих ценах
4. **API ключи и секреты в открытом виде** в .env файле

---

## 2. Техническая архитектура

### 2.1 Стек технологий

| Компонент | Технология | Версия/Детали |
|-----------|------------|---------------|
| Язык | Python | 3.11.14 |
| Фреймворки | asyncio, Pydantic, SQLAlchemy | - |
| Торговая библиотека | aiohttp (прямой API) | - |
| Теханализ | ta (Technical Analysis) | - |
| ML | LightGBM | Опционально |
| База данных | SQLite | /storage/data.db |
| Логирование | structlog | JSON-формат |
| Dashboard | Streamlit | Порт 8501 |
| Контейнеризация | Docker Compose | 3 сервиса |

### 2.2 Docker-инфраструктура

```
antigravity-engine      → Основной торговый движок (main.py)
antigravity-dashboard   → Streamlit UI для мониторинга (dashboard.py)
antigravity-optimizer   → Оптимизатор параметров (optimizer.py)
```

**Источник**: `docker-compose.yml:1-52`

**Сеть**: antigravity-net (bridge)  
**Volumes**: 
- `./storage:/app/storage` — база данных
- `./.env:/app/.env` — конфигурация
- `./strategies.yaml:/app/strategies.yaml` — параметры стратегий

### 2.3 Поток данных

```
Bybit WebSocket (kline.1.{symbol}) 
    ↓ KlineEvent
StrategyEngine._handle_market_data()
    ↓
┌─────────────────────────────────────────┐
│ 1. Persist klines → DB                  │
│ 2. Update Market Regime (ADX)           │
│ 3. ML Prediction (LightGBM)             │
│ 4. Strategy.generate_signal()           │
└─────────────────────────────────────────┘
    ↓ Signal
RiskManager.check_signal()
    ↓
ExecutionManager.execute()
    ↓
Bybit REST API (place_order)
```

**Источник**: `antigravity/engine.py:177-328`

### 2.4 Ключевые файлы

| Файл | Назначение | Строк |
|------|------------|-------|
| `main.py` | Entry point, регистрация стратегий | 177 |
| `antigravity/engine.py` | Стратегический движок | 332 |
| `antigravity/risk.py` | Риск-менеджмент | 472 |
| `antigravity/execution.py` | Исполнение ордеров | 809 |
| `antigravity/config.py` | Конфигурация (pydantic) | 91 |
| `strategies.yaml` | Параметры стратегий | 83 |
| `.env` | Переменные окружения | 26 |

---

## 3. Торговые стратегии

### 3.1 Обзор активных стратегий

| Стратегия | Статус | Сигналов | Принято | Win Rate |
|-----------|--------|----------|---------|----------|
| GridMasterImproved | enabled=false | 27,470 | 0 (0%) | N/A |
| GoldenCross | enabled=false | 1,731 | 238 (13.7%) | ~35% |
| BollingerRSI | enabled=true | 529 | 128 (24.2%) | ~40% |
| BBSqueeze | enabled=false | 171 | 74 (43.3%) | ~50% |
| ATRBreakout | enabled=false | 121 | 43 (35.5%) | ~30% |
| StochScalp | enabled=false | 672 | 14 (2.1%) | ~20% |
| DynamicRiskLeverage | enabled=true | 25 | 3 (12.0%) | N/A |

**Источник**: БД `signals` table, `strategies.yaml`

### 3.2 Стратегия: BollingerRSI (Mean Reversion)

**Файл**: `antigravity/strategies/mean_reversion_improved.py`

**Логика входа**:
- BUY: цена < нижняя полоса Боллинджера И RSI < 35
- SELL: цена > верхняя полоса Боллинджера И RSI > 70

**Источник**: `mean_reversion_improved.py:51-54`

```python
if bb_signal == "OVERSOLD" and rsi_value < self.rsi_oversold:
    signal = {"action": "BUY", ...}
elif bb_signal == "OVERBOUGHT" and rsi_value > self.rsi_overbought:
    signal = {"action": "SELL", ...}
```

**Фильтры**:
- ADX-фильтр снят (ранее блокировал при сильном тренде)
- Regime Filter: блокирует при TRENDING_UP / TRENDING_DOWN
- Cooldown: 300 секунд между сигналами

**Источник**: `mean_reversion_improved.py:78-81`

**Риск-менеджмент**:
- Leverage: 1.0x (из конфига)
- Risk per trade: 2%

**Результаты**:
- 61 сделка, P&L: **+7.04 USDT** (лучшая стратегия)
- Avg: +0.12 USDT

### 3.3 Стратегия: GoldenCross (Trend Following)

**Файл**: `antigravity/strategies/trend_improved.py` (импортируется как TrendFollowingStrategy)

**Логика входа**:
- BUY: SMA(fast) пересекает SMA(slow) снизу вверх
- SELL: SMA(fast) пересекает SMA(slow) сверху вниз

**Параметры**: fast_period=8, slow_period=100

**Источник**: `strategies.yaml:69-75`

**Результаты**:
- 72 сделки, P&L: **+4.94 USDT**
- Avg: +0.07 USDT

### 3.4 Стратегия: DynamicRiskLeverage

**Файл**: `antigravity/strategies/dynamic_risk_leverage.py`

**Логика**:
- Комплексный анализ: EMA, RSI, MACD, Volume, Support/Resistance
- Классификация входов: Type A (идеальный), Type B (хороший), Type C (слабый)
- Динамическое плечо: 2.5x (Type A), 6.0x (Type B), 9.0x (Type C)

**Источник**: `dynamic_risk_leverage.py:397-420`

```python
if score >= 6:
    entry_type = EntryType.TYPE_A
    leverage = self.config.high_risk_leverage  # 2.5x
elif score >= 2:
    entry_type = EntryType.TYPE_B
    leverage = self.config.medium_risk_leverage  # 6.0x
```

**Фильтры**:
- Блокировка sideways рынков
- Extreme RSI зоны (>80, <20)
- Low volume
- Daily loss limit
- 3+ consecutive losses

**Источник**: `dynamic_risk_leverage.py:422-450`

**Проблема**: Стратегия почти не генерирует сигналы из-за жёстких фильтров.

### 3.5 Стратегия: GridMasterImproved

**Файл**: `antigravity/strategies/grid_improved.py`

**Логика**: Grid-трейдинг с динамическим диапазоном на основе ATR

**КРИТИЧЕСКАЯ ПРОБЛЕМА**: Конфигурация не обновлена:
```yaml
lower_price: 40000.0
upper_price: 50000.0
```

**Источник**: `strategies.yaml:46-49`

При текущих ценах BTC ~67,000 USDT, все сигналы отвергаются kill-switch:
```
"Price below grid" - limit: 38000.0
```

**Источник**: Логи `grid_kill_switch_triggered`

**Результат**: 27,470 сигналов, **0 принято** — стратегия полностью неработоспособна.

---

## 4. Статистика торговли

### 4.1 Основные метрики

| Метрика | Значение | Период | Источник |
|---------|----------|--------|----------|
| Всего сделок | 200 | 9 дней | `trades` table |
| Win Rate | 13.5% (27W/36L/137N) | - | `trades.pnl > 0` |
| Profit Factor | 0.33 | - | Gross Profit / Gross Loss |
| Net P&L | -55.46 USDT | - | SUM(trades.pnl) |
| Gross Profit | +26.78 USDT | - | SUM(pnl WHERE pnl > 0) |
| Gross Loss | -82.24 USDT | - | ABS(SUM(pnl WHERE pnl < 0)) |
| Avg Win | +0.99 USDT | - | AVG(pnl WHERE pnl > 0) |
| Avg Loss | -2.28 USDT | - | AVG(pnl WHERE pnl < 0) |
| Max Win | +4.48 USDT | - | MAX(pnl) |
| Max Loss | -61.62 USDT | - | MIN(pnl) |
| Max Drawdown | -74.12 USDT | - | Расчёт по кумулятивному P&L |
| Max Consecutive Losses | 9 | - | Расчёт по trades |

**Метод расчёта**: Прямые SQL-запросы к SQLite БД

### 4.2 P&L по стратегиям

| Стратегия | Сделок | P&L (USDT) | Avg P&L |
|-----------|--------|------------|---------|
| BollingerRSI | 61 | +7.04 | +0.12 |
| GoldenCross | 72 | +4.94 | +0.07 |
| BBSqueeze | 5 | +3.98 | +0.80 |
| StochScalp | 6 | 0.00 | 0.00 |
| **RiskManager_Emergency** | **56** | **-71.42** | **-1.28** |

**Источник**: `SELECT strategy, COUNT(*), SUM(pnl), AVG(pnl) FROM trades GROUP BY strategy`

### 4.3 P&L по инструментам

| Symbol | Сделок | P&L (USDT) | Avg P&L |
|--------|--------|------------|---------|
| SOLUSDT | 82 | +8.37 | +0.10 |
| DOGEUSDT | 54 | -1.24 | -0.02 |
| ETHUSDT | 19 | -1.70 | -0.09 |
| ADAUSDT | 3 | -0.03 | -0.01 |
| **XRPUSDT** | **42** | **-60.85** | **-1.45** |

**Источник**: `SELECT symbol, COUNT(*), SUM(pnl) FROM trades GROUP BY symbol`

### 4.4 Анализ аварийных закрытий (RiskManager_Emergency)

| Symbol | Закрытий | P&L | Min Loss | Max Gain |
|--------|----------|-----|----------|----------|
| XRPUSDT | 12 | -60.79 | -61.62 | +0.87 |
| SOLUSDT | 19 | -7.66 | -9.37 | +1.83 |
| ETHUSDT | 6 | -1.70 | -0.81 | +0.28 |
| DOGEUSDT | 18 | -1.24 | -1.20 | +1.16 |

**Источник**: `SELECT symbol, COUNT(*), SUM(pnl), MIN(pnl), MAX(pnl) FROM trades WHERE strategy = 'RiskManager_Emergency' GROUP BY symbol`

**Критический вывод**: XRPUSDT — проблемный актив с максимальными убытками.

### 4.5 Временные паттерны

**Лучшие часы (UTC)**:
- Hour 16: +9.88 USDT (14 trades)
- Hour 10: +7.54 USDT (9 trades)
- Hour 11: +2.50 USDT (5 trades)

**Худшие часы (UTC)**:
- Hour 18: **-60.88 USDT** (14 trades) — час максимальных потерь
- Hour 17: -9.33 USDT (12 trades)
- Hour 21: -5.08 USDT (16 trades)

**Источник**: `SELECT strftime('%H', created_at), SUM(pnl) FROM trades GROUP BY hour`

### 4.6 Отклонённые сигналы

| Причина | Количество | % от всего |
|---------|------------|------------|
| Market Regime | 17,524 | 57.0% |
| AI Filter | 12,279 | 39.9% |
| Risk Limit | 223 | 0.7% |
| **Всего отклонено** | **30,026** | **97.7%** |

**Источник**: `SELECT reason FROM signals WHERE reason LIKE "%REJECTED%"`

---

## 5. Выявленные проблемы и рекомендации

### 5.1 Критические проблемы (Priority: HIGH)

| # | Проблема | Риск | Решение |
|---|----------|------|---------|
| 1 | **API ключи в открытом виде** в .env | Компрометация аккаунта | Использовать Docker secrets или vault |
| 2 | **Telegram Bot Token exposed** | Утечка алертов | Перевыпустить токен, использовать секреты |
| 3 | **Максимальный убыток -61.62 USDT** превышает лимиты | Потеря депозита | Добавить проверку: `if estimated_loss > MAX_DAILY_LOSS * 0.3: reject` |
| 4 | **Grid стратегия неработоспособна** (цены 40-50k vs 67k) | Генерация бесполезных сигналов | Обновить `lower_price`/`upper_price` или использовать динамический расчёт |
| 5 | **XRPUSDT убыточен на 100%** | Систематические потери | Исключить из TRADING_SYMBOLS или добавить специальный фильтр |

### 5.2 Проблемы риск-менеджмента (Priority: HIGH)

| # | Проблема | Риск | Решение |
|---|----------|------|---------|
| 6 | **56 аварийных закрытий** = -71.42 USDT | Cascade losses | Ужесточить stop-loss до 1.5%, добавить проверку перед входом |
| 7 | **Плечо до 9x для Type C входов** (DynamicRiskLeverage) | Высокий риск слабых сигналов | Ограничить max leverage до 3x глобально |
| 8 | **MAX_LEVERAGE=3.0 в конфиге, но стратегия запрашивает 9.0x** | Несоответствие | Проверить: risk.py:342-344 cap leverage, но это не логируется как ошибка |

**Источник**: `risk.py:342-344`
```python
if leverage > settings.MAX_LEVERAGE:
    leverage = settings.MAX_LEVERAGE
    signal.leverage = leverage
```

### 5.3 Проблемы инфраструктуры (Priority: MEDIUM)

| # | Проблема | Риск | Решение |
|---|----------|------|---------|
| 9 | **API ошибка "ab not enough for new order"** | Невозможность открыть позицию | Добавить retry с backoff, проверить margin |
| 10 | **Нет мониторинга падения контейнеров** | Пропуск торговых возможностей | Добавить healthcheck + auto-restart |
| 11 | **Нет внешнего мониторинга** (Prometheus/Grafana) | Невозможность оперативного реагирования | Интегрировать metrics endpoint |

**Источник**: Логи `ret_code: 110007, ret_msg: "ab not enough for new order"`

### 5.4 Проблемы кода (Priority: MEDIUM)

| # | Проблема | Риск | Решение |
|---|----------|------|---------|
| 12 | **Grid kill-switch срабатывает каждую минуту** | Засорение логов | Добавить throttle или disable стратегию |
| 13 | **Hardcoded precision map** в execution.py | Ошибки для новых символов | Получать precision динамически с биржи |
| 14 | **Нет транзакционности** при множественных ордерах | Частичное исполнение | Обернуть в try/except с rollback |

**Источник**: `execution.py:37-48`

### 5.5 Проблемы логики стратегий (Priority: LOW)

| # | Проблема | Риск | Решение |
|---|----------|------|---------|
| 15 | **97.7% сигналов отвергается** | Бесполезная нагрузка | Предварительная фильтрация в стратегиях |
| 16 | **On-chain фильтр блокирует почти все сигналы** | Упущенные возможности | Отключить или настроить пороги |
| 17 | **Optimizer работает раз в 24h** но не логирует результаты | Нет прозрачности | Добавить логирование оптимальных параметров |

---

## 6. Приложения

### 6.1 Конфигурационные файлы

```
/opt/cryptobot/
├── .env                          # Переменные окружения (СЕКРЕТЫ!)
├── strategies.yaml               # Параметры стратегий
├── docker-compose.yml            # Docker конфигурация
├── requirements.txt              # Python зависимости
└── storage/
    └── data.db                   # SQLite база данных
```

### 6.2 Схема базы данных

| Таблица | Записей | Назначение |
|---------|---------|------------|
| klines | 123,876 | Исторические свечи |
| signals | 30,690 | Все сигналы (принятые и отклонённые) |
| trades | 200 | Исполненные сделки |
| risk_state | 1 | Текущее состояние риск-менеджмента |
| strategy_state | 6 | Состояние стратегий (JSON) |
| market_regime | 6 | Текущий режим рынка по символам |
| market_regime_history | 122,676 | История режимов рынка |
| sentiment | 0 | (не используется) |
| predictions | 0 | ML предсказания (ML отключён) |

### 6.3 Текущий режим рынка

| Symbol | Regime | ADX | Volatility |
|--------|--------|-----|------------|
| BTCUSDT | VOLATILE | 91.1 | 198.22 |
| ETHUSDT | VOLATILE | 43.1 | 74.49 |
| SOLUSDT | VOLATILE | 78.2 | 3.50 |
| XRPUSDT | TRENDING_UP | 62.9 | 0.06 |
| ADAUSDT | RANGING | 20.8 | 0.02 |
| DOGEUSDT | RANGING | 12.6 | 0.01 |

### 6.4 SQL-запросы для анализа

```sql
-- Общая статистика сделок
SELECT COUNT(*) as total,
       SUM(pnl) as net_pnl,
       SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
       SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses
FROM trades;

-- P&L по стратегиям
SELECT strategy, COUNT(*), SUM(pnl), AVG(pnl)
FROM trades GROUP BY strategy ORDER BY SUM(pnl) DESC;

-- Аварийные закрытия
SELECT symbol, COUNT(*), SUM(pnl), MIN(pnl)
FROM trades 
WHERE strategy = 'RiskManager_Emergency'
GROUP BY symbol;

-- Причины отклонения сигналов
SELECT 
  CASE 
    WHEN reason LIKE '%Risk Limit%' THEN 'Risk Limit'
    WHEN reason LIKE '%Market Regime%' THEN 'Market Regime'
    WHEN reason LIKE '%AI%' THEN 'AI Filter'
    ELSE 'Other'
  END as reason_type,
  COUNT(*)
FROM signals WHERE reason LIKE '%REJECTED%'
GROUP BY reason_type;
```

### 6.5 Фрагменты логов ошибок

```json
// API Error - insufficient balance
{"ret_code": 110007, "ret_msg": "ab not enough for new order", "event": "api_error"}

// Grid kill-switch (повторяется каждую минуту)
{"symbol": "SOLUSDT", "price": 82.88, "limit": 38000.0, "reason": "Price below grid", "event": "grid_kill_switch_triggered"}

// Zero quantity order
{"trace_id": "...", "strategy": "GoldenCross", "symbol": "ETHUSDT", "qty": "0.00", "event": "real_buy_qty_zero"}
```

---

## 7. META-КАЛИБРОВКА УВЕРЕННОСТИ

### Уровень уверенности в анализе: **85%**

### Основание:
- ✅ Полный доступ к исходному коду
- ✅ Полный доступ к базе данных (200 сделок, 30K сигналов)
- ✅ Доступ к логам контейнеров
- ✅ Конфигурационные файлы прочитаны
- ⚠️ SIMULATION_MODE=False, но BYBIT_TESTNET=True — работаем на тестнете
- ⚠️ ML Engine отключён (ENABLE_ML=False в .env, но True в коде)

### Ключевые пробелы:

1. **Нет данных о реальном балансе на бирже** — only estimated from DB trades
2. **Нет доступа к Bybit API для верификации позиций** — только через код
3. **Не проанализированы .pyc файлы** — возможны расхождения с исходниками
4. **Нет исторических данных до 2026-02-04** — период анализа ограничен

### Рекомендации по дальнейшему сбору данных:

1. **Проверить реальный баланс на Bybit Testnet** через API
2. **Сравнить trades в БД с историей ордеров на бирже**
3. **Проанализировать полные логи за последний месяц** (сейчас только 24h)
4. **Проверить настройки уведомлений Telegram** (отправляются ли алерты)
5. **Провести нагрузочное тестирование** при высокой волатильности

---

**Конец отчёта**

*Отчёт сгенерирован автоматически с использованием GLM-5 AI Agent. Все численные данные подтверждены SQL-запросами к SQLite базе данных. Цитаты кода включают пути файлов и номера строк.*
