import aiohttp
import asyncio
import json
import time
from typing import List, Callable, Awaitable
from antigravity.config import settings
from antigravity.logging import get_logger
from antigravity.event import event_bus, MarketDataEvent, KlineEvent

logger = get_logger("websocket_client")

class BybitWebSocket:
    def __init__(self):
        self.url = "wss://stream-testnet.bybit.com/v5/public/linear" if settings.BYBIT_TESTNET else "wss://stream.bybit.com/v5/public/linear"
        self._session = None
        self._ws = None
        self._running = False
        self._topics = []
        self._ping_interval = 20
        self._ping_task = None

    async def connect(self, topics: List[str]):
        """Connect to WS and subscribe to topics with aggressive reconnection logic."""
        self._topics = topics
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
                    logger.info("ws_connected", url=self.url)
                    reconnect_delay = 5 # Reset delay on success
                    
                    # Subscribe
                    await self.subscribe(topics)
                    
                    # Start Ping Task
                    if self._ping_task:
                        self._ping_task.cancel()
                    self._ping_task = asyncio.create_task(self._keep_alive())
                    
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_message(msg.data)
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            logger.warning("ws_connection_closed")
                            break
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error("ws_error", error=str(ws.exception()))
                            break
            except Exception as e:
                logger.error("ws_connection_failed", error=str(e), next_retry=f"{reconnect_delay}s")
                if self._session and not self._session.closed:
                    await self._session.close()
                self._session = None # Force new session on next attempt

            if self._running:
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)

    async def subscribe(self, topics: List[str]):
        if not self._ws:
            return
        req = {
            "op": "subscribe",
            "args": topics
        }
        await self._ws.send_json(req)
        logger.info("ws_subscribed", topics=topics)

    async def _keep_alive(self):
        while self._running:
            await asyncio.sleep(self._ping_interval)
            if self._ws and not self._ws.closed:
                try:
                    await self._ws.send_json({"op": "ping"})
                    logger.debug("ws_ping")
                except Exception as e:
                    logger.error("ws_ping_error", error=str(e))
                    break

    async def _handle_message(self, data: str):
        try:
            msg = json.loads(data)
            
            # Handle Ping/Pong
            if msg.get("op") == "pong":
                return
                
            topic = msg.get("topic", "")
            
            if msg.get("type") == "snapshot" or msg.get("type") == "delta":
                # Generic Market Data (Orderbook/Trade)
                 await event_bus.publish(MarketDataEvent(
                     topic=topic,
                     data=msg.get("data")
                 ))
            
            # Handle Kline Data
            if "kline" in topic:
                for k in msg.get("data", []):
                    # Only emit confirmed (closed) candles or stream updates?
                    # For strategies, we want confirmed candles usually.
                    if k.get("confirm"):
                        await event_bus.publish(KlineEvent(
                            symbol=topic.split(".")[-1],
                            interval=topic.split(".")[1],
                            open=float(k.get("open")),
                            high=float(k.get("high")),
                            low=float(k.get("low")),
                            close=float(k.get("close")),
                            volume=float(k.get("volume")),
                            timestamp=int(k.get("start"))
                        ))
                 
            # Log subscription success
            if msg.get("success") and msg.get("op") == "subscribe":
                logger.info("ws_subscription_success", args=msg.get("ret_msg"))

        except Exception as e:
            logger.error("ws_message_error", error=str(e), data=data[:100])

    async def close(self):
        self._running = False
        if self._ping_task:
            self._ping_task.cancel()
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
