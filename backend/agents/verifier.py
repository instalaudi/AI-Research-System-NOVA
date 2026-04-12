import asyncio
from typing import Dict, Any
from agents.base_agent import BaseAgent
from core.config import QUALITY_THRESHOLD

class VerifierAgent(BaseAgent):
    def __init__(self):
        super().__init__("Verifier")

    async def execute(self, critique: Dict[str, Any], **kwargs) -> bool:
        """
        Final check on information quality and reliability.
        """
        print(f"[{self.name}] Verifying quality of: {critique.get('title')}")
        
        score = critique.get("review_score", 0)
        is_valid = score >= QUALITY_THRESHOLD
        
        if is_valid:
            print(f"[{self.name}] Quality confirmed: {score}")
        else:
            print(f"[{self.name}] Quality rejected: {score}")
            
        return is_valid
