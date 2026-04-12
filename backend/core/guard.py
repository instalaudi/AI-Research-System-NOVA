import re
from typing import Tuple, List, Optional
from core.logging_config import get_logger

logger = get_logger("core.guard")

class PromptGuard:
    def __init__(self):
        # 1. Simple Keyword Blacklist (Case insensitive)
        self.blacklist = [
            "drop table", "truncate table", "delete from", 
            "rm -rf", "format c:", "sudo rm",
            "sql injection", "ignore previous instructions", 
            "now you are an evil"
        ]
        
        # 2. Pattern Matching for specific destructive intents
        self.patterns = [
            (r"(borra|elimina|destruye).*(base de datos|db|registros)", "Destructive data command detected."),
            (r"(olvida|ignora).*(instrucciones|sistema|reglas)", "Instruction override attempt detected."),
            (r"(sandbox|ejecuta).*(formatear|borrar disco|shell)", "Dangerous execution pattern detected.")
        ]

    def is_safe(self, query: str, intent: str = "CHAT") -> Tuple[bool, Optional[str]]:
        """
        Checks if a user query is safe to process.
        Returns (is_safe, reason).
        """
        query_lower = query.lower()

        # Rule 1: SYSTEM intent protection (High risk)
        if intent == "SYSTEM" and any(w in query_lower for w in ["borrar", "eliminar", "clear", "flush"]):
            logger.warning(f"BLOCKED: Attempted destructive system intent. Query: {query[:50]}...")
            return False, "Lo siento, no tengo permitido realizar acciones destructivas sobre el sistema core."

        # Rule 2: Blacklist Check
        for word in self.blacklist:
            if word in query_lower:
                logger.warning(f"BLOCKED: Blacklisted keyword '{word}' detected.")
                return False, "Se ha detectado una instrucción o palabra clave no permitida por razones de seguridad."

        # Rule 3: Pattern matching
        for pattern, reason in self.patterns:
            if re.search(pattern, query_lower):
                logger.warning(f"BLOCKED: {reason}")
                return False, "Tu consulta parece contener patrones de ejecución peligrosos o intentas saltar restricciones de seguridad."

        return True, None

# Global instance
prompt_guard = PromptGuard()
