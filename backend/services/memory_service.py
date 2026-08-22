import json
import re
import asyncio
import logging
import datetime
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

from core.lightrag_manager import lightrag_manager
from core.llm_gateway import llm_gateway
from core.config import LLM_FAST_MODEL
from core.prompts import MEMORY_EXTRACTION_PROMPT

# Configuración de Logs
logger = logging.getLogger("nova.memory")

# Rutas del Proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_JSON_PATH = BASE_DIR / "data" / "long_term_memory.json"

class MemoryService:
    def __init__(self):
        self._lock = Lock()
        self.max_value_length = 500
        self.memory_max_chars = 4000
        self.base_dir = BASE_DIR
        
    # --- MÉTODOS DE MEMORIA JSON (BASADOS EN MARK-XXXIX) ---
    
    def _empty_memory(self) -> Dict[str, Any]:
        return {
            "identity":      {},
            "preferences":   {},
            "projects":      {},
            "relationships": {},
            "wishes":        {},
            "notes":         {},
        }

    def load_json_memory(self) -> Dict[str, Any]:
        if not MEMORY_JSON_PATH.exists():
            return self._empty_memory()
        
        with self._lock:
            try:
                data = json.loads(MEMORY_JSON_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    base = self._empty_memory()
                    for key in base:
                        if key not in data:
                            data[key] = {}
                    return data
                return self._empty_memory()
            except Exception as e:
                logger.error(f"Error cargando memoria JSON: {e}")
                return self._empty_memory()

    def save_json_memory(self, memory: Dict[str, Any]) -> None:
        if not isinstance(memory, dict):
            return
        
        # Recorte de tamaño
        memory = self._trim_to_limit(memory)
        MEMORY_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        
        with self._lock:
            try:
                MEMORY_JSON_PATH.write_text(
                    json.dumps(memory, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.error(f"Error guardando memoria JSON: {e}")

    def _trim_to_limit(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        memory_str = json.dumps(memory, ensure_ascii=False)
        if len(memory_str) <= self.memory_max_chars:
            return memory
        
        entries = []
        for cat, items in memory.items():
            if not isinstance(items, dict): continue
            for key, entry in items.items():
                if isinstance(entry, dict) and "value" in entry:
                    entries.append((cat, key, entry))
        
        entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
        
        for cat, key, _ in entries:
            if len(json.dumps(memory, ensure_ascii=False)) <= self.memory_max_chars:
                break
            del memory[cat][key]
            logger.info(f"Memoria recortada: {cat}/{key}")
        
        return memory

    def update_json_memory(self, memory_update: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(memory_update, dict) or not memory_update:
            return self.load_json_memory()
        
        memory = self.load_json_memory()
        changed = self._recursive_update(memory, memory_update)
        if changed:
            self.save_json_memory(memory)
        return memory

    def _recursive_update(self, target: Dict[str, Any], updates: Dict[str, Any]) -> bool:
        changed = False
        for key, value in updates.items():
            if value is None: continue
            if isinstance(value, str) and not value.strip(): continue
                
            if isinstance(value, dict) and "value" not in value:
                if key not in target or not isinstance(target[key], dict):
                    target[key] = {}
                    changed = True
                if self._recursive_update(target[key], value):
                    changed = True
            else:
                raw_val = value["value"] if isinstance(value, dict) else value
                new_val = str(raw_val)
                if len(new_val) > self.max_value_length:
                    new_val = new_val[:self.max_value_length].rstrip() + "..."
                
                entry = {"value": new_val, "updated": datetime.datetime.now().strftime("%Y-%m-%d")}
                
                existing = target.get(key, {})
                if not isinstance(existing, dict) or existing.get("value") != new_val:
                    target[key] = entry
                    changed = True
        return changed

    def get_formatted_json_memory(self) -> str:
        memory = self.load_json_memory()
        if not any(memory.values()): return ""

        lines = []
        # Estructura simplificada para el prompt
        sections = {
            "identity": "## Perfil del Usuario",
            "preferences": "## Preferencias y Gustos",
            "projects": "## Proyectos Activos",
            "relationships": "## Círculo Social",
            "wishes": "## Planes y Deseos",
            "notes": "## Otras Notas"
        }
        
        for cat, title in sections.items():
            items = memory.get(cat, {})
            if items:
                lines.append(f"\n{title}")
                for key, entry in list(items.items())[:15]:
                    val = entry.get("value") if isinstance(entry, dict) else entry
                    if val:
                        lines.append(f"- {key.replace('_', ' ').title()}: {val}")

        if not lines: return ""
        return "### MEMORIA A LARGO PLAZO\n" + "\n".join(lines) + "\n"

    def get_recent_chat_history(self, user_id: int, db: Any, num_turns: int = 5) -> List[Dict[str, str]]:
        """
        v13.9.5 FIX: Recupera los últimos N turnos de conversación del ChatLog
        para inyectarlos en el array messages[] y dar contexto conversacional.
        
        Args:
            user_id: ID del usuario
            db: Sesión de base de datos
            num_turns: Número de turnos (pares user-assistant) a recuperar
            
        Returns:
            Lista de dicts con {"role": "user"|"assistant", "content": "..."}
        """
        try:
            from core.database import ChatLog
            
            # Recuperar los últimos (num_turns * 2) mensajes = num_turns pares
            recent_logs = db.query(ChatLog).filter(
                ChatLog.user_id == user_id
            ).order_by(ChatLog.timestamp.desc()).limit(num_turns * 2).all()
            
            if not recent_logs:
                return []
            
            # Invertir para obtener orden cronológico (más antiguo primero)
            recent_logs = list(reversed(recent_logs))
            
            # Convertir a formato de messages
            history = []
            for log in recent_logs:
                history.append({
                    "role": log.role,
                    "content": log.content
                })
            
            return history
        except Exception as e:
            logger.error(f"Error recuperando historial de chat: {e}")
            return []

    # --- MÉTODOS REQUERIDOS POR CHAT_SERVICE Y ROUTERS ---

    async def build_rag_context(self, intent: str, query: str, files_context: str, db: Any) -> str:
        """
        v14.0: Construye el contexto híbrido ultra-enriquecido combinando:
        1. Hybrid RAG (Dense ChromaDB + Sparse BM25 + Reciprocal Rank Fusion)
        2. Memoria Episódica Jerárquica (Hitos pasados e investigaciones previas)
        3. Memoria JSON estructurada y Grafo de Conocimiento (LightRAG / SQL).
        """
        # 1. Recuperación Híbrida RRF (Dense ChromaDB + Sparse BM25)
        hybrid_context = ""
        try:
            from core.hybrid_retriever import hybrid_retriever
            from core.vector_db import vector_db

            async def _dense_search(q: str, top_k: int = 5):
                hits = await vector_db.search_similar(q, limit=top_k)
                dense_docs = []
                for h in (hits or []):
                    dense_docs.append({
                        "id": h.get("id", str(h.get("document", "")[:30])),
                        "text": h.get("document", ""),
                        "metadata": h.get("metadata", {}),
                        "source": "chromadb"
                    })
                return dense_docs

            hybrid_hits = await hybrid_retriever.retrieve(query, dense_search_fn=_dense_search, top_k=4)
            if hybrid_hits:
                hybrid_context = "\n[CONOCIMIENTO HÍBRIDO RRF (BM25 + VECTORIAL)]:\n"
                for h in hybrid_hits:
                    src = h.get("metadata", {}).get("source", h.get("source", "kb"))
                    rrf = h.get("rrf_score", 0.0)
                    hybrid_context += f"- [{src} | rrf:{rrf}] {h.get('text', '')[:350]}\n"
        except Exception as e:
            logger.warning(f"[MemoryService] Hybrid retriever error: {e}")

        # 2. Recuperación de Memoria Episódica
        episodic_context = ""
        try:
            from core.episodic_memory import episodic_memory
            episodes = episodic_memory.recall_relevant_episodes(query, limit=2)
            if episodes:
                episodic_context = "\n[HITOS Y MEMORIA EPISÓDICA RELACIONADA]:\n"
                for ep in episodes:
                    episodic_context += f"- [{ep.get('category', 'general')}] {ep.get('topic')}: {ep.get('summary')}\n"
        except Exception as e:
            logger.warning(f"[MemoryService] Episodic memory recall error: {e}")

        # 3. Contexto del Grafo de Conocimiento Global (LightRAG)
        rag_context = ""
        try:
            rag_context = await lightrag_manager.query(query, mode="naive")
            if not rag_context or "Contexto de grafo no disponible" in rag_context:
                rag_context = ""
        except Exception as e:
            logger.debug(f"LightRAG fallback: {e}")

        # 4. Contexto del Puente Graph-RAG Local (SQL Structural Graph)
        sql_context = ""
        try:
            from core.knowledge_base import knowledge_base
            sql_graph_results = await knowledge_base.search_enhanced(query, limit=3)
            if sql_graph_results:
                sql_context = "\n[CONOCIMIENTO ESTRUCTURAL RELACIONADO]:\n"
                for res in sql_graph_results:
                    sql_context += f"- {res['title']}: {res['content'][:300]} (Fuente: {res['source']})\n"
        except Exception as e:
            logger.debug(f"SQL Graph search fallback: {e}")

        # 5. Obtener Memoria JSON estructurada (Identidad/Preferencias)
        json_memory = self.get_formatted_json_memory()

        # 6. Combinar todas las capas de contexto
        full_context = f"{json_memory}\n{episodic_context}\n{hybrid_context}\n{sql_context}"
        if rag_context.strip():
            full_context += f"\n\n### CONOCIMIENTO NARRATIVO (GRAFO)\n{rag_context}"
            
        return full_context.strip()


    async def ingest_document(self, file_stream, filename: str, user_id: int):
        """Wrapper para el Librarian para ingesta de libros/documentos."""
        from core.librarian import librarian
        # Guardar temporalmente para que el Librarian lo procese
        temp_path = self.base_dir / "data" / "uploads" / filename
        temp_path.parent.mkdir(parents=True, exist_ok=True)
        with open(temp_path, "wb") as f:
            f.write(file_stream.read())
        
        try:
            result = await librarian.ingest_book(str(temp_path), filename, user_id=user_id)
            return result
        finally:
            if temp_path.exists():
                os.remove(temp_path)

    def list_knowledge(self, db: Any, limit: int = 50, offset: int = 0):
        """Lista entradas de la base de conocimiento (v10.12.0)."""
        from core.database import KnowledgeEntry
        entries = db.query(KnowledgeEntry).order_by(KnowledgeEntry.date.desc()).offset(offset).limit(limit).all()
        return [
            {
                "id": e.id,
                "title": e.title,
                "category": e.category,
                "date": e.date.isoformat(),
                "score": e.score,
                "concepts": e.concepts.split(",") if e.concepts else []
            } for e in entries
        ]

    async def extract_and_store_memory(self, query: str, user_id: int) -> Optional[str]:
        """Analiza la query para extraer hechos y guardarlos en JSON y Grafo."""
        try:
            # 1. Extracción vía LLM
            prompt = MEMORY_EXTRACTION_PROMPT.replace("{user_query}", query)
            extracted = await llm_gateway.chat(
                [
                    {"role": "system", "content": "Extrae conocimiento relevante de la siguiente consulta. Responde solo con el hecho extraído de forma clara y directa, o 'NONE' si no hay información personal o útil."}, 
                    {"role": "user", "content": prompt}
                ], 
                lane="batch", 
                model=LLM_FAST_MODEL, 
                priority=2
            )
            
            extracted = extracted.strip()
            if not extracted or extracted.upper() == "NONE":
                return None
            
            # 2. Guardar en Grafo de Conocimiento (LightRAG)
            await lightrag_manager.insert_text(f"Hecho sobre Juan Ramón: {extracted}")
            
            # 3. Guardar en Memoria JSON (Categorización simple)
            # Intentamos adivinar la categoría por palabras clave
            category = "notes"
            lower_ext = extracted.lower()
            if any(x in lower_ext for x in ["prefiero", "gusta", "amo", "odio", "favorito"]):
                category = "preferences"
            elif any(x in lower_ext for x in ["proyecto", "meta", "objetivo", "trabajando"]):
                category = "projects"
            elif any(x in lower_ext for x in ["llamo", "soy", "vivo", "trabajo de"]):
                category = "identity"
            
            # Generar una clave corta basada en el contenido
            key = re.sub(r'[^a-z0-9]', '_', extracted.lower()[:30]).strip('_')
            self.update_json_memory({category: {key: extracted}})
            
            return f"He aprendido algo nuevo: {extracted}"
        except Exception as e:
            logger.error(f"Error en extract_and_store_memory: {e}")
            return None

    async def store_chat_message(self, role: str, content: str, user_id: int):
        """Guarda un mensaje en el grafo para persistencia narrativa."""
        try:
            if not content or len(content.strip()) < 10:
                return
                
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            entry = f"[{timestamp}] {role.upper()}: {content}"
            
            # Solo guardamos mensajes significativos en el grafo para no ensuciarlo
            # v12.1.0: Filtramos respuestas cortas o puramente sociales
            if len(content) > 50:
                await lightrag_manager.insert_text(entry)
        except Exception as e:
            logger.error(f"Error guardando mensaje en memoria: {e}")

    async def store_visual_memory(self, analysis_dict: Dict[str, Any]):
        """Convierte una observación visual en narrativa y la guarda en la Memoria a Largo Plazo."""
        try:
            timestamp = datetime.datetime.now().strftime("%A %d de %B de %Y, %I:%M %p")
            
            # Construir texto narrativo para LightRAG
            narrative = f"[{timestamp}] OBSERVACIÓN VISUAL DE NOVA: "
            narrative += f"El entorno se veía: {analysis_dict.get('descripcion_general', 'Normal')}. "
            
            if analysis_dict.get('juan_ramon_detectado'):
                narrative += "Mi creador Juan Ramón estaba presente. "
                ropa = analysis_dict.get('apariencia_juan_ramon')
                if ropa: narrative += f"Él llevaba puesto: {ropa}. "
                emocion = analysis_dict.get('estado_emocional_juan_ramon')
                if emocion: narrative += f"Su estado emocional era: {emocion}. "
            
            extranos = analysis_dict.get('personas_desconocidas', 0)
            if extranos > 0:
                narrative += f"Había {extranos} persona(s) desconocida(s) en la habitación acompañándolo. "
                
            objetos = analysis_dict.get('objetos_comunes', [])
            if objetos and isinstance(objetos, list):
                narrative += f"Objetos visibles en la mesa/entorno: {', '.join(objetos)}. "
                
            # Guardar en LightRAG (el Long Term Memory Graph)
            await lightrag_manager.insert_text(narrative)
            logger.info(f"Memoria visual a largo plazo guardada: {narrative}")
            
        except Exception as e:
            logger.error(f"Error guardando memoria visual: {e}")

# Singleton para exportar
memory_service = MemoryService()
