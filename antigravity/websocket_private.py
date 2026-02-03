import aiohttp
import asyncio
import json
import time
import hmac
import hashlib
from typing import List, Dict, Any
from antigravity.config import settings
from antigravity.logging import get_logger
from antigravity.event import event_bus, OrderUpdateEvent

logger = get_logger("websocket_private")

class BybitPrivateWebSocket:
    def __init__(self):
        self.url = "wss://stream-testnet.bybit.com/v5/private" if settings.BYBIT_TESTNET else "wss://stream.bybit.com/v5/private"
        self._session = None
        self._ws = None
        self._running = False
        self._ping_interval = 20
        self._ping_task = None
        self.api_key = settings.BYBIT_API_KEY
        self.api_secret = settings.BYBIT_API_SECRET

    async def connect(self):
        """Connect to Private WS with aggressive reconnection and authentication."""
        self._running = True
        reconnect_delay = 5
        max_reconnect_delay = 60

        while self._running:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            try:
                if self._session is None or self._session.closed:
                    self._session = aiohttp.ClientSession(headers=headers)

                async with self._session.ws_connect(self.url, heartbeat=30) as ws:
                    self._ws = ws
                    logger.info("ws_private_connected", url=self.url)

                    # Authenticate
                    if await self._authenticate():
                        # Subscribe to private topics
                        await self.subscribe(["execution", "order"])
                        reconnect_delay = 5 # Reset delay on success

                        # Start Ping Task
                        if self._ping_task:
                            self._ping_task.cancel()
                        self._ping_task = asyncio.create_task(self._keep_alive())

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_message(msg.data)
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                logger.warning("ws_private_closed")
                                break
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error("ws_private_error", error=str(ws.exception()))
                                break
                    else:
                        logger.error("ws_private_auth_failed")
                        await asyncio.sleep(reconnect_delay)

            except Exception as e:
                logger.error("ws_private_connection_failed", error=str(e))
                if self._session and not self._session.closed:
                    await self._session.close()
                self._session = None

            if self._running:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)

    async def _authenticate(self) -> bool:
        if not self._ws:
            return False

        expires = int((time.time() + 10) * 1000)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            f"GET/realtime{expires}".encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        auth_payload = {
            "op": "auth",
            "args": [self.api_key, expires, signature]
        }

        await self._ws.send_json(auth_payload)

        # Wait for auth response
        try:
            msg = await self._ws.receive_json()
            if msg.get("success") and msg.get("op") == "auth":
                logger.info("ws_private_authenticated")
                return True
            else:
                logger.error("ws_private_auth_response_failed", msg=msg)
                return False
        except Exception as e:
            logger.error("ws_private_auth_exception", error=str(e))
            return False

    async def subscribe(self, topics: List[str]):
        if not self._ws:
            return
        req = {
            "op": "subscribe",
            "args": topics
        }
        await self._ws.send_json(req)
        logger.info("ws_private_subscribed", topics=topics)

    async def _keep_alive(self):
        while self._running:
            await asyncio.sleep(self._ping_interval)
            if self._ws and not self._ws.closed:
                try:
                    await self._ws.send_json({"op": "ping"})
                except Exception as e:
                    logger.error("ws_private_ping_error", error=str(e))
                    break

    async def _handle_message(self, data: str):
        try:
            msg = json.loads(data)
            topic = msg.get("topic", "")

            # 1. Order Updates
            if topic == "order":
                for item in msg.get("data", []):
                    await event_bus.publish(OrderUpdateEvent(
                        symbol=item.get("symbol"),
                        order_id=item.get("orderId"),
                        order_status=item.get("orderStatus"),
                        side=item.get("side"),
                        price=float(item.get("price", 0)),
                        qty=float(item.get("qty", 0)),
                        filled_qty=float(item.get("cumExecQty", 0)),
                        timestamp=int(item.get("updatedTime", 0))
                    ))

            # 2. Execution Updates (Fills)
            # Execution stream gives detailed fill info, but "order" stream is sufficient for status updates
            # We can log executions or refine OrderUpdateEvent if needed.
            if topic == "execution":
                # For now, we rely on "order" stream for status changes
                pass

            # Log subscription success
            if msg.get("success") and msg.get("op") == "subscribe":
                logger.info("ws_private_subscription_success", args=msg.get("ret_msg"))

        except Exception as e:
            logger.error("ws_private_message_error", error=str(e))

    async def close(self):
        self._running = False
        if self._ping_task:
            self._ping_task.cancel()
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
