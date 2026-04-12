# ════════════════════════════════════════════════════════════════
#  DESTILACIÓN DE CONOCIMIENTO — Agregar a main.py
# ════════════════════════════════════════════════════════════════

# 1. IMPORTS — agregar junto a los otros imports al inicio:

from core.distillation   import nova_distillation, run_distillation_scheduler
from core.dataset_builder import nova_dataset_builder

# 2. EN lifespan() — agregar después de evolution_task:

    distillation_task = asyncio.create_task(run_distillation_scheduler())

# Y en el cierre:

    if not distillation_task.done():
        distillation_task.cancel()

# 3. NUEVOS ENDPOINTS — agregar antes de /health:

# ── Progreso del dataset de NOVA ─────────────────────────────────
@app.get("/nova/dataset/progress")
async def nova_dataset_progress(current_user: User = Depends(get_current_user)):
    """Estado actual del dataset de entrenamiento de NOVA."""
    return nova_dataset_builder.get_progress()

# ── Construir dataset completo ────────────────────────────────────
@app.post("/nova/dataset/build")
async def nova_build_dataset(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Construye el dataset completo de NOVA en background."""
    background_tasks.add_task(nova_dataset_builder.build_complete_dataset)
    return {"status": "Construyendo dataset en background — revisa /nova/dataset/progress"}

# ── Sesión de destilación manual ─────────────────────────────────
@app.post("/nova/distill")
async def nova_distill_now(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Ejecuta una sesión de destilación ahora mismo."""
    body = await request.json()
    domain    = body.get("domain", None)
    questions = body.get("questions", 5)

    result = await nova_distillation.distill_session(
        domain               = domain,
        questions_per_domain = questions
    )
    return {"status": "ok", "result": result}

# ── Destilación masiva en background ─────────────────────────────
@app.post("/nova/distill/full")
async def nova_distill_full(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Inicia destilación masiva de todos los dominios."""
    background_tasks.add_task(nova_distillation.run_full_distillation)
    return {"status": "Destilación masiva iniciada — tomará varios minutos"}

# ── Estadísticas del dataset ──────────────────────────────────────
@app.get("/nova/dataset/stats")
async def nova_dataset_stats(current_user: User = Depends(get_current_user)):
    """Estadísticas detalladas del dataset acumulado."""
    return nova_distillation.get_dataset_stats()