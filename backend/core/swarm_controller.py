from typing import List, Dict, Any, Optional
from core.llm_client import llm_client
from core.prompts import RESEARCHER_AGENT_PROMPT, CODER_AGENT_PROMPT, VALIDATOR_AGENT_PROMPT, SYNTHESIS_AGENT_PROMPT

class SwarmController:
    """
    Manages dynamic collaboration between specialized agents.
    Decides the next action based on current state and goals.
    """
    def __init__(self):
        self.max_steps = 5
        
    async def decide_next_agent(self, context: Dict[str, Any]) -> str:
        """
        Logic to determine which agent should act next.
        """
        history = context.get("history", [])
        last_action = history[-1]["agent"] if history else None
        
        if not last_action:
            return "researcher"
            
        if last_action == "researcher":
            # If data looks like it needs calculation/processing
            findings = context.get("findings", "")
            
            # Prioritize Vision if images are found
            if context.get("images") and len(context["images"]) > 0:
                return "vision"

            if any(word in findings.lower() for word in ["calcula", "promedio", "tendencia", "datos", "json", "csv"]):
                return "coder"
            return "validator"
            
        if last_action == "vision":
            return "coder" if any(word in context.get("findings", "").lower() for word in ["calcula", "datos"]) else "validator"
            
        if last_action == "coder":
            return "validator"
            
        if last_action == "validator":
            critique = context.get("validator_critique", "")
            if "RECHAZADO" in critique.upper() or "ERROR" in critique.upper():
                return "researcher" # Back to research if failed
            return "synthesis"
            
        return "end"

swarm_controller = SwarmController()
