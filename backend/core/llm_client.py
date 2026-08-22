import httpx  # type: ignore
import json
import logging
import os
import time
import asyncio
import psutil
import subprocess
import re
from typing import Dict, Any, List, Optional, Union
import random as _random
from services.system_service import system_service
from core.safe_subprocess import run_safe

logger = logging.getLogger("core.llm_client")

# Regex para limpiar tags de razonamiento de qwen3 (modo thinking)
_THINK_TAG_RE = re.compile(r'<think>.*?</think>', re.DOTALL)

def _strip_think_tags(text: str) -> str:
    """Elimina tags <think>...</think> de qwen3 que filtran razonamiento interno."""
    if not text or '<think>' not in text:
        return text
    cleaned = _THINK_TAG_RE.sub('', text).strip()
    return cleaned  # Puede ser vacío si todo era pensamiento — el caller lo maneja

# Config values will be loaded later or used via os.getenv
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11438/api/chat")
OLLAMA_EMBED_URL_NEW = os.getenv("OLLAMA_EMBED_URL_NEW", "http://localhost:11438/api/embed")
OLLAMA_EMBED_URL_OLD = os.getenv("OLLAMA_EMBED_URL_OLD", "http://localhost:11438/api/embeddings")

# Import config
from core.config import (
    OLLAMA_NUM_THREAD, LLM_CONCURRENCY, LLM_FAST_MODEL, MAX_LLM_RETRIES, 
    LLM_EMBED_MODEL, CIRCUIT_BREAKER_FAILURE_THRESHOLD, CIRCUIT_BREAKER_RECOVERY_TIMEOUT, 
    OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT, LLM_MODEL_NAME, LLM_CODER_MODEL,
    USE_LOCAL_EMBEDDINGS
)

DEFAULT_MODEL = LLM_MODEL_NAME

class LLMBusyError(Exception):
    """Exception raised when the LLM is saturated and cannot process more requests."""
    pass

class AbortBackgroundTask(Exception):
    """Excepción lanzada para abortar tareas de fondo en modo Overdrive."""
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold=None, recovery_timeout=None):
        self.failures = 0
        self.threshold = failure_threshold or CIRCUIT_BREAKER_FAILURE_THRESHOLD
        self.recovery_timeout = recovery_timeout or CIRCUIT_BREAKER_RECOVERY_TIMEOUT
        self.state = "closed" # closed, open, half-open
        self.last_failure: float = 0.0
        self.half_open_calls = 0
        self.half_open_max_calls = 2 

    def record_failure(self, is_network_error: bool = True):
        if not is_network_error: return
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.threshold:
            if self.state != "open":
                print(f"[CircuitBreaker] State changed to OPEN after {self.failures} network failures.")
                try:
                    # v11.0: Registrar fallo estructural
                    task = asyncio.create_task(system_service.log_system_failure(
                        type='API_ERROR',
                        description=f'Ollama inalcanzable: Circuit Breaker activado tras {self.failures} fallos de red.',
                        severity='critical'
                    ))
                except: pass
            self.state = "open"
            self.half_open_calls = 0

    def record_success(self):
        if self.state == "half-open":
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                print(f"[CircuitBreaker] State changed to CLOSED after {self.half_open_calls} successful probes.")
                self.failures = 0
                self.state = "closed"
                self.half_open_calls = 0
        else:
            self.failures = 0
            self.state = "closed"

    def can_execute(self):
        if self.state == "closed": return True
        if self.state == "open":
            if time.time() - self.last_failure > self.recovery_timeout:
                self.state = "half-open"
                self.half_open_calls = 0
                print(f"[CircuitBreaker] Entering HALF-OPEN state (probing backend...)")
                return True
            return False
        return True 

