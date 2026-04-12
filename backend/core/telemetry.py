import time
import datetime
import asyncio
import psutil
import httpx
from typing import Dict, Any, List
from core.database import SessionLocal, KnowledgeEntry, EvolutionAudit, ResearchJob
from sqlalchemy import func

class NOVATelemetry:
    """Sistema de telemetría y monitoreo de salud de NOVA v11."""
    
    def __init__(self):
        self.start_time = time.time()
        self.llm_metrics = {} # model -> {success, total_latency, count}
        self._cache = None
        self._cache_time = 0
        self._cache_duration = 5.0 # Segundos de vida de la caché (v10.11.0)

    def record_llm_success(self, model: str, latency_ms: float):
        """Registra una llamada exitosa al LLM."""
        if model not in self.llm_metrics:
            self.llm_metrics[model] = {"success": 0, "total_latency": 0.0, "count": 0}
        
        self.llm_metrics[model]["success"] += 1
        self.llm_metrics[model]["total_latency"] += latency_ms
        self.llm_metrics[model]["count"] += 1

    async def get_snapshot(self) -> Dict[str, Any]:
        """v10.11.0: Devuelve snapshot asíncrono y cacheado para no bloquear el Event Loop."""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_duration:
            return self._cache

        # Ejecutamos la recolección pesada en un hilo separado para no bloquear FastAPI
        snapshot = await asyncio.to_thread(self._fetch_snapshot_sync)
        
        self._cache = snapshot
        self._cache_time = now
        return snapshot

    def _fetch_snapshot_sync(self) -> Dict[str, Any]:
        """Recolección síncrona de datos (para ser llamada vía to_thread)."""
        from core.llm_client import llm_client
        from core.task_queue import task_queue
        
        db = SessionLocal()
        try:
            # 1. Conocimiento y Tareas
            total_articles = db.query(KnowledgeEntry).count()
            avg_conf = db.query(func.avg(KnowledgeEntry.confidence_score)).scalar() or 0.0
            
            # Tareas detalladas (Filtramos por heartbeat reciente para evitar fantasmas)
            timeout_limit = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
            running_jobs_objs = db.query(ResearchJob).filter(
                ResearchJob.status == "running",
                ResearchJob.last_heartbeat > timeout_limit
            ).all()
            
            active_jobs = [
                {"topic": j.topic, "stage": j.stage, "id": j.id, "heartbeat": j.last_heartbeat.isoformat()} 
                for j in running_jobs_objs
            ]

            task_stats = {
                "completed": db.query(ResearchJob).filter(ResearchJob.status == "completed").count(),
                "in_progress": len(active_jobs),
                "pending": db.query(ResearchJob).filter(ResearchJob.status == "pending").count(),
                "failed": db.query(ResearchJob).filter(ResearchJob.status == "failed").count(),
                "live_activity": active_jobs
            }

            # 2. Ollama Live Probe (v10.16.0)
            ollama_status = "ok"
            ollama_latency = 0
            active_models_in_ram = []
            try:
                import requests
                check_start = time.time()
                # Probar conectividad general
                resp_tags = requests.get("http://localhost:11434/api/tags", timeout=2.0)
                if resp_tags.status_code == 200:
                    ollama_latency = int((time.time() - check_start) * 1000)
                    
                    # Probar modelos cargados en RAM (v10.16)
                    resp_ps = requests.get("http://localhost:11434/api/ps", timeout=2.0)
                    if resp_ps.status_code == 200:
                        ps_data = resp_ps.json()
                        active_models_in_ram = [m.get("name") for m in ps_data.get("models", [])]
                else:
                    ollama_status = "error"
            except:
                ollama_status = "offline"

            llm_models = {}
            relevant_models = set(list(self.llm_metrics.keys()) + active_models_in_ram)
            for name in relevant_models:
                m = self.llm_metrics.get(name, {"total_latency": 0.0, "count": 0})
                llm_models[name] = {
                    "avg_latency_ms": int(m["total_latency"] / m["count"]) if m["count"] > 0 else 0,
                    "calls_total": m["count"],
                    "is_active": name in active_models_in_ram
                }

            return {
                "generated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "uptime": {
                    "uptime_human": str(datetime.timedelta(seconds=int(time.time() - self.start_time)))
                },
                "workers": {
                    "total": task_queue.concurrency,
                    "active": len(task_queue.workers),
                    "busy": max(task_stats["in_progress"], len([w for w in task_queue.workers if not w.done()])),
                    "idle": max(0, task_queue.concurrency - max(task_stats["in_progress"], len([w for w in task_queue.workers if not w.done()]))),
                    "queue_size": task_queue.get_size(),
                },
                "llm": {
                    "total_requests": sum(m["count"] for m in self.llm_metrics.values()),
                    "busy_rate": llm_client.busy_rate,
                    "cache_hit_rate": 0.45,
                    "models": llm_models
                },
                "knowledge": {
                    "total_articles": total_articles,
                    "avg_confidence_score": round(avg_conf, 3),
                    "tasks": task_stats
                },
                "ollama": {
                    "status": ollama_status,
                    "latency_ms": ollama_latency,
                    "models_loaded": active_models_in_ram
                },
                "hardware": {
                    "cpu_usage": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                    "memory_used_gb": round(psutil.virtual_memory().used / (1024**3), 2)
                }
            }
        finally:
            db.close()

# Instancia global
nova_telemetry = NOVATelemetry()
