from typing import Dict, Any, List
from sqlalchemy import func, desc
from core.database import SessionLocal, ModuleHealth, EvolutionAudit
from core.self_evolution import nova_self_evolution
from core.distillation import nova_distillation
from core.dataset_builder import nova_dataset_builder
from core.logging_config import get_logger

logger = get_logger("services.evolution")

class EvolutionService:
    def __init__(self):
        pass

    def get_evolution_status(self) -> Dict[str, Any]:
        proposals = nova_self_evolution.get_pending_proposals()
        return {
            "status": "active",
            "last_introspection": nova_self_evolution._last_introspection,
            "last_tech_watch": nova_self_evolution._last_tech_watch,
            "pending_proposals": len(proposals),
            "proposals": proposals,
            "evolution_cycles": len(nova_self_evolution._evolution_log),
        }

    async def force_evolution_cycle(self, background_tasks: Any):
        background_tasks.add_task(nova_self_evolution.run_evolution_cycle)
        logger.info("Manual evolution cycle triggered.")
        return {"status": "Ciclo de auto-evolución iniciado en background"}

    async def introspect_self(self) -> Dict[str, Any]:
        result = await nova_self_evolution.introspect()
        return {"introspection": result}

    async def analyze_file(self, filename: str) -> Dict[str, Any]:
        result = await nova_self_evolution.analyze_own_file(filename)
        return {"filename": filename, "analysis": result}

    async def tech_watch(self) -> Dict[str, Any]:
        result = await nova_self_evolution.tech_watch()
        return {"tech_watch": result}

    def get_proposals(self) -> Dict[str, Any]:
        proposals = nova_self_evolution.get_pending_proposals()
        return {"proposals": proposals, "total": len(proposals)}

    def approve_proposal(self, proposal_id: str) -> Dict[str, Any]:
        result = nova_self_evolution.approve_proposal(proposal_id)
        if result:
            logger.info(f"Proposal {proposal_id} approved.")
            return {"status": "approved", "proposal": result}
        return {}

    def get_dataset_progress(self) -> Dict[str, Any]:
        return nova_dataset_builder.get_progress()

    def build_dataset(self, background_tasks: Any):
        background_tasks.add_task(nova_dataset_builder.build_complete_dataset)
        logger.info("Dataset building triggered.")
        return {"status": "Construyendo dataset en background"}

    async def run_distillation(self, domain: str, questions: int) -> Dict[str, Any]:
        result = await nova_distillation.distill_session(domain=domain, questions_per_domain=questions)
        return {"status": "ok", "result": result}

    def run_full_distillation(self, background_tasks: Any):
        background_tasks.add_task(nova_distillation.run_full_distillation)
        logger.info("Full distillation triggered.")
        return {"status": "Destilación masiva iniciada"}

    def get_dataset_stats(self) -> Dict[str, Any]:
        return nova_distillation.get_dataset_stats()

    def get_evolution_telemetry(self) -> Dict[str, Any]:
        """Consolida métricas de inteligencia y auditoría Ultra v2.5."""
        trend = nova_self_evolution.get_intelligence_trend()
        
        # Obtener módulos en cuarentena
        from core.database import SessionLocal, ModuleHealth
        import datetime
        db = SessionLocal()
        quarantined = []
        try:
            now = datetime.datetime.utcnow()
            q_list = db.query(ModuleHealth).filter(ModuleHealth.cooldown_until > now).all()
            quarantined = [{"filename": m.filename, "fails": m.failure_count, "until": m.cooldown_until} for m in q_list]
            
            # v10.7.0: Movido dentro del bloque try para evitar sesin cerrada
            total_value = db.query(func.sum(ModuleHealth.total_value_generated)).scalar() or 0.0
        finally:
            db.close()

        return {
            "intelligence_trend": trend,
            "success_rate": round((trend.get("success_count", 0) / trend.get("total_attempts", 1)) * 100, 1) if trend.get("total_attempts", 0) > 0 else 0,
            "system_health": "optimal" if trend.get("status") == "improving" else "monitored",
            "evolution_mode": nova_self_evolution.evolution_mode,
            "total_system_value": round(total_value, 2),
            "quarantined_modules": quarantined,
            "consecutive_successes": nova_self_evolution.consecutive_successes,
            "emergency_status": {"soft_stop": nova_self_evolution._soft_stop, "hard_stop": nova_self_evolution._hard_stop}
        }

    def get_evolution_rankings(self) -> Dict[str, Any]:
        """Obtiene rankings accionables de módulos."""
        return nova_self_evolution.get_critical_modules_ranking()

    def emergency_action(self, level: str) -> Dict[str, Any]:
        """Ejecuta acciones de emergencia."""
        nova_self_evolution.emergency_control(level)
        return {"status": "success", "action": level}

    def set_evolution_mode(self, mode: str) -> Dict[str, Any]:
        """Cambia el modo de evolución manualmente (active/learning)."""
        if mode in ["active", "learning"]:
            nova_self_evolution.evolution_mode = mode
            return {"status": "success", "new_mode": mode}
        return {"status": "error", "message": "Invalid mode"}

    def cleanup_evolution_logs(self, force: bool = False) -> Dict[str, Any]:
        """Limpia manualmente los logs de auditoría."""
        nova_self_evolution._manage_evolution_logs(force=force)
        return {"status": "Cleanup process triggered"}

    def get_evolution_logs(self, limit=50) -> List[Dict[str, Any]]:
        """Recupera los logs de auditoría de evolución más recientes."""
        db = SessionLocal()
        try:
            logs = db.query(EvolutionAudit).order_by(desc(EvolutionAudit.timestamp)).limit(limit).all()
            return [{
                "id": log.id,
                "filename": log.filename,
                "timestamp": log.timestamp.isoformat(),
                "score_internal": log.score_internal,
                "confidence_score": log.confidence_score,
                "status": log.status,
                "proposal_title": log.proposal_title
            } for log in logs]
        finally:
            db.close()

evolution_service = EvolutionService()
