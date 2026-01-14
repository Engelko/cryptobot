import asyncio
from antigravity.strategies.config import load_strategy_config
from antigravity.strategies.trend_improved import GoldenCrossImproved
from antigravity.strategies.mean_reversion_improved import BollingerRSIImproved
from antigravity.strategies.grid_improved import GridMasterImproved

# Mock settings
symbols = ["BTCUSDT"]

def main():
    config = load_strategy_config("strategies.yaml")

    print("Attempting to initialize GoldenCrossImproved with (config, symbols)...")
    try:
        # main.py does: TrendFollowingStrategy(config.trend_following, symbols)
        # In main.py: TrendFollowingStrategy = GoldenCrossImproved
        s = GoldenCrossImproved(config.trend_following, symbols)
        print("GoldenCrossImproved initialized successfully (Unexpectedly!)")
        print(f"Symbols type: {type(s.symbols)}")
        print(f"Symbols: {s.symbols}")

        # Check if basic membership test works
        if "BTCUSDT" in s.symbols:
            print("Membership test passed (Unexpected!)")
        else:
            print("Membership test failed (Expected if symbols is config object)")

    except Exception as e:
        print(f"GoldenCrossImproved failed/crashed: {e}")

    print("\nAttempting to initialize BollingerRSIImproved with (config, symbols)...")
    try:
        s = BollingerRSIImproved(config.mean_reversion, symbols)
        print("BollingerRSIImproved initialized successfully (Unexpectedly!)")
        print(f"Symbols type: {type(s.symbols)}")
    except Exception as e:
        print(f"BollingerRSIImproved failed/crashed: {e}")

    print("\nAttempting to initialize GridMasterImproved with (config, symbols)...")
    try:
        s = GridMasterImproved(config.grid, symbols)
        print("GridMasterImproved initialized successfully (Unexpectedly!)")
    except Exception as e:
        print(f"GridMasterImproved failed/crashed: {e}")

if __name__ == "__main__":
    main()
