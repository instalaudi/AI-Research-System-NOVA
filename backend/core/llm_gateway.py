import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx

from core.config import (
    DISTILL_MASTER_TIMEOUT_SECONDS,
    LLM_BATCH_BACKEND_URL,
    LLM_BATCH_ENABLED,
    LLM_BATCH_MAX_CONCURRENCY,
    LLM_GATEWAY_BATCH_MODEL,
    LLM_GATEWAY_BATCH_TIMEOUT_SECONDS,
    LLM_GATEWAY_REALTIME_MODEL,
    LLM_REALTIME_MAX_CONCURRENCY,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_PREDICT,
    OLLAMA_NUM_THREAD,
)
from core.llm_client import CircuitBreaker
from core.llm_router import llm_router


class LLMGateway:
    """
    Enrutador local de inferencia para separar:
    - lane realtime (chat interactivo)
    - lane batch (destilación/evolución/tareas en segundo plano)
    """

    def __init__(self) -> None:
        self._batch_client: Optional[httpx.AsyncClient] = None
        self._realtime_breaker = CircuitBreaker()
        self._batch_breaker = CircuitBreaker()
        self._metrics: Dict[str, Dict[str, float]] = {
            "realtime": {"attempts": 0, "requests": 0, "errors": 0, "busy": 0, "latency_ms_acc": 0.0, "latency_samples": 0},
            "batch": {"attempts": 0, "requests": 0, "errors": 0, "busy": 0, "latency_ms_acc": 0.0, "latency_samples": 0},
        }

    def _can_use_batch_backend(self) -> bool:
        return bool(LLM_BATCH_ENABLED and LLM_BATCH_BACKEND_URL)

    def _record_request(self, lane: str) -> None:
        self._metrics[lane]["requests"] += 1

    def _record_attempt(self, lane: str) -> None:
        self._metrics[lane]["attempts"] += 1

    def _record_success(self, lane: str, latency_ms: float) -> None:
        self._metrics[lane]["latency_ms_acc"] += latency_ms
        self._metrics[lane]["latency_samples"] += 1

    def _record_error(self, lane: str) -> None:
        self._metrics[lane]["errors"] += 1

    def _record_busy(self, lane: str) -> None:
        self._metrics[lane]["busy"] += 1

    def _get_batch_client(self) -> httpx.AsyncClient:
        if self._batch_client is None or self._batch_client.is_closed:
            timeout = max(float(DISTILL_MASTER_TIMEOUT_SECONDS), float(LLM_GATEWAY_BATCH_TIMEOUT_SECONDS))
            self._batch_client = httpx.AsyncClient(timeout=timeout)
        return self._batch_client

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        lane: str = "realtime",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        format: Optional[str] = None,
        images: Optional[List[str]] = None,
        ignore_overdrive: bool = False,
        priority: Optional[int] = None,
        timeout: Optional[float] = None,
        agent_name: str = "default",
    ) -> str:
        lane_name = (lane or "realtime").lower()
        if lane_name == "batch":
            self._record_attempt("batch")
            # v13.8.16 audit: Circuit Breaker restaurado
            if not self._batch_breaker.can_execute():
                self._record_busy("batch")
                return ""
            # Concurrency managed by LLMClient PrioritySemaphore
            started = time.time()
            self._record_request("batch")
            model_to_use = model or LLM_GATEWAY_BATCH_MODEL
            # v13.8.16 audit: Siempre usamos el router local para mayor control y fallback offline
            try:
                result = await llm_router.chat(
                    messages=messages,
                    model=model_to_use,
                    temperature=temperature,
                    format=format,
                    images=images,
                    ignore_overdrive=ignore_overdrive,
                    priority=2 if priority is None else priority,
                    max_retries=2,
                    agent_name=agent_name,
                    timeout=timeout  # Propagación de timeout restaurada
                )
                self._batch_breaker.record_success()
                self._record_success("batch", (time.time() - started) * 1000)
                return result
            except Exception:
                self._batch_breaker.record_failure()
                self._record_error("batch")
                raise

        self._record_attempt("realtime")
        if not self._realtime_breaker.can_execute():
            self._record_busy("realtime")
            return ""
        
        started = time.time()
        self._record_request("realtime")
        model_to_use = model or LLM_GATEWAY_REALTIME_MODEL
        try:
            result = await llm_router.chat(
                messages=messages,
                model=model_to_use,
                temperature=temperature,
                format=format,
                images=images,
                ignore_overdrive=ignore_overdrive,
                priority=0 if priority is None else priority,
                max_retries=3,
                agent_name=agent_name
            )
            self._realtime_breaker.record_success()
            self._record_success("realtime", (time.time() - started) * 1000)
            return result
        except Exception:
            self._realtime_breaker.record_failure()
            self._record_error("realtime")
            raise

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        lane: str = "realtime",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        images: Optional[List[str]] = None,
        ignore_overdrive: bool = False,
        priority: Optional[int] = None,
        agent_name: str = "default",
    ):
        """
        Stream wrapper del gateway.
        Nota: para mantener compatibilidad local máxima, el stream utiliza llm_client
        incluso en batch lane (con priorización y semáforos del gateway).
        """
        lane_name = (lane or "realtime").lower()
        if lane_name == "batch":
            self._record_attempt("batch")
            if not self._batch_breaker.can_execute():
                self._record_busy("batch")
                return
            # Concurrency managed by LLMClient PrioritySemaphore
            started = time.time()
            self._record_request("batch")
            model_to_use = model or LLM_GATEWAY_BATCH_MODEL
            try:
                async for chunk in llm_router.chat_stream(
                    messages=messages,
                    model=model_to_use,
                    temperature=temperature,
                    images=images,
                    ignore_overdrive=ignore_overdrive,
                    priority=2 if priority is None else priority,
                    agent_name=agent_name
                ):
                    yield chunk
                self._batch_breaker.record_success()
                self._record_success("batch", (time.time() - started) * 1000)
            except Exception:
                self._batch_breaker.record_failure()
                self._record_error("batch")
                raise
            return

        self._record_attempt("realtime")
        if not self._realtime_breaker.can_execute():
            self._record_busy("realtime")
            return
        # Concurrency managed by LLMClient PrioritySemaphore
        started = time.time()
        self._record_request("realtime")
        model_to_use = model or LLM_GATEWAY_REALTIME_MODEL
        try:
            async for chunk in llm_router.chat_stream(
                messages=messages,
                model=model_to_use,
                temperature=temperature,
                images=images,
                ignore_overdrive=ignore_overdrive,
                priority=0 if priority is None else priority,
                agent_name=agent_name
            ):
                yield chunk
            self._realtime_breaker.record_success()
            self._record_success("realtime", (time.time() - started) * 1000)
        except Exception:
            self._realtime_breaker.record_failure()
            self._record_error("realtime")
            raise

    def get_lane_metrics(self) -> Dict[str, Any]:
        def lane_view(name: str, breaker: CircuitBreaker) -> Dict[str, Any]:
            metrics = self._metrics[name]
            samples = metrics["latency_samples"]
            avg_latency = (metrics["latency_ms_acc"] / samples) if samples > 0 else 0.0
            requests = metrics["requests"]
            attempts = metrics["attempts"]
            busy_rate = (metrics["busy"] / attempts) if attempts > 0 else 0.0
            return {
                "attempts": int(attempts),
                "requests": int(requests),
                "errors": int(metrics["errors"]),
                "busy": int(metrics["busy"]),
                "busy_rate": round(busy_rate, 4),
                "avg_latency_ms": round(avg_latency, 2),
                "breaker_state": breaker.state,
                "breaker_failures": breaker.failures,
            }

        return {
            "realtime": lane_view("realtime", self._realtime_breaker),
            "batch": lane_view("batch", self._batch_breaker),
        }

    async def close(self) -> None:
        if self._batch_client and not self._batch_client.is_closed:
            await self._batch_client.aclose()


llm_gateway = LLMGateway()
