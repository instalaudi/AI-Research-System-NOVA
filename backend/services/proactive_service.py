import httpx
from typing import Dict, Any, Optional
from core.proactive import nova_proactive, TELEGRAM_API
from core.logging_config import get_logger

logger = get_logger("services.proactive")

class ProactiveService:
    def __init__(self):
        pass

    async def handle_telegram_webhook(self, update: Dict[str, Any]) -> Dict[str, Any]:
        result = await nova_proactive.process_telegram_update(update)
        return {"ok": True, "result": result}

    def get_proactive_status(self) -> Dict[str, Any]:
        return nova_proactive.get_status()

    def trigger_proactive_check(self, background_tasks: Any):
        background_tasks.add_task(nova_proactive.check_and_act)
        logger.info("Manual proactive check triggered.")
        return {"status": "Revisión iniciada"}

    async def send_notification(self, message: str) -> Dict[str, Any]:
        sent = await nova_proactive.notify(message, initiative="manual")
        logger.info(f"Manual notification sent: {sent}")
        return {"sent": sent, "message": message}

    async def setup_telegram_webhook(self, public_url: str) -> Dict[str, Any]:
        webhook_url = f"{public_url.rstrip('/')}/telegram/webhook"
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": webhook_url})
            data = r.json()
        
        status = "ok" if data.get("ok") else "error"
        logger.info(f"Telegram webhook setup: {status} at {webhook_url}")
        return {"status": status, "webhook_url": webhook_url, "telegram": data}

proactive_service = ProactiveService()
