import asyncio
from typing import Dict, Any, List, Optional
from core.llm_client import LLMClient
from core.config import (
    OLLAMA_URL, LLM_DEV_URL, LLM_AUDIT_URL,
    LLM_MODEL_NAME, LLM_CODER_MODEL, LLM_FAST_MODEL,
    DISTILL_MODEL_REASONING
)

class LLMRouter:
    """
    Inteligencia de Enjambre: Enruta peticiones a diferentes motores LLM
    basándose en el tipo de agente, presencia de imágenes o saturación.
    """
    def __init__(self):
        # Registro de motores (lazily instantiated)
        self._engines: Dict[str, LLMClient] = {
            "default": LLMClient(model=LLM_MODEL_NAME, base_url=OLLAMA_URL, name="Main"),
            "developer": LLMClient(model=LLM_CODER_MODEL, base_url=LLM_DEV_URL, name="Developer"),
            "auditor": LLMClient(model="phi3:3b", base_url=LLM_AUDIT_URL, name="Auditor"),
            "vision": LLMClient(model="llava-llama3", base_url=LLM_AUDIT_URL, name="Vision"),
            "distillery": LLMClient(model=DISTILL_MODEL_REASONING, base_url=OLLAMA_URL, name="Distillery")
        }
        self._lock = asyncio.Lock()
        self._active_high_priority = 0 # Contador de tareas críticas (Chat, Dev)

    def get_client_for_agent(self, agent_name: str, has_images: bool = False) -> LLMClient:
        """
        Devuelve el cliente LLM óptimo para un agente específico.
        """
        agent_name = agent_name.lower() if agent_name else "default"
        
        # Lógica de Visión (Prioridad Máxima)
        if has_images:
            return self._engines["vision"]

        # Mapeo de Agentes
        if "developer" in agent_name or "coder" in agent_name or "planner" in agent_name:
            return self._engines["developer"]
        
        if "critic" in agent_name or "verifier" in agent_name or "auditor" in agent_name:
            return self._engines["auditor"]

        if "librarian" in agent_name or "explorer" in agent_name:
            return self._engines["default"]
        
        if "distill" in agent_name:
            return self._engines["distillery"]

        return self._engines["default"]

    async def chat(self, messages: List[Dict[str, Any]], agent_name: str = "default", **kwargs) -> str:
        """
        Método unificado para enviar chat a través del router con priorización dinámica.
        """
        has_images = bool(kwargs.get("images"))
        is_distillery = "distill" in agent_name.lower()
        client = self.get_client_for_agent(agent_name, has_images=has_images)

        # v11.5: PAUSA GLOBAL DE FONDO
        # Si hay actividad crítica (Chat, Developer), las tareas de fondo ceden el paso.
        is_high_prio = not is_distillery and (agent_name.lower() in ["chat", "developer", "default"] or kwargs.get("priority", 1) == 0)
        
        if not is_high_prio and self._active_high_priority > 0:
            pass # Removed 8s hard sleep for better 50/50 balance
            
        if is_high_prio:
            async with self._lock:
                self._active_high_priority += 1

        try:
            print(f"[Router] Routing request for '{agent_name}' to engine: {client.name} (Port: {client.base_url})")
            return await client.chat(messages, **kwargs)
        finally:
            if is_high_prio:
                async with self._lock:
                    self._active_high_priority = max(0, self._active_high_priority - 1)

    async def chat_stream(self, messages: List[Dict[str, Any]], agent_name: str = "default", **kwargs):
        """
        Método unificado para streaming a través del router.
        """
        has_images = bool(kwargs.get("images"))
        client = self.get_client_for_agent(agent_name, has_images=has_images)
        
        # El streaming suele ser Chat (Prioridad Máxima)
        async with self._lock:
            self._active_high_priority += 1
        try:
            print(f"[Router] Routing stream for '{agent_name}' to engine: {client.name}")
            async for chunk in client.chat_stream(messages, **kwargs):
                yield chunk
        finally:
            async with self._lock:
                self._active_high_priority = max(0, self._active_high_priority - 1)

    async def close_all(self):
        for engine in self._engines.values():
            await engine.close()

# Instancia global del Router
llm_router = LLMRouter()
