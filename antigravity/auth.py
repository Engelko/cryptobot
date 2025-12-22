import hmac
import hashlib
import time
import json
from typing import Dict, Any

class Authentication:
    @staticmethod
    def generate_signature(api_key: str, api_secret: str, payload: str, recv_window: int = 5000) -> Dict[str, str]:
        """
        Generate headers for Bybit v5 API.
        Payload should be the query string for GET or JSON body string for POST.
        """
        timestamp = str(int(time.time() * 1000))
        
        raw_signature = timestamp + api_key + str(recv_window) + payload
        
        signature = hmac.new(
            api_secret.encode("utf-8"),
            raw_signature.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        
        return {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-SIGN-TYPE": "2",
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": str(recv_window),
            "Content-Type": "application/json"
        }
