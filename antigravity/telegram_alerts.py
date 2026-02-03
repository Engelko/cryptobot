import aiohttp
import asyncio
import os
from antigravity.logging import get_logger

logger = get_logger("telegram_alerts")

class TelegramAlerts:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)

    async def send_message(self, text: str):
        if not self.enabled:
            return

        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        res_text = await resp.text()
                        logger.error("telegram_send_failed", status=resp.status, response=res_text)
                    else:
                        logger.info("telegram_alert_sent")
        except Exception as e:
            logger.error("telegram_error", error=str(e))

    def send_message_sync(self, text: str):
        """Helper for non-async parts (like startup/shutdown if needed)"""
        if not self.enabled: return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.send_message(text))
            else:
                loop.run_until_complete(self.send_message(text))
        except Exception:
            pass

telegram_alerts = TelegramAlerts()
