import time
import asyncio
from typing import List, Dict, Any

class AgentLogger:
    def __init__(self, max_logs: int = 50):
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = max_logs
        self.agent_states: Dict[str, str] = {
            "Planner": "idle",
            "Explorer": "idle",
            "Analyzer": "idle",
            "Critic": "idle",
            "Verifier": "idle",
            "Librarian": "idle",
            "Browser": "idle"
        }
        self.lock = asyncio.Lock() # BUG-02: Prevention

    async def log(self, agent: str, message: str):
        async with self.lock:
            timestamp = time.strftime("%H:%M:%S")
            log_entry = {"time": timestamp, "agent": agent, "message": message}
            self.logs.append(log_entry)
            if len(self.logs) > self.max_logs:
                self.logs.pop(0)
            
            # BUG-03: Refined state deduction. 
            # Only auto-set 'working' if it looks like a clear start.
            # Don't auto-set 'idle' here, let set_state handle it to avoid flickering.
            working_keywords = ["Iniciando", "Buscando", "Analizando", "Verificando", "Sincronizando", "Criticando"]
            if any(kw in message for kw in working_keywords):
                self.agent_states[agent] = "working"

    async def set_state(self, agent: str, state: str):
        async with self.lock:
            if agent in self.agent_states:
                self.agent_states[agent] = state

    async def get_data(self):
        async with self.lock:
            return {
                "logs": self.logs.copy(),
                "states": self.agent_states.copy()
            }

# Global instance
agent_logger = AgentLogger()
