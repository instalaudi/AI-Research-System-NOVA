import hashlib
import time
import json
from typing import Any, Optional, Dict
from core.logging_config import get_logger

logger = get_logger("core.cache")

class SmartCache:
    def __init__(self, ttl_seconds: int = 7200): # Enterprise: 2 hours TTL
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.ttl = ttl_seconds

    def _generate_key(self, prompt: str, model: str, params: Dict[str, Any], session_id: str) -> str:
        """
        Generates a unique SHA-256 hash for the given request parameters.
        Includes model and parameters to ensure cache precision.
        """
        payload = {
            "prompt": prompt,
            "model": model,
            "params": params,
            "session_id": session_id
        }
        payload_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()

    def get(self, prompt: str, model: str, params: Dict[str, Any], session_id: str) -> Optional[str]:
        """
        Attempts to retrieve a cached response.
        """
        key = self._generate_key(prompt, model, params, session_id)
        if key in self._cache:
            entry = self._cache[key]
            if time.time() - entry['timestamp'] < self.ttl:
                logger.info(f"Cache HIT for key: {key[:8]}...")
                return entry['response']
            else:
                # Expired
                del self._cache[key]
                logger.info(f"Cache EXPIRED for key: {key[:8]}...")
        
        logger.info(f"Cache MISS for prompt summary: {prompt[:30]}...")
        return None

    def set(self, prompt: str, model: str, params: Dict[str, Any], session_id: str, response: str):
        """
        Stores a response in the cache.
        """
        key = self._generate_key(prompt, model, params, session_id)
        self._cache[key] = {
            "response": response,
            "timestamp": time.time()
        }
        # Basic cleanup: if cache grows too large, clear it (very simple strategy)
        if len(self._cache) > 200:
            logger.info("Cache size reached limit, clearing for memory safety.")
            self._cache.clear()

# Global instance
smart_cache = SmartCache()
