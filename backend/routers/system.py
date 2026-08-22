from fastapi import APIRouter, Depends, HTTPException
from core.database import User, get_db
from core.auth import get_current_user, get_current_admin
from services.system_service import system_service, FEATURE_FLAG_KEYS
from core.logging_config import get_logger
from core.llm_gateway import llm_gateway
from routers.schemas import FeatureFlagsUpdate

logger = get_logger("routers.system")
router = APIRouter(tags=["system"])

@router.get("/health", dependencies=[Depends(get_current_admin)])
async def health_check():
    """Basic health check and queue status."""
    return await system_service.get_health_status()

@router.get("/status", dependencies=[Depends(get_current_admin)])
async def get_status():
    """Current agent activity and logs."""
    return await system_service.get_agent_logs()

@router.get("/llm/lanes", dependencies=[Depends(get_current_admin)])
async def get_llm_lane_metrics():
    """Observabilidad por lane del gateway LLM (realtime vs batch)."""
    return {"status": "ok", "lanes": llm_gateway.get_lane_metrics()}


@router.get("/system/features", dependencies=[Depends(get_current_admin)])
async def get_automation_features():
    """Estado de procesos autónomos (Panel de control)."""
    flags = system_service.get_feature_flags()
    return {"status": "ok", "features": flags, "keys": list(FEATURE_FLAG_KEYS)}


@router.put("/system/features", dependencies=[Depends(get_current_admin)])
async def put_automation_features(body: FeatureFlagsUpdate):
    """Actualiza uno o varios flags de automatización."""
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="Ningún campo para actualizar.")
    for k in patch:
        if k not in FEATURE_FLAG_KEYS:
            raise HTTPException(status_code=400, detail=f"Flag desconocido: {k}")
    updated = system_service.patch_feature_flags(patch)
    return {"status": "ok", "features": updated}


@router.post("/system/features/preset/focus", dependencies=[Depends(get_current_admin)])
async def preset_automation_focus():
    """Modo piloto: desactiva destilación, evolución, proactivo e investigación autónoma en cola."""
    updated = system_service.apply_feature_preset_focus()
    return {"status": "ok", "preset": "focus", "features": updated}


@router.post("/system/features/preset/full", dependencies=[Depends(get_current_admin)])
async def preset_automation_full():
    """Reactiva todo el comportamiento autónomo por defecto."""
    updated = system_service.apply_feature_preset_full()
    return {"status": "ok", "preset": "full", "features": updated}

@router.get("/stats", dependencies=[Depends(get_current_admin)])
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


@router.post("/vector-db/cleanup", dependencies=[Depends(get_current_admin)])
async def cleanup_vector_db():
    """
    FIX M-4 (Auditoría v11.9.18): Limpia documentos huérfanos en ChromaDB.
    Sincroniza con KnowledgeEntry activos en SQLite.
    ADMIN ONLY.
    """
    from core.vector_db import vector_db
    result = await vector_db.cleanup_orphans()
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
    return result


@router.get("/vector-db/stats", dependencies=[Depends(get_current_admin)])
async def get_vector_db_stats():
    """Returns document counts across all ChromaDB collections."""
    from core.vector_db import vector_db
    return {"status": "ok", "collections": vector_db.get_document_count()}


# ═══════════════════════════════════════════════════════
#  DIAGNOSTICS — Chunking Optimizer + Lessons Learned
#  (Fase 2 Skills Integration v12.0.0)
# ═══════════════════════════════════════════════════════

@router.get("/diagnostics/chunking", dependencies=[Depends(get_current_admin)])
async def diagnostics_chunking():
    """
    Evalúa la calidad del chunking del corpus actual de NOVA.
    Toma una muestra de los últimos 50 documentos en ChromaDB y analiza
    tamaño, coherencia y calidad de los cortes.
    """
    from core.vector_db import vector_db
    import asyncio

    try:
        # Obtener muestra de chunks actuales
        sample = await asyncio.to_thread(
            vector_db.collection.get,
            limit=50,
            include=["documents"]
        )
        documents = sample.get("documents", [])
        if not documents:
            return {"status": "ok", "message": "No hay documentos para analizar."}

        from core.chunking_optimizer import ChunkingOptimizer
        analysis = ChunkingOptimizer.analyze_chunks(documents)
        return {"status": "ok", "analysis": analysis}
    except Exception as e:
        logger.error(f"Error en diagnóstico de chunking: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics/lessons", dependencies=[Depends(get_current_admin)])
