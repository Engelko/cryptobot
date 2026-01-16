import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import json

from antigravity.client import BybitClient
from antigravity.strategy import Signal, SignalType
from antigravity.execution import RealBroker
from antigravity.exceptions import APIError

class TestLeverageFix(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    @patch('antigravity.client.BybitClient._request')
    def test_set_leverage_payload(self, mock_request):
        """
        Unit Test: Verify BybitClient.set_leverage sends 'buyLeverage' and 'sellLeverage'.
        """
        # Setup mock to return success
        mock_request.return_value = {} # success result

        client = BybitClient()
        symbol = "BTCUSDT"
        leverage = "5.0"

        success = self.loop.run_until_complete(
            client.set_leverage(category="linear", symbol=symbol, leverage=leverage)
        )

        self.assertTrue(success)

        # Verify call arguments
        args, kwargs = mock_request.call_args
        method, endpoint, payload = args[0], args[1], args[2]

        self.assertEqual(endpoint, "/v5/position/set-leverage")
        self.assertIn("buyLeverage", payload)
        self.assertIn("sellLeverage", payload)
        self.assertEqual(payload["buyLeverage"], "5.0")
        self.assertEqual(payload["sellLeverage"], "5.0")
        self.assertNotIn("leverage", payload) # Ensure old key is NOT present

    @patch('antigravity.client.BybitClient._request')
    def test_set_leverage_api_error(self, mock_request):
        """
        Unit Test: Verify set_leverage handles API errors correctly.
        """
        # Simulate API Error (e.g. invalid symbol)
        mock_request.side_effect = APIError("Invalid Symbol", 10001, 400)

        client = BybitClient()
        success = self.loop.run_until_complete(
            client.set_leverage(category="linear", symbol="INVALID", leverage="5.0")
        )

        self.assertFalse(success)

    @patch('antigravity.client.BybitClient._request')
    def test_set_leverage_already_set(self, mock_request):
        """
        Unit Test: Verify set_leverage treats retCode 110043 as success.
        """
        # Simulate "Leverage not modified" error
        mock_request.side_effect = APIError("Leverage not modified", 110043, 200)

        client = BybitClient()
        success = self.loop.run_until_complete(
            client.set_leverage(category="linear", symbol="BTCUSDT", leverage="5.0")
        )

        self.assertTrue(success)

    @patch('antigravity.execution.BybitClient')
    def test_real_broker_execution_flow(self, MockClientClass):
        """
        Integration Test: Verify RealBroker calls set_leverage with correct args before placing order.
        """
        # Setup Mock Client Instance
        mock_instance = MockClientClass.return_value
        mock_instance.get_wallet_balance = AsyncMock(return_value={"totalWalletBalance": "1000"})
        mock_instance.get_positions = AsyncMock(return_value=[])
        mock_instance.set_leverage = AsyncMock(return_value=True)
        mock_instance.place_order = AsyncMock(return_value={"orderId": "12345"})
        mock_instance.close = AsyncMock()

        broker = RealBroker()
        signal = Signal(
            type=SignalType.BUY,
            symbol="ETHUSDT",
            price=3000.0,
            quantity=0.1,
            reason="Integration Test",
            leverage=2.5 # Specific leverage
        )

        self.loop.run_until_complete(broker.execute_order(signal, "TestStrategy"))

        # Verify set_leverage was called
        mock_instance.set_leverage.assert_called_once()
        call_args = mock_instance.set_leverage.call_args

        # Check arguments passed to set_leverage
        # RealBroker passes leverage as string or float, client converts it.
        # But RealBroker passes it as keyword arg 'leverage'
        _, kwargs = call_args
        self.assertEqual(kwargs['symbol'], "ETHUSDT")
        self.assertEqual(float(kwargs['leverage']), 2.5)

if __name__ == '__main__':
    unittest.main()
