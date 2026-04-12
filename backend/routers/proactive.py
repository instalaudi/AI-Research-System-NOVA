from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from core.database import User
from core.auth import get_current_user, get_current_admin
from services.proactive_service import proactive_service
from core.logging_config import get_logger

logger = get_logger("routers.proactive")
router = APIRouter(tags=["proactive"])

@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    import os
    TELEGRAM_SECRET_TOKEN = os.getenv("TELEGRAM_SECRET_TOKEN")
    
    # v10.7.0: Validacin de secreto para evitar peticiones maliciosas
    token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if TELEGRAM_SECRET_TOKEN and token != TELEGRAM_SECRET_TOKEN:
        logger.warning(f"Webhook recibido con token invlido desde {request.client.host}")
        raise HTTPException(status_code=403, detail="Acceso denegado")

    update = await request.json()
    return await proactive_service.handle_telegram_webhook(update)

@router.get("/nova/proactive/status")
async def nova_proactive_status(current_user: User = Depends(get_current_user)):
    return proactive_service.get_proactive_status()

@router.post("/nova/proactive/check")
async def nova_proactive_check(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
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
    public_url = body.get("public_url", "")
    if not public_url:
        raise HTTPException(status_code=400, detail="URL requerida")
    return await proactive_service.setup_telegram_webhook(public_url)
