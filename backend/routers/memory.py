from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
import os
from io import BytesIO
from core.database import User, get_db
from core.auth import get_current_user
from services.memory_service import memory_service
from core.logging_config import get_logger

logger = get_logger("routers.memory")
router = APIRouter(tags=["memory"])

@router.post("/library/upload")
async def upload_book(file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    """Receives a book (PDF, EPUB, TXT) and processes it through the MemoryService."""
    # v10.7.0: Lmite de tamao de archivo (50 MB)
    MAX_SIZE = 50 * 1024 * 1024
    
    # Intentar obtener el tamao sin leer todo a RAM si es posible
    file_size = 0
    if hasattr(file, "size") and file.size:
        file_size = file.size
    else:
        # Fallback: leer y buscar
        content = await file.read()
        file_size = len(content)
        await file.seek(0)
    
    if file_size > MAX_SIZE:
        raise HTTPException(status_code=413, detail=f"Archivo demasiado grande ({file_size / 1024 / 1024:.1f}MB). El lmite es 50MB.")

    allowed_exts = {".pdf", ".epub", ".txt"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa PDF, EPUB o TXT.")

    logger.info(f"Uploading book: {file.filename} (Size: {file_size}) by user {current_user.id}")
    success = await memory_service.ingest_document(file.file, file.filename, current_user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Error al procesar el libro.")
    
    return {"status": "success", "message": f"Libro '{file.filename}' procesado e indexado correctamente."}

@router.get("/knowledge", dependencies=[Depends(get_current_user)])
async def get_knowledge(
    limit: int = Query(50, ge=1, le=500), 
    offset: int = Query(0, ge=0), 
    db=Depends(get_db)
):
    """
    Lists knowledge entries with pagination (v10.12.0). 
    Prevents browser hangs by limiting initial data volume.
    """
    try:
        return memory_service.list_knowledge(db, limit=limit, offset=offset)
    except Exception as e:
        logger.error(f"Error fetching knowledge: {e}")
        raise HTTPException(status_code=500, detail="Error fetching knowledge.")
