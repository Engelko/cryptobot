import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from antigravity.risk import RiskManager, TradingMode
from antigravity.strategy import Signal, SignalType
from antigravity.config import settings

@pytest.mark.asyncio
async def test_risk_manager_emergency_stop():
    with patch('antigravity.database.db.get_risk_state', return_value=None):
        rm = RiskManager()
        rm.initial_deposit = 100.0

        # Mock get_equity to return 40 (below 50%)
        rm.get_equity = AsyncMock(return_value=40.0)
        rm._get_balance = AsyncMock(return_value=40.0)

        signal = Signal(symbol="BTCUSDT", type=SignalType.BUY, price=50000.0)

        # We need to mock _is_reduce_only to avoid API calls
        rm._is_reduce_only = AsyncMock(return_value=False)
        rm._close_all_positions = AsyncMock()

        allowed = await rm.check_signal(signal)
        assert allowed is False
        assert rm.trading_mode == TradingMode.EMERGENCY_STOP

@pytest.mark.asyncio
async def test_risk_manager_leverage_cap():
    with patch('antigravity.database.db.get_risk_state', return_value=None):
        rm = RiskManager()
        rm.initial_deposit = 1000.0
        rm.get_equity = AsyncMock(return_value=1000.0)
        rm._get_balance = AsyncMock(return_value=1000.0)
        rm._is_reduce_only = AsyncMock(return_value=False)

        signal = Signal(symbol="BTCUSDT", type=SignalType.BUY, price=50000.0, leverage=10.0)

        allowed = await rm.check_signal(signal)
        assert allowed is True
        assert signal.leverage == 3.0 # Capped

@pytest.mark.asyncio
async def test_risk_manager_recovery_mode():
    with patch('antigravity.database.db.get_risk_state', return_value=None):
        rm = RiskManager()
        rm.initial_deposit = 1000.0
        # 75% equity (between 50% and 80%)
        rm.get_equity = AsyncMock(return_value=750.0)
        rm._get_balance = AsyncMock(return_value=750.0)
        rm._is_reduce_only = AsyncMock(return_value=False)

        signal = Signal(symbol="BTCUSDT", type=SignalType.BUY, price=50000.0)

        allowed = await rm.check_signal(signal)
        assert allowed is True
        assert rm.trading_mode == TradingMode.RECOVERY
        assert signal.category == "spot"
        assert signal.leverage == 1.0
