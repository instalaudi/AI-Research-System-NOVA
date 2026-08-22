"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v14.0 — Memoria Jerárquica Episódica                    ║
║  Archivo: core/episodic_memory.py                            ║
║  Gestiona 3 capas temporales de memoria:                     ║
║  1. Memoria de Sesión (Corto Plazo)                          ║
║  2. Memoria Episódica (Resúmenes e Hitos de Investigación)   ║
║  3. Memoria Semántica (Hechos y Preferencias del Usuario)    ║
╚══════════════════════════════════════════════════════════════╝
"""

import re
import json
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.config import DATA_DIR


logger = logging.getLogger("core.episodic_memory")


class EpisodicMemory:
    """
    Sistema de Memoria Jerárquica para NOVA.
    Permite recordar contexto de sesiones pasadas, hitos de proyectos generados
    y preferencias del usuario a lo largo del tiempo.
    """
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or (Path(DATA_DIR) / "episodic_memory.json")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Capa 1: Memoria de Sesión Activa (turnos recientes)
        self.session_buffer: List[Dict[str, Any]] = []
        self.max_session_turns: int = 20
        
        # Capa 2: Memoria Episódica (Hitos, resúmenes de builds, investigaciones)
        self.episodes: List[Dict[str, Any]] = []
        
        # Capa 3: Memoria Semántica (Hechos aprendidos y preferencias de usuario)
        self.user_facts: Dict[str, Any] = {}
        
        self._load_memory()

    def _load_memory(self):
        """Carga la memoria episódica desde disco."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.episodes = data.get("episodes", [])
                    self.user_facts = data.get("user_facts", {})
            except Exception as e:
                logger.error(f"[EpisodicMemory] Error cargando memoria: {e}")
                self.episodes = []
                self.user_facts = {}

    def _save_memory(self):
        """Persiste la memoria episódica a disco."""
        try:
            temp_file = self.storage_path.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump({
                    "episodes": self.episodes[-200:], # Guardar últimos 200 episodios
                    "user_facts": self.user_facts,
                    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                }, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.storage_path)
        except Exception as e:
            logger.error(f"[EpisodicMemory] Error guardando memoria: {e}")

    # ── CAPA 1: Sesión Corta ──────────────────────────────────────────

    def record_turn(self, role: str, content: str, intent: Optional[str] = None):
        """Registra un turno en la memoria de sesión activa."""
        self.session_buffer.append({
            "role": role,
            "content": content,
            "intent": intent,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
        if len(self.session_buffer) > self.max_session_turns:
            self.session_buffer.pop(0)

    def get_recent_session(self, n: int = 5) -> List[Dict[str, Any]]:
        """Retorna los últimos N turnos de la sesión actual."""
        return self.session_buffer[-n:]

    # ── CAPA 2: Episodios (Hitos e Investigaciones) ────────────────────

    def record_episode(
        self,
        topic: str,
        summary: str,
        category: str = "research", # "research", "project_build", "curiosity", "bug_fix"
        key_learnings: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Registra un episodio relevante para recuerdo a largo plazo."""
        episode = {
            "id": f"ep_{len(self.episodes) + 1}_{int(datetime.datetime.now().timestamp())}",
            "topic": topic,
            "summary": summary,
            "category": category,
            "key_learnings": key_learnings or [],
            "metadata": metadata or {},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.episodes.append(episode)
        self._save_memory()
        logger.info(f"[EpisodicMemory] 💾 Nuevo episodio guardado: [{category}] {topic}")

    def recall_relevant_episodes(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Recupera episodios pasados relevantes para la consulta actual usando solapamiento léxico y semántico.
        """
        if not self.episodes or not query:
            return []

        query_words = set(re.findall(r'\w+', query.lower()))
        scored_episodes = []

        for ep in self.episodes:
            content_to_match = f"{ep.get('topic', '')} {ep.get('summary', '')} {' '.join(ep.get('key_learnings', []))}".lower()
            ep_words = set(re.findall(r'\w+', content_to_match))
            
            overlap = len(query_words.intersection(ep_words))
            if overlap > 0:
                score = overlap / (len(query_words) + 1)
                scored_episodes.append((score, ep))

        scored_episodes.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored_episodes[:limit]]

    # ── CAPA 3: Hechos y Preferencias del Usuario ──────────────────────

    def record_fact(self, key: str, value: Any):
        """Almacena o actualiza un hecho relevante sobre el usuario o su entorno."""
        self.user_facts[key] = {
            "value": value,
            "learned_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self._save_memory()

    def get_facts_context(self) -> str:
        """Formatea los hechos del usuario como bloque de contexto para el prompt."""
        if not self.user_facts:
            return ""
        lines = ["# Preferencias y Hechos del Usuario:"]
        for k, v in self.user_facts.items():
            lines.append(f"- **{k}**: {v.get('value')}")
        return "\n".join(lines)


# Instancia global de memoria episódica
episodic_memory = EpisodicMemory()
