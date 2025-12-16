import asyncio
import time
from antigravity.ml_engine import ml_engine
from antigravity.logging import configure_logging

async def main():
    configure_logging()
    
    print("X-Testing ML Engine...")
    
    if not ml_engine.enabled:
        print("!! ML Stub is NOT enabled in config.")
        return

    # Simulate Prediction Request
    features = {"close": 50000.0, "volume": 100.0, "rsi": 45.0}
    print(f">> Requesting Prediction for BTCUSDT with features: {features}")
    
    result = await ml_engine.predict_price_movement("BTCUSDT", features)
    
    if result:
        print(f"X-Prediction Received: Change={result['predicted_change']:.4f}, Confidence={result['confidence']:.4f}")
    else:
        print("!! No Prediction returned.")

    print("X-Test Complete")

if __name__ == "__main__":
    asyncio.run(main())
