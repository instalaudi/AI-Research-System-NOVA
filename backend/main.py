from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import os
import sys

# v13.9.5: Asegurar UTF-8 en todos los subprocesos (Windows fix)
os.environ['PYTHONIOENCODING'] = 'utf-8:replace'

# v13.9.1: Evitar caídas por codificación Unicode (UTF-8) en consolas Windows (CP1252)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except Exception:
    pass

# v12.1.0: Silenciador Maestro de Telemetría
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "True"
os.environ["TELEMETRY_DISABLED"] = "True"
# Removido el force global offline para permitir descarga de modelos faltantes

# Monkeypatch para posthog (Evita error 'capture() takes 1 positional argument but 3 were given')
try:
    class MockPosthog:
        def capture(self, *args, **kwargs): pass
        def identify(self, *args, **kwargs): pass
        def task(self, *args, **kwargs): pass
        def __getattr__(self, name):
            # Devolver un callable no-op seguro para cualquier submódulo o atributo importado/llamado
            return lambda *args, **kwargs: None
    mock = MockPosthog()
    mock.disabled = True
    sys.modules["posthog"] = mock
except Exception:
    pass

from slowapi.errors import RateLimitExceeded  # type: ignore
from slowapi.middleware import SlowAPIMiddleware  # type: ignore
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
from core.config import CORS_ORIGINS, LLM_FAST_MODEL
# FIX: Solo importar los prompts que se usan activamente en este modulo.
# Los demas se importan en cada router segun necesidad.
from core.health_monitor import run_health_monitor
from core.database import SessionLocal, init_db, KnowledgeEntry
from core.llm_client import llm_client
from core.config import (
    OLLAMA_URL, LLM_EMBED_MODEL, LLM_DEV_URL, LLM_AUDIT_URL,
    LLM_AUDIT_MODEL, LLM_VISION_MODEL,
)
from core.self_evolution import nova_self_evolution, run_self_evolution_scheduler
from core.distillation import run_distillation_scheduler
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
            logger.info(f"[MODEL] Pre-cargando modelo de embeddings '{LLM_EMBED_MODEL}'...")
            # Intento 1: Offline mode
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            embed_model = await asyncio.to_thread(llm_client._get_local_model)
            
            # Intento 2: Online mode (if missing)
            if not embed_model:
                logger.warning(f"[!] Falló carga offline. Intentando descarga online de '{LLM_EMBED_MODEL}'...")
                os.environ["HF_HUB_OFFLINE"] = "0"
                os.environ["TRANSFORMERS_OFFLINE"] = "0"
                llm_client._local_embed_model = None
                embed_model = await asyncio.to_thread(llm_client._get_local_model)

            if embed_model:
                logger.info(f"[OK] Modelo de embeddings '{LLM_EMBED_MODEL}' cargado y listo")
            else:
                logger.warning("[!] Definitivamente falló la carga del modelo de embeddings")
        except Exception as e:
            logger.error(f"[!] Excepción crítica cargando embeddings: {e}")

    # Ejecutar tareas críticas en paralelo con un timeout de seguridad de 120 segundos
    from core.regression_guard import run_regression_checks
    try:
        results = await asyncio.wait_for(
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
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error(f"[!] Tarea de arranque {idx} falló con excepción: {res}")
    except asyncio.TimeoutError:
        logger.error("[!] Excedido el tiempo límite de arranque de 120s en el gather inicial de subsistemas.")
    
    logger.info("Starting Orchestrator Workers...")
    orchestrator.start()
    logger.info("[OK] Todos los subsistemas listos")

    # v10.14.0: Warm-up por motor — cada modelo en su puerto (11438/11439/11440).
    logger.info("[WARMUP] Pre-calentando modelos LLM por motor (secuencial)...")
    async def _warmup():
        try:
            import httpx as _httpx
            from core.config import LLM_CODER_MODEL, LLM_MODEL_NAME

            def _base_url(chat_url: str) -> str:
                return chat_url.rsplit("/api/", 1)[0] if "/api/" in chat_url else chat_url

            async def _warmup_on_engine(chat_url: str, model: str, engine_label: str) -> None:
                base = _base_url(chat_url)
                for attempt in range(3):
                    try:
                        num_threads = int(os.getenv("OLLAMA_THREADS", str(os.cpu_count() or 8)))
                        payload = {
                            "model": model,
                            "messages": [{"role": "user", "content": "warmup"}],
                            "stream": False,
                            "options": {"num_predict": 1, "num_thread": num_threads},
                        }
                        async with _httpx.AsyncClient(timeout=120.0) as client:
                            resp = await client.post(f"{base}/api/chat", json=payload)
                        if resp.status_code == 200:
                            logger.info(f"  [OK] Warm-up {engine_label}: {model} @ {base}")
                            return
                        logger.warning(
                            f"  [!] Warm-up {engine_label} {model} intento {attempt + 1}: HTTP {resp.status_code}"
                        )
                    except Exception as exc:
                        logger.warning(f"  [!] Warm-up {engine_label} {model} intento {attempt + 1}: {exc}")
                    if attempt < 2:
                        await asyncio.sleep(5)
                logger.error(f"[ERROR] Warm-up fallido: {engine_label} / {model} @ {base}")

            engine_plan = [
                ("Motor-1 Chat", OLLAMA_URL, [LLM_FAST_MODEL, LLM_MODEL_NAME]),
                ("Motor-2 Dev", LLM_DEV_URL, [LLM_CODER_MODEL]),
                ("Motor-3 Audit", LLM_AUDIT_URL, [LLM_AUDIT_MODEL, LLM_VISION_MODEL]),
            ]
            for label, chat_url, models in engine_plan:
                for model in dict.fromkeys(models):
                    await _warmup_on_engine(chat_url, model, label)
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
        logger.info("[TaskQueue] Recovery scan delayed 30s (waiting for warm-up to finish)...")
        await asyncio.sleep(30)
        try:
            await task_queue.recovery_scan(orchestrator.handle_task)
        except Exception as _rec_err:
            logger.error(f"[TaskQueue] Recovery scan error: {_rec_err}")
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
    
    tts_init_task = asyncio.create_task(nova_voice.initialize())

    try:
        yield
    except asyncio.CancelledError:
        pass
    finally:
        # FIX: Cancelar todas las tareas background de forma ordenada
        bg_tasks = [
            health_task, evolution_task, distillation_task,
            polling_task, proactive_task, warmup_task, recovery_task,
            reboot_task, vision_task, tts_init_task
        ]

        bg_tasks = [t for t in bg_tasks if t is not None]
        # C1: Detener vision monitor y liberar cámara antes de cancelar la tarea
        try:
            from core.vision_monitor import get_vision_monitor
            get_vision_monitor().stop()
            logger.info("[OK] Cámara y recursos de visión liberados.")
        except Exception as e:
            logger.error(f"[!] Error liberando recursos de visión: {e}")

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
        nova_voice.shutdown()
        app.state.stt_model = None
        print("Shutting down...")


setup_logging()
logger = get_logger("main")

app = FastAPI(
    title="NOVA v13.8 (Overdrive Phase 1)",
    description="NOVA v13.8 - Structural Stabilization & Contextual Intelligence",
    version="13.8.18",
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
# v13.9.1 FIX (M-8): Evitar wildcard en allow_origins si allow_credentials=True
_origins = [origin.strip() for origin in CORS_ORIGINS if origin.strip() and origin.strip() != "*"]
if not _origins:
    _origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
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


async def get_system_info() -> dict:
    """v13.9.6: Retorna metadatos del sistema (modelo, arquitectura y estado de agentes) para diagnóstico."""
    from core.logger import agent_logger
    from core.config import LLM_MODEL_NAME
    
    db = SessionLocal()
    try:
        # Consulta de verificación para inicializar/usar el modelo
        _ = db.query(KnowledgeEntry).count()
    except Exception:
        pass
    finally:
        db.close()
        
    agents_data = await agent_logger.get_data()
    agents_status = agents_data.get("agents", {})
    
    return {
        "model": LLM_MODEL_NAME,
        "architecture": "Cognitive Controller (Expert Edition)",
        "agents_status": agents_status
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)