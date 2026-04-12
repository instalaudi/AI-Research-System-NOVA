import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, File, UploadFile
from fastapi.responses import StreamingResponse, Response, FileResponse
from sqlalchemy.orm import Session
import base64

from core.database import User, SessionLocal, get_db
from core.auth import get_current_user, get_current_admin
from core.tts_engine import nova_voice
from core.logging_config import get_logger

from routers.schemas import QueryRequest
from services.chat_service import chat_service
from services.stt_service import stt_service
from services.memory_service import memory_service
from agents.developer_agent import developer_agent
from core.project_manager import project_manager

logger = get_logger("routers.chat")
router = APIRouter(tags=["chat"])

@router.post("/stt")
async def speech_to_text(request: Request, audio: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """
    Delegates speech-to-text processing to STTService.
    """
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
async def ask_knowledge(request: Request, req: QueryRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Standard Query endpoint. Delegates to ChatService for orchestration."""
    files_context = _get_files_context(req)
    return await chat_service.handle_standard_query(req.query, req.images, files_context, current_user.id, db)

@router.post("/query/stream")
async def ask_knowledge_stream(request: Request, req: QueryRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Streaming Query endpoint. Delegates to ChatService context and generator."""
    files_context = _get_files_context(req)
    # El db se pasa al generador y FastAPI asegura que la sesión se mantenga abierta
    # hasta que la StreamingResponse finalice.
    
    async def stream_with_cleanup():
        try:
            async for chunk in chat_service.stream_orchestrator(req.query, req.images, files_context, current_user.id, db):
                yield chunk
        finally:
            db.close()
    
    return StreamingResponse(
        stream_with_cleanup(),
        media_type="text/event-stream"
    )

@router.post("/query/voice")
async def ask_with_voice(request: Request, req: QueryRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Combined Audio/Text endpoint. Uses ChatService + TTS Synthesis."""
    files_context = _get_files_context(req)
    result = await chat_service.handle_standard_query(req.query, req.images, files_context, current_user.id, db)
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

@router.post("/project/build")
async def build_project_zip(request: Request, req: QueryRequest, current_user: User = Depends(get_current_user)):
    """
    Experimental Endpoint: Uses the Developer Agent to divide a requirement 
    into multiple files, zip them, and return the archive for download.
    """
    try:
        # Build virtual payload logic dict {path: content}
        files_dict = await developer_agent.build_project(req.query)
        
        # Package to ZIP file
        zip_path = project_manager.package_project(
            files_dict, 
            project_name="nova_project_" + str(current_user.id)
        )
        
        # Return physical file stream for downloading
        return FileResponse(
            path=zip_path, 
            media_type='application/zip', 
            filename=zip_path.split("/")[-1].split("\\")[-1]
        )
    except Exception as e:
        logger.error(f"Project building failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{filename}")
async def download_project_zip(filename: str):
    """
    Serves the statically generated ZIP files created by the Developer Builder.
    v10.7.0: Seguridad reforzada contra Path Traversal usando pathlib.
    """
    from pathlib import Path
    
    BASE_PROJECT_DIR = Path("data/projects").resolve()
    
    # SECURITY: Prevent Path Traversal attacks
    safe_filename = Path(filename).name
    file_path = (BASE_PROJECT_DIR / safe_filename).resolve()
    
    if not file_path.is_relative_to(BASE_PROJECT_DIR):
        raise HTTPException(status_code=403, detail="Acceso denegado a esta ruta.")
    
    if not safe_filename.endswith(".zip") or not safe_filename.startswith("nova_project_"):
        raise HTTPException(status_code=403, detail="Acceso denegado a este tipo de archivo.")
        
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="El proyecto expir expir o no existe.")
    
    return FileResponse(
        path=str(file_path),
        media_type="application/zip",
        filename=filename
    )

