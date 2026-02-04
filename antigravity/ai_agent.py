import os
import joblib
import pandas as pd
import numpy as np
import ta
import lightgbm as lgb
from typing import List, Dict, Optional, Tuple, Any
from antigravity.logging import get_logger

logger = get_logger("ai_agent")

MODEL_PATH = "storage/ai_model.joblib"

class AIAgent:
    def __init__(self):
        self.model = self._load_model()
        self.feature_names = []

    def _load_model(self):
        if os.path.exists(MODEL_PATH):
            try:
                return joblib.load(MODEL_PATH)
            except Exception as e:
                logger.error("model_load_failed", error=str(e))
        return None

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate 50+ technical indicators as features."""
        if len(df) < 50:
            return pd.DataFrame()

        df = df.copy()
        # Ensure numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])

        # 1. Trend Indicators (15+)
        df['sma_20'] = ta.trend.sma_indicator(df['close'], window=20)
        df['ema_20'] = ta.trend.ema_indicator(df['close'], window=20)
        df['ema_50'] = ta.trend.ema_indicator(df['close'], window=50)
        df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
        df['adx_pos'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=14)
        df['adx_neg'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=14)
        df['cci'] = ta.trend.cci(df['high'], df['low'], df['close'], window=20)
        df['dpo'] = ta.trend.dpo(df['close'], window=20)
        df['ichimoku_a'] = ta.trend.ichimoku_a(df['high'], df['low'])
        df['ichimoku_b'] = ta.trend.ichimoku_b(df['high'], df['low'])
        df['kst'] = ta.trend.kst(df['close'])
        df['macd'] = ta.trend.macd(df['close'])
        df['macd_signal'] = ta.trend.macd_signal(df['close'])
        df['macd_diff'] = ta.trend.macd_diff(df['close'])
        df['trix'] = ta.trend.trix(df['close'])
        df['vortex_pos'] = ta.trend.vortex_indicator_pos(df['high'], df['low'], df['close'])
        df['vortex_neg'] = ta.trend.vortex_indicator_neg(df['high'], df['low'], df['close'])

        # 2. Momentum Indicators (10+)
        df['rsi'] = ta.momentum.rsi(df['close'], window=14)
        df['stoch_rsi'] = ta.momentum.stochrsi(df['close'])
        df['stoch_rsi_k'] = ta.momentum.stochrsi_k(df['close'])
        df['stoch_rsi_d'] = ta.momentum.stochrsi_d(df['close'])
        df['tsi'] = ta.momentum.tsi(df['close'])
        df['william_r'] = ta.momentum.williams_r(df['high'], df['low'], df['close'])
        df['ao'] = ta.momentum.awesome_oscillator(df['high'], df['low'])
        df['kama'] = ta.momentum.kama(df['close'])
        df['roc'] = ta.momentum.roc(df['close'])

        # 3. Volatility Indicators (10+)
        bb = ta.volatility.BollingerBands(df['close'])
        df['bb_h'] = bb.bollinger_hband()
        df['bb_l'] = bb.bollinger_lband()
        df['bb_m'] = bb.bollinger_mavg()
        df['bb_w'] = bb.bollinger_wband()
        df['bb_p'] = bb.bollinger_pband()

        keltner = ta.volatility.KeltnerChannel(df['high'], df['low'], df['close'])
        df['kc_h'] = keltner.keltner_channel_hband()
        df['kc_l'] = keltner.keltner_channel_lband()
        df['kc_m'] = keltner.keltner_channel_mband()

        df['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close'])
        df['ui'] = ta.volatility.ulcer_index(df['close'])

        donchian = ta.volatility.DonchianChannel(df['high'], df['low'], df['close'])
        df['dc_h'] = donchian.donchian_channel_hband()
        df['dc_l'] = donchian.donchian_channel_lband()
        df['dc_m'] = donchian.donchian_channel_mband()

        # 4. Others
        psar = ta.trend.PSARIndicator(df['high'], df['low'], df['close'])
        df['psar'] = psar.psar()
        df['aroon_up'] = ta.trend.aroon_up(df['high'], df['low'])
        df['aroon_down'] = ta.trend.aroon_down(df['high'], df['low'])

        # 5. Volume Indicators (5+)
        df['obv'] = ta.volume.on_balance_volume(df['close'], df['volume'])
        df['mfi'] = ta.volume.money_flow_index(df['high'], df['low'], df['close'], df['volume'])
        df['cmf'] = ta.volume.chaikin_money_flow(df['high'], df['low'], df['close'], df['volume'])
        df['em'] = ta.volume.ease_of_movement(df['high'], df['low'], df['volume'])
        df['vpt'] = ta.volume.volume_price_trend(df['close'], df['volume'])
        df['nvi'] = ta.volume.negative_volume_index(df['close'], df['volume'])

        # Drop NaNs
        df = df.dropna()

        # Select only feature columns (exclude original OHLCV if desired, but we keep them for now)
        # Or specifically define self.feature_names
        exclude = ['ts', 'created_at', 'symbol', 'interval', 'target']
        self.feature_names = [c for c in df.columns if c not in exclude]

        return df

    def predict(self, klines_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Predict next 4h direction.
        Returns {'direction': 'UP'/'DOWN', 'confidence': float}
        """
        if self.model is None:
            return {"direction": "NEUTRAL", "confidence": 0.5}

        features_df = self.prepare_features(klines_df)
        if features_df.empty:
            return {"direction": "NEUTRAL", "confidence": 0.5}

        X = features_df[self.feature_names].tail(1)
        prob = self.model.predict(X)[0]

        direction = "UP" if prob > 0.5 else "DOWN"
        confidence = prob if prob > 0.5 else 1 - prob

        logger.info("ai_prediction", direction=direction, confidence=f"{confidence:.2%}")
        return {"direction": direction, "confidence": float(confidence)}

    def train(self, historical_df: pd.DataFrame):
        """
        Train the LightGBM model.
        Target: 1 if close price in 4 periods is higher, else 0.
        """
        logger.info("ai_training_started", rows=len(historical_df))

        df = self.prepare_features(historical_df)
        if len(df) < 100:
            logger.warning("ai_training_aborted", reason="insufficient_data")
            return

        # Create target: price increase in 4 hours (assuming 1h candles)
        # If we use 15m candles, maybe look 16 periods ahead.
        look_ahead = 4
        df['target'] = (df['close'].shift(-look_ahead) > df['close']).astype(int)

        # Drop last rows where target is NaN
        train_df = df.iloc[:-look_ahead].copy()

        X = train_df[self.feature_names]
        y = train_df['target']

        # Simple split
        split = int(len(X) * 0.8)
        X_train, X_val = X.iloc[:split], X.iloc[split:]
        y_train, y_val = y.iloc[:split], y.iloc[split:]

        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'verbosity': -1,
            'boosting_type': 'gbdt',
            'random_state': 42,
            'learning_rate': 0.05,
            'num_leaves': 31,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5
        }

        dtrain = lgb.Dataset(X_train, label=y_train)
        dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)

        self.model = lgb.train(
            params,
            dtrain,
            num_boost_round=1000,
            valid_sets=[dtrain, dval],
            callbacks=[lgb.early_stopping(stopping_rounds=50)]
        )

        # Save model
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        joblib.dump(self.model, MODEL_PATH)
        logger.info("ai_model_saved", path=MODEL_PATH)

ai_agent = AIAgent()
