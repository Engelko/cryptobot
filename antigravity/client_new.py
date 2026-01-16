import asyncio
import json
from typing import Optional, Dict, List, Any
from urllib.parse import urlencode

from antigravity.config import settings
from antigravity.logging import get_logger
from antigravity.auth import Authentication
from antigravity.exceptions import APIError, AntigravityError

logger = get_logger("bybit_client")

class BybitClient:
    def __init__(self):
        self.api_key = settings.BYBIT_API_KEY
        self.api_secret = settings.BYBIT_API_SECRET
        self.testnet = settings.BYBIT_TESTNET
        self.base_url = "https://api-testnet.bybit.com" if self.testnet else "https://api.bybit.com"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, endpoint: str, payload: Dict[str, Any] = None, params: Dict[str, Any] = None, suppress_error_log: bool = False) -> Any:
        url = self.base_url + endpoint
        headers = {
            "Content-Type": "application/json"
        }
        
        # Add authentication for private endpoints
        if endpoint.startswith("/v5/") and not endpoint.startswith("/v5/market/"):
            auth = Authentication(self.api_key, self.api_secret)
            timestamp = str(auth._get_timestamp())
            recv_window = str(5000)
            if payload is None:
                payload_str = ""
            else:
                payload_str = json.dumps(payload, separators=(",", ":"))
            
            sign = auth._sign(payload_str + timestamp + recv_window)
            headers.update({
                "X-BAPI-API-KEY": self.api_key,
                "X-BAPI-SIGN": sign,
                "X-BAPI-SIGN-TYPE": "2",
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": recv_window
            })

        session = await self._get_session()
        
        try:
            if method == "GET":
                if params:
                    url += "?" + urlencode(params)
                async with session.get(url, headers=headers) as response:
                    data = await response.json()
                    if response.status != 200:
                        raise APIError(f"HTTP {response.status}: {data}")
                    return data.get("result", data)
            elif method == "POST":
                async with session.post(url, headers=headers, json=payload) as response:
                    data = await response.json()
                    if response.status != 200:
                        raise APIError(f"HTTP {response.status}: {data}")
                    return data.get("result", data)
        except Exception as e:
            if not suppress_error_log:
                logger.error("api_request_failed", method=method, url=url, error=str(e))
            raise

    async def get_kline(self, symbol: str, interval: str, limit: int = 200) -> List[Dict]:
        """
        Get Kline data.
        """
        endpoint = "/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": str(limit)
        }
        
        res = await self._request("GET", endpoint, params)
        return res.get("list", []) if res else []

    async def place_order(self, category: str, symbol: str, side: str, orderType: str, qty: str, price: str = None, timeInForce: str = "GTC") -> Dict:
        """
        Place Order.
        """
        endpoint = "/v5/order/create"
        payload = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": orderType,
            "qty": qty,
            "timeInForce": timeInForce
        }
        
        if price:
            payload["price"] = price

        res = await self._request("POST", endpoint, payload)
        return res

    async def get_server_time(self) -> int:
         endpoint = "/v5/market/time"
         res = await self._request("GET", endpoint)
         return int(res.get("timeSecond"))

    async def get_wallet_balance(self, coin: str = "USDT") -> Dict[str, Any]:
        """
        Get Wallet Balance. Tries UNIFIED then CONTRACT (Standard).
        """
        endpoint = "/v5/account/wallet-balance"

        # 1. Try UNIFIED
        try:
            params = {"accountType": "UNIFIED", "coin": coin}
            # Suppress errors (like 10001) during probing
            res = await self._request("GET", endpoint, params, suppress_error_log=True)
            if res and "list" in res and len(res["list"]) > 0:
                 return res["list"][0]
        except Exception as e:
            logger.debug(f"Unified balance fetch failed: {e}")

        # 2. Try CONTRACT (Standard Account)
        try:
            params = {"accountType": "CONTRACT", "coin": coin}
            # Suppress errors during probing
            res = await self._request("GET", endpoint, params, suppress_error_log=True)
            if res and "list" in res and len(res["list"]) > 0:
                 return res["list"][0]
        except Exception as e:
            logger.debug(f"Contract balance fetch failed: {e}")

        return {}

    async def get_positions(self, category: str = "linear", symbol: str = None) -> List[Dict]:
        """
        Get Open Positions.
        """
        endpoint = "/v5/position/list"
        params = {
            "category": category,
            "settleCoin": "USDT"  # For linear, usually settleCoin is USDT
        }
        if symbol:
            params["symbol"] = symbol

        res = await self._request("GET", endpoint, params)
        return res.get("list", []) if res else []

    async def get_open_orders(self, category: str = "linear", symbol: str = None) -> List[Dict]:
        """
        Get Open Orders.
        """
        endpoint = "/v5/order/realtime"
        params = {
            "category": category
        }
        if symbol:
            params["symbol"] = symbol

        res = await self._request("GET", endpoint, params)
        return res.get("list", []) if res else []

    async def get_closed_pnl(self, category: str = "linear", symbol: str = None, limit: int = 50) -> List[Dict]:
        """
        Get Closed PnL (History).
        """
        endpoint = "/v5/position/closed-pnl"
        params = {
            "category": category,
            "limit": limit
        }
        if symbol:
            params["symbol"] = symbol
        elif category == "linear":
            params["settleCoin"] = "USDT"

        res = await self._request("GET", endpoint, params)
        return res.get("list", [])

    async def set_leverage(self, category: str = "linear", symbol: str = "", buyLeverage: str = "", sellLeverage: str = "") -> bool:
        """
        Set Leverage for a symbol.
        """
        endpoint = "/v5/position/set-leverage"
        payload = {
            "category": category,
            "symbol": symbol
        }
        
        # Set leverage for both buy and sell sides
        if buyLeverage:
            payload["buyLeverage"] = buyLeverage
        if sellLeverage:
            payload["sellLeverage"] = sellLeverage
            
        try:
            res = await self._request("POST", endpoint, payload)
            return res and res.get("retCode") == 0
        except Exception as e:
            logger.error("set_leverage_failed", symbol=symbol, leverage=buyLeverage, error=str(e))
            return False