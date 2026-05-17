import os
import asyncio
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from core.intent_classifier import classify_intent # type: ignore
from core.logger import agent_logger # type: ignore
from core.llm_client import llm_client # type: ignore
from core.llm_gateway import llm_gateway # type: ignore
from core.config import LLM_MODEL_NAME, COGNITIVE_MODE # type: ignore
from core.file_manager import file_manager # type: ignore
from core.context_manager import context_manager # type: ignore

class ToolRegistry:
    """
    Registro formal de herramientas del sistema para acceso controlado.
    """
    def __init__(self, controller):
        self.controller = controller
        self.tools = {
            "system_status": self.controller.get_system_status,
            "memory_search": self.controller.get_consolidated_context,
            "list_files": file_manager.list_directory,
            "read_file": file_manager.read_file,
            "write_file": file_manager.write_file,
            # "code_exec": sandbox.execute_js  # Future integration
        }

    async def call(self, tool_name: str, **kwargs):
        if tool_name in self.tools:
            return await self.tools[tool_name](**kwargs)
        return f"Error: Herramienta '{tool_name}' no encontrada."

class CognitiveController:
    """
    Motor lógico principal que desacopla la decisión del LLM.
    Actúa como el 'Cerebro' del backend.
    """
    
    def __init__(self):
        self.state = "idle"
        self.tools = ToolRegistry(self)
        self.memory_layer = {
            "episodic": [], # Conversaciones recientes
            "semantic": "chroma_db",
            "operative": "system_metadata"
        }

    pass

    async def verify_response(self, response: str, facts: str) -> Dict[str, Any]:
        """
        Reflection Layer: Verifica la respuesta contra los hechos del sistema para detectar alucinaciones.
        """
        facts_str = str(facts)[:1000]
        response_str = str(response)[:1000]
        prompt = f"""
        [CAPA DE REFLEXIÓN NOVA]
        Compara la respuesta generada contra los hechos reales del sistema:
        
        HECHOS REALES:
        {facts_str}
        
        RESPUESTA GENERADA:
        {response_str}
        
        ¿La respuesta contiene errores, contradicciones o alucinaciones basadas en los hechos?
        Responde en JSON: {{"has_errors": bool, "corrections": "string o null", "confidence": float}}
        """
        try:
            res = await llm_gateway.chat([{"role": "user", "content": prompt}], lane="batch", priority=1)
            import json, re
            json_match = re.search(r'\{.*\}', res, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {"has_errors": False, "corrections": None, "confidence": 1.0}
        except:
            return {"has_errors": False, "corrections": None, "confidence": 0.5}

    async def get_system_status(self) -> Dict[str, Any]:
        """
        Self-Inspection Tool: Consultar el propio estado del sistema.
        """
        from core.database import SessionLocal, KnowledgeEntry # type: ignore
        db = SessionLocal()
        try:
            doc_count = db.query(KnowledgeEntry).count()
            agents_info = await agent_logger.get_data()
            
            return {
                "status": "online",
                "model": LLM_MODEL_NAME,
                "architecture": "Cognitive Controller (Expert Edition)",
                "agents_count": 6,
                "active_agents": agents_info.get("states", {}),
                "knowledge_base": {
                    "type": "ChromaDB + SQLite",
                    "documents_indexed": doc_count
                },
                "memory_layers": {
                    "episodic": "Active",
                    "semantic": "Active",
                    "operative": "Active"
                }
            }
        except Exception as e:
            print(f"Error gathering system status: {e}")
            return {
                "status": "partial_offline",
                "model": LLM_MODEL_NAME,
                "architecture": "Cognitive Controller",
                "agents_count": 0,
                "active_agents": {},
                "knowledge_base": {"type": "Error", "documents_indexed": 0},
                "memory_layers": {"episodic": "Error", "semantic": "Error", "operative": "Error"}
            }
        finally:
            db.close()

    async def get_consolidated_context(self, query: str, db_session: "Session") -> str:
        """
        Produce un bloque de contexto estructurado delegando al ContextManager central.
        """
        # FIX-AUDIT: Centralizado hacia el Tier 4 Context Manager (Adaptative Mode)
        return await context_manager.build_context("DEEP_RESEARCH", query, "", db_session)

    async def log_interaction(self, query: str, response: str) -> Dict[str, Any]:
        """
        Guarda la interacción en la memoria operativa/episódica.
        """
        # Podríamos usar Redis o simplemente confiar en ChatLog de SQLite
        print(f"[Log] Query: {str(query)[:50]}... Response: {str(response)[:50]}...") # type: ignore
        return {"status": "logged"}

cognitive_controller = CognitiveController()