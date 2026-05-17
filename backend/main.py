from fastapi import FastAPI, HTTPException, Request, File, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse, Response
from starlette.responses import JSONResponse
import os
import sys

# v12.1.0: Silenciador Maestro de Telemetría y Modo Offline
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "True"
os.environ["TELEMETRY_DISABLED"] = "True"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

# Monkeypatch para posthog (Evita error 'capture() takes 1 positional argument but 3 were given')
try:
    import posthog
    class MockPosthog:
        def capture(self, *args, **kwargs): pass
        def identify(self, *args, **kwargs): pass
        def task(self, *args, **kwargs): pass
        def __getattr__(self, name):
            # Devolver un callable no-op seguro para cualquier submódulo o atributo importado/llamado
            return lambda *args, **kwargs: None
    sys.modules["posthog"] = MockPosthog()
    posthog.capture = lambda *args, **kwargs: None
    posthog.disabled = True
except ImportError:
    pass

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from typing import Any
from contextlib import asynccontextmanager
import whisper  # type: ignore
from core.limiter import limiter
import json
import re
import asyncio
import uuid
from core.logging_config import setup_logging, request_id_var, get_logger

# AI System Core Imports
from core.orchestrator import orchestrator
from core.task_queue import task_queue
from core.logger import agent_logger
from core.config import CORS_ORIGINS, CHAT_HISTORY_MAX_SIZE, MAX_QUERY_LENGTH, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW, COGNITIVE_MODE, LLM_FAST_MODEL
# FIX: Solo importar los prompts que se usan activamente en este modulo.
# Los demas se importan en cada router segun necesidad.
from core.health_monitor import run_health_monitor
from core.sandbox import sandbox
from core.database import get_db, SessionLocal, init_db
from core.llm_client import llm_client
from core.controller import cognitive_controller
from core.config import LLM_MODEL_NAME, CHROMA_DB_PATH, OLLAMA_URL, LLM_EMBED_MODEL
from core.self_evolution import nova_self_evolution, run_self_evolution_scheduler
from core.distillation import nova_distillation, run_distillation_scheduler
from core.tts_engine import nova_voice
from core.proactive import run_proactive_scheduler, run_telegram_polling
from core.integrity import check_system_integrity

from routers.auth import router as auth_router
from routers.system import router as system_router
from routers.memory import router as memory_router
from routers.evolution import router as evolution_router
from routers.agents_router import router as agents_router
from routers.proactive import router as proactive_router
from routers.chat import router as chat_router
from routers.metrics import router as metrics_router  # v10.1 Telemetría
from routers.graph import router as graph_router      # v10.3 MetaCritic

# --- CONFIGURATION & GLOBAL STATE ---

# SEC-04: Rate limiting configuration
# Use shared limiter instance from core.limiter

