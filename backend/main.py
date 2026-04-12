from fastapi import FastAPI, HTTPException, Request, File, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse, Response
from starlette.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session
from pydantic import BaseModel, constr
from typing import List, Optional, Any
from contextlib import asynccontextmanager
import whisper  # type: ignore
import shutil
import tempfile
import os
import datetime
import json
import re
import unicodedata
import asyncio
import subprocess
import uuid
from core.logging_config import setup_logging, request_id_var, get_logger

# AI System Core Imports
from core.orchestrator import orchestrator
from core.task_queue import task_queue
from core.logger import agent_logger
from core.knowledge_base import knowledge_base
from core.config import CORS_ORIGINS, CHAT_HISTORY_MAX_SIZE, MAX_QUERY_LENGTH, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW, COGNITIVE_MODE, LLM_FAST_MODEL
# FIX: Solo importar los prompts que se usan activamente en este módulo.
# Los demás se importan en cada router según necesidad.
from core.health_monitor import run_health_monitor
from core.sandbox import sandbox
from core.database import (
    get_db, SessionLocal, User, UserSession, KnowledgeEntry,
    UserMemory, ChatLog, ResearchJob, init_db
    # KnowledgeNode, GraphLink — usados desde routers/graph, no en main
)
from core.auth import get_password_hash, verify_password, create_access_token, get_current_user, get_current_admin
from core.librarian import librarian
from core.llm_client import llm_client
from core.intent_classifier import classify_intent
# FIX: extract_keywords y escape_like no se usan en main.py — importar en routers según necesidad.
from core.vector_db import vector_db
from core.controller import cognitive_controller
from core.config import LLM_MODEL_NAME, CHROMA_DB_PATH, OLLAMA_URL, LLM_EMBED_MODEL
from core.self_evolution import nova_self_evolution, run_self_evolution_scheduler
from core.distillation import nova_distillation, run_distillation_scheduler
from core.dataset_builder import nova_dataset_builder
from core.tts_engine import nova_voice
from core.proactive import nova_proactive, run_proactive_scheduler, run_telegram_polling
from core.context_manager import context_manager
from core.integrity import check_system_integrity

from routers.auth import router as auth_router
from routers.system import router as system_router
from routers.memory import router as memory_router
from routers.evolution import router as evolution_router
from routers.agents import router as agents_router
from routers.proactive import router as proactive_router
from routers.chat import router as chat_router
from routers.metrics import router as metrics_router  # v10.1 Telemetría
from routers.graph import router as graph_router      # v10.3 MetaCritic

# --- CONFIGURATION & GLOBAL STATE ---

# SEC-04: Rate limiting configuration
limiter = Limiter(key_func=get_remote_address)