class PrioritySemaphore:
    """A semaphore that respects task priority."""
    def __init__(self, value: int = 1):
        self._value = value
        self._waiters = [] # List of (priority, future)
        self._lock = asyncio.Lock()

    async def acquire(self, priority: int = 1, timeout: Optional[float] = None):
        async with self._lock:
            if self._value > 0:
                if priority > 0 and self._value == 1:
                     pass # Reserve 1 for chat
                else:
                    self._value -= 1
                    return True
            fut = asyncio.get_event_loop().create_future()
            self._waiters.append((priority, fut))
            self._waiters.sort(key=lambda x: x[0]) 
        try:
            if timeout: await asyncio.wait_for(fut, timeout=timeout)
            else: await fut
            return True
        except asyncio.TimeoutError:
            async with self._lock: self._waiters = [w for w in self._waiters if w[1] != fut]
            raise TimeoutError(f"Model busy: Priority {priority} timed out")
        except asyncio.CancelledError:
            async with self._lock: self._waiters = [w for w in self._waiters if w[1] != fut]
            raise

    def _release_sync(self):
        """v13.9.1 CRÍTICO FIX: Procesar TODOS los waiters en lista, no solo uno.
        El bug anterior hacía pop(0) una sola vez, causando starvation del resto."""
        if not self._waiters:
            self._value += 1
            return
        # v13.9.1 FIX: Iterar todos los waiters y procesar por prioridad
        while self._waiters:
            _, next_fut = self._waiters.pop(0)
            if not next_fut.done(): 
                next_fut.set_result(True)
                break  # Solo procesar uno por release, el resto en próximo cycle

    async def __aenter__(self):
        await self.acquire(priority=1)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        async with self._lock: self._release_sync()

    def request(self, priority: int = 1, timeout: Optional[float] = None):
        class PriorityContext:
            def __init__(self, sem, prio, tout):
                self.sem, self.prio, self.tout = sem, prio, tout
            async def __aenter__(self):
                await self.sem.acquire(self.prio, self.tout)
                return self.sem
            async def __aexit__(self, et, ev, tb) -> None:
                async with self.sem._lock: self.sem._release_sync()
        return PriorityContext(self, priority, timeout)

