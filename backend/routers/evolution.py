from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from core.database import User
from core.auth import get_current_user, get_current_admin
from services.evolution_service import evolution_service
from core.logging_config import get_logger
from routers.schemas import ApproveProposalRequest

logger = get_logger("routers.evolution")
router = APIRouter(tags=["evolution"], dependencies=[Depends(get_current_admin)])

@router.get("/nova/status")
async def nova_evolution_status(current_user: User = Depends(get_current_user)):
    """Estado actual de la auto-evolución de NOVA."""
    return evolution_service.get_evolution_status()

@router.post("/nova/evolve")
async def nova_force_evolution(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    """Fuerza un ciclo completo de auto-evolución ahora."""
    return await evolution_service.force_evolution_cycle(background_tasks)

@router.post("/nova/introspect")
async def nova_introspect(current_user: User = Depends(get_current_user)):
    """NOVA analiza su propio sistema."""
    return await evolution_service.introspect_self()

@router.post("/nova/analyze-file")
async def nova_analyze_file(request: Request, current_user: User = Depends(get_current_user)):
    """NOVA lee y analiza un archivo de su propio código."""
    body = await request.json()
    filename = body.get("filename", "main.py")
    return await evolution_service.analyze_file(filename)

@router.post("/nova/tech-watch")
async def nova_tech_watch(current_user: User = Depends(get_current_user)):
    """NOVA busca novedades tecnológicas para su evolución."""
    return await evolution_service.tech_watch()

@router.get("/nova/proposals")
async def nova_get_proposals(current_user: User = Depends(get_current_user)):
    """Lista propuestas de mejora pendientes de aprobación."""
    return evolution_service.get_proposals()

@router.post("/nova/proposals/approve")
async def nova_approve_proposal(req: ApproveProposalRequest, current_user: User = Depends(get_current_user)):
    """Juan Ramón aprueba una propuesta de NOVA por ID."""
    result = evolution_service.approve_proposal(req.proposal_id)
    if result:
        return result
    raise HTTPException(status_code=404, detail="Propuesta no encontrada")

@router.get("/nova/dataset/progress")
async def nova_dataset_progress(current_user: User = Depends(get_current_user)):
    """Estado actual del dataset de entrenamiento de NOVA."""
    return evolution_service.get_dataset_progress()

@router.post("/nova/dataset/build")
async def nova_build_dataset(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    """Construye el dataset completo de NOVA en background."""
    return evolution_service.build_dataset(background_tasks)

@router.post("/nova/distill")
async def nova_distill_now(request: Request, current_user: User = Depends(get_current_user)):
    """Ejecuta una sesión de destilación ahora mismo."""
    body = await request.json()
    domain, questions = body.get("domain", None), body.get("questions", 5)
    return await evolution_service.run_distillation(domain=domain, questions=questions)

@router.post("/nova/distill/full")
async def nova_distill_full(background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    """Inicia destilación masiva de todos los dominios."""
    return evolution_service.run_full_distillation(background_tasks)

@router.get("/nova/dataset/stats")
async def nova_dataset_stats(current_user: User = Depends(get_current_user)):
    """Estadísticas detalladas del dataset acumulado."""
    return evolution_service.get_dataset_stats()

@router.get("/nova/telemetry", dependencies=[Depends(get_current_admin)])
async def nova_evolution_telemetry(current_user: User = Depends(get_current_admin)):
    """Dashboard de inteligencia y salud evolutiva."""
    return evolution_service.get_evolution_telemetry()

@router.post("/nova/audit/cleanup", dependencies=[Depends(get_current_admin)])
async def nova_cleanup_logs(request: Request):
    """Limpia los logs de auditoría (manual override)."""
    body = await request.json()
    force = body.get("force", False)
    return evolution_service.cleanup_evolution_logs(force=force)

@router.post("/nova/mode")
async def nova_set_evolution_mode(request: Request, current_user: User = Depends(get_current_user)):
    """Cambia manualmente el modo de evolución (active/learning)."""
    body = await request.json()
    mode = body.get("mode", "active")
    return evolution_service.set_evolution_mode(mode)

@router.get("/nova/rankings")
async def nova_evolution_rankings(current_user: User = Depends(get_current_user)):
    """Rankings accionables de módulos críticos."""
    return evolution_service.get_evolution_rankings()

@router.get("/nova/logs")
async def nova_evolution_logs(limit: int = 50, current_user: User = Depends(get_current_user)):
    """Historial cronológico de la evolución de NOVA (Auditoría)."""
    return evolution_service.get_evolution_logs(limit=limit)

@router.post("/nova/emergency", dependencies=[Depends(get_current_admin)])
async def nova_emergency_action(request: Request):
    """Botón de emergencia multinivel (soft_stop, hard_stop, reset)."""
    body = await request.json()
    level = body.get("level", "soft")
    return evolution_service.emergency_action(level)
