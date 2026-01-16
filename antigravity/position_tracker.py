from dataclasses import dataclass
from typing import Dict, Optional
from .database import db
from .logging import get_logger
from .client import BybitClient

logger = get_logger("position_tracker")

@dataclass
class Position:
    symbol: str
    side: str
    entry_price: float
    quantity: float
    entry_value: float
    strategy: str

class PositionTracker:
    def __init__(self):
        self._positions: Dict[str, Position] = {}
        self._client = None
    
    async def initialize(self):
        self._client = BybitClient()
        try:
            positions = await self._client.get_positions(category="linear")
            for pos in positions:
                if float(pos['size']) > 0:
                    self._positions[pos['symbol']] = Position(
                        symbol=pos['symbol'],
                        side=pos['side'],
                        entry_price=float(pos['avgPrice']),
                        quantity=float(pos['size']),
                        entry_value=float(pos['positionValue']),
                        strategy='imported'
                    )
            logger.info("positions_loaded", count=len(self._positions))
        finally:
            await self._client.close()
    
    async def update_prices(self):
        if not self._positions:
            return
        
        symbols = list(self._positions.keys())
        prices = await self._fetch_current_prices(symbols)
        
        for symbol, pos in self._positions.items():
            if symbol in prices:
                current_price = prices[symbol]
                if pos.side == 'Buy':
                    unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
                else:
                    unrealized_pnl = (pos.entry_price - current_price) * pos.quantity
                
                await db.update_position_pnl(symbol, current_price, unrealized_pnl)
    
    async def on_order_filled(self, symbol: str, side: str, price: float, quantity: float, strategy: str):
        value = price * quantity
        
        if side == 'Buy':
            if symbol in self._positions:
                existing = self._positions[symbol]
                total_qty = existing.quantity + quantity
                total_value = existing.entry_value + value
                new_entry_price = total_value / total_qty
                
                self._positions[symbol] = Position(
                    symbol=symbol,
                    side='Buy',
                    entry_price=new_entry_price,
                    quantity=total_qty,
                    entry_value=total_value,
                    strategy=strategy
                )
            else:
                self._positions[symbol] = Position(
                    symbol=symbol,
                    side='Buy',
                    entry_price=price,
                    quantity=quantity,
                    entry_value=value,
                    strategy=strategy
                )
            
            await db.save_position(symbol, 'Buy', price, quantity, value, strategy)
        
        elif side == 'Sell':
            if symbol in self._positions and self._positions[symbol].side == 'Buy':
                existing = self._positions[symbol]
                real_pnl = (price - existing.entry_price) * quantity
                
                if quantity >= existing.quantity:
                    del self._positions[symbol]
                else:
                    self._positions[symbol].quantity -= quantity
                    self._positions[symbol].entry_value -= quantity * existing.entry_price
                
                await db.close_position(symbol, price, quantity, real_pnl)
                logger.info("position_closed", symbol=symbol, pnl=real_pnl)
    
    async def _fetch_current_prices(self, symbols: list) -> dict:
        prices = {}
        self._client = BybitClient() if not self._client else self._client
        try:
            tickers = await self._client.get_tickers(category="linear", symbol=symbols[0])
            for ticker in tickers:
                if ticker['symbol'] in symbols:
                    prices[ticker['symbol']] = float(ticker['lastPrice'])
        finally:
            pass
        
        return prices

position_tracker = PositionTracker()
