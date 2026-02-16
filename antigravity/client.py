import aiohttp
import asyncio
import aiohttp
import json
from typing import Optional, Dict, List, Any
from urllib.parse import urlencode

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
import logging

from antigravity.config import settings
from antigravity.logging import get_logger
from antigravity.auth import Authentication
from antigravity.exceptions import APIError, AntigravityError
from antigravity.utils import safe_float

logger = get_logger("bybit_client")

RETRYABLE_API_CODES = [
    110007,  # Insufficient balance (might be temporary)
    10001,   # Rate limit
    10016,   # Server error
]

class RetryableAPIError(APIError):
    """API Error that should trigger a retry."""
    pass

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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.bybit.com/"
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, RetryableAPIError)),
        reraise=True
    )
    async def _request(self, method: str, endpoint: str, payload: Dict[str, Any] = None, suppress_error_log: bool = False, ignorable_ret_codes: List[int] = None) -> Any:
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
                
                ret_code = data.get("retCode")
                if ret_code != 0:
                    if not suppress_error_log and (not ignorable_ret_codes or ret_code not in ignorable_ret_codes):
                        logger.error("api_error", ret_code=ret_code, ret_msg=data.get("retMsg"))
                    if ret_code in RETRYABLE_API_CODES:
                        logger.warning("api_error_retryable", ret_code=ret_code, ret_msg=data.get("retMsg"))
                        raise RetryableAPIError(data.get("retMsg"), ret_code, response.status)
                    raise APIError(data.get("retMsg"), ret_code, response.status)
                
                return data.get("result")
        except aiohttp.ClientError as e:
            # Re-raise ClientError so tenacity can handle retries
            logger.warning("network_error_retry", error=str(e))
            raise e

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

    async def get_ticker(self, symbol: str, category: str = "linear") -> Dict:
        """
        Get ticker data for a symbol.
        """
        endpoint = "/v5/market/tickers"
        params = {
            "category": category,
            "symbol": symbol
        }
        res = await self._request("GET", endpoint, params)
        if res and "list" in res and len(res["list"]) > 0:
            return res["list"][0]
        return {}

    async def get_orderbook(self, symbol: str, category: str = "linear", limit: int = 25) -> Dict:
        """
        Get orderbook data.
        """
        endpoint = "/v5/market/orderbook"
        params = {
            "category": category,
            "symbol": symbol,
            "limit": limit
        }
        return await self._request("GET", endpoint, params)

    async def place_order(self, category: str, symbol: str, side: str, orderType: str, qty: str, price: str = None, timeInForce: str = "GTC", orderLinkId: str = None, stopLoss: str = None, takeProfit: str = None, trailingStop: str = None) -> Dict:
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
        if stopLoss:
            payload["stopLoss"] = stopLoss
        if takeProfit:
            payload["takeProfit"] = takeProfit
        if trailingStop:
            payload["trailingStop"] = trailingStop

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

        # 3. Try SPOT (Standard Account)
        try:
            params = {"accountType": "SPOT", "coin": coin}
            res = await self._request("GET", endpoint, params, suppress_error_log=True)
            if res and "list" in res and len(res["list"]) > 0:
                 return res["list"][0]
        except Exception as e:
            logger.debug(f"Spot balance fetch failed: {e}")

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
        leverage_num = safe_float(leverage, default=1.0)

        # Format leverage string (remove trailing .0 for integers)
        if leverage_num.is_integer():
            leverage_str = str(int(leverage_num))
        else:
            leverage_str = str(leverage_num)

        # Bybit V5 requires buyLeverage and sellLeverage
        payload = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": leverage_str,
            "sellLeverage": leverage_str
        }
            
        try:
            logger.info("set_leverage_attempt", symbol=symbol, leverage=leverage_str, payload=payload)
            # _request raises APIError if retCode != 0
            # Ignore 110043 (Leverage not modified) in the main request logger
            res = await self._request("POST", endpoint, payload, ignorable_ret_codes=[110043])

            logger.info("set_leverage_success", symbol=symbol, leverage=leverage_str)
            return True

        except APIError as e:
            # Handle "Leverage not modified" (110043) as success
            if e.code == 110043:
                logger.info("leverage_already_set", symbol=symbol, leverage=leverage_num)
                return True

            # If error is related to invalid leverage (e.g. decimal not supported), try integer fallback
            # Common codes: 10001 (Params error), 110043 (Not modified - handled above)
            if not leverage_num.is_integer():
                fallback_leverage = str(int(leverage_num))
                logger.info("set_leverage_fallback", symbol=symbol, original=leverage_str, fallback=fallback_leverage, error_code=e.code)

                payload["buyLeverage"] = fallback_leverage
                payload["sellLeverage"] = fallback_leverage

                try:
                    await self._request("POST", endpoint, payload, ignorable_ret_codes=[110043])
                    logger.info("set_leverage_fallback_success", symbol=symbol, leverage=fallback_leverage)
                    return True
                except APIError as e2:
                    if e2.code == 110043:
                        logger.info("leverage_already_set_fallback", symbol=symbol, leverage=fallback_leverage)
                        return True
                    logger.error("set_leverage_fallback_failed", symbol=symbol, code=e2.code, msg=str(e2))
                except Exception as e2:
                    logger.error("set_leverage_fallback_exception", symbol=symbol, error=str(e2))

            logger.error("set_leverage_api_error", symbol=symbol, code=e.code, msg=str(e))
            return False

        except Exception as e:
            logger.error("set_leverage_failed", symbol=symbol, leverage=leverage, error=str(e))
            return False

