import asyncio
import json
from typing import List
from core.config import MAX_TOPICS_PER_DAY # type: ignore
from core.llm_gateway import llm_gateway # type: ignore

from agents.base_agent import BaseAgent # type: ignore

class PlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__("Planner") # type: ignore

    async def execute(self, interest_areas: List[str], **kwargs) -> List[str]:
        """
        Generates research topics based on interest areas using pure logic (no LLM).
        """
        print(f"[{self.name}] Generating topics using pure logic for: {interest_areas}")
        
        # Pure logic topic generation
        topics = []
        for area in interest_areas:
            # Generate variations based on current trends
            base_topics = [
                f"Avances recientes en {area}",
                f"Aplicaciones prácticas de {area}",
                f"Desafíos éticos en {area}",
                f"Tendencias futuras de {area}",
                f"Casos de estudio en {area}"
            ]
            topics.extend(base_topics)
        
        # Limit to MAX_TOPICS_PER_DAY
        topics = topics[:MAX_TOPICS_PER_DAY]
        
        # Deduplication using knowledge base (no LLM)
        try:
            from core.knowledge_base import knowledge_base
            existing_titles = await knowledge_base.get_recent_titles(limit=50)
            
            unique_topics = []
            for topic in topics:
                is_duplicate = any(
                    topic.strip().lower() == existing.strip().lower() 
                    for existing in existing_titles
                )
                if not is_duplicate:
                    unique_topics.append(topic)
            
            topics = unique_topics[:MAX_TOPICS_PER_DAY]
        except Exception as e:
            print(f"[{self.name}] Warning in deduplication: {e}")
        
        print(f"[{self.name}] Generated {len(topics)} topics using pure logic.")
        return topics
