from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def execute(self, input_data: Any, **kwargs) -> Any:
        """
        Main execution logic for the agent.
        Must be implemented by all specialized agents.
        """
        pass

    def __repr__(self):
        return f"<{self.name}Agent>"
