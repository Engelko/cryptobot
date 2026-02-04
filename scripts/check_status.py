import asyncio
import os
from antigravity.config import settings
from antigravity.client import BybitClient
from antigravity.logging import configure_logging, get_logger

logger = get_logger("diagnostics")

async def main():
    configure_logging()
    print("=== ANTIGRAVITY DIAGNOSTICS ===")

    # 1. Check Configuration
    print(f"INITIAL_DEPOSIT: ${settings.INITIAL_DEPOSIT}")
    print(f"EMERGENCY_THRESHOLD: {settings.EMERGENCY_THRESHOLD * 100}%")
    print(f"Emergency Limit: ${settings.INITIAL_DEPOSIT * settings.EMERGENCY_THRESHOLD}")
    print(f"Recovery Limit: ${settings.INITIAL_DEPOSIT * 0.80}")

    # 2. Check API Connection & Balance
    if not settings.BYBIT_API_KEY:
        print("ERROR: BYBIT_API_KEY is not set!")
        return

    client = BybitClient()
    try:
        print("Fetching balance from Bybit...")
        balance_data = await client.get_wallet_balance(coin="USDT")

        balance = 0.0
        if "totalWalletBalance" in balance_data:
            balance = float(balance_data.get("totalWalletBalance", 0.0))
        elif "coin" in balance_data:
            for c in balance_data["coin"]:
                if c.get("coin") == "USDT":
                    balance = float(c.get("walletBalance", 0.0))

        print(f"Current Wallet Balance: ${balance:.2f} USDT")

        # 3. Check Positions (Equity)
        positions = await client.get_positions(category="linear")
        unrealized_pnl = sum(float(p.get("unrealisedPnl", 0)) for p in positions)
        print(f"Unrealized PnL: ${unrealized_pnl:.2f} USDT")

        equity = balance + unrealized_pnl
        print(f"Total Equity: ${equity:.2f} USDT")

        # 4. Mode Evaluation
        ratio = equity / settings.INITIAL_DEPOSIT if settings.INITIAL_DEPOSIT > 0 else 1.0
        print(f"Equity Ratio: {ratio:.2%}")

        if ratio < settings.EMERGENCY_THRESHOLD:
            print("STATUS: EMERGENCY STOP (Active)")
            print("REASON: Equity is too low compared to INITIAL_DEPOSIT.")
            print("FIX: Increase your balance on Bybit OR reduce INITIAL_DEPOSIT in .env")
        elif ratio < 0.80:
            print("STATUS: RECOVERY MODE (Active)")
        else:
            print("STATUS: NORMAL")

    except Exception as e:
        print(f"ERROR during diagnostics: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
