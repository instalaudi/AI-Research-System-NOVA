import hashlib
import time
import json
import re
from typing import Any, Optional, Dict
from collections import OrderedDict
from core.logging_config import get_logger

logger = get_logger("core.cache")


class SmartCache:
    """
    v11.9.0: Caché inteligente con normalización semántica y evicción LRU.
    
    Cambios principales vs v11.8:
    - Normalización de prompts (elimina timestamps, UUIDs, whitespace redundante)
    - session_id ya no forma parte del hash (sistema single-user)
    - Evicción LRU en lugar de borrar todo al llegar al límite
    - Métricas de hit/miss para monitoreo
    """

    def __init__(self, ttl_seconds: int = 7200, max_entries: int = 300):
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.ttl = ttl_seconds
        self.max_entries = max_entries
        # Métricas
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        """
        Normaliza el prompt para maximizar cache hits.
        Elimina variaciones triviales que no afectan la respuesta:
        - UUIDs (e.g. session IDs)
        - Timestamps ISO y en Español (lunes 11 de mayo...)
        - Whitespace redundante
        """
        text = prompt.strip().lower()
        # Eliminar UUIDs (8-4-4-4-12 hex)
        text = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '', text)
        # Eliminar timestamps ISO (2024-01-15T10:30:00)
        text = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?', '', text)
        
        # v12.1.5: Eliminar fechas y horas en español (ej: "lunes 12 de mayo de 2026, 10:30 pm")
        # Esto es vital porque NOVA inyecta el tiempo actual cada minuto, rompiendo la caché.
        dias = r'(lunes|martes|miércoles|jueves|viernes|sábado|domingo)'
        meses = r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)'
        text = re.sub(rf'{dias}\s+\d{{1,2}}\s+de\s+{meses}\s+de\s+\d{{4}}.*?(am|pm)', '', text, flags=re.IGNORECASE)
        
        # Eliminar timestamps epoch (1713000000)
        text = re.sub(r'\b1[6-9]\d{8,9}\b', '', text)
        # Colapsar whitespace múltiple
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _generate_key(self, prompt: str, model: str, params: Dict[str, Any], session_id: str = None) -> str:
        """
        Genera SHA-256 normalizado. session_id se ignora para permitir
        cache hits cross-session (aceptable en sistema single-user).
        """
        normalized = self._normalize_prompt(prompt)
        payload = {
            "prompt": normalized,
            "model": model,
            "params": params,
        }
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()

    def get(self, prompt: str, model: str, params: Dict[str, Any], session_id: str = None) -> Optional[str]:
        """Intenta recuperar una respuesta cacheada."""
        key = self._generate_key(prompt, model, params, session_id)
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry['timestamp'] < self.ttl:
                # Mover al final (MRU) para LRU eviction
                self._cache.move_to_end(key)
                self._hits += 1
                logger.info(f"Cache HIT for key: {key[:8]}... (hit_rate: {self.hit_rate:.1%})")
                return entry['response']
            else:
                # Expirado
                del self._cache[key]
                logger.info(f"Cache EXPIRED for key: {key[:8]}...")
        
        self._misses += 1
        logger.info(f"Cache MISS for prompt summary: {prompt[:40]}... (hit_rate: {self.hit_rate:.1%})")
        return None

    def set(self, prompt: str, model: str, params: Dict[str, Any], session_id: str, response: str):
        """Almacena una respuesta en la caché con evicción LRU."""
        key = self._generate_key(prompt, model, params, session_id)
        
        # Si ya existe, actualizar y mover al final
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = {
                "response": response,
                "timestamp": time.time()
            }
            return
        
        # Evicción LRU: eliminar el más antiguo si estamos al límite
        while len(self._cache) >= self.max_entries:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug(f"Cache LRU eviction: {evicted_key[:8]}...")
        
        self._cache[key] = {
            "response": response,
            "timestamp": time.time()
        }

    @property
    def hit_rate(self) -> float:
        """Tasa de acierto actual."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    def get_stats(self) -> Dict[str, Any]:
        """Estadísticas de rendimiento del caché."""
        return {
            "entries": len(self._cache),
            "max_entries": self.max_entries,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 4),
            "ttl_seconds": self.ttl,
        }

    def clear(self):
        """Purga completa del caché."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("Cache PURGED successfully.")

# Global instance
smart_cache = SmartCache()
