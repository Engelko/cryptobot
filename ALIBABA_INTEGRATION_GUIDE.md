# Интеграция Alibaba Model Studio

## Обзор

Интеграция позволяет использовать AI модели от Alibaba (Qwen, Kimi, GLM, MiniMax) для анализа рынка и фильтрации торговых сигналов.

## Быстрый старт

### 1. Установка

Скопируйте новые файлы в проект:
```bash
sudo cp /tmp/config_updated.py /opt/cryptobot/antigravity/config.py
sudo cp /tmp/ai_provider.py /opt/cryptobot/antigravity/ai_provider.py
sudo cp /tmp/ai_market_analyzer.py /opt/cryptobot/antigravity/ai_market_analyzer.py
sudo cp /tmp/engine_updated.py /opt/cryptobot/antigravity/engine.py
```

### 2. Конфигурация

Отредактируйте файл `.env`:
```bash
cd /opt/cryptobot
nano .env
```

Добавьте настройки Alibaba:
```env
AI_PROVIDER=alibaba
ALIBABA_API_KEY=sk-sp-998b1971f6c5434c949b6f6cc21c6db7
ALIBABA_BASE_URL=https://coding-intl.dashscope.aliyuncs.com/apps/anthropic/v1
ALIBABA_MODEL=qwen3.5-plus
ALIBABA_AVAILABLE_MODELS=qwen3.5-plus,qwen3-coder-plus,kimi-k2.5
```

### 3. Запуск

```bash
python main.py
```

## Доступные модели

| Модель | Контекст | Сильные стороны | Лучше всего для |
|--------|----------|-----------------|-----------------|
| **qwen3.5-plus** | 1M tokens | Универсальная, мультиязычная | Общий анализ рынка |
| **qwen3-coder-plus** | 1M tokens | Анализ кода, логика | Анализ стратегий |
| **kimi-k2.5** | 262K tokens | Длинный контекст, reasoning | Долгосрочный анализ |
| **MiniMax-M2.5** | 196K tokens | Быстрая, эффективная | Высокочастотная торговля |
| **glm-5** | 202K tokens | Сбалансированная | Баланс скорости/качества |
| **glm-4.7** | 202K tokens | Экономичная | Экономия на API |

## Как это работает

### Архитектура

```
Trading Signal
     ↓
Strategy Router (Regime Filter)
     ↓
🆕 AI Market Analyzer (Alibaba/DeepSeek)
     ↓
ML Filter (LightGBM)
     ↓
On-chain Filter
     ↓
Risk Manager
     ↓
Execution
```

### Процесс анализа

1. **Сбор данных** — получение последних 50 свечей
2. **Анализ AI** — отправка данных в выбранную модель
3. **Проверка** — сравнение сигнала стратегии с рекомендацией AI
4. **Фильтрация** — отклонение при сильном несоответствии

### Пример ответа AI

```json
{
  "sentiment": 0.65,
  "confidence": 0.82,
  "reasoning": "Bullish trend confirmed by EMA crossover and rising volume",
  "recommendation": "BUY",
  "risk_level": "MEDIUM",
  "key_factors": ["EMA golden cross", "Volume increase", "Support level hold"],
  "technical_score": 0.75,
  "market_regime": "TRENDING_UP",
  "time_horizon": "MEDIUM"
}
```

## Управление через Dashboard

1. Откройте Dashboard: `streamlit run dashboard.py`
2. В боковой панели найдите раздел "🤖 AI Model Configuration"
3. Выберите провайдера (Alibaba/DeepSeek/OpenAI)
4. Для Alibaba — выберите конкретную модель
5. Нажмите "🔄 Test AI Connection" для проверки

## Переключение моделей в коде

```python
from antigravity.ai_market_analyzer import market_analyzer

# Переключение модели
market_analyzer.switch_model("qwen3-coder-plus")

# Переключение провайдера
market_analyzer.switch_provider("alibaba")

# Получение информации о модели
info = market_analyzer.get_model_info()
print(info["best_for"])  # "General market analysis"
```

## API Provider Manager

```python
from antigravity.ai_provider import ai_provider

# Получить клиент для конкретной модели
client = ai_provider.get_client(provider="alibaba", model="kimi-k2.5")

# Получить список доступных моделей
models = ai_provider.list_available_models("alibaba")

# Получить текущую конфигурацию
config = ai_provider.get_current_config()
```

## Тестирование

### Ручной тест AI анализа

```python
import asyncio
import pandas as pd
from antigravity.ai_market_analyzer import market_analyzer

async def test_analysis():
    # Создайте тестовые данные
    df = pd.DataFrame({
        'open': [50000, 50100, 50200, 50150, 50300],
        'high': [50200, 50300, 50400, 50350, 50500],
        'low': [49900, 50000, 50100, 50050, 50200],
        'close': [50100, 50200, 50150, 50300, 50400],
        'volume': [1000, 1200, 1100, 1300, 1500]
    })
    
    result = await market_analyzer.analyze_market_data(
        symbol="BTCUSDT",
        klines_df=df,
        regime="TRENDING_UP"
    )
    
    print(f"Recommendation: {result['recommendation']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Reasoning: {result['reasoning']}")

asyncio.run(test_analysis())
```

## Отладка

### Проверка логов

```bash
tail -f logs/cryptobot.log | grep ai_
```

### Проверка конфигурации

```python
from antigravity.config import settings

print(f"Provider: {settings.AI_PROVIDER}")
print(f"Alibaba Key: {settings.ALIBABA_API_KEY[:10]}...")
print(f"Available Models: {settings.ALIBABA_AVAILABLE_MODELS}")
```

## Решение проблем

### Проблема: AI анализ не работает

**Решение:**
1. Проверьте API ключ: `echo $ALIBABA_API_KEY`
2. Проверьте провайдера: должен быть "alibaba"
3. Проверьте сетевое подключение к dashscope.aliyuncs.com

### Проблема: Сигналы отклоняются AI

**Решение:**
- Это нормальное поведение — AI фильтрует рискованные сделки
- Проверьте логи для понимания причины отклонения
- Настройте confidence threshold при необходимости

### Проблема: Долгий ответ AI

**Решение:**
- Используйте более быстрые модели (MiniMax-M2.5, glm-4.7)
- Уменьшите количество свечей для анализа
- Проверьте сетевое соединение

## Безопасность

- API ключи хранятся в `.env` файле
- Не коммитьте `.env` в git
- Используйте ограниченные по правам ключи API

## Производительность

- AI анализ добавляет ~1-3 секунды задержки на сигнал
- Используйте кэширование клиентов для ускорения
- Рассмотрите async batch processing для множества символов

## Дальнейшее развитие

- [ ] Fine-tuning моделей под специфику крипто-рынка
- [ ] Multi-model ensemble (комбинация нескольких моделей)
- [ ] Автоматический выбор модели на основе рыночных условий
- [ ] Integration с on-chain данными
- [ ] Custom prompts для разных типов стратегий
