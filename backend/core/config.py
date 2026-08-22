import os
# HuggingFace / Stability Tweaks (Silenciar advertencias de terminal)
# v11.9.18: Forzar antes de cualquier importación de librerías
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
if not os.getenv("HF_TOKEN"):
    os.environ["HF_TOKEN"] = "hf_dummy_token_to_silence_warnings"

# Load .env file
from dotenv import load_dotenv  # type: ignore
load_dotenv()

# System Version
VERSION = "13.9.0"
SYSTEM_VERSION = VERSION  # v13.9.0: AUTONOMOUS VISION & NEURAL VOICE — OpenCV + Kokoro-82M + Swarm Dev

# ── Path Configuration (Absolute to Backend) ─────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
# Asegurar que la carpeta data exista
os.makedirs(DATA_DIR, exist_ok=True)

# Security Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# Resource Limits
MAX_ARTICLES_PER_TOPIC = 5
MAX_TOPICS_PER_DAY = 10
QUALITY_THRESHOLD = 0.55  # Reducido (antes 0.65) para permitir que más artículos superen el filtro de calidad
SIMILARITY_THRESHOLD = 0.92
MAX_TASK_RETRIES = 3
TASK_TIMEOUT_SECONDS = 600
TASK_TIMEOUT_LLM_SECONDS = 1200
CHAT_HISTORY_MAX_SIZE = 100
MAX_QUERY_LENGTH = 50000
RELEVANCE_THRESHOLD = 0.6
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
DEFAULT_MAX_WORKERS = 2  # v10.10.0: Reducido para estabilidad de CPU

# ── Queue Backpressure (Anti Auto-DDOS) ─────────────────────────
QUEUE_BACKPRESSURE_THRESHOLD = int(os.getenv("QUEUE_BACKPRESSURE_THRESHOLD", "150"))
QUEUE_HIGH_PRIORITY_THRESHOLD = int(os.getenv("QUEUE_HIGH_PRIORITY_THRESHOLD", "150"))
TASK_DYNAMIC_TIMEOUT_CAP = int(os.getenv("TASK_DYNAMIC_TIMEOUT_CAP", "120"))  # segundos extra máx

# ── CircuitBreaker ───────────────────────────────────────────────
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "12"))
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = int(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "60"))

# ── Thinker / Proactive Limits ───────────────────────────────────
THINKER_MAX_EXECUTION_SECONDS = int(os.getenv("THINKER_MAX_EXECUTION_SECONDS", "180"))
THINKER_QUEUE_THRESHOLD = int(os.getenv("THINKER_QUEUE_THRESHOLD", "500"))
THINKER_USE_FAST_LANE = os.getenv("THINKER_USE_FAST_LANE", "true").lower() == "true"
RESEARCH_DOMAINS_FOCUS = ["STEM", "Software Architecture", "AI Ethics", "Cybersecurity"]

# Model Configuration
LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH", "models/qwen2.5:3b.gguf")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen2.5:3b")
# v11.8: Migración a Local Embeddings para evitar latencia de Ollama (28s -> 100ms)
USE_LOCAL_EMBEDDINGS = os.getenv("USE_LOCAL_EMBEDDINGS", "true").lower() == "true"
LLM_EMBED_MODEL = os.getenv("LLM_EMBED_MODEL", "all-MiniLM-L6-v2")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11438/api/chat")
# v11.2: Enjambre multi-motor — un puerto por rol (ollama_1/2/3 del Control Center)
LLM_DEV_URL = os.getenv("LLM_DEV_URL", "http://localhost:11439/api/chat")
LLM_AUDIT_URL = os.getenv("LLM_AUDIT_URL", "http://localhost:11440/api/chat")
LLM_AUDIT_MODEL = os.getenv("LLM_AUDIT_MODEL", "phi3:mini")
LLM_VISION_MODEL = os.getenv("LLM_VISION_MODEL", "llava-llama3:latest")

OLLAMA_NUM_THREAD   = int(os.getenv("OLLAMA_NUM_THREAD",   "6")) # v11.9.0: Reducido a 6 para reservar 2 cores para backend Python + OS (Ryzen 7 5700G 8C/16T)

