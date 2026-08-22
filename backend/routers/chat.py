import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, File, UploadFile
from fastapi.responses import StreamingResponse, Response, FileResponse
from sqlalchemy.orm import Session  # type: ignore
import base64


from core.database import User, SessionLocal, get_db
from core.auth import get_current_user, get_current_admin
from core.tts_engine import nova_voice
from core.logging_config import get_logger
from core.limiter import limiter
from core.config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW

from routers.schemas import QueryRequest
from services.chat_service import chat_service
from services.stt_service import stt_service
from services.memory_service import memory_service
from agents.developer_agent import developer_agent
from core.project_manager import project_manager
from core.config import ENABLE_AUTO_GIT_VERSIONING
from core.git_versioning import git_versioning

logger = get_logger("routers.chat")
router = APIRouter(tags=["chat"])

# v13.9.1 CRÍTICO FIX: Validación de tamaño de archivo
MAX_AUDIO_SIZE_MB = 50  # Límite de 50MB para archivos de audio
MAX_UPLOAD_SIZE_MB = 100  # Límite genérico de upload

@router.post("/stt")
async def speech_to_text(request: Request, audio: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """
    Delegates speech-to-text processing to STTService.
    v13.9.1: Agregar validación de tamaño de archivo.
    """
    # v13.9.1 FIX: Validar tamaño antes de procesar
    if audio.size and audio.size > MAX_AUDIO_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large (max {MAX_AUDIO_SIZE_MB}MB)"
        )
    stt_model = request.app.state.stt_model
    text = await stt_service.transcribe_audio(audio, stt_model)
    return {"text": text}

def _get_files_context(req: QueryRequest) -> str:
    """v10.7.0: Helper con lmites para extraer contexto de archivos adjuntos."""
    if not req.files: return ""
    # Limitar a los primeros 5 archivos para no saturar el contexto
    files_to_process = req.files[:5]
    context = "\n\n[ARCHIVOS ADJUNTOS]:\n"
    for f in files_to_process:
        # Truncar contenido individual a 5000 chars
        context += f"{f.name}: {f.content[:5000]}\n"
    
    # Truncar contexto total a 20,000 para no exceder la ventana del LLM
    if len(context) > 20000:
        context = context[:19997] + "..."
    return context

