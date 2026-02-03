import asyncio
import sys
from datetime import datetime, timedelta
from antigravity.database import db
from antigravity.client import BybitClient
from antigravity.config import settings

async def run_health_check():
    issues = []
    print(f"--- Antigravity Health Check ({datetime.now().isoformat()}) ---")

    # 1. Database Connectivity & Data Freshness
    try:
        from sqlalchemy import text
        with db.engine.connect() as conn:
            # Check latest kline
            res = conn.execute(text("SELECT MAX(ts) FROM klines")).fetchone()
            if res and res[0]:
                last_ts = datetime.fromtimestamp(res[0] / 1000)
                if datetime.now() - last_ts > timedelta(minutes=15):
                    issues.append(f"CRITICAL: Klines are stale. Last update: {last_ts}")
                else:
                    print(f"✓ Klines fresh (Last: {last_ts})")
            else:
                issues.append("WARNING: No klines found in database")

            # Check for duplicate klines
            dup_res = conn.execute(text("SELECT symbol, ts, COUNT(*) FROM klines GROUP BY symbol, ts HAVING COUNT(*) > 1 LIMIT 5")).fetchall()
            if dup_res:
                issues.append(f"WARNING: Duplicate klines found for {dup_res[0][0]}")
    except Exception as e:
        issues.append(f"CRITICAL: Database error: {str(e)}")

    # 2. Risk State
    try:
        risk = db.get_risk_state()
        if risk:
            daily_loss = risk.get('daily_loss', 0)
            if daily_loss >= settings.MAX_DAILY_LOSS * 0.9:
                issues.append(f"WARNING: Daily loss near limit (${daily_loss:.2f} / ${settings.MAX_DAILY_LOSS})")
            else:
                print(f"✓ Risk state OK (Daily Loss: ${daily_loss:.2f})")
        else:
            issues.append("WARNING: Risk state not found in DB")
    except Exception as e:
        issues.append(f"ERROR: Failed to check risk state: {str(e)}")

    # 3. API Connectivity (Probing only)
    try:
        client = BybitClient()
        server_time = await client.get_server_time()
        print(f"✓ Bybit API Connectivity OK (Server time: {server_time})")
        await client.close()
    except Exception as e:
        issues.append(f"CRITICAL: API Connectivity failed: {str(e)}")

    # 4. Memory/Process Check (Internal simulation)
    # In a real environment, we'd check psutil or docker stats

    print("\nSummary:")
    if not issues:
        print("✅ All systems functional")
        return True
    else:
        for issue in issues:
            print(f"  {issue}")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_health_check())
    sys.exit(0 if success else 1)