# FIX: chat_history eliminada - era un artefacto sin uso (los routers usan ChatLog en BD).

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger("main")
    init_db()
    from services.system_service import system_service
    system_service.load_feature_flags_from_db()
    
    # Inicializar Snippet Cache para reutilización de código
    from core.snippet_cache import init_snippet_cache
    from core.database import get_db, SessionLocal
    try:
        db = SessionLocal()
        init_snippet_cache(db)
        db.close()
        logger.info("[OK] Snippet Cache inicializado")
    except Exception as e:
        logger.error(f"[!] Error inicializando Snippet Cache: {e}")
    
    # v11.9.11: Inicialización Paralela para acelerar el arranque ("Modo Turbo")
    logger.info("[START] Iniciando subsistemas en paralelo...")
    
    async def _safe_load_whisper():
        try:
            # v11.9.18: Upgrade a Whisper large-v3-turbo para mayor precisión en CPU
            # Configurable vía .env para poder volver a "base" si la RAM es insuficiente
            whisper_model_name = os.getenv("WHISPER_MODEL", "turbo")
            logger.info(f"[AUDIO] Cargando modelo Whisper '{whisper_model_name}'... (primera vez descarga ~1.5GB)")
            stt_model = await asyncio.to_thread(whisper.load_model, whisper_model_name)
            app.state.stt_model = stt_model
            logger.info(f"[OK] Oído de NOVA (Whisper {whisper_model_name}) listo")
        except Exception as e:
            logger.error(f"[!] Error cargando Whisper: {e}")

    async def _safe_load_embeddings():
        """v11.9.18: Pre-cargar modelo de embeddings al arranque para evitar
        latencia de 13s+ en la primera query RAG del usuario."""
        try:
            # Desactivar verificaciones HTTP a HuggingFace (el modelo ya está en caché local)
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            logger.info(f"[MODEL] Pre-cargando modelo de embeddings '{LLM_EMBED_MODEL}'...")
            embed_model = await asyncio.to_thread(llm_client._get_local_model)
            if embed_model:
                logger.info(f"[OK] Modelo de embeddings '{LLM_EMBED_MODEL}' listo (modo offline)")
            else:
                logger.warning("[!] No se pudo pre-cargar el modelo de embeddings")
        except Exception as e:
            logger.error(f"[!] Error pre-cargando embeddings: {e}")

    # Ejecutar tareas críticas en paralelo con un timeout de seguridad de 120 segundos
    from core.regression_guard import run_regression_checks
    try:
        await asyncio.wait_for(
            asyncio.gather(
                check_system_integrity(), # INTEGRITY ya usa su propio logger interno
                _safe_load_whisper(),
                _safe_load_embeddings(),  # v11.9.18: Evitar cold-start en primera query RAG
                nova_voice.initialize(),   # TTS ya usa su propio logger interno
                run_regression_checks(),   # v13.8.18: Verificacion de regresiones al arranque
                return_exceptions=True
            ),
            timeout=120.0
        )
    except asyncio.TimeoutError:
        logger.error("[!] Excedido el tiempo límite de arranque de 120s en el gather inicial de subsistemas.")
    
    logger.info("Starting Orchestrator Workers...")
    orchestrator.start()
    logger.info("[OK] Todos los subsistemas listos")

    # v10.14.0: Warm-up Secuencial - Evita picos de I/O de disco y saturacion de RAM al arrancar.
    logger.info("[WARMUP] Pre-calentando modelos LLM en RAM (warm-up SECUENCIAL)...")
    async def _warmup():
        try:
            import httpx as _httpx
            warmup_models = [LLM_FAST_MODEL] 
            _url = OLLAMA_URL.rsplit("/api/", 1)[0] if "/api/" in OLLAMA_URL else OLLAMA_URL
            
            for _model in warmup_models:
                success = False
                for attempt in range(3):
                    try:
                        _payload = {
                            "model": _model,
                            "messages": [{"role": "user", "content": "warmup"}],
                            "stream": False,
                            "options": {"num_predict": 1, "num_thread": 4}
                        }
                        async with _httpx.AsyncClient(timeout=60.0) as _c:
                            _r = await _c.post(f"{_url}/api/chat", json=_payload)
                        if _r.status_code == 200:
                            logger.info(f"  [OK] Warm-up OK: {_model}")
                            success = True
                            await asyncio.sleep(2)
                            break
                        else:
                            logger.warning(f"  [!] Warm-up {_model} attempt {attempt+1} failed with status {_r.status_code}")
                    except Exception as _e:
                        logger.warning(f"  [!] Warm-up {_model} attempt {attempt+1} error: {_e}")
                    
                    if not success and attempt < 2:
                        await asyncio.sleep(5)
                
                    if not success:
                        logger.error(f"[ERROR] Fallo crítico de warm-up para {_model} tras 3 intentos. ¿Ollama está corriendo?")
        except Exception as _e:
            logger.error(f"[!] Warm-up error: {_e}")

    # FIX: Guardar referencias a TODAS las tareas background para cancelarlas limpiamente al cierre
    warmup_task     = asyncio.create_task(_warmup())
    health_task     = asyncio.create_task(run_health_monitor())
    evolution_task  = asyncio.create_task(run_self_evolution_scheduler())
    distillation_task = asyncio.create_task(run_distillation_scheduler())
    telegram_mode = os.getenv("TELEGRAM_MODE", "polling").strip().lower()
    polling_task = asyncio.create_task(run_telegram_polling()) if telegram_mode == "polling" else None
    # FIX CRITICO: run_proactive_scheduler nunca se iniciaba - el sistema proactivo
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
    
    # v13.8.18: Monitor de Visión Persistente (Ojo de NOVA)
    vision_task = None
    try:
        from core.vision_monitor import run_vision_monitor
        vision_task = asyncio.create_task(run_vision_monitor())
        logger.info("[OK] Monitor de Visión Persistente iniciado.")
    except ImportError:
        logger.warning("[!] Módulo core/vision_monitor.py no disponible. Continuando sin monitor de visión.")
    
    try:
        yield
    except asyncio.CancelledError:
        pass
    finally:
        # FIX: Cancelar todas las tareas background de forma ordenada
        bg_tasks = [
            health_task, evolution_task, distillation_task,
            polling_task, proactive_task, warmup_task, recovery_task,
            reboot_task, vision_task  # v13.8.18: Incluir Vision Monitor en shutdown
        ]
        bg_tasks = [t for t in bg_tasks if t is not None]
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
        app.state.stt_model = None
        print("Shutting down...")

setup_logging()
logger = get_logger("main")

app = FastAPI(
    title="NOVA v13.7 (Overdrive Phase 1)",
    description="NOVA v13.7 - Structural Stabilization & Contextual Intelligence",
    version="13.7.0",
    lifespan=lifespan
)

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
    # FIX: No exponer str(exc) en la respuesta publica - puede filtrar rutas, claves o info sensible.
    # El detalle completo queda en los logs con el request_id para diagnostico.
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred. Please contact support with the request ID.",
            "request_id": request_id
        }
    )

app.state.limiter = limiter  # SEC-04: Attach limiter to app
app.add_middleware(SlowAPIMiddleware)
# FIX: Consolidar JSONResponse - StarletteJSONResponse es identico, usar la misma importacion.
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
app.include_router(metrics_router, prefix="/api")   # v10.1 - Acceso via /api/metrics
app.include_router(graph_router, prefix="/api")     # v10.3 - Acceso via /api/graph/health


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)