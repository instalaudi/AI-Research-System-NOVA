# ════════════════════════════════════════════════════════════════
#  NOVA AUTO-EVOLUCIÓN — Pegar en main.py
#  1. Al inicio del archivo junto a los otros imports:
# ════════════════════════════════════════════════════════════════

from core.self_evolution import nova_self_evolution, run_self_evolution_scheduler

# ════════════════════════════════════════════════════════════════
#  2. Dentro de la función lifespan(), después de health_task:
#     Agrega esta línea:
# ════════════════════════════════════════════════════════════════

    evolution_task = asyncio.create_task(run_self_evolution_scheduler())

#  Y en el bloque de cierre (después de health_task.cancel()):

    if not evolution_task.done():
        evolution_task.cancel()

# ════════════════════════════════════════════════════════════════
#  3. Nuevos endpoints — pegar antes del endpoint /health:
# ════════════════════════════════════════════════════════════════

# ── Estado de auto-evolución de NOVA ─────────────────────────────
@app.get("/nova/status")
async def nova_evolution_status(current_user: User = Depends(get_current_user)):
    """Estado actual de la auto-evolución de NOVA."""
    proposals = nova_self_evolution.get_pending_proposals()
    return {
        "status": "active",
        "last_introspection": nova_self_evolution._last_introspection,
        "last_tech_watch": nova_self_evolution._last_tech_watch,
        "pending_proposals": len(proposals),
        "proposals": proposals,
        "evolution_cycles": len(nova_self_evolution._evolution_log),
    }

# ── Forzar ciclo de auto-evolución ahora ─────────────────────────
@app.post("/nova/evolve")
async def nova_force_evolution(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """Fuerza un ciclo completo de auto-evolución ahora."""
    background_tasks.add_task(nova_self_evolution.run_evolution_cycle)
    return {"status": "Ciclo de auto-evolución iniciado en background"}

# ── Solo introspección ────────────────────────────────────────────
@app.post("/nova/introspect")
async def nova_introspect(current_user: User = Depends(get_current_user)):
    """NOVA analiza su propio sistema."""
    result = await nova_self_evolution.introspect()
    return {"introspection": result}

# ── Analizar un archivo específico del código ─────────────────────
@app.post("/nova/analyze-file")
async def nova_analyze_file(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """NOVA lee y analiza un archivo de su propio código."""
    body = await request.json()
    filename = body.get("filename", "main.py")
    result = await nova_self_evolution.analyze_own_file(filename)
    return {"filename": filename, "analysis": result}

# ── Vigilancia tecnológica ────────────────────────────────────────
@app.post("/nova/tech-watch")
async def nova_tech_watch(current_user: User = Depends(get_current_user)):
    """NOVA busca novedades tecnológicas para su evolución."""
    result = await nova_self_evolution.tech_watch()
    return {"tech_watch": result}

# ── Propuestas de mejora ──────────────────────────────────────────
@app.get("/nova/proposals")
async def nova_get_proposals(current_user: User = Depends(get_current_user)):
    """Lista propuestas de mejora pendientes de aprobación."""
    proposals = nova_self_evolution.get_pending_proposals()
    return {"proposals": proposals, "total": len(proposals)}

# ── Aprobar una propuesta ─────────────────────────────────────────
@app.post("/nova/proposals/{index}/approve")
async def nova_approve_proposal(
    index: int,
    current_user: User = Depends(get_current_user)
):
    """Juan Ramón aprueba una propuesta de NOVA."""
    result = nova_self_evolution.approve_proposal(index)
    if result:
        return {"status": "approved", "proposal": result}
    raise HTTPException(status_code=404, detail="Propuesta no encontrada")