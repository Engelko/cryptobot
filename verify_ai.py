import pandas as pd
import numpy as np
from antigravity.ai_agent import ai_agent

def test_feature_engineering():
    # Create mock kline data
    data = {
        'open': np.random.uniform(50000, 51000, 100),
        'high': np.random.uniform(51000, 52000, 100),
        'low': np.random.uniform(49000, 50000, 100),
        'close': np.random.uniform(50000, 51000, 100),
        'volume': np.random.uniform(10, 100, 100)
    }
    df = pd.DataFrame(data)

    features_df = ai_agent.prepare_features(df)
    print(f"Generated {len(ai_agent.feature_names)} features")
    assert len(ai_agent.feature_names) >= 50
    assert not features_df.empty

if __name__ == "__main__":
    test_feature_engineering()
    print("AI Agent feature engineering verified")
