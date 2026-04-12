from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Query
from typing import List
from core.database import User
from core.auth import get_current_user
from core.sandbox import sandbox
from core.knowledge_base import knowledge_base
from core.logging_config import get_logger

from routers.schemas import ExecuteCodeRequest, GameRequest, ResearchRequest
from services.agent_service import agent_service

logger = get_logger("routers.agents")
router = APIRouter(tags=["agents"])

@router.post("/research/start")
async def start_research(request: Request, body: ResearchRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    """
    Triggers a new research cycle. Logic moved to AgentService.
    """
    return await agent_service.start_research_task(body.interest_areas, current_user.id, background_tasks)

@router.post("/sandbox/execute", dependencies=[Depends(get_current_user)])
async def execute_code(request: ExecuteCodeRequest):
    """
    Execution in sandbox remains a simple core call, but we wrap it here.
    """
    lang = request.language.lower()
    if lang == "python":
        return await sandbox.execute_python(request.code)
    elif lang in ["javascript", "js"]:
        return await sandbox.execute_js(request.code)
    elif lang in ["typescript", "ts"]:
        return await sandbox.execute_ts(request.code)
    else:
        return {"success": False, "stderr": f"Languaje '{lang}' no soportado."}

@router.get("/graph", dependencies=[Depends(get_current_user)])
async def get_graph(limit: int = Query(100, ge=1, le=500)):
    """
    Retrieves knowledge graph nodes and links with pagination (v10.15.0).
    Prevents UI freezing by limiting the number of rendered entities.
    """
    return await knowledge_base.get_graph(limit=limit)

@router.post("/generate-game")
async def generate_game(request: Request, req: GameRequest, current_user: User = Depends(get_current_user)):
    """
    Delegates game generation and scene creation to AgentService.
    """
    return await agent_service.generate_game_scene(req.idea, req.genre, req.complexity, current_user.id)
