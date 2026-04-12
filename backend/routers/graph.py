"""
╔══════════════════════════════════════════════════════════════╗
║  NOVA v10.3 — Router de Grafo (MetaCritic)                   ║
║  Archivo: routers/graph.py                                   ║
║  Endpoints: GET /graph/health                                ║
╚══════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from core.graph_health import analyze_graph_health

from fastapi import APIRouter, Query, Depends
from fastapi.responses import JSONResponse
from core.graph_health import analyze_graph_health
from core.auth import get_current_admin

router = APIRouter(prefix="/graph", tags=["graph"])

@router.get("/health", summary="Anlisis de Salud Estructural del Grafo")
def get_graph_health():
    """
    Fase 3.1: Devuelve un informe pasivo determinista usando NetworkX.
    """
    report = analyze_graph_health()
    if "error" in report:
        return JSONResponse(status_code=500, content={"error": report["error"]})
    return JSONResponse(content=report)

@router.post("/prune/noise", summary="Poda de Nodos Aislados y Aristas Redundantes", dependencies=[Depends(get_current_admin)])
def prune_noise_endpoints():
    """
    Fase 3.2: Ejecuciu de poda determinista.
    """
    from core.graph_pruning import prune_isolated_noise_nodes, prune_redundant_edges
    res_nodes = prune_isolated_noise_nodes()
    res_edges = prune_redundant_edges()
    
    return JSONResponse(content={
        "nodes": res_nodes,
        "edges": res_edges
    })

@router.post("/prune/merge", summary="Fusin Semntica de Nodos Hoja", dependencies=[Depends(get_current_admin)])
async def prune_merge_nodes(limit: int = Query(100, ge=1, le=500)):
    """
    Fase 3.2: Fusin semntica con validacin de lmite.
    """
    from core.graph_pruning import merge_similar_nodes
    res = await merge_similar_nodes(limit=limit)
    if "error" in res:
        return JSONResponse(status_code=500, content=res)
    return JSONResponse(content=res)

@router.get("/audit", summary="Registro de Auditora de Destruccin de Grafo", dependencies=[Depends(get_current_admin)])
def get_graph_audit_log(limit: int = Query(50, ge=1, le=1000)):
    """
    Lista el rastro seguro de auditora con validacin de lmite.
    """
    from core.database import SessionLocal, GraphAuditLog
    import json
    db = SessionLocal()
    try:
        logs = db.query(GraphAuditLog).order_by(GraphAuditLog.timestamp.desc()).limit(limit).all()
        data = []
        for l in logs:
            data.append({
                "id": l.id,
                "action": l.action,
                "target_id": l.target_id,
                "timestamp": l.timestamp.isoformat(),
                "reverted_at": l.reverted_at.isoformat() if l.reverted_at else None,
                "details": json.loads(l.restoration_payload) if l.restoration_payload else {}
            })
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        db.close()
