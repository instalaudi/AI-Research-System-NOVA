import os
from dotenv import load_dotenv  # type: ignore

# Load .env file
load_dotenv()

# Security Configuration
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

# Resource Limits
MAX_ARTICLES_PER_TOPIC = 5
MAX_TOPICS_PER_DAY = 10
QUALITY_THRESHOLD = 0.55  # Reducido (antes 0.65) para permitir que más artículos superen el filtro de calidad
SIMILARITY_THRESHOLD = 0.92
MAX_TASK_RETRIES = 3
TASK_TIMEOUT_SECONDS = 300
TASK_TIMEOUT_LLM_SECONDS = 1200
CHAT_HISTORY_MAX_SIZE = 100
MAX_QUERY_LENGTH = 50000
RELEVANCE_THRESHOLD = 0.6
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
DEFAULT_MAX_WORKERS = 2  # v10.10.0: Reducido para estabilidad de CPU

# ── Queue Backpressure (Anti Auto-DDOS) ─────────────────────────
QUEUE_BACKPRESSURE_THRESHOLD = int(os.getenv("QUEUE_BACKPRESSURE_THRESHOLD", "300"))
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
LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH", "models/llama3-8b.gguf")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama3.1:8b")
LLM_EMBED_MODEL = os.getenv("LLM_EMBED_MODEL", "all-minilm")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_NUM_THREAD   = int(os.getenv("OLLAMA_NUM_THREAD",   "6")) # v11.1: Aumentado a 6 para aprovechar Ryzen 7 5700G (8 núcleos/16 hilos)

# ── Parámetros de generación de Ollama ──────────────────────────────────────
# FIX #3: Subido de 2048 a 4096 para que coincida con ContextManager.max_tokens=4000.
# Con 2048, Ollama truncaba silenciosamente el contexto RAG en cada petición.
# v11.1 CRÍTICO FIX: Reducido de 8192 a 4096 para resolver latencia extrema (221s → ~30s esperado).
# Con 8192 tokens, Ollama en CPU requería >3 minutos por inferencia. 4096 es suficiente para RAG.
OLLAMA_NUM_CTX     = int(os.getenv("OLLAMA_NUM_CTX",     "4096"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "4096"))
# FIX CRÍTICO: Chat ahora usa qwen3:8b (8B params, modo dual thinking/fast, mejor español)
# Antes: qwen2.5:1.5b causaba alucinaciones masivas por ser demasiado pequeño.
LLM_FAST_MODEL = os.getenv("LLM_FAST_MODEL", "qwen3:8b")
LLM_THINKER_MODEL = os.getenv("LLM_THINKER_MODEL", LLM_FAST_MODEL)
LLM_CODER_MODEL = os.getenv("LLM_CODER_MODEL", "qwen2.5-coder:7b")

# v10.5: Optimización de Concurrencia
LLM_CONCURRENCY = 2 # Allow 1 chat stream + 1 overhead/background call
MAX_LLM_RETRIES = 3
COGNITIVE_MODE = os.getenv("COGNITIVE_MODE", "balanced").lower() # fast, balanced, high_precision

# Database Configuration
CHROMA_DB_PATH = "data/chroma_db"

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

# ── Distillation Tuning (CPU local stable) ────────────────────────
DISTILL_MODEL_REASONING = os.getenv("DISTILL_MODEL_REASONING", "deepseek-r1:8b")
DISTILL_MODEL_GENERAL = os.getenv("DISTILL_MODEL_GENERAL", "llama3.1:8b")
DISTILL_MODEL_CREATIVE = os.getenv("DISTILL_MODEL_CREATIVE", "qwen3:4b")
DISTILL_MAX_CONCURRENCY = int(os.getenv("DISTILL_MAX_CONCURRENCY", "1"))
DISTILL_MASTER_TIMEOUT_SECONDS = int(os.getenv("DISTILL_MASTER_TIMEOUT_SECONDS", "120"))
