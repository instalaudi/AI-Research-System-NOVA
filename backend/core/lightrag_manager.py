import os
import asyncio
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
from core.config import LIGHTRAG_DB_PATH, LLM_FAST_MODEL, LIGHTRAG_ENABLED
from core.logging_config import get_logger
from core.llm_gateway import llm_gateway
from core.llm_client import llm_client

logger = get_logger("core.lightrag")

class LightRAGManager:
    def __init__(self):
        self.rag = None
        if LIGHTRAG_ENABLED:
            self._initialize_rag()

    def _initialize_rag(self):
        try:
            if not os.path.exists(LIGHTRAG_DB_PATH):
                os.makedirs(LIGHTRAG_DB_PATH)

            # v12.0.1: Adaptador para LLM Gateway (con prioridades y límites de concurrencia)
            async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                if history_messages:
                    messages.extend(history_messages)
                messages.append({"role": "user", "content": prompt})

                # Enrutamos a través del gateway en carril 'batch' (prioridad baja)
                # para no bloquear el chat interactivo del usuario.
                return await llm_gateway.chat(
                    messages, 
                    lane="batch", 
                    model=LLM_FAST_MODEL, 
                    priority=2,
                    temperature=kwargs.get("temperature", 0.0),
                    ignore_overdrive=True # Evita abortar la extracción si el usuario está activo
                )

            # v12.0.1: Adaptador para Embeddings Locales (all-MiniLM-L6-v2)
            # Evita peticiones HTTP a Ollama y es ~100x más rápido.
            async def embedding_func(texts, **kwargs):
                # llm_client.get_embeddings detecta automáticamente si usar el modelo local
                return await llm_client.get_embeddings(texts)

            self.rag = LightRAG(
                working_dir=LIGHTRAG_DB_PATH,
                llm_model_func=llm_model_func,
                llm_model_name=LLM_FAST_MODEL,
                llm_model_max_async=1, # Serializado para no saturar el Ryzen 7
                llm_model_max_token_size=4096,
                embedding_func=EmbeddingFunc(
                    embedding_dim=384, # all-MiniLM-L6-v2 es 384
                    max_token_size=8192,
                    func=embedding_func
                )
            )
            logger.info(f"LightRAG initialized in {LIGHTRAG_DB_PATH}")
        except Exception as e:
            logger.error(f"Failed to initialize LightRAG: {e}")
            self.rag = None

    async def insert_text(self, text: str):
        if not self.rag: return
        try:
            # v12.0.1: Verificación básica de longitud para evitar saturación
            if not text or len(text.strip()) < 5:
                return
            
            await self.rag.ainsert(text)
            logger.info(f"Text indexed in Knowledge Graph ({len(text)} chars)")
        except Exception as e:
            logger.error(f"LightRAG insertion error: {e}")

    async def query(self, query: str, mode: str = "local") -> str:
        if not self.rag: return ""
        try:
            # modes: "global", "local", "hybrid", "naive"
            # v12.1.5: Optimización agresiva para CPU (Ryzen 7 5700G)
            param = QueryParam(
                mode=mode,
                top_k=3, # Reducido a 3 para minimizar el recorrido del grafo en CPU
                response_type="Single Paragraph" # Respuestas más concisas = menos tokens = más rápido
            )
            # v12.1.5: Timeout aumentado a 90s para evitar el error de 52s observado en logs
            result = await asyncio.wait_for(self.rag.aquery(query, param=param), timeout=90.0)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"LightRAG query timed out ({mode}) for: {query[:50]}...")
            return "[Contexto de grafo no disponible: el sistema requiere más tiempo de procesamiento]"
        except Exception as e:
            logger.error(f"LightRAG query error ({mode}): {e}")
            return ""

# Singleton
lightrag_manager = LightRAGManager()