# FIX: chat_history eliminada — era un artefacto sin uso (los routers usan ChatLog en BD).
stt_model: Any = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global stt_model
    init_db()
    
    # NIAW: Verificación de integridad ante posibles fallos de energía previos
    await check_system_integrity()
    
    print("Starting Orchestrator Workers...")
    orchestrator.start()
    
    print("Loading STT Model (Whisper)...")
    try:
        # FIX: whisper.load_model es bloqueante — ejecutar en thread pool
        # para no bloquear el event loop durante el arranque.
        stt_model = await asyncio.to_thread(whisper.load_model, "base")
        app.state.stt_model = stt_model
    except Exception as e:
        print(f"Failed to load Whisper: {e}")
        app.state.stt_model = None

    print("Inicializando voz de NOVA (TTS)...")
    try:
        await nova_voice.initialize()
        print("✅ Voz de NOVA lista")
    except Exception as e:
        print(f"⚠ TTS no disponible: {e}")

    # FIX-5.1: Proactive Model Verification
    from core.config import LLM_EMBED_MODEL
    try:
        await llm_client.ensure_model_available(LLM_EMBED_MODEL)
    except Exception as e:
        print(f"⚠ Critical Model Check failed: {e}")

    # v10.14.0: Warm-up Secuencial — Evita picos de I/O de disco y saturación de RAM al arrancar.
    print("🔥 Pre-calentando modelos LLM en RAM (warm-up SECUENCIAL)...")
    async def _warmup():
        try:
            import httpx as _httpx
            # FIX: Construcción robusta de la URL base — funciona con o sin /api/chat al final
            _url = OLLAMA_URL.rsplit("/api/", 1)[0] if "/api/" in OLLAMA_URL else OLLAMA_URL
            warmup_models = [LLM_FAST_MODEL, LLM_MODEL_NAME]
            for _model in warmup_models:
                try:
                    _payload = {
                        "model": _model,
                        "messages": [{"role": "user", "content": "warmup"}],
                        "stream": False,
                        "options": {"num_predict": 1, "num_thread": 4}
                    }
                    async with _httpx.AsyncClient(timeout=120.0) as _c:
                        _r = await _c.post(f"{_url}/api/chat", json=_payload)
                    print(f"  ✅ Warm-up OK: {_model}")
                    await asyncio.sleep(5)
                except Exception as _e:
                    print(f"  ⚠️ Warm-up {_model}: {_e}")
        except Exception as _e:
            print(f"⚠ Warm-up error: {_e}")

    # FIX: Guardar referencias a TODAS las tareas background para cancelarlas limpiamente al cierre
    warmup_task     = asyncio.create_task(_warmup())
    health_task     = asyncio.create_task(run_health_monitor())
    evolution_task  = asyncio.create_task(run_self_evolution_scheduler())
    distillation_task = asyncio.create_task(run_distillation_scheduler())
    polling_task    = asyncio.create_task(run_telegram_polling())
    # FIX CRÍTICO: run_proactive_scheduler nunca se iniciaba — el sistema proactivo
    # (notificaciones, briefings, ciclo de curiosidad) estaba completamente inactivo.
    proactive_task  = asyncio.create_task(run_proactive_scheduler())

    # FIX: Aumentar retraso a 30s para evitar solapamiento con el warm-up en hardware lento.
    # FIX: Guardar referencia para cancelar limpiamente en el cierre.
    async def _deferred_recovery():
        print("[TaskQueue] Recovery scan delayed 30s (waiting for warm-up to finish)...")
        await asyncio.sleep(30)
        try:
            await task_queue.recovery_scan(orchestrator.handle_task)
        except Exception as _rec_err:
            print(f"[TaskQueue] Recovery scan error: {_rec_err}")
    recovery_task = asyncio.create_task(_deferred_recovery())
    
    # PHASE 5: Verificar si acabamos de volver de un reinicio autónomo
    reboot_task = asyncio.create_task(nova_self_evolution.check_reboot_status())
    
    yield
    
    # FIX: Cancelar todas las tareas background de forma ordenada
    bg_tasks = [
        health_task, evolution_task, distillation_task,
        polling_task, proactive_task, warmup_task, recovery_task
    ]
    for _t in bg_tasks:
        if not _t.done():
            _t.cancel()
    await asyncio.gather(*bg_tasks, return_exceptions=True)
        
    # FIX-4.5: Graceful worker shutdown
    print("Cancelling workers...")
    for worker in task_queue.workers:
        if not worker.done():
            worker.cancel()
    if task_queue.workers:
        await asyncio.gather(*task_queue.workers, return_exceptions=True)
        task_queue.workers.clear()
        
    await llm_client.close()
    
    stt_model = None
    print("Shutting down...")

setup_logging()
logger = get_logger("main")

app = FastAPI(title="Autonomous Research AI", lifespan=lifespan)

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_var.reset(token)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = request_id_var.get()
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True, extra={"request_id": request_id})
    # FIX: No exponer str(exc) en la respuesta pública — puede filtrar rutas, claves o info sensible.
    # El detalle completo queda en los logs con el request_id para diagnóstico.
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred. Please contact support with the request ID.",
            "request_id": request_id
        }
    )

app.state.limiter = limiter  # SEC-04: Attach limiter to app
# FIX: Consolidar JSONResponse — StarletteJSONResponse es idéntico, usar la misma importación.
app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"}))

# SEC-03: Dynamic CORS configuration based on environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTERS INTEGRATION ---
app.include_router(auth_router, prefix="/api")
app.include_router(system_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(evolution_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(proactive_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(metrics_router, prefix="/api")   # v10.1 — Acceso via /api/metrics
app.include_router(graph_router, prefix="/api")     # v10.3 — Acceso via /api/graph/health


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)