import aiohttp
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
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()

    async def _request(self, method: str, endpoint: str, payload: Dict[str, Any] = None) -> Any:
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

    async def get_server_time(self) -> int:
         endpoint = "/v5/market/time"
         res = await self._request("GET", endpoint)
         return int(res.get("timeSecond"))

    async def get_wallet_balance(self, coin: str = "USDT") -> Dict[str, Any]:
        """
        Get Unified Account Wallet Balance.
        """
        endpoint = "/v5/account/wallet-balance"
        params = {
            "accountType": "UNIFIED",
            "coin": coin
        }
        res = await self._request("GET", endpoint, params)
        # Result structure: { "list": [ { "coin": [ ... ] } ] }
        if res and "list" in res and len(res["list"]) > 0:
             return res["list"][0]
        return {}
