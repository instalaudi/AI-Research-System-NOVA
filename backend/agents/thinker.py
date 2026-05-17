"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v10.0 — ThinkerAgent (Motor de Curiosidad)             ║
║  Archivo: agents/thinker.py                                  ║
║  Analiza el Grafo de Conocimiento para generar hipótesis     ║
║  y proponer nuevas líneas de investigación técnica.          ║
╚══════════════════════════════════════════════════════════════╝
"""

import json
import asyncio
import random
import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import func, or_

from agents.base_agent import BaseAgent
# ... (rest of imports)
from core.config import LLM_THINKER_MODEL, THINKER_USE_FAST_LANE
from core.llm_client import llm_client
from core.llm_gateway import llm_gateway
from core.database import SessionLocal, KnowledgeNode, GraphLink, ResearchJob
from core.logging_config import get_logger

logger = get_logger("agents.thinker")

class ThinkerAgent(BaseAgent):
    """
    El Agente Pensador de NOVA. 
    Su función no es buscar información externa, sino 'meditar' sobre lo que
    NOVA ya sabe para encontrar contradicciones, vacíos o nuevas ideas.
    """
    
    # v11.1: Cache para snapshot del grafo (optimización crítica)
    _graph_snapshot_cache = None
    _graph_snapshot_cache_time = 0.0
    _graph_snapshot_cache_ttl = 300  # 5 minutos

    def __init__(self):
        super().__init__("Thinker")
        self.technical_focus = [
            "IA", "Machine Learning", "Ciberseguridad", "Arquitectura de Software",
            "Blockchain", "Computación Cuántica", "Sistemas Distribuidos", "DevOps",
            "Bases de Datos", "Redes", "Frontend Moderno", "Backend Escalable"
        ]

    def _log_status(self, msg: str):
        print(f"[{self.name}] {msg}")
        logger.info(msg)

    async def execute(self, input_data: Any = None, **kwargs) -> Dict[str, Any]:
        """
        Ciclo principal del Thinker:
        1. Verificar que el sistema no está saturado.
        2. Obtener estado del Grafo.
        3. Identificar 'Gaps' o nodos aislados.
        4. Generar Hipótesis Técnica.
        """
        # ── GUARD: No ejecutar si el sistema está bajo carga ────────────
        try:
            from core.task_queue import task_queue as tq  # type: ignore
            from core.llm_client import llm_client  # type: ignore
            from core.config import THINKER_QUEUE_THRESHOLD  # type: ignore
            queue_size = tq.get_size()
            busy_rate  = llm_client.busy_rate
            if queue_size > THINKER_QUEUE_THRESHOLD:
                self._log_status(f"Sistema saturado (cola={queue_size}). Thinker pospuesto.")
                return {"success": False, "reason": "system_busy", "queue_size": queue_size}
            if busy_rate > 0.5:
                self._log_status(f"LLM saturado (busy_rate={busy_rate:.1%}). Thinker pospuesto.")
                return {"success": False, "reason": "llm_busy", "busy_rate": busy_rate}
        except Exception as guard_err:
            logger.warning(f"Guard check failed (non-critical): {guard_err}")
        # ─────────────────────────────────────────────────────────────────

        self._log_status("Analizando Grafo de Conocimiento...")
        
        # 1. Obtener Nodos y Enlaces
        nodes, links = await self._get_graph_snapshot()
        if not nodes:
            return {"success": False, "message": "Grafo vacío. No hay base para pensar."}

        # 2. Identificar Nodos Críticos (pocos enlaces)
        gaps = self._identify_knowledge_gaps(nodes, links)
        
        # 3. Generar Hipótesis via LLM
        self._log_status("Generando Hipótesis Curiosa...")
        hypothesis = await self._generate_strategic_hypothesis(gaps)

        return {
            "success": True,
            "hypothesis": hypothesis,
            "analyzed_nodes": len(nodes),
            "identified_gaps": len(gaps)
        }


    async def _get_graph_snapshot(self):
        """v10.5.1: Obtiene una vista mixta (50 recientes + 50 alta centralidad).
        v11.1: Implementa caché de 5 minutos para evitar consultas SQL pesadas.
        """
        import time
        
        # Verificar caché
        current_time = time.time()
        if (self._graph_snapshot_cache is not None and 
            (current_time - self._graph_snapshot_cache_time) < self._graph_snapshot_cache_ttl):
            self._log_status(f"Usando snapshot cacheado ({(current_time - self._graph_snapshot_cache_time):.1f}s antiguo).")
            return self._graph_snapshot_cache
        
        db = SessionLocal()
        try:
            start_time = datetime.datetime.utcnow()
            # 1. 50 Nodos más recientes
            recent_nodes = db.query(KnowledgeNode).order_by(KnowledgeNode.updated_at.desc()).limit(50).all()
            recent_node_ids = [n.id for n in recent_nodes]

            # 2. 50 Nodos con mayor grado (centralidad), excluyendo los recientes para maximizar diversidad
            degree_node_ids_query = (
                db.query(KnowledgeNode.id)
                .join(
                    GraphLink,
                    or_(KnowledgeNode.id == GraphLink.source, KnowledgeNode.id == GraphLink.target)
                )
                .filter(~KnowledgeNode.id.in_(recent_node_ids))
                .group_by(KnowledgeNode.id)
                .order_by(func.count(GraphLink.id).desc())
                .limit(50)
            )
            degree_node_ids = [row[0] for row in degree_node_ids_query.all()]
            degree_nodes = db.query(KnowledgeNode).filter(KnowledgeNode.id.in_(degree_node_ids)).all()

            # Combinar (evitando duplicados)
            combined_nodes = {n.id: n for n in (recent_nodes + degree_nodes)}
            node_list = list(combined_nodes.values())
            node_ids = list(combined_nodes.keys())

            # 3. Obtener enlaces relacionados a estos nodos en dos consultas indexadas
            source_links = db.query(GraphLink).filter(GraphLink.source.in_(node_ids)).limit(200).all()
            target_links = db.query(GraphLink).filter(GraphLink.target.in_(node_ids)).limit(200).all()

            seen_link_ids = set()
            links = []
            for link in source_links + target_links:
                if link.id not in seen_link_ids:
                    seen_link_ids.add(link.id)
                    links.append(link)
                if len(links) >= 200:
                    break

            elapsed = (datetime.datetime.utcnow() - start_time).total_seconds()
            logger.debug(f"Thinker graph snapshot: {len(node_list)} nodes, {len(links)} links, {elapsed:.2f}s")
            
            # Guardar en caché
            result = (node_list, links)
            self.__class__._graph_snapshot_cache = result
            self.__class__._graph_snapshot_cache_time = current_time
            return result
        except Exception as e:
            logger.error(f"Error en snapshot del Thinker: {e}")
            return [], []
        finally:
            db.close()

    def _identify_knowledge_gaps(self, nodes, links) -> List[str]:
        """Encuentra temas técnicos con poca profundidad o conexiones."""
        # Contar conexiones por nodo
        conn_count = {node.id: 0 for node in nodes}
        for link in links:
            if link.source in conn_count: conn_count[link.source] += 1
            if link.target in conn_count: conn_count[link.target] += 1
        
        # Filtrar nodos técnicos 'aislados' (pocos enlaces)
        candidates = []
        for node in nodes:
            if conn_count.get(node.id, 0) <= 1:
                # Priorizar si está en el foco técnico
                if any(tech.lower() in node.id.lower() for tech in self.technical_focus):
                    candidates.append(node.id)
        
        # Si no hay candidatos aislados, tomar temas técnicos aleatorios del foco
        if not candidates:
            candidates = random.sample(self.technical_focus, 3)
            
        return candidates[:5]

    async def _generate_strategic_hypothesis(self, gaps: List[str]) -> Dict[str, Any]:
        """Usa el LLM para conectar puntos y proponer algo nuevo.
        
        Optimizado: prompt compacto (≤ 3 gaps, max 80 chars cada uno) para que
        qwen2.5:1.5b genere respuesta dentro del timeout de 60s con el grafo actual.
        """
        # FIX: Convertir a str antes del slicing — gaps puede contener KnowledgeNode o strings
        trimmed_gaps = [str(g)[:80] for g in gaps[:3]]
        gaps_str = ", ".join(trimmed_gaps)
        first_gap = trimmed_gaps[0] if trimmed_gaps else "IA Avanzada"

        prompt = f"""Eres ThinkerAgent de NOVA. Detectaste conocimiento escaso en: {gaps_str}

