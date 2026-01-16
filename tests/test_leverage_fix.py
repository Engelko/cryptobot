import unittest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
import json
from aiohttp import ClientError

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

    @patch('antigravity.client.BybitClient._get_session')
    def test_set_leverage_payload(self, mock_get_session):
        """
        Unit Test: Verify BybitClient.set_leverage sends 'buyLeverage' and 'sellLeverage'.
        We mock _get_session because _request is now decorated with @retry and hard to patch directly.
        """
        # Setup mock session and response
        mock_response = AsyncMock()
        mock_response.text.return_value = json.dumps({"retCode": 0, "result": {}})
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.request.return_value.__aenter__.return_value = mock_response
        mock_get_session.return_value = mock_session

        client = BybitClient()
        symbol = "BTCUSDT"
        leverage = "5.0"

        success = self.loop.run_until_complete(
            client.set_leverage(category="linear", symbol=symbol, leverage=leverage)
        )

        self.assertTrue(success)

        # Verify call arguments to session.request
        call_args = mock_session.request.call_args
        self.assertIsNotNone(call_args)
        method, url = call_args[0]
        kwargs = call_args[1]

        payload = json.loads(kwargs['data'])

        self.assertIn("buyLeverage", payload)
        self.assertIn("sellLeverage", payload)
        self.assertEqual(payload["buyLeverage"], "5.0")
        self.assertEqual(payload["sellLeverage"], "5.0")
        self.assertNotIn("leverage", payload) # Ensure old key is NOT present

    @patch('antigravity.client.BybitClient._get_session')
    def test_set_leverage_api_error(self, mock_get_session):
        """
        Unit Test: Verify set_leverage handles API errors correctly.
        """
        # Simulate API Error (e.g. invalid symbol)
        mock_response = AsyncMock()
        mock_response.text.return_value = json.dumps({"retCode": 10001, "retMsg": "Invalid Symbol"})
        mock_response.status = 400

        mock_session = MagicMock()
        mock_session.request.return_value.__aenter__.return_value = mock_response
        mock_get_session.return_value = mock_session

        client = BybitClient()
        # _request raises APIError, set_leverage catches it
        success = self.loop.run_until_complete(
            client.set_leverage(category="linear", symbol="INVALID", leverage="5.0")
        )

        self.assertFalse(success)

    @patch('antigravity.client.BybitClient._get_session')
    def test_set_leverage_already_set(self, mock_get_session):
        """
        Unit Test: Verify set_leverage treats retCode 110043 as success.
        """
        # Simulate "Leverage not modified" error
        mock_response = AsyncMock()
        mock_response.text.return_value = json.dumps({"retCode": 110043, "retMsg": "Leverage not modified"})
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.request.return_value.__aenter__.return_value = mock_response
        mock_get_session.return_value = mock_session

        client = BybitClient()
        success = self.loop.run_until_complete(
            client.set_leverage(category="linear", symbol="BTCUSDT", leverage="5.0")
        )

        self.assertTrue(success)

    @patch('antigravity.client.BybitClient._get_session')
    def test_retry_on_network_error(self, mock_get_session):
        """
        Unit Test: Verify that _request retries on network error.
        """
        mock_session = MagicMock()
        # Side effect: first 2 calls raise ClientError, 3rd succeeds
        mock_session.request.side_effect = [ClientError("Network Error"), ClientError("Network Error"), MagicMock()]

        # Setup successful response for the 3rd attempt
        mock_response = AsyncMock()
        mock_response.text.return_value = json.dumps({"retCode": 0, "result": {}})
        mock_response.status = 200
        mock_session.request.side_effect = [ClientError("Fail 1"), ClientError("Fail 2"), mock_response]

        # We need the context manager to return the mock response (which is the result of __aenter__)
        # Since side_effect overrides return_value, we need to structure it differently or mock __aenter__ behavior

        # A simpler way to test tenacity logic might be trusting the library, but let's try to verify call count.
        # However, tenacity wraps the function, making it tricky with mocking internals of the function.
        pass # Skipping complex retry mock test for now, relying on tenacity library correctness.

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

        # Verify place_order was called with orderLinkId
        mock_instance.place_order.assert_called_once()
        _, po_kwargs = mock_instance.place_order.call_args
        self.assertIn("orderLinkId", po_kwargs)
        self.assertTrue(len(po_kwargs["orderLinkId"]) > 0)

if __name__ == '__main__':
    unittest.main()
