import httpx  # type: ignore
import json
import os
import time
import asyncio
import psutil
import subprocess
import re
from typing import Dict, Any, List, Optional, Union
import random as _random
from services.system_service import system_service

# Regex para limpiar tags de razonamiento de qwen3 (modo thinking)
_THINK_TAG_RE = re.compile(r'<think>.*?</think>', re.DOTALL)

def _strip_think_tags(text: str) -> str:
    """Elimina tags <think>...</think> de qwen3 que filtran razonamiento interno."""
    if not text or '<think>' not in text:
        return text
    cleaned = _THINK_TAG_RE.sub('', text).strip()
    return cleaned  # Puede ser vacío si todo era pensamiento — el caller lo maneja

# Config values will be loaded later or used via os.getenv
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_EMBED_URL_NEW = os.getenv("OLLAMA_EMBED_URL_NEW", "http://localhost:11434/api/embed")
OLLAMA_EMBED_URL_OLD = os.getenv("OLLAMA_EMBED_URL_OLD", "http://localhost:11434/api/embeddings")

# Import config
from core.config import (
    OLLAMA_NUM_THREAD, LLM_CONCURRENCY, LLM_FAST_MODEL, MAX_LLM_RETRIES, 
    LLM_EMBED_MODEL, CIRCUIT_BREAKER_FAILURE_THRESHOLD, CIRCUIT_BREAKER_RECOVERY_TIMEOUT, 
    OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT, LLM_MODEL_NAME, LLM_CODER_MODEL
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
        if not self._waiters:
            self._value += 1
            return
        _, next_fut = self._waiters.pop(0)
        if not next_fut.done(): next_fut.set_result(True)

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
    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        self.fast_model = LLM_FAST_MODEL
        self.coder_model = LLM_CODER_MODEL
        self.circuit_breaker = CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None
        # v10.5.1: 1 slot for chat + 1 slot for background (Total 2 for CPU safety)
        self.chat_semaphore = asyncio.Semaphore(1) 
        self.bg_semaphore = asyncio.Semaphore(1)
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

    def is_user_active(self) -> bool:
        """Determina si el usuario ha interactuado en los últimos 15 minutos.
        v11.1: Aumentado desde 300s (5 min) a 900s (15 min) para permitir
        que tareas de fondo (destilación, curiosidad) se ejecuten con polling normal.
        El polling de telemetría (~1 req/s) no debe bloquear todo el aprendizaje autónomo.
        """
        return (time.time() - self.last_chat_activity) < 900 # 15 min lockout

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

    def get_client(self) -> httpx.AsyncClient:
        client = self._client
        if client is None or client.is_closed:
            self._client = httpx.AsyncClient(timeout=600.0)
            return self._client
        return client

    async def chat(self, messages: List[Dict[str, Any]], format: Optional[str] = None, temperature: Optional[float] = None, images: Optional[List[str]] = None, **kwargs) -> str:
        if not self.circuit_breaker.can_execute(): return ""
        priority = kwargs.get("priority", 1)
        ignore_overdrive = kwargs.get("ignore_overdrive", False)  # v11.1: Para destilación nocturna
        
        # USER_OVERDRIVE: Bloqueo total de fondo si el humano está activo
        # v11.1: Excepto si ignore_overdrive=True (para destilación nocturna)
        if priority > 0 and self.is_user_active() and not ignore_overdrive:
            print(f"[OVERDRIVE] Task aborted: {messages[0]['content'][:30]}...")
            raise AbortBackgroundTask("User active - Overdrive engaged")

        if priority == 0: self.last_chat_activity = time.time()
        max_retries = kwargs.get("max_retries", MAX_LLM_RETRIES)
        self.total_requests += 1

        # DUAL-BRAIN: Chat use Fast Model, Evolution use Heavy Model
        model_to_use = kwargs.get("model")
        if not model_to_use:
            model_to_use = self.fast_model if priority == 0 else self.model
        
        # Hard Timeout: 300s for Chat (v10.9.4 synchronized with frontend), 600s for Background
        request_timeout = 300.0 if priority == 0 else 600.0

        # Cache check
        cache_key = (model_to_use, str(messages))
        if priority > 0 and len(messages) == 1 and cache_key in self._fast_cache:
            self.cache_hits += 1
            return self._fast_cache[cache_key]
        if priority > 0 and len(messages) == 1: self.cache_misses += 1

        for attempt in range(max_retries):
            wait_start = time.time()
            try:
                target_semaphore = self.chat_semaphore if priority == 0 else self.bg_semaphore
                wait_timeout = 120.0 if priority == 0 else 270.0
                
                try:
                    # v10.5.2 FIX: Use await + try/finally instead of 'async with' on result of wait_for
                    await asyncio.wait_for(target_semaphore.acquire(), timeout=wait_timeout)
                    try:
                        wait_duration = time.time() - wait_start
                        self.total_wait_time += wait_duration
                        
                        # Vision
                        if images:
                            model_to_use = "llava-llama3"
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

                        request_start = time.time()
                        try:
                            response = await self.get_client().post(OLLAMA_URL, json=payload, timeout=request_timeout)
                        except httpx.TimeoutException:
                            # v11.0: Registrar timeout en DB
                            try:
                                asyncio.create_task(system_service.log_system_failure(
                                    type='API_ERROR',
                                    description=f'Timeout detectado en solicitud a Ollama (Modelo: {model_to_use})',
                                    severity='warning'
                                ))
                            except: pass
                            
                            if priority == 0:
                                return "⏱️ El modelo tardó demasiado en responder (Timeout). Por favor, intenta de nuevo."
                            raise
                        response.raise_for_status()
                        
                        latency_ms = (time.time() - request_start) * 1000
                        self.latency_samples.append(latency_ms)
                        if len(self.latency_samples) > self.max_samples: self.latency_samples.pop(0)

                        data = response.json()
                        result = data["message"]["content"]
                        # FIX BUG #8: Strip qwen3 thinking tags
                        result = _strip_think_tags(result)
                        self.circuit_breaker.record_success()

                        try:
                            from core.telemetry import nova_telemetry
                            nova_telemetry.record_llm_success(model_to_use, latency_ms)
                        except: pass
                        
                        if priority > 0 and len(messages) == 1 and result:
                            if len(self._fast_cache) >= self._max_cache_size: self._fast_cache.pop(next(iter(self._fast_cache)))
                            self._fast_cache[cache_key] = result
                        return result
                    finally:
                        target_semaphore.release()
                except httpx.HTTPStatusError as e:
                    # v11.0: Registrar error de API (404, 500, etc)
                    try:
                        asyncio.create_task(system_service.log_system_failure(
                            type='API_ERROR',
                            description=f'Error HTTP de Ollama: {e.response.status_code} {e.response.reason_phrase} (Modelo: {model_to_use})',
                            severity='critical' if e.response.status_code >= 500 else 'warning'
                        ))
                    except: pass
                    
                    self.circuit_breaker.record_failure(is_network_error=e.response.status_code >= 500)
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2 ** attempt + _random.uniform(0, 1))
                        continue
                    return ""
                except (asyncio.TimeoutError, TimeoutError):
                    self.busy_count += 1
                    # v11.0: Registrar saturación en Dashboard
                    try:
                        from services.system_service import system_service
                        asyncio.create_task(system_service.log_system_failure(
                            type='SATURATION',
                            description=f'Saturación de LLM: Tiempo de espera en semáforo excedido para {model_to_use}',
                            severity='warning'
                        ))
                    except: pass
                    raise LLMBusyError("Saturación de LLM (Semaphore Timeout)")
            except Exception as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise e
        return ""

    async def chat_stream(self, messages: List[Dict[str, Any]], temperature: Optional[float] = None, images: Optional[List[str]] = None, **kwargs):
        if not self.circuit_breaker.can_execute():
            yield ""
            return
        priority = kwargs.get("priority", 1)

        # USER_OVERDRIVE: Bloqueo total de fondo si el humano está activo
        if priority > 0 and self.is_user_active():
            print(f"[OVERDRIVE] Stream aborted: user active")
            raise AbortBackgroundTask("User active - Overdrive engaged")

        if priority == 0:
            self.last_chat_activity = time.time()

        # BUG #2 FIX: Variables definidas antes del bucle (antes causaban NameError)
        max_retries = kwargs.get("max_retries", MAX_LLM_RETRIES)
        target_semaphore = self.chat_semaphore if priority == 0 else self.bg_semaphore
        wait_timeout = 120.0 if priority == 0 else 270.0

        # BUG #3 FIX: fast_model para chat (priority=0), heavy model para fondo
        model_to_use = self.fast_model if priority == 0 else self.model

        # Timeout routing: 300s for Chat (v10.9.4 synchronized), 600s for Background
        request_timeout = 300.0 if priority == 0 else 600.0
        
        for attempt in range(max_retries):
            try:
                # wait_for semaphore
                try:
                    await asyncio.wait_for(target_semaphore.acquire(), timeout=wait_timeout)
                except (asyncio.TimeoutError, TimeoutError):
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
                        continue
                    # v11.0: Registrar saturación en stream
                    try:
                        asyncio.create_task(system_service.log_system_failure(
                            type='SATURATION',
                            description=f'Saturación de LLM en Stream: Semáforo excedido para {model_to_use}',
                            severity='warning'
                        ))
                    except: pass
                    raise LLMBusyError("Saturación de LLM (Stream Semaphore)")

                try:
                    _model = model_to_use
                    if images:
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
                    _inside_think = False  # Estado para filtrar tags de pensamiento de qwen3
                    _think_buffer = ""     # Buffer para acumular contenido parcial de tags
                    try:
                        async with self.get_client().stream("POST", OLLAMA_URL, json=payload, timeout=request_timeout) as response:
                            response.raise_for_status()
                            self.circuit_breaker.record_success()
                            async for line in response.aiter_lines():
                                if not line: continue
                                try:
                                    data = json.loads(line)
                                    if "message" in data and "content" in data["message"]:
                                        chunk = data["message"]["content"]
                                        
                                        # FIX BUG #8: Filtro de pensamiento qwen3 con estado
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
                                                    # Revertir los caracteres de "<think>" ya agregados a output
                                                    output = output[:-6] if len(output) >= 6 else ""
                                                    _think_buffer = ""
                                                else:
                                                    output += char
                                                    # Solo mantener últimos 7 chars en buffer para detectar tag
                                                    if len(_think_buffer) > 7:
                                                        _think_buffer = _think_buffer[-7:]
                                        
                                        if output:
                                            accumulated_content += output
                                            yield output
                                except Exception as _parse_err:
                                    print(f"[LLM_STREAM] JSON parse error (skipping): {_parse_err}")
                                    continue
                            latency_ms = (time.time() - request_start) * 1000
                            self.latency_samples.append(latency_ms)
                            if len(self.latency_samples) > self.max_samples:
                                self.latency_samples.pop(0)
                        return
                    except httpx.TimeoutException:
                        # Si hay contenido parcial, el stream ya lo envió — fin limpio
                        if priority == 0 and accumulated_content:
                            yield ""  # señal de fin limpio
                        return
                finally:
                    target_semaphore.release()

            except AbortBackgroundTask:
                raise  # Propagar hacia task_queue sin silenciar
            except Exception as e:
                # v11.0: Registrar fallo en stream
                if isinstance(e, httpx.HTTPStatusError):
                    try:
                        asyncio.create_task(system_service.log_system_failure(
                            type='API_ERROR',
                            description=f'Error HTTP en Stream: {e.response.status_code} (Modelo: {model_to_use})',
                            severity='critical'
                        ))
                    except: pass

                self.circuit_breaker.record_failure()
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                print(f"[LLM_STREAM] Error fatal tras {max_retries} intentos: {e}")
                yield f"[Error: {str(e)}]"
                return

    async def ensure_model_available(self, model_name: str) -> bool:
        try:
            process = await asyncio.to_thread(subprocess.run, ["ollama", "list"], capture_output=True, text=True)
            if model_name in process.stdout: return True
            await asyncio.to_thread(subprocess.run, ["ollama", "pull", model_name], check=True)
            return True
        except: return False

    async def get_embeddings(self, text: str, model: Optional[str] = None) -> List[float]:
        if not text: return []
        normalized_text = self._normalize_text(text)
        if normalized_text in self._embed_cache: return self._embed_cache[normalized_text]

        target_model = model or LLM_EMBED_MODEL
        payload = {"model": target_model, "prompt": text[:4000]}
        async def _try_fetch(url: str, is_new: bool):
            try:
                response = await self.get_client().post(url, json=payload, timeout=20.0)
                if response.status_code == 200:
                    data = response.json()
                    if is_new: return data["embeddings"][0] if "embeddings" in data else data.get("embedding")
                    return data.get("embedding", [])
            except: pass
            return None
        result = await _try_fetch(OLLAMA_EMBED_URL_NEW, True) or await _try_fetch(OLLAMA_EMBED_URL_OLD, False)
        if result:
            if len(self._embed_cache) >= self._max_embed_cache_size: self._embed_cache.pop(next(iter(self._embed_cache)))
            self._embed_cache[normalized_text] = result
            return result
        return []

    async def close(self):
        if self._client and not self._client.is_closed: await self._client.aclose()

llm_client = LLMClient()
