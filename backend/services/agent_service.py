import json
import re
from typing import List, Any
from fastapi import HTTPException
from core.database import SessionLocal, KnowledgeEntry, User
from core.task_queue import task_queue
from core.distillation import nova_distillation
from core.llm_client import llm_client
from core.config import LLM_FAST_MODEL
from core.prompts import GAME_GENERATION_PROMPT
from core.logging_config import get_logger

logger = get_logger("services.agent")

class AgentService:
    def __init__(self):
        pass

    async def start_research_task(self, interest_areas: List[str], user_id: int, background_tasks: Any):
        """
        Orchestrates the start of research tasks and master model distillation.
        """
        if task_queue.get_size() > 100:
            raise HTTPException(status_code=429, detail="System overloaded. Please try again later.")

        for area in interest_areas:
            # 1. Start research in internet (task queue)
            await task_queue.add_task(
                "start_research",
                {"interest_areas": [area]},
                topic=area,
                user_id=user_id
            )
            # 2. Master Model Distillation (Background)
            background_tasks.add_task(
                nova_distillation.distill_session,
                area,
                3,
            )
        logger.info(f"Research cycle started for areas: {interest_areas} by user {user_id}")
        return {
            "status": "Aprendizaje doble iniciado",
            "areas": interest_areas,
            "systems": ["Internet Research -> Knowledge Graph", "Distillation -> Dataset"]
        }

    async def generate_game_scene(self, idea: str, genre: str, complexity: str, user_id: int) -> dict:
        """
        Generates a NexusEngine JSON scene from a text idea.
        """
        prompt = GAME_GENERATION_PROMPT.format(idea=idea, genre=genre, complexity=complexity)
        
        # v10.7.0: Se utiliza el singleton 'llm_client' global en lugar de instanciar un nuevo cliente.
        # Esto asegura que se respeten los semáforos de concurrencia, el pool de conexiones compartido
        # y las métricas del sistema, evitando saturación de recursos en hardware local (Ryzen).
        # Use Global LLM Client with background priority (1)
        try:
            response = await llm_client.chat(
                [{"role": "user", "content": prompt}], 
                temperature=0.3,
                priority=1,
                model=LLM_FAST_MODEL
            )
        except Exception as e:
            logger.error(f"LLM failed to generate scene: {e}")
            raise HTTPException(status_code=503, detail="Generation failed.")

        if not response:
            logger.error(f"LLM failed to generate scene for idea: {idea}")
            raise HTTPException(status_code=503, detail="Generation failed.")

        scene_data = self._parse_scene_json(response, idea, genre)
        
        # Persist scene as knowledge
        db = SessionLocal()
        try:
            entry = KnowledgeEntry(
                title=f"[NexusEngine] Juego: {idea[:60]}",
                category="NexusEngine",
                content=json.dumps(scene_data, ensure_ascii=False),
                confidence_score=0.9,
                concepts=f"videojuego,nexusengine,{genre},{scene_data.get('biome','')}",
                user_id=user_id
            )
            db.add(entry)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist game scene in DB: {e}")
        finally:
            db.close()

        return {
            "status": "ok",
            "scene": scene_data,
            "message": f"🌟 NOVA generó tu juego: {scene_data.get('name', idea)}"
        }

    def _parse_scene_json(self, response: str, idea: str, genre: str) -> dict:
        """
        Safely attempts to parse JSON from LLM response or returns a fallback scene.
        """
        scene_data = None
        try:
            scene_data = json.loads(response.strip())
            if scene_data: scene_data["_fallback"] = False
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try: 
                    scene_data = json.loads(json_match.group())
                    if scene_data: scene_data["_fallback"] = True # Marcar como extraccin parcial/fallback
                except: pass

        if not scene_data:
            # Fallback Logic
            idea_lower = idea.lower()
            biome, hour = "forest", 14
            if any(w in idea_lower for w in ["noche", "oscuro", "espacio", "night", "dark"]):
                biome, hour = "night", 2
            elif any(w in idea_lower for w in ["mar", "playa", "isla", "agua", "sea", "ocean"]):
                biome, hour = "coast", 13

            scene_data = {
                "name": idea[:50],
                "genre": genre,
                "biome": biome,
                "entities": [{"type": "tree", "count": 10, "area": 20}],
                "environment": {"hour": hour, "exposure": 1.0},
                "_fallback": True
            }
        return scene_data

agent_service = AgentService()
