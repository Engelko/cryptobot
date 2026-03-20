# Module: `antigravity/strategies/` — Trading Strategies

## Назначение

Набор торговых стратегий, каждая из которых наследует `AbstractStrategy` из `antigravity/strategy.py`. Каждая стратегия получает `KlineEvent`, вычисляет индикаторы и при выполнении условий возвращает объект `Signal`. Все стратегии работают через `StrategyEngine`.

## Компоненты

| Имя | Тип | Класс (активный) | Индикаторы | Файл |
|-----|-----|------------------|------------|------|
| `GoldenCrossImproved` | `class` | `TrendFollowingStrategy` | EMA/SMA crossover, MACD | `trend_improved.py` |
| `BollingerRSIImproved` | `class` | `MeanReversionStrategy` | Bollinger Bands, RSI | `mean_reversion_improved.py` |
| `VolatilityBreakoutStrategy` | `class` | — | ATR breakout | `volatility.py` |
| `ScalpingStrategy` | `class` | — | Stochastic | `scalping.py` |
| `BBSqueezeStrategy` | `class` | — | BB Squeeze (Keltner + Bollinger) | `bb_squeeze.py` |
| `GridMasterImproved` | `class` | `GridStrategy` | Grid levels, OrderUpdate | `grid_improved.py` |
| `DynamicRiskLeverageStrategy` | `class` | — | ATR, dynamic leverage | `dynamic_risk_leverage.py` |
| `SpotRecoveryStrategy` | `class` | — | Spot position recovery | `spot_recovery.py` |

### Устаревшие / неактивные файлы

| Файл | Класс | Статус |
|------|-------|--------|
| `trend.py` | `TrendFollowingStrategy` (v1) | Заменён `trend_improved.py` |
| `mean_reversion.py` | `BollingerRSI` (v1) | Заменён `mean_reversion_improved.py` |
| `grid.py` | `GridStrategy` (v1) | Заменён `grid_improved.py` |
| `macd.py` | `MACDStrategy` | Статус неясен `[UNCLEAR]` |
| `rsi.py` | `RSIStrategy` | Статус неясен `[UNCLEAR]` |

## Интерфейс AbstractStrategy (из `antigravity/strategy.py`)

| Метод | Тип | Описание |
|-------|-----|----------|
| `on_market_data(event)` | `async method` | Получает KlineEvent, возвращает `Signal` или `None` |
| `on_order_update(event)` | `async method` | Получает OrderUpdateEvent (нужен Grid-стратегии) |
| `start()` | `async method` | Инициализация стратегии |
| `stop()` | `async method` | Остановка стратегии |
| `is_active` | `property` | Флаг активности |
| `name` | `property` | Уникальное имя стратегии |
| `symbols` | `property` | Список торговых символов |

## Связи

**depends_on:**
- `antigravity.strategy` — `AbstractStrategy`, `Signal`, `SignalType`
- `antigravity.strategies.config` — конфиг-объекты (pydantic/dataclass)
- `antigravity.event` — `KlineEvent`, `OrderUpdateEvent`
- `antigravity.database` — `db` (некоторые стратегии)

**used_by:**
- `antigravity.engine` — `StrategyEngine.register_strategy()`, вызовы `on_market_data()`, `on_order_update()`
- `main.py` — инстанцирование классов

## Диаграмма

```mermaid
graph TD
    ENGINE[StrategyEngine] -->|register_strategy| ABSTRACT[AbstractStrategy]
    ABSTRACT <|-- TREND[GoldenCrossImproved]
    ABSTRACT <|-- MEAN[BollingerRSIImproved]
    ABSTRACT <|-- VOL[VolatilityBreakoutStrategy]
    ABSTRACT <|-- SCALP[ScalpingStrategy]
    ABSTRACT <|-- BBSQ[BBSqueezeStrategy]
    ABSTRACT <|-- GRID[GridMasterImproved]
    ABSTRACT <|-- DRL[DynamicRiskLeverageStrategy]
    ABSTRACT <|-- SPOT[SpotRecoveryStrategy]

    KLINE[KlineEvent] -->|on_market_data| ABSTRACT
    ORDER[OrderUpdateEvent] -->|on_order_update| GRID
    ABSTRACT -->|Signal| ENGINE
```

## Примечания

- `GridMasterImproved` — единственная стратегия, активно потребляющая `OrderUpdateEvent` (нужен для отслеживания исполнения grid-ордеров)
- `SpotRecoveryStrategy` всегда регистрируется в `main.py` без проверки флага enabled — логика активации внутри самой стратегии
- В директории есть `macd.py` и `rsi.py` — не импортируются в `main.py`, статус `[UNCLEAR]`: возможно legacy или для тестов
- TODO: убрать `grid.py`, `trend.py`, `mean_reversion.py` (v1) если они не используются, чтобы не вносить путаницу
- `DynamicRiskLeverageStrategy` — самый большой файл (26 KB), возможно содержит дублирующую логику риска с `antigravity/risk.py`
