from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from typing import List
import os
from io import BytesIO
from core.database import User, get_db
from core.auth import get_current_user
from services.memory_service import memory_service
from core.logging_config import get_logger

logger = get_logger("routers.memory")
router = APIRouter(tags=["memory"])

@router.post("/library/upload")
async def upload_books(files: List[UploadFile] = File(...), current_user: User = Depends(get_current_user)):
    """
    v11.4: Recibe múltiples libros (PDF, EPUB, TXT) y los procesa en cola.
    """
    MAX_SIZE = 50 * 1024 * 1024
    allowed_exts = {".pdf", ".epub", ".txt"}
    
    results = []
    
    for file in files:
        # Validación de tamaño
        file_size = 0
        if hasattr(file, "size") and file.size:
            file_size = file.size
        else:
            content = await file.read()
            file_size = len(content)
            await file.seek(0)
        
        if file_size > MAX_SIZE:
            results.append({"file": file.filename, "status": "error", "message": "Archivo demasiado grande (Max 50MB)"})
            continue

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_exts:
            results.append({"file": file.filename, "status": "error", "message": "Formato no soportado"})
            continue

        logger.info(f"Queueing book: {file.filename} (Size: {file_size}) by user {current_user.id}")
        
        # Procesamos el libro (el Librarian se encarga de la cola secuencial internamente)
        result = await memory_service.ingest_document(file.file, file.filename, current_user.id)
        
        if result is True:
            results.append({"file": file.filename, "status": "success"})
        elif isinstance(result, dict) and result.get("status") == "duplicate":
            results.append({
                "file": file.filename, 
                "status": "duplicate", 
                "message": f"Ya existe en la biblioteca como '{result.get('title')}'"
            })
        else:
            results.append({"file": file.filename, "status": "error", "message": "Fallo en la absorción técnica"})
    
    return {
        "status": "completed",
        "processed": len(results),
        "details": results
    }

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
