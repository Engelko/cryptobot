import pandas as pd
import numpy as np
from antigravity.ai_agent import ai_agent

# Create 200 rows of dummy data
data = {
    'open': np.random.randn(200) + 100,
    'high': np.random.randn(200) + 102,
    'low': np.random.randn(200) + 98,
    'close': np.random.randn(200) + 100,
    'volume': np.random.randn(200) * 1000 + 5000
}
df = pd.DataFrame(data)

# Test prepare_features
features_df = ai_agent.prepare_features(df)
print(f"Original rows: {len(df)}")
print(f"Features rows: {len(features_df)}")

if len(features_df) > 100:
    print("AI Data Check: PASSED")
else:
    print("AI Data Check: FAILED")
