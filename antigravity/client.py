import aiohttp
import asyncio
import aiohttp
import json
from typing import Optional, Dict, List, Any
from urllib.parse import urlencode

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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
        if self._session:
            await self._session.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        # Retry on network errors and 5xx/429 server errors (APIError with status >= 500)
        retry=retry_if_exception_type(aiohttp.ClientError),
        reraise=True
    )
    async def _request(self, method: str, endpoint: str, payload: Dict[str, Any] = None, suppress_error_log: bool = False) -> Any:
        # Rate Limiting: Simple sleep to prevent bursting.
        # Ideally this should be a token bucket.
        await asyncio.sleep(0.05)

        session = await self._get_session()
        
        # Prepare Payload
        payload_str = ""
        if method == "GET":
            if payload:
                # Sort params for consistent signature
                payload_str = urlencode(sorted(payload.items()))
        else:
            if payload:
                payload_str = json.dumps(payload)
        
        # Generate Headers
        headers = Authentication.generate_signature(self.api_key, self.api_secret, payload_str)
        
        url = self.base_url + endpoint
        if method == "GET" and payload_str:
            url = f"{url}?{payload_str}"
            
        logger.debug("api_request", method=method, url=url)
        
        try:
            async with session.request(method, url, data=payload_str if method != "GET" else None, headers=headers) as response:
                text = await response.text()
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    raise APIError(f"Invalid JSON: {text}", -1, response.status)
                
                if data.get("retCode") != 0:
                     if not suppress_error_log:
                        logger.error("api_error", ret_code=data.get("retCode"), ret_msg=data.get("retMsg"))
                     raise APIError(data.get("retMsg"), data.get("retCode"), response.status)
                
                return data.get("result")
        except aiohttp.ClientError as e:
            logger.error("network_error", error=str(e))
            raise AntigravityError(f"Network error: {str(e)}")

    async def get_kline(self, symbol: str, interval: str, limit: int = 200) -> List[Dict]:
        """
        Get Kline (Candlestick) data.
        """
        endpoint = "/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        res = await self._request("GET", endpoint, params)
        return res.get("list", [])

    async def place_order(self, category: str, symbol: str, side: str, orderType: str, qty: str, price: str = None, timeInForce: str = "GTC", orderLinkId: str = None) -> Dict:
        """
        Place a new order.
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
        if orderLinkId:
            payload["orderLinkId"] = orderLinkId

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
        return res.get("list", [])

    async def get_open_orders(self, category: str = "linear", symbol: str = None) -> List[Dict]:
        """
        Get Real-time Open Orders.
        """
        endpoint = "/v5/order/realtime"
        params = {
            "category": category,
        }
        if symbol:
            params["symbol"] = symbol
        elif category == "linear":
            params["settleCoin"] = "USDT"

        res = await self._request("GET", endpoint, params)
        return res.get("list", [])

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

    async def set_leverage(self, category: str = "linear", symbol: str = "", leverage: str = "") -> bool:
        """
        Set Leverage for a symbol using Bybit V5 API.
        Accepts a single leverage value and applies it to both Buy and Sell sides (Symmetric Leverage).
        """
        endpoint = "/v5/position/set-leverage"

        # Convert to float for proper numeric format
        try:
            # Default to 1.0 (safe fallback) if empty
            leverage_num = float(leverage) if leverage else 1.0
        except (ValueError, TypeError):
            logger.error("invalid_leverage_format", symbol=symbol, leverage=leverage)
            return False

        # Bybit V5 requires buyLeverage and sellLeverage
        payload = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(leverage_num),
            "sellLeverage": str(leverage_num)
        }
            
        try:
            logger.info("set_leverage_attempt", symbol=symbol, leverage=leverage_num, payload=payload)
            # _request raises APIError if retCode != 0
            res = await self._request("POST", endpoint, payload)

            logger.info("set_leverage_success", symbol=symbol, leverage=leverage_num)
            return True

        except APIError as e:
            # Handle "Leverage not modified" (110043) as success
            if e.code == 110043:
                logger.info("leverage_already_set", symbol=symbol, leverage=leverage_num)
                return True

            logger.error("set_leverage_api_error", symbol=symbol, code=e.code, msg=str(e))
            return False

        except Exception as e:
            logger.error("set_leverage_failed", symbol=symbol, leverage=leverage, error=str(e))
            return False