async def diagnostics_lessons():
    """Estadísticas del sistema de lecciones aprendidas."""
    from core.lessons_learned import lessons_db
    return {
        "status": "ok",
        "stats": lessons_db.stats(),
        "recent_lessons": [l.to_dict() for l in lessons_db.get_lessons(limit=10)],
        "recent_corrections": [c.to_dict() for c in lessons_db.get_corrections(limit=10)],
    }


@router.get("/lessons/warnings/{context}", dependencies=[Depends(get_current_admin)])
async def get_context_warnings(context: str):
    """
    Obtiene advertencias basadas en lecciones pasadas para un contexto dado.
    Ej: GET /api/lessons/warnings/project_build
    """
    from core.lessons_learned import lessons_db
    warnings = lessons_db.get_context_warnings(context)
    return {"status": "ok", "context": context, "warnings": warnings, "count": len(warnings)}


# ═══════════════════════════════════════════════════════
#  VISION — Webcam & Screen Capture (v13.8.18)
# ═══════════════════════════════════════════════════════

@router.post("/vision/webcam/capture")
async def capture_webcam(current_user: User = Depends(get_current_user)):
    """
    v13.8.18: Captura un frame de la cámara web del usuario.
    Retorna la imagen como base64 para preview en el frontend.
    """
    from services.vision_service import vision_service
    import asyncio
    
    result = await asyncio.to_thread(vision_service.capture_webcam)
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error", "Cámara no disponible"))
    
    return {
        "status": "ok",
        "image_b64": result["b64"],
        "resolution": result.get("resolution", "unknown"),
    }


@router.post("/vision/webcam/analyze")
async def analyze_webcam(request_body: dict = None, current_user: User = Depends(get_current_user)):
    """
    v13.8.18: Captura un frame de la webcam y lo envía al modelo de visión para análisis.
    Body opcional: {"prompt": "¿Qué ves en esta imagen?"}
    """
    from services.vision_service import vision_service
    import asyncio
    
    # 1. Capturar frame
    result = await asyncio.to_thread(vision_service.capture_webcam)
    if not result.get("success"):
        raise HTTPException(status_code=503, detail=result.get("error", "Cámara no disponible"))
    
    b64_image = result["b64"]
    
    # 2. Enviar al modelo de visión con prompt en inglés para máxima precisión en Moondream
    vision_prompt = "Describe what is shown in this webcam image in detail. Identify any people, expressions, objects, text, and surroundings."
    if request_body and request_body.get("prompt"):
        user_req = request_body["prompt"]
        if any(c in user_req.lower() for c in ["describe", "que", "qué", "ves", "vez"]):
            vision_prompt = "Describe what is shown in this webcam image in detail. Identify any people, expressions, objects, text, and surroundings."
    
    raw_analysis = await llm_gateway.chat(
        [{"role": "user", "content": vision_prompt}],
        lane="realtime",
        images=[b64_image],
        priority=0,
        agent_name="vision"
    )
    
    # 3. Formatear y traducir al español de forma natural usando el modelo de lenguaje
    final_spanish = raw_analysis.strip() if raw_analysis else "No pude analizar la imagen."
    if raw_analysis and len(raw_analysis.strip()) > 5:
        try:
            translation = await llm_gateway.chat(
                [
                    {"role": "system", "content": "Eres el asistente de visión de NOVA. Transmite en español natural, fluido y conciso lo que se ve en la cámara web a partir del análisis visual."},
                    {"role": "user", "content": f"Análisis visual de la cámara: '{raw_analysis}'. Descríbelo al usuario en español."}
                ],
                lane="fast",
                priority=0,
                agent_name="planner"
            )
            if translation and len(translation.strip()) > 5:
                final_spanish = translation.strip()
        except Exception:
            pass

    return {
        "status": "ok",
        "image_b64": b64_image,
        "resolution": result.get("resolution", "unknown"),
        "analysis": final_spanish,
    }