class LLMClient:
    def __init__(self, model: str = DEFAULT_MODEL, base_url: Optional[str] = None, name: str = "Standard"):
        self.model = model
        self.base_url = base_url or OLLAMA_URL
        self.name = name
        self.fast_model = LLM_FAST_MODEL
        self.coder_model = LLM_CODER_MODEL
        self.circuit_breaker = CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None
        
        # v11.5: Unificación de Semáforos para evitar Gridlock en CPU
        # Usamos un único semáforo de prioridad maestro por cliente.
        self.semaphore = PrioritySemaphore(LLM_CONCURRENCY) 
        
        # Metrics
        self.total_requests = 0
        self.busy_count = 0
        self.total_wait_time = 0.0
        self.latency_samples: List[float] = [] # Last 10 samples
        self.max_samples = 10
        self.cache_hits = 0
        self.cache_misses = 0
        self.last_chat_activity = 0.0 
        self._local_embed_model = None

    def is_user_active(self) -> bool:
        """Determina si el usuario ha interactuado en los últimos 30 segundos."""
        return (time.time() - self.last_chat_activity) < 30 # 30s lockout


    @property
    def avg_latency(self) -> float:
        if not self.latency_samples: return 0.0
        return sum(self.latency_samples) / len(self.latency_samples)

    @property
    def busy_rate(self) -> float:
        if self.total_requests == 0: return 0.0
        return self.busy_count / self.total_requests

    @property
    def is_degraded(self) -> bool:
        return self.avg_latency > 15000.0

    _fast_cache = {} # (model, prompt) -> response
    _max_cache_size = 200
    _max_embed_cache_size = 5000 
    _embed_cache: Dict[str, List[float]] = {}

    def _normalize_text(self, text: str) -> str:
        """v10.5.1: Normalización agresiva para aumentar hit rate de caché."""
        if not text: return ""
        text = text.lower().strip()
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[áéíóú]', lambda m: {'á':'a','é':'e','í':'i','ó':'o','ú':'u'}[m.group()], text)
        text = re.sub(r'[¿?¡!.,;:]', '', text)
        stopwords = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'en', 'y', 'o', 'que'}
        words = [w for w in text.split() if w not in stopwords]
        return " ".join(words)

    def _get_local_model(self):
        """Lazy loading del modelo de embeddings local para ahorrar RAM si no se usa."""
        if not self._local_embed_model:
            try:
                from sentence_transformers import SentenceTransformer
                # Force CPU to avoid conflict with Ollama/OOM
                self._local_embed_model = SentenceTransformer(LLM_EMBED_MODEL, device="cpu")
                print(f"[LLMClient] Modelo de embeddings local cargado: {LLM_EMBED_MODEL}")
            except Exception as e:
                print(f"[LLMClient] Error cargando modelo local: {e}")
                return None
        return self._local_embed_model

    def get_client(self) -> httpx.AsyncClient:
        client = self._client
        if client is None or client.is_closed:
            self._client = httpx.AsyncClient(timeout=600.0)
            return self._client
        return client

    async def chat(self, messages: List[Dict[str, Any]], format: Optional[str] = None, temperature: Optional[float] = None, images: Optional[List[str]] = None, **kwargs) -> str:
        if not self.circuit_breaker.can_execute(): return ""
        priority = kwargs.get("priority", 1)
        ignore_overdrive = kwargs.get("ignore_overdrive", False)
        
        if priority >= 2 and self.is_user_active() and not ignore_overdrive and self.busy_rate > 0.8:
            print(f"[OVERDRIVE] Task aborted (Critical Load): {messages[0]['content'][:30]}...")
            raise AbortBackgroundTask("User active + Critical Load")

        if priority == 0: self.last_chat_activity = time.time()
        max_retries = kwargs.get("max_retries", MAX_LLM_RETRIES)
        self.total_requests += 1

        model_to_use = kwargs.get("model")
        if not model_to_use:
            model_to_use = self.fast_model if priority == 0 else self.model
        
        # v11.7.0: Timeout extendido a 600s para evitar Error 500 en hardware CPU
        request_timeout = 600.0

        # Cache check
        cache_key = (model_to_use, str(messages))
        if priority > 0 and len(messages) == 1 and cache_key in self._fast_cache:
            self.cache_hits += 1
            return self._fast_cache[cache_key]
        if priority > 0 and len(messages) == 1: self.cache_misses += 1

        # Identificar Proveedor (v13.8.16 Hybrid Mode)
        # IMPORTANTE: Lista explícita para evitar falsos positivos con modelos locales tipo "llava-llama3"
        _GROQ_MODELS = {"llama-3.3-70b-versatile", "llama-3.1-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"}
        _GEMINI_MODELS = {"gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-lite"}
        is_groq = model_to_use in _GROQ_MODELS and os.getenv("GROQ_API_KEY")
        is_gemini = model_to_use in _GEMINI_MODELS and os.getenv("GOOGLE_API_KEY")

        for attempt in range(max_retries):
            wait_start = time.time()
            try:
                # v11.5: Semáforo de Prioridad Maestro
                wait_timeout = 180.0 if priority == 0 else 1200.0
                async with self.semaphore.request(priority=priority, timeout=wait_timeout):
                    wait_duration = time.time() - wait_start
                    self.total_wait_time += wait_duration
                    
                    request_start = time.time()
                    headers = {}
                    payload = {}
                    url = self.base_url

                    # ── CONFIGURACIÓN SEGÚN PROVEEDOR ──
                    if is_groq:
                        url = "https://api.groq.com/openai/v1/chat/completions"
                        headers = {"Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"}
                        payload = {
                            "model": model_to_use,
                            "messages": messages,
                            "temperature": temperature if temperature is not None else 0.5,
                            "stream": False
                        }
                        # v13.8.14: Desactivado nativo para evitar 400 Bad Request en Groq
                        # if format == "json":
                        #     payload["response_format"] = {"type": "json_object"}
                    elif is_gemini:
                        key = os.getenv("GOOGLE_API_KEY")
                        # v13.8.16: v1beta es el endpoint correcto para API Keys de Google AI Studio
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_to_use}:generateContent?key={key}"
                        gemini_contents = [{"role": "user", "parts": [{"text": m["content"]}]} for m in messages if m["role"] == "user"]
                        payload = {"contents": gemini_contents}
                        if format == "json":
                            payload["generationConfig"] = {"response_mime_type": "application/json"}
                    else:
                        # OLLAMA (Local) — opciones de rendimiento restauradas
                        if images and len(messages) > 0:
                            clean_images = [img.split(",")[-1] if "," in img else img for img in images]
                            messages[-1]["images"] = clean_images

                        payload = {
                            "model": model_to_use,
                            "messages": messages,
                            "stream": False,
                            "options": {
                                "temperature": temperature if temperature is not None else (0.4 if priority == 0 else 0.1),
                                "num_thread": OLLAMA_NUM_THREAD,
                                "num_ctx": OLLAMA_NUM_CTX,
                                "num_predict": 1024 if priority == 0 else OLLAMA_NUM_PREDICT,
                            }
                        }
                        if format == "json": payload["format"] = "json"

                    # ── EJECUCIÓN ──
                    try:
                        response = await self.get_client().post(url, json=payload, headers=headers, timeout=request_timeout)
                        response.raise_for_status()
                        data = response.json()
                        
                        if is_groq: 
                            result = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                        elif is_gemini: 
                            result = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        else: 
                            result = data.get("message", {}).get("content", "")
                        
                        if not result: raise ValueError("Respuesta vacía del proveedor LLM")
                        
                        # Métricas y caché restaurados (v13.8.16 audit fix)
                        latency_ms = (time.time() - request_start) * 1000
                        self.latency_samples.append(latency_ms)
                        if len(self.latency_samples) > self.max_samples:
                            self.latency_samples = self.latency_samples[-self.max_samples:]
                        
                        result = _strip_think_tags(result)
                        self.circuit_breaker.record_success()
                        
                        if priority > 0 and len(messages) == 1 and result:
                            if len(self._fast_cache) >= self._max_cache_size:
                                self._fast_cache.pop(next(iter(self._fast_cache)))
                            self._fast_cache[cache_key] = result
                        return result

                    except (httpx.ConnectError, httpx.ConnectTimeout,
                            httpx.NetworkError, httpx.RemoteProtocolError,
                            OSError) as net_e:
                        # ── SIN INTERNET: Fallback silencioso a modelo local ──
                        # Solo aplica cuando el error es de red (no de API)
                        if is_groq or is_gemini:
                            logger.warning(
                                f"[Client] 🌐 Nube no disponible ({type(net_e).__name__}). "
                                f"Usando modelo local como respaldo offline."
                            )
                            try:
                                fallback_model = self.fast_model or self.model
                                fallback_payload = {
                                    "model": fallback_model,
                                    "messages": messages,
                                    "stream": False,
                                    "options": {"temperature": temperature or 0.4}
                                }
                                fallback_resp = await self.get_client().post(
                                    self.base_url, json=fallback_payload,
                                    headers={}, timeout=120.0
                                )
                                fallback_resp.raise_for_status()
                                result = fallback_resp.json().get("message", {}).get("content", "")
                                if result:
                                    self.circuit_breaker.record_success()
                                    return _strip_think_tags(result)
                            except Exception as local_e:
                                logger.warning(f"[Client] Modelo local también falló: {local_e}")
                            # Si el local también falla, devolvemos cadena vacía sin explosión
                            return ""
                        raise net_e  # Si no es cloud, propagar normalmente

                    except Exception as inner_e:
                        if hasattr(inner_e, "response") and hasattr(inner_e.response, "text"):
                            logger.debug(f"[Client] API error body: {inner_e.response.text[:200]}")
                        self.circuit_breaker.record_failure(is_network_error=True)
                        if attempt < max_retries - 1:
                            await asyncio.sleep(1)
                            continue
                        raise inner_e

            except Exception as outer_e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                if priority == 0: return f"⏱️ Error: {str(outer_e)[:50]}"
                raise outer_e
        return ""

    async def chat_stream(self, messages: List[Dict[str, Any]], temperature: Optional[float] = None, images: Optional[List[str]] = None, **kwargs):
        if not self.circuit_breaker.can_execute():
            yield ""
            return
            
        priority = kwargs.get("priority", 1)
        if priority >= 2 and self.is_user_active() and not kwargs.get("ignore_overdrive", False) and self.busy_rate > 0.8:
            print(f"[OVERDRIVE] Stream aborted (Critical Load): user active")
            raise AbortBackgroundTask("User active + Critical Load")

        if priority == 0: self.last_chat_activity = time.time()
        max_retries = kwargs.get("max_retries", MAX_LLM_RETRIES)
        wait_timeout = 600.0 
        # v11.7.0: Timeout extendido a 600s para evitar Error 500 en hardware CPU
        request_timeout = 600.0

        model_to_use = kwargs.get("model")
        if not model_to_use:
            model_to_use = self.fast_model if priority == 0 else self.model

        for attempt in range(max_retries):
            yielded_output = False
            try:
                try:
                    async with self.semaphore.request(priority=priority, timeout=wait_timeout):
                        _model = model_to_use
                        if images:
                            if not kwargs.get("model"):
                                _model = "llava-llama3"
                            clean_images = [img.split(",")[-1] if "," in img else img for img in images]
                            messages[-1]["images"] = clean_images

                        payload = {
                            "model": _model, "messages": messages, "stream": True,
                            "options": {
                                "temperature": temperature if temperature is not None else 0.4,
                                "num_thread": OLLAMA_NUM_THREAD,
                                "num_ctx": OLLAMA_NUM_CTX,
                                "num_predict": 1024 if priority == 0 else OLLAMA_NUM_PREDICT,
                            }
                        }
                        accumulated_content = ""
                        request_start = time.time()
                        _inside_think = False
                        _think_buffer = ""
                        
                        try:
                            async with self.get_client().stream("POST", self.base_url, json=payload, timeout=request_timeout) as response:
                                response.raise_for_status()
                                self.circuit_breaker.record_success()
                                async for line in response.aiter_lines():
                                    if not line: continue
                                    try:
                                        data = json.loads(line)
                                        if "message" in data and "content" in data["message"]:
                                            chunk = data["message"]["content"]
                                            output = ""
                                            for char in chunk:
                                                _think_buffer += char
                                                if _inside_think:
                                                    if _think_buffer.endswith("</think>"):
                                                        _inside_think = False
                                                        _think_buffer = ""
                                                else:
                                                    if _think_buffer.endswith("<think>"):
                                                        _inside_think = True
                                                        output = output[:-6] if len(output) >= 6 else ""
                                                        _think_buffer = ""
                                                    else:
                                                        output += char
                                                        if len(_think_buffer) > 7: _think_buffer = _think_buffer[-7:]
                                            
                                            if output:
                                                accumulated_content += output
                                                yielded_output = True
                                                yield output
                                    except: continue
                                
                                latency_ms = (time.time() - request_start) * 1000
                                self.latency_samples.append(latency_ms)
                                if len(self.latency_samples) > self.max_samples: self.latency_samples.pop(0)
                            return
                        except httpx.TimeoutException:
                            if yielded_output:
                                raise
                            return
                except (asyncio.TimeoutError, TimeoutError):
                    if yielded_output:
                        raise
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    raise LLMBusyError("Saturación de LLM (Stream Semaphore)")
            except AbortBackgroundTask:
                raise
            except Exception as e:
                if yielded_output:
                    raise
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                yield f"[Error: {str(e)}]"
                return

    async def ensure_model_available(self, model_name: str) -> bool:
        try:
            process = await asyncio.to_thread(run_safe, ["ollama", "list"], timeout=120)
            if model_name in process.stdout: return True
            await asyncio.to_thread(run_safe, ["ollama", "pull", model_name], check=True, timeout=120)
            return True
        except: return False

    async def get_embeddings(self, text_or_list: Union[str, List[str]], model: Optional[str] = None) -> Union[List[float], List[List[float]]]:

        """
        v11.8.1: Soporte para batching y modelo local compartido.
        """
        if not text_or_list: return []
        
        is_batch = isinstance(text_or_list, list)
        texts = text_or_list if is_batch else [text_or_list]
        
        results = [None] * len(texts)
        missing_indices = []
        
        # 1. Verificar caché
        for i, text in enumerate(texts):
            norm = self._normalize_text(text)
            if norm in self._embed_cache:
                results[i] = self._embed_cache[norm]
            else:
                missing_indices.append(i)
                
        if not missing_indices:
            return results if is_batch else results[0]

        # 2. Generar faltantes
        texts_to_process = [texts[i] for i in missing_indices]
        new_vectors = []

        if USE_LOCAL_EMBEDDINGS:
            try:
                local_model = await asyncio.to_thread(self._get_local_model)
                if local_model:
                    batch_results = await asyncio.to_thread(local_model.encode, texts_to_process)
                    new_vectors = batch_results.tolist()
            except Exception as e:
                print(f"[LLMClient] Fallo en batch embedding local: {e}")

        if not new_vectors:
            target_model = model or LLM_EMBED_MODEL
            for text in texts_to_process:
                payload = {"model": target_model, "prompt": text[:4000]}
                v = None
                for url, is_new in [(OLLAMA_EMBED_URL_NEW, True), (OLLAMA_EMBED_URL_OLD, False)]:
                    try:
                        response = await self.get_client().post(url, json=payload, timeout=20.0)
                        if response.status_code == 200:
                            data = response.json()
                            v = data["embeddings"][0] if is_new and "embeddings" in data else data.get("embedding")
                            if v: break
                    except: continue
                new_vectors.append(v or [])

        # 3. Cachear y retornar
        for idx, vector in zip(missing_indices, new_vectors):
            results[idx] = vector
            if vector:
                norm = self._normalize_text(texts[idx])
                if len(self._embed_cache) >= self._max_embed_cache_size:
                    self._embed_cache.pop(next(iter(self._embed_cache)))
                self._embed_cache[norm] = vector

        return results if is_batch else (results[0] if results else [])


    async def close(self):
        if self._client and not self._client.is_closed: await self._client.aclose()

# v11.5: Instancia por defecto
llm_client = LLMClient(name="Default")