Genera UNA hipótesis técnica audaz que conecte estos temas.
Ej: "Si combinamos {first_gap} con seguridad, ¿optimizamos X?"

Responde EXCLUSIVAMENTE en JSON (sin texto extra):
{{
  "title": "Título corto",
  "reasoning": "Por qué investigar esto ahora (1 frase)",
  "hypothesis": "Pregunta técnica a validar (1 frase)",
  "target_topic": "Tema para el Explorer",
  "suggested_model": "coder|default (usar 'coder' si implica generación de software)",
  "priority": "alta",
  "estimated_value": 8
}}"""

        thinker_priority = 0 if THINKER_USE_FAST_LANE and not llm_client.is_user_active() else 1
        if thinker_priority == 0:
            self._log_status("Ejecutando Thinker en carril rápido (usuario inactivo).")

        response = await llm_gateway.chat(
            messages=[{"role": "user", "content": prompt}],
            lane="realtime" if thinker_priority == 0 else "batch",
            temperature=0.7,   # Ligeramente menos aleatorio → respuestas más cortas y directas
            priority=thinker_priority,
            model=LLM_THINKER_MODEL
        )

        try:
            # Limpieza básica de la respuesta JSON
            clean_json = response.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0]
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[1].split("```")[0]
                
            parsed = json.loads(clean_json)
            required_fields = {
                "title": lambda: "Exploración de " + (str(gaps[0]) if gaps else "Nuevas Tecnologías"),
                "reasoning": lambda: "Detección de baja densidad de conexiones en el grafo técnico.",
                "hypothesis": lambda: "¿Cómo podemos profundizar en el impacto de estas tecnologías?",
                "target_topic": lambda: str(gaps[0]) if gaps else "Tendencias Tecnológicas 2026",
                "priority": lambda: "media",
                "estimated_value": lambda: 7
            }
            for field, fallback_fn in required_fields.items():
                if field not in parsed or not parsed[field]:
                    parsed[field] = fallback_fn()
            return parsed
        except Exception as e:
            logger.error(f"Error parseando hipótesis del Thinker: {e}")
            return {
                "title": "Exploración de " + (str(gaps[0]) if gaps else "Nuevas Tecnologías"),
                "reasoning": "Detección de baja densidad de conexiones en el grafo técnico.",
                "hypothesis": "¿Cómo podemos profundizar en el impacto de estas tecnologías en el ecosistema actual?",
                "target_topic": str(gaps[0]) if gaps else "Tendencias Tecnológicas 2026",
                "priority": "media",
                "estimated_value": 7
            }

# Instancia global para facilitar acceso
thinker_agent = ThinkerAgent()
