import asyncio
import json
from typing import List
from core.config import MAX_TOPICS_PER_DAY # type: ignore
from core.llm_client import llm_client # type: ignore

from agents.base_agent import BaseAgent # type: ignore

class PlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__("Planner") # type: ignore

    async def execute(self, interest_areas: List[str], **kwargs) -> List[str]:
        """
        Generates research topics based on interest areas using real LLM.
        """
        from core.utils import parse_llm_json # type: ignore
        print(f"[{self.name}] Generating real topics for: {interest_areas}")
        
        prompt = f"""
        Como un Agente Planificador experto, genera exactamente {MAX_TOPICS_PER_DAY} temas de investigación 
        específicos y actuales basados en estas áreas de interés: {', '.join(interest_areas)}.
        Los temas deben ser concisos y listos para ser buscados en la web.
        Responde exclusivamente en formato JSON con una lista de strings llamada "topics".
        """
        
        messages = [{"role": "user", "content": prompt}]
        response_text = await llm_client.chat(messages, format="json", priority=1)
        
        try:
            from core.knowledge_base import knowledge_base # type: ignore
            from core.vector_db import vector_db # type: ignore
            existing_titles = await knowledge_base.get_recent_titles(limit=50)
            
            data = parse_llm_json(response_text)
            raw_topics = data.get("topics", [])
            
            # FIX-6.3: Optimized Semantic deduplication (Batch)
            unique_topics = []
            
            # Perform batch search for all topics at once
            all_search_results = vector_db.search_similar_batch(raw_topics, limit=1)
            
            for i, topic in enumerate(raw_topics):
                if len(unique_topics) >= MAX_TOPICS_PER_DAY: break
                
                is_redundant = False
                # Check semantic redundancy from batch results
                if i < len(all_search_results):
                    results = all_search_results[i]
                    if results and results[0].get('distance', 1.0) < 0.15:
                        print(f"[{self.name}] Topic '{topic}' is semantically redundant (dist: {results[0].get('distance')}).")
                        is_redundant = True
                
                # Keyword-based exact match fallback
                if not is_redundant:
                    for existing in existing_titles:
                        if topic.strip().lower() == existing.strip().lower():
                            is_redundant = True
                            break
                
                if not is_redundant:
                    unique_topics.append(topic)
            
            print(f"[{self.name}] Generated {len(unique_topics)} unique topics (filtered {len(raw_topics) - len(unique_topics)}).")
            return unique_topics if unique_topics else raw_topics[:MAX_TOPICS_PER_DAY]

        except Exception as e:
            print(f"[{self.name}] Error parsing LLM response: {e}")
            topics = [f"Avances recientes en {area}" for area in interest_areas]
            return topics[:MAX_TOPICS_PER_DAY] # type: ignore