@router.post("/query")
@limiter.limit(f"{RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW} second")
async def ask_knowledge(request: Request, req: QueryRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Standard Query endpoint. Delegates to ChatService for orchestration."""
    logger.debug(f"/query received query={req.query!r} images={len(req.images or [])} files={len(req.files or [])}")
    files_context = _get_files_context(req)
    # v11.9.7: Pasamos background_tasks para Memoria
    return await chat_service.handle_standard_query(req.query, req.images, files_context, current_user.id, db, mode=req.mode, background_tasks=background_tasks)

@router.post("/query/stream")
@limiter.limit(f"{RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW} second")
async def ask_knowledge_stream(request: Request, req: QueryRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logger.debug(f"/query/stream received query={req.query!r} images={len(req.images or [])} files={len(req.files or [])}")
    """Streaming Query endpoint. Delegates to ChatService context and generator."""
    files_context = _get_files_context(req)
    # El db se pasa al generador y FastAPI asegura que la sesión se mantenga abierta
    # hasta que la StreamingResponse finalice.
    
    async def stream_with_cleanup():
        try:
            # v11.9.7: Pasamos background_tasks para Memoria
            async for chunk in chat_service.stream_orchestrator(req.query, req.images, files_context, current_user.id, db, mode=req.mode, background_tasks=background_tasks):
                yield chunk
        finally:
            db.close()
    
    return StreamingResponse(
        stream_with_cleanup(),
        media_type="text/event-stream"
    )

@router.post("/query/voice")
@limiter.limit(f"{RATE_LIMIT_REQUESTS}/{RATE_LIMIT_WINDOW} second")
async def ask_with_voice(request: Request, req: QueryRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Combined Audio/Text endpoint. Uses ChatService + TTS Synthesis."""
    logger.debug(f"/query/voice received query={req.query!r} images={len(req.images or [])} files={len(req.files or [])}")
    files_context = _get_files_context(req)
    result = await chat_service.handle_standard_query(req.query, req.images, files_context, current_user.id, db, mode=req.mode)
    text_response = result.get("answer", "No pude generar respuesta.")
    
    audio = await nova_voice.synthesize(text_response)
    if audio:
        return {
            "text": text_response, 
            "audio_b64": base64.b64encode(audio).decode("utf-8"), 
            "audio_type": "audio/wav", 
            "has_audio": True
        }
    return {"text": text_response, "has_audio": False}

@router.get("/audio/{cache_key}")
async def get_audio_chunk(cache_key: str):
    """
    v13.7.2: Entrega fragmentos de audio de la caché para streaming.
    Utilizado por el flujo de chat para reproducir voz frase por frase.
    """
    import asyncio
    from core.tts_engine import CACHE_DIR
    path = CACHE_DIR / f"{cache_key}.wav"
    
    # Esperar hasta 15 segundos a que la tarea de fondo de síntesis termine
    for _ in range(150):
        if path.exists():
            break
        await asyncio.sleep(0.1)
        
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio chunk not found or synthesis timed out")
    return FileResponse(path, media_type="audio/wav")


@router.post("/tts")
async def text_to_speech(request: Request, current_user: User = Depends(get_current_user)):
    body = await request.json()
    text, speed = body.get("text", "").strip(), float(body.get("speed", 1.0))
    if not text: raise HTTPException(status_code=400, detail="Text empty")
    
    audio = await nova_voice.synthesize(text, speed=speed)
    if not audio: raise HTTPException(status_code=503, detail="TTS Unavailable")
    
    return Response(
        content=audio, 
        media_type="audio/wav", 
        headers={"Content-Disposition": "inline; filename=nova_voice.wav"}
    )

@router.post("/tts/stream")
@router.post("/chat/tts/stream")
async def stream_text_to_speech(request: Request, current_user: User = Depends(get_current_user)):

    """
    v14.0: Emite fragmentos de audio en streaming mediante StreamingResponse.
    Permite al frontend reproducir audio a medida que se sintetiza con Time-to-First-Audio < 300ms.
    """
    body = await request.json()
    text = body.get("text", "").strip()
    speed = float(body.get("speed", 1.0))
    if not text:
        raise HTTPException(status_code=400, detail="Text empty")
        
    async def _audio_generator():
        async for chunk in nova_voice.synthesize_stream(text, speed=speed):
            if chunk:
                yield chunk

    return StreamingResponse(
        _audio_generator(),
        media_type="audio/wav",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    )


@router.get("/tts/status")
async def tts_status(current_user: User = Depends(get_current_user)):
    return nova_voice.get_status()

@router.post("/tts/voice")
async def set_nova_voice(request: Request, current_user: User = Depends(get_current_user)):
    body = await request.json()
    voice = body.get("voice", "es_MX-high")
    nova_voice.set_voice(voice)
    await nova_voice.initialize(voice)
    return {"status": "ok", "voice": voice}

@router.delete("/tts/cache")
async def clear_tts_cache(admin: User = Depends(get_current_admin)):
    nova_voice.clear_cache()
    return {"status": "Cache cleared"}

@router.post("/feedback")
async def submit_feedback(request: Request, current_user: User = Depends(get_current_user), db=Depends(get_db)):
    """Allows user to rate a response."""
    body = await request.json()
    message_id = body.get("message_id")
    rating = body.get("rating")
    if rating not in ["good", "bad"]:
        raise HTTPException(status_code=400, detail="Rating must be 'good' or 'bad'")
    
    chat_service.process_feedback(db, current_user.id, message_id, rating)
    return {"status": "success", "message": "Feedback received"}

@router.get("/user/profile")
async def get_user_profile(current_user: User = Depends(get_current_user), db=Depends(get_db)):
    """Returns the consolidated profile for the current user."""
    return chat_service.get_consolidated_profile(db, current_user.id)


@router.get("/user/profile/debug")
async def debug_user_profile(current_user: User = Depends(get_current_admin), db: Session = Depends(get_db)):
    """
    Endpoint de diagnóstico para inspeccionar el perfil bruto y top preferencias.
    Solo admin.
    """
    try:
        from core.user_profile import UserProfile
        profile_service = UserProfile(db)
        raw_profile = profile_service.get_profile(current_user.id)
        top_preferences = profile_service.get_top_preferences(current_user.id, top_n=5)
        return {"status": "success", "raw": raw_profile, "top": top_preferences}
    except Exception as e:
        logger.error(f"Profile debug error: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/project/build")
async def build_project_zip(request: Request, req: QueryRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    v11.9.22: Asynchronous Project Builder.
    Enqueues the build task to the orchestrator via task_queue.
    Prevents HTTP timeouts and allows long-running generations.
    """
    try:
        from core.task_queue import task_queue
        from core.database import ResearchJob
        import datetime
        
        # 1. Create a job entry in the DB
        job = ResearchJob(
            user_id=current_user.id,
            topic=req.query[:100],
            stage="project_build_queued",
            status="pending",
            created_at=datetime.datetime.utcnow()
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # 2. Add task to background queue
        await task_queue.add_task(
            "project_build",
            {"query": req.query},
            topic=req.query[:50],
            job_id=job.id,
            user_id=current_user.id
        )
        
        logger.info(f"[Chat] Project build job {job.id} enqueued for user {current_user.id}")

        return {
            "message": "🏗️ **Construcción Iniciada.** He recibido tu solicitud de software y mis agentes están trabajando en ello. Te avisaré por el chat en cuanto el paquete ZIP esté listo para descargar.",
            "job_id": job.id,
            "status": "queued",
            "action_required": "wait_for_notification"
        }
    except Exception as e:
        logger.error(f"Project building enqueue failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{filename}")
async def download_project_zip(filename: str, current_user: User = Depends(get_current_user)):
    """
    Serves the statically generated ZIP files created by the Developer Builder.
    v10.7.0: Seguridad reforzada contra Path Traversal usando pathlib.
    """
    from pathlib import Path
    
    BASE_PROJECT_DIR = Path("data/projects").resolve()
    
    safe_filename = Path(filename).name
    file_path = (BASE_PROJECT_DIR / safe_filename).resolve()
    
    if not file_path.is_relative_to(BASE_PROJECT_DIR):
        raise HTTPException(status_code=403, detail="Acceso denegado a esta ruta.")
    
    if not safe_filename.endswith(".zip") or not safe_filename.startswith(f"nova_project_{current_user.id}_"):
        raise HTTPException(status_code=403, detail="Acceso denegado a este tipo de archivo.")
        
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="El proyecto expir expir o no existe.")
    
    return FileResponse(
        path=str(file_path),
        media_type="application/zip",
        filename=filename
    )

@router.get("/projects/list")
async def list_user_projects(current_user: User = Depends(get_current_user)):
    """
    Lista todos los proyectos ZIP disponibles para el usuario actual.
    """
    from pathlib import Path
    import os
    
    projects_dir = Path("data/projects")
    if not projects_dir.exists():
        return {"projects": []}
    
    # Buscar archivos ZIP del usuario
    user_projects = []
    for file_path in projects_dir.glob(f"nova_project_{current_user.id}_*.zip"):
        if file_path.is_file():
            stat = file_path.stat()
            user_projects.append({
                "filename": file_path.name,
                "size": stat.st_size,
                "created": stat.st_ctime,
                "download_url": f"/api/download/{file_path.name}"
            })
    
    # Ordenar por fecha de creación (más recientes primero)
    user_projects.sort(key=lambda x: x["created"], reverse=True)
    
    return {"projects": user_projects}

@router.delete("/projects/delete/{filename}")
async def delete_project(filename: str, current_user: User = Depends(get_current_user)):
    """
    Elimina un proyecto ZIP específico del usuario directamente desde el almacenamiento físico.
    """
    from pathlib import Path
    import os
    import shutil
    
    safe_filename = Path(filename).name
    if not safe_filename.startswith(f"nova_project_{current_user.id}_"):
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar este archivo.")
    
    projects_dir = Path("data/projects").resolve()
    file_path = (projects_dir / safe_filename).resolve()
    if not file_path.is_relative_to(projects_dir):
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar este archivo.")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Proyecto no encontrado.")
    
    try:
        # Eliminar archivo ZIP físico en disco
        os.remove(file_path)
        
        # Eliminar directorio extraído asociado si existe
        extracted_dir = projects_dir / f"{safe_filename.replace('.zip', '')}_extracted"
        if extracted_dir.exists() and extracted_dir.is_dir():
            shutil.rmtree(extracted_dir)
            
        return {"success": True, "message": f"Proyecto {filename} eliminado correctamente."}
    except Exception as e:
        logger.error(f"Error al eliminar proyecto {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar el archivo físico: {str(e)}")

@router.delete("/projects/clear-all")
async def clear_all_projects(current_user: User = Depends(get_current_user)):
    """
    Elimina TODOS los proyectos del usuario actual.
    """
    from pathlib import Path
    import os
    import shutil
    
    projects_dir = Path("data/projects")
    if not projects_dir.exists():
        return {"success": True, "deleted_count": 0}
        
    deleted_count = 0
    # Buscar todos los archivos y carpetas que empiezan con el ID del usuario
    for path in projects_dir.glob(f"nova_project_{current_user.id}_*"):
        try:
            if path.is_file():
                os.remove(path)
                deleted_count += 1
            elif path.is_dir():
                shutil.rmtree(path)
        except Exception as e:
            logger.warning(f"No se pudo eliminar {path}: {e}")
            continue
            
    return {"success": True, "deleted_count": deleted_count}


# SPRINT 1.1: Endpoints para Snippet Cache

@router.get("/snippets/search")
async def search_snippets(
    query: str,
    snippet_type: str = None,
    language: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Busca snippets guardados en caché.
    
    Query params:
    - query: Termino de búsqueda
    - snippet_type: Filtrar por tipo (opcional)
    - language: Filtrar por lenguaje (opcional)
    """
    try:
        from core.snippet_cache import SnippetCache
        
        snippet_cache = SnippetCache(db)
        results = snippet_cache.search(
            user_id=current_user.id,
            query=query,
            snippet_type=snippet_type,
            language=language,
            limit=10
        )
        
        return {"status": "success", "count": len(results), "results": results}
    
    except Exception as e:
        logger.error(f"Error en búsqueda de snippets: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/snippets/similar")
async def get_similar_snippets(
    req: QueryRequest,
    snippet_type: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Encuentra snippets similares basado en código.
    """
    try:
        from core.snippet_cache import SnippetCache
        
        snippet_cache = SnippetCache(db)
        results = snippet_cache.get_similar(
            user_id=current_user.id,
            code=req.query,  # Usar query como código
            snippet_type=snippet_type,
            similarity_threshold=0.85
        )
        
        return {"status": "success", "count": len(results), "results": results}
    
    except Exception as e:
        logger.error(f"Error encontrando similares: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/snippets/similar")
async def get_similar_snippets_get(
    code: str,
    snippet_type: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Versión GET para compatibilidad con clientes que envían ?code=...
    """
    try:
        from core.snippet_cache import SnippetCache

        snippet_cache = SnippetCache(db)
        results = snippet_cache.get_similar(
            user_id=current_user.id,
            code=code,
            snippet_type=snippet_type,
            similarity_threshold=0.90
        )
        return {"status": "success", "count": len(results), "results": results}
    except Exception as e:
        logger.error(f"Error encontrando similares (GET): {e}")
        return {"status": "error", "message": str(e)}


@router.get("/snippets/by-type/{snippet_type}")
async def get_snippets_by_type(
    snippet_type: str,
    language: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene snippets guardados por tipo.
    
    Path params:
    - snippet_type: Tipo de snippet (ej: 'react_component', 'python_function')
    
    Query params:
    - language: Filtrar por lenguaje (opcional)
    """
    try:
        from core.snippet_cache import SnippetCache
        
        snippet_cache = SnippetCache(db)
        results = snippet_cache.get_by_type(
            user_id=current_user.id,
            snippet_type=snippet_type,
            language=language,
            limit=20
        )
        
        return {"status": "success", "count": len(results), "results": results}
    
    except Exception as e:
        logger.error(f"Error obteniendo por tipo: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/snippets/stats")
async def get_snippet_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Obtiene estadísticas del caché del usuario.
    """
    try:
        from core.snippet_cache import SnippetCache
        
        snippet_cache = SnippetCache(db)
        stats = snippet_cache.get_stats(user_id=current_user.id)
        
        return {"status": "success", "stats": stats}
    
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        return {"status": "error", "message": str(e)}


@router.delete("/snippets/{snippet_id}")
async def delete_snippet(
    snippet_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Elimina un snippet del caché.
    """
    try:
        from core.snippet_cache import SnippetCache
        
        snippet_cache = SnippetCache(db)
        success = snippet_cache.delete(
            user_id=current_user.id,
            snippet_id=snippet_id
        )
        
        if success:
            return {"status": "success", "message": "Snippet deletado"}
        else:
            return {"status": "error", "message": "Snippet no encontrado"}
    
    except Exception as e:
        logger.error(f"Error deletando snippet: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/history/search")
async def search_history(
    query: str,
    current_user: User = Depends(get_current_user)
):
    """
    SPRINT 1.3: Búsqueda semántica de historial de código.
    """
    try:
        from core.vector_db import vector_db
        results = await vector_db.search_code_history(query=query, user_id=current_user.id, limit=10)
        return {"status": "success", "count": len(results), "results": results}
    except Exception as e:
        logger.error(f"Error en historial semántico: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/git/history")
async def get_git_history(
    limit: int = 20,
    snapshots_only: bool = False,
    current_user: User = Depends(get_current_user)
):
    """
    Retorna historial de commits del repo local.
    snapshots_only=true filtra por data/project_snapshots.
    """
    try:
        path_filter = "data/project_snapshots" if snapshots_only else None
        result = git_versioning.get_history(limit=limit, path_filter=path_filter)
        return result
    except Exception as e:
        logger.error(f"Git history error: {e}")
        return {"status": "error", "message": str(e), "commits": []}


@router.get("/git/diff/{commit_hash}")
async def get_git_diff(
    commit_hash: str,
    current_user: User = Depends(get_current_user)
):
    """
    Retorna diff detallado de un commit.
    """
    try:
        return git_versioning.get_diff(commit_hash=commit_hash)
    except Exception as e:
        logger.error(f"Git diff error: {e}")
        return {"status": "error", "message": str(e), "diff": ""}