# ── Parámetros de generación de Ollama ──────────────────────────────────────
# Ajuste: aumentar a 8192 por defecto para soportar RAG y largo historial cuando el hardware lo permita.
# Si el sistema tiene restricciones de CPU/RAM, sobrescribe con la variable de entorno OLLAMA_NUM_CTX.
OLLAMA_NUM_CTX     = int(os.getenv("OLLAMA_NUM_CTX",     "8192"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "2048"))
# PERFORMANCE OPTIMIZATION: Usando modelo ligero para mejor rendimiento
# v13.9.5 FIX: Cambiar de qwen2.5:1.5b a qwen2.5:3b para mejorar seguimiento de instrucciones complejas
# con RAG rico. 1.5B es demasiado pequeño para prompts largos con contexto RAG.
LLM_FAST_MODEL = os.getenv("LLM_FAST_MODEL", "qwen2.5:3b")
LLM_THINKER_MODEL = os.getenv("LLM_THINKER_MODEL", LLM_FAST_MODEL)
LLM_CODER_MODEL = os.getenv("LLM_CODER_MODEL", "qwen2.5-coder:3b")  # v11.9.0: 3B para CPU-only (2.4x más rápido que 7B, ~2.5GB RAM)
LLM_GATEWAY_REALTIME_MODEL = os.getenv("LLM_GATEWAY_REALTIME_MODEL", LLM_FAST_MODEL)
LLM_GATEWAY_BATCH_MODEL = os.getenv("LLM_GATEWAY_BATCH_MODEL", LLM_MODEL_NAME)
LLM_BATCH_ENABLED = os.getenv("LLM_BATCH_ENABLED", "false").lower() == "true"
LLM_BATCH_BACKEND_URL = os.getenv("LLM_BATCH_BACKEND_URL", "http://localhost:11438/api/chat")
# v11.5: Concurrencia serializada para evitar saturación de CPU (Gridlock de núcleos)
LLM_REALTIME_MAX_CONCURRENCY = int(os.getenv("LLM_REALTIME_MAX_CONCURRENCY", "1"))
LLM_BATCH_MAX_CONCURRENCY = int(os.getenv("LLM_BATCH_MAX_CONCURRENCY", "1"))
LLM_GATEWAY_REALTIME_TIMEOUT_SECONDS = int(os.getenv("LLM_GATEWAY_REALTIME_TIMEOUT_SECONDS", "600"))
LLM_GATEWAY_BATCH_TIMEOUT_SECONDS = int(os.getenv("LLM_GATEWAY_BATCH_TIMEOUT_SECONDS", "600"))

# v10.5: Optimización de Concurrencia
# v11.5: Capacidad total de inferencia de la instancia. 1 asegura modo Serial estricto.
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "1")) 
MAX_LLM_RETRIES = 2
COGNITIVE_MODE = os.getenv("COGNITIVE_MODE", "balanced").lower() # fast, balanced, high_precision

# Database Configuration
CHROMA_DB_PATH = os.path.join(DATA_DIR, "chroma_db")
LIGHTRAG_DB_PATH = os.path.join(DATA_DIR, "lightrag_db")
LIGHTRAG_ENABLED = os.getenv("LIGHTRAG_ENABLED", "true").lower() == "true"

# Agent Configuration
POLLING_INTERVAL_SECONDS = 86400  # 1 day

# Rate Limiting Configuration (SEC-04)
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

# User-Agents for Explorer rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
]

# ── Auto-Evolution Configuration (Closed-Loop) ──────────────────────
ENABLE_AUTO_EVOLUTION = os.getenv("ENABLE_AUTO_EVOLUTION", "true").lower() == "true"
MAX_EVOLUTIONS_PER_HOUR = int(os.getenv("MAX_EVOLUTIONS_PER_HOUR", "2"))
# Whitelist estricta: Solo se permite modificar estos submódulos menores o inofensivos
ALLOWED_EVOLUTION_MODULES = ["utils.py", "text_utils.py", "content_sanitizer.py", "telemetry.py", "sanitizer.py", "config.py"]
# Módulos cuya firma de función o estructura de respuesta es intocable
IMMUTABLE_STRUCTURE_MODULES = ["content_sanitizer.py", "sanitizer.py", "schemas.py"]
EVOLUTION_ERROR_THRESHOLD = 3 # Mínimo de errores para activar evolución proactiva

# ── Auto Git Versioning (Single-user local) ───────────────────────
ENABLE_AUTO_GIT_VERSIONING = os.getenv("ENABLE_AUTO_GIT_VERSIONING", "true").lower() == "true"

# ── Distillation Tuning (v13.8.16: Estrategia Dual-Cloud) ─────────
# Reasoning → Groq Llama 3.3 70B  (razonamiento técnico profundo)
# General   → Gemini 2.0 Flash     (síntesis y conocimiento general)
# Creative  → Gemini 2.0 Flash     (creatividad, sin fallback local)
DISTILL_MODEL_REASONING = os.getenv("DISTILL_MODEL_REASONING", "llama-3.3-70b-versatile")
DISTILL_MODEL_GENERAL   = os.getenv("DISTILL_MODEL_GENERAL",   "gemini-2.0-flash")
DISTILL_MODEL_CREATIVE  = os.getenv("DISTILL_MODEL_CREATIVE",  "gemini-2.0-flash")
DISTILL_MAX_CONCURRENCY = int(os.getenv("DISTILL_MAX_CONCURRENCY", "1"))
DISTILL_MASTER_TIMEOUT_SECONDS = int(os.getenv("DISTILL_MASTER_TIMEOUT_SECONDS", "300"))

# ── External API Keys (opcional) ───────────────────────────────────
HF_TOKEN = os.getenv("HF_TOKEN", "")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
