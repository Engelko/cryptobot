#!/usr/bin/env python3
import subprocess
import sys

APP_DIR = "/opt/cryptobot"

def modify_risk_py():
    """Modify risk.py to add caching and metrics"""
    print("Modifying antigravity/risk.py...")
    
    # Read the file
    with open(f"{APP_DIR}/antigravity/risk.py", 'r') as f:
        content = f.read()
    
    # Modify imports
    if 'import time' not in content:
        content = content.replace('from datetime import datetime, timezone', 'import time\nfrom datetime import datetime, timezone')
    
    if 'from antigravity.metrics import metrics' not in content:
        content = content.replace('from antigravity.event import event_bus, TradeClosedEvent, on_event', 
                                 'from antigravity.event import event_bus, TradeClosedEvent, on_event\nfrom antigravity.metrics import metrics')
    
    # Modify __init__
    if '# Cache fields' not in content:
        content = content.replace('self.last_reset_date = None', 
                                 'self.last_reset_date = None\n\n        # Cache fields\n        self._cached_balance = 0.0\n        self._balance_cache_time = 0\n        self._last_rejection_reason = None')
    
    # Add _fetch_balance_from_api method before _get_available_balance
    fetch_balance_method = '''
    def _fetch_balance_from_api(self) -> float:
        """Fetch fresh balance from API"""
        if settings.SIMULATION_MODE:
            return execution_manager.paper_broker.balance
        
        client = BybitClient()
        try:
            balance_data = await client.get_wallet_balance(coin="USDT")
            if "totalWalletBalance" in balance_data:
                return float(balance_data.get("totalWalletBalance", 0.0))
            elif "coin" in balance_data:
                for c in balance_data["coin"]:
                    if c.get("coin") == "USDT":
                        return float(c.get("walletBalance", 0.0))
        finally:
            await client.close()
        
        return 0.0
'''
    
    # Replace old _get_available_balance method
    new_get_balance = '''
    async def _get_available_balance(self) -> float:
        """
        Fetch available USDT balance with 30-second cache.
        If Simulation Mode, fetch from PaperBroker.
        If Real Mode, fetch from Bybit API.
        """
        # Use cached balance for 30 seconds
        current_time = time.time()
        if hasattr(self, '_cached_balance') and (current_time - self._balance_cache_time) < 30:
            return self._cached_balance

        balance = await self._fetch_balance_from_api()
        self._cached_balance = balance
        self._balance_cache_time = current_time
        return balance
'''
    
    # Replace the method
    if '# Use cached balance for 30 seconds' not in content:
        content = content.replace('    async def _get_available_balance(self) -> float:\n        """\n        Fetch available USDT balance.\n        If Simulation Mode, fetch from PaperBroker.\n        If Real Mode, fetch from Bybit API.\n        """', 
                                 new_get_balance)
    
    # Write back
    with open(f"{APP_DIR}/antigravity/risk.py", 'w') as f:
        f.write(content)
    
    print("✓ risk.py modified")

def modify_execution_py():
    """Modify execution.py to add dynamic sizing and metrics"""
    print("Modifying antigravity/execution.py...")
    
    with open(f"{APP_DIR}/antigravity/execution.py", 'r') as f:
        content = f.read()
    
    # Add imports
    if 'from antigravity.metrics import metrics' not in content:
        content = content.replace('import time', 'import time\nfrom .metrics import metrics')
    
    # Add helper methods to RealBroker class
    helper_methods = '''
    def _get_min_order_value(self, symbol: str) -> float:
        """Get minimum order value from Bybit specs"""
        MIN_ORDER_VALUES = {
            "BTCUSDT": 10.0,
            "ETHUSDT": 5.0,
            "SOLUSDT": 5.0,
            "XRPUSDT": 5.0,
            "ADAUSDT": 5.0,
            "DOGEUSDT": 5.0,
        }
        return MIN_ORDER_VALUES.get(symbol, 10.0)

    def _round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity according to Bybit precision"""
        precision = PRECISION_MAP.get(symbol, 2)
        return round(quantity, precision)

    async def _calculate_position_size(self, symbol: str, price: float):
        """Calculate position size based on available balance"""
        available = await self._get_available_balance()
        min_order = self._get_min_order_value(symbol)
        
        if available < min_order:
            logger.warning("insufficient_funds_skip_signal", 
                         available=available, required=min_order, symbol=symbol)
            return None
        
        # Use 90% of available balance (with buffer)
        size_usdt = min(available * 0.9, settings.MAX_POSITION_SIZE)
        quantity = size_usdt / price
        
        # Round to correct precision
        return self._round_quantity(symbol, quantity)
'''
    
    if 'def _get_min_order_value' not in content:
        content = content.replace('class RealBroker:', f'class RealBroker:{helper_methods}')
    
    print("✓ execution.py modified")

