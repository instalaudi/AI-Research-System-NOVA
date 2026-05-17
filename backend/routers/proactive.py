from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from urllib.parse import urlparse
from core.database import User
from core.auth import get_current_user, get_current_admin
from services.proactive_service import proactive_service
from services.system_service import system_service
from core.logging_config import get_logger

logger = get_logger("routers.proactive")
router = APIRouter(tags=["proactive"])

@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    import os
    TELEGRAM_SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN", "").strip()
    
    # v10.7.0: Validación de secreto para evitar peticiones maliciosas
    if not TELEGRAM_SECRET_TOKEN:
        logger.warning("Telegram webhook recibido pero TELEGRAM_SECRET_TOKEN no está configurado.")
        raise HTTPException(status_code=403, detail="Webhook no configurado")

    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if token != TELEGRAM_SECRET_TOKEN:
        host = request.client.host if request.client else "unknown"
        logger.warning(f"Webhook recibido con token inválido desde {host}")
        raise HTTPException(status_code=403, detail="Acceso denegado")

    update = await request.json()
    return await proactive_service.handle_telegram_webhook(update)

@router.get("/nova/proactive/status")
async def nova_proactive_status(current_user: User = Depends(get_current_user)):
    return proactive_service.get_proactive_status()

@router.post("/nova/proactive/check")
async def nova_proactive_check(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    if not system_service.is_feature_enabled("proactive"):
        raise HTTPException(
            status_code=403,
            detail="Sistema proactivo desactivado en el Panel de control.",
        )
    return proactive_service.trigger_proactive_check(background_tasks)

@router.post("/nova/notify")
async def nova_send_notification(request: Request, current_user: User = Depends(get_current_user)):
    body = await request.json()
    message = body.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Mensaje vacío")
    return await proactive_service.send_notification(message)

@router.post("/telegram/setup")
async def setup_telegram_webhook(request: Request, admin: User = Depends(get_current_admin)):
    body = await request.json()
    public_url = body.get("public_url", "").strip()
    if not public_url:
        raise HTTPException(status_code=400, detail="URL requerida")

    parsed = urlparse(public_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL inválida")

    return await proactive_service.setup_telegram_webhook(public_url)
