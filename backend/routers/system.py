from fastapi import APIRouter, Depends, HTTPException
from core.database import User, get_db
from core.auth import get_current_user, get_current_admin
from services.system_service import system_service
from core.logging_config import get_logger

logger = get_logger("routers.system")
router = APIRouter(tags=["system"])

@router.get("/health")
async def health_check():
    """Basic health check and queue status."""
    return await system_service.get_health_status()

@router.get("/status")
async def get_status():
    """Current agent activity and logs."""
    return await system_service.get_agent_logs()

@router.get("/stats", dependencies=[Depends(get_current_user)])
async def get_system_stats(db=Depends(get_db)):
    """System-wide performance and knowledge stats."""
    try:
        return system_service.get_detailed_stats(db)
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail="Error fetching system stats.")

@router.post("/jobs/clear-failed", dependencies=[Depends(get_current_admin)])
async def clear_failed_jobs(db=Depends(get_db)):
    """Removes failed jobs from history."""
    if system_service.clear_failed_jobs(db):
        return {"status": "success", "message": "Failed jobs cleared"}
    raise HTTPException(status_code=500, detail="Could not clear failed jobs.")

@router.get("/system/failures", dependencies=[Depends(get_current_admin)])
async def get_system_failures(db=Depends(get_db)):
    """Retorna los últimos fallos del sistema no resueltos."""
    return system_service.get_system_failures(db)

@router.get("/test-embeddings", dependencies=[Depends(get_current_admin)])
async def test_embeddings(model: str = "nomic-embed-text"):
    """Internal diagnostic for embedding fallback."""
    return await system_service.test_embeddings(model)

@router.get("/test-cache", dependencies=[Depends(get_current_admin)])
async def test_cache(topic: str = "test"):
    """Internal diagnostic for search cache."""
    return await system_service.test_search_cache(topic)

from routers.schemas import ManualStoreRequest

@router.post("/research/store", dependencies=[Depends(get_current_admin)])
async def store_manual_knowledge(req: ManualStoreRequest):
    """Internal diagnostic for manual knowledge storage (bypassing full pipeline)."""
    from core.knowledge_base import knowledge_base
    try:
        await knowledge_base.add_entry(req.content)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