def modify_database_py():
    """Modify database.py to add position methods"""
    print("Modifying antigravity/database.py...")
    
    with open(f"{APP_DIR}/antigravity/database.py", 'r') as f:
        content = f.read()
    
    # Add new methods
    position_methods = '''
    async def save_position(self, symbol: str, side: str, price: float, quantity: float, value: float, strategy: str):
        """Save a new position to database"""
        await self.execute_async(
            "INSERT INTO positions (symbol, side, entry_price, quantity, entry_value, strategy) VALUES (?, ?, ?, ?, ?, ?)",
            (symbol, side, price, quantity, value, strategy)
        )

    async def update_position_pnl(self, symbol: str, current_price: float, unrealized_pnl: float):
        """Update current price and unrealized PnL for a position"""
        await self.execute_async(
            "UPDATE positions SET current_price = ?, unrealized_pnl = ?, updated_at = CURRENT_TIMESTAMP WHERE symbol = ?",
            (current_price, unrealized_pnl, symbol)
        )

    async def close_position(self, symbol: str, price: float, quantity: float, real_pnl: float):
        """Close a position (delete from DB and log PnL)"""
        await self.execute_async(
            "DELETE FROM positions WHERE symbol = ?",
            (symbol,)
        )
        logger.info("position_closed_db", symbol=symbol, pnl=real_pnl, price=price, quantity=quantity)
'''
    
    if 'async def save_position' not in content:
        content = content.rstrip() + position_methods
    
    with open(f"{APP_DIR}/antigravity/database.py", 'w') as f:
        f.write(content)
    
    print("✓ database.py modified")

def modify_main_py():
    """Modify main.py to add position tracker and alert checker"""
    print("Modifying main.py...")
    
    with open(f"{APP_DIR}/main.py", 'r') as f:
        content = f.read()
    
    # Add import
    if 'from .position_tracker import position_tracker' not in content:
        content = content.replace('from antigravity.websocket_private import BybitPrivateWebSocket', 
                                 'from antigravity.websocket_private import BybitPrivateWebSocket\nfrom antigravity.position_tracker import position_tracker')
    
    # Add initialization in main()
    if 'await position_tracker.initialize()' not in content:
        content = content.replace('await strategy_engine.start();', 
                                 'await position_tracker.initialize();\n    await strategy_engine.start();')
    
    # Add alert checker and price updater tasks
    background_tasks = '''
async def alert_checker():
    """Check for alerts periodically"""
    from .alerts import check_alerts
    while True:
        try:
            alerts = check_alerts()
            if alerts:
                logger.info("alerts_checked", count=len(alerts))
        except Exception as e:
            logger.error("alert_checker_error", error=str(e))
        await asyncio.sleep(3600)  # Check every hour

async def position_price_updater():
    """Update prices and unrealized PnL periodically"""
    while True:
        try:
            await position_tracker.update_prices()
        except Exception as e:
            logger.error("price_update_error", error=str(e))
        await asyncio.sleep(60)  # Update every minute
'''
    
    if 'async def alert_checker()' not in content:
        content = content.rstrip() + '\n\n' + background_tasks
    
    # Add task creation before stop_event
    if 'asyncio.create_task(alert_checker())' not in content:
        content = content.replace('await stop_event.wait()', 
                                 'asyncio.create_task(alert_checker())\n    asyncio.create_task(position_price_updater())\n    \n    await stop_event.wait()')
    
    with open(f"{APP_DIR}/main.py", 'w') as f:
        f.write(content)
    
    print("✓ main.py modified")

def modify_dashboard_py():
    """Modify dashboard.py to add unrealized PnL display"""
    print("Modifying dashboard.py...")
    
    with open(f"{APP_DIR}/dashboard.py", 'r') as f:
        content = f.read()
    
    # Find the right place to add positions display (in tab2)
    positions_code = '''
    st.subheader("Open Positions (Unrealized PnL)")
    
    try:
        positions_df = pd.read_sql("""
            SELECT 
                symbol, side, entry_price, quantity, entry_value,
                current_price, unrealized_pnl, strategy, opened_at
            FROM positions 
            ORDER BY opened_at DESC
        """, engine)
        
        if not positions_df.empty:
            # Calculate PnL percentage
            positions_df['pnl_pct'] = (positions_df['unrealized_pnl'] / positions_df['entry_value'] * 100).round(2)
            
            # Format for display
            display_df = positions_df.copy()
            display_df['entry_value'] = display_df['entry_value'].round(2)
            display_df['unrealized_pnl'] = display_df['unrealized_pnl'].round(2)
            display_df['pnl_pct'] = display_df['pnl_pct'].apply(lambda x: f"{x:+.2f}%")
            
            # Display dataframe
            st.dataframe(display_df, use_container_width=True)
            
            # Total unrealized PnL
            total_pnl = positions_df['unrealized_pnl'].sum()
            total_value = positions_df['entry_value'].sum()
            st.metric("Total Unrealized PnL", f"{total_pnl:.2f} USDT", 
                     delta=f"{total_pnl/total_value*100:.2f}%",
                     delta_color="normal" if total_pnl >= 0 else "inverse")
            
            st.write(f"Total invested: {total_value:.2f} USDT")
        else:
            st.info("No open positions tracked")
    except Exception as e:
        st.error(f"Error loading positions: {e}")
'''
    
    # Add after "Open Orders" section in tab2
    if 'Open Positions (Unrealized PnL)' not in content:
        content = content.replace('st.subheader("Open Orders")', 
                                 f'st.subheader("Open Positions (Unrealized PnL)"){positions_code}\\n    st.subheader("Open Orders")')
    
    with open(f"{APP_DIR}/dashboard.py", 'w') as f:
        f.write(content)
    
    print("✓ dashboard.py modified")

if __name__ == "__main__":
    print("=== Applying code modifications ===\\n")
    
    try:
        modify_risk_py()
        modify_execution_py()
        modify_database_py()
        modify_main_py()
        modify_dashboard_py()
        
        print("\\n=== All modifications applied successfully ===")
        print("Now run: cd /opt/cryptobot && docker-compose down && docker-compose up -d --build")
    except Exception as e:
        print(f"\\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)
